"""End-to-end SQL ingestion test against a real database (Navicat connection).

It creates a *clearly named temporary* table in the target database, fills it
with real image bytes, runs the real CLI ingest path, verifies the results and
drops the table again. Existing tables are only read (introspection).

Requires PADRON_DB_URL in the environment. Never write the DSN into the repo.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TABLE = "padron_crop_test_blobs"


def load_image_bytes() -> list[tuple[str, bytes]]:
    """Real photo bytes: the anchor plus distinct lot variants."""
    out: list[tuple[str, bytes]] = []
    anchor = ROOT / "0aaa2b82-4607-4f53-8a28-ccafa017104d.jpg"
    out.append((anchor.name, anchor.read_bytes()))
    lot = ROOT / "out" / "lot-big"
    if lot.exists():
        seen: set[str] = set()
        for p in sorted(lot.glob("img_*")):
            tag = p.name.split("_", 2)[-1]
            key = tag.rsplit(".", 1)[0].split("_")[0]
            if key in seen or "corrupt" in tag:
                continue
            seen.add(key)
            out.append((tag, p.read_bytes()))
            if len(seen) >= 12:
                break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=240)
    ap.add_argument("--out", default=str(ROOT / "out" / "sql-run"))
    args = ap.parse_args()

    from sqlalchemy import text

    from padron_crop.ingest.sql import SqlIngest

    ing = SqlIngest()                     # reads PADRON_DB_URL
    url = ing.engine.url
    print(f"connected: {url.drivername}://{url.username}@{url.host}:{url.port}/{url.database}")

    images = load_image_bytes()
    rows = [(i, images[i % len(images)][0], images[i % len(images)][1])
            for i in range(args.rows)]

    lines = ["## SQL ingestion against a real database", "",
             f"- server: `{url.host}:{url.port}/{url.database}` "
             f"(driver `{url.drivername}`)",
             f"- temporary table created for the test: `{TABLE}`",
             f"- rows inserted: {args.rows} of real image bytes "
             f"({len(images)} distinct photos)", ""]

    # --- introspection first (read-only), as the CLI does ---
    cands_before = ing.introspect_candidates()
    lines += [f"- existing BLOB/path candidates found by introspection: "
              f"{len(cands_before)}", ""]

    created = False
    try:
        with ing.engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
            conn.execute(text(
                f"CREATE TABLE {TABLE} ("
                f"id INT PRIMARY KEY, filename VARCHAR(255), foto LONGBLOB)"
            ))
            created = True
            conn.execute(
                text(f"INSERT INTO {TABLE} (id, filename, foto) "
                     f"VALUES (:i, :f, :b)"),
                [{"i": i, "f": f, "b": b} for i, f, b in rows],
            )
        with ing.engine.connect() as conn:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE}")).scalar()
        lines += [f"- rows verified in the table: {n}", ""]

        # --- run the real CLI ingest path ---
        out_dir = Path(args.out)
        if out_dir.exists():
            shutil.rmtree(out_dir)
        qf = out_dir / "query.sql"
        out_dir.mkdir(parents=True)
        qf.write_text(f"SELECT foto FROM {TABLE}", encoding="utf-8")
        cmd = [sys.executable, "-m", "padron_crop", "sql",
               "--query-file", str(qf), "--out", str(out_dir),
               "--confirm", f"{TABLE}.foto"]
        env = {**__import__("os").environ}
        env["PYTHONPATH"] = str(ROOT / "src")
        t0 = time.perf_counter()
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env,
                              cwd=str(ROOT))
        dt = time.perf_counter() - t0
        lines += ["### CLI run", "", f"```\n$ {' '.join(cmd[2:])}\n```", ""]
        if proc.returncode != 0:
            lines += [f"- **CLI failed** (exit {proc.returncode})", "",
                      "```", (proc.stderr or "")[-1500:], "```", ""]
        else:
            summary = json.loads(proc.stdout)
            summary.pop("query_file", None)
            cropped = [p for p in out_dir.rglob("*")
                       if p.is_file() and "quarantine" not in p.parts
                       and "_blobs" not in p.parts
                       and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp",
                                                ".bmp", ".tif", ".tiff")]
            sidecars = [p for p in out_dir.rglob("*.json")
                        if "_blobs" not in p.parts and "quarantine" not in p.parts]
            lines += [
                f"- wall time: {dt:.1f} s for {args.rows} rows "
                f"({args.rows / dt:.1f} rows/s)",
                f"- CLI summary: `{json.dumps(summary)}`",
                f"- cropped images written: {len(cropped)}",
                f"- sidecars written: {len(sidecars)}",
                "",
            ]

        # --- can it also auto-plan without a query file? ---
        plan = ing.plan_scan(TABLE, "foto")
        lines += ["### Dialect-correct default statement", "",
                  f"- `{plan['statement']}`", ""]
        streamed = sum(1 for _ in ing.iter_images(TABLE, "foto", batch=32))
        lines += [f"- streamed {streamed} rows with the default plan", ""]
    finally:
        if created:
            with ing.engine.begin() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
            print(f"dropped {TABLE}")
    lines += ["### Cleanup", "",
              f"- temporary table `{TABLE}` dropped: {created}", ""]

    dest = ROOT / "out" / "sqltest.md"
    dest.write_text("# sqltest.md — SQL ingestion evidence (2026-09-17)\n"
                    + "\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
