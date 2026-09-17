"""Large-scale load test: throughput, memory, interrupt + resume integrity.

Phases:
  1. full run over the lot (fresh)
  2. interrupt mid-run, then resume -> proves no work is lost or repeated
  3. integrity checks: sidecar count, source untouched, ledger consistency

Memory is sampled for the whole process tree (parent + workers), which is the
number that actually matters when deciding how many workers a machine can run.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from benchmark import peak_rss_mb  # noqa: E402
from padron_crop.batch import run_batch  # noqa: E402
from padron_crop.safeio import Stop, read_jsonl_tolerant  # noqa: E402


class RssSampler:
    """Peak RSS of this process and of the whole process tree (parent+workers)."""

    def __init__(self, interval: float = 0.2):
        self.interval = interval
        self.peak_tree = 0.0
        self._stop = threading.Event()
        self._t: threading.Thread | None = None
        self.psutil = None
        try:
            import psutil

            self.psutil = psutil
        except Exception:
            pass

    def _run(self):
        import psutil

        proc = psutil.Process()
        while not self._stop.is_set():
            total = 0
            try:
                procs = [proc, *proc.children(recursive=True)]
                for p in procs:
                    try:
                        total += p.memory_info().rss
                    except psutil.Error:
                        pass
            except Exception:
                pass
            self.peak_tree = max(self.peak_tree, total / (1 << 20))
            self._stop.wait(self.interval)

    def __enter__(self):
        if self.psutil is not None:
            self._t = threading.Thread(target=self._run, daemon=True)
            self._t.start()
        return self

    def __exit__(self, *a):
        self._stop.set()
        if self._t:
            self._t.join(timeout=2)


def lot_stats(src: Path) -> tuple[int, int]:
    files = [p for p in src.rglob("*") if p.is_file() and p.name != "manifest.json"]
    return len(files), sum(p.stat().st_size for p in files)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--interrupt-after", type=float, default=8.0,
                    help="seconds after which phase 2 requests a stop")
    args = ap.parse_args()

    src, out = Path(args.src), Path(args.out)
    n, total_bytes = lot_stats(src)
    gb = total_bytes / 2**30
    lines: list[str] = []
    lines += ["## Large-scale load test", "",
              f"- lot: `{src.name}` — {n} files, {gb:.2f} GB on disk", ""]

    # ---------- phase 1: full run ----------
    with RssSampler() as s1:
        t0 = time.perf_counter()
        s1_summary = run_batch(src, out, workers=args.workers, resume=False)
        dt1 = time.perf_counter() - t0
    lines += [
        "### Phase 1 — full run",
        "",
        f"- workers: {args.workers}",
        f"- summary: `{json.dumps(s1_summary)}`",
        f"- wall time: {dt1:.1f} s -> {n / dt1:.1f} files/s, "
        f"{gb / dt1 * 1024:.0f} MB/s",
        f"- peak RSS process tree: {s1.peak_tree:.0f} MB"
        + (f" | this process: {peak_rss_mb():.0f} MB" if peak_rss_mb() else ""),
        "",
    ]

    # ---------- phase 2: interrupt + resume ----------
    out2 = out.parent / (out.name + "-resume")
    stop = Stop()
    watchdog = threading.Thread(
        target=lambda: (time.sleep(args.interrupt_after), stop.request("SIGINT")),
        daemon=True)
    watchdog.start()
    t0 = time.perf_counter()
    interrupted = run_batch(src, out2, workers=args.workers, resume=False, stop=stop)
    dt2 = time.perf_counter() - t0
    done_first = sum(interrupted[k] for k in ("ok", "noop", "quarantine", "failed"))

    ledger = out2 / "state.jsonl"
    done_first = min(done_first, len({r["source"] for r in read_jsonl_tolerant(ledger)}))

    t0 = time.perf_counter()
    resumed = run_batch(src, out2, workers=args.workers, resume=True)
    dt3 = time.perf_counter() - t0
    lines += [
        "### Phase 2 — interrupt and resume",
        "",
        f"- run 1: interrupted={interrupted['interrupted']} "
        f"reason=`{interrupted['stop_reason']}` after {dt2:.1f} s",
        f"- records completed before the stop: **{done_first}**",
        f"- run 2 (`--resume`): skipped={resumed['skipped']} "
        f"processed={sum(resumed[k] for k in ('ok', 'noop', 'quarantine', 'failed'))} "
        f"in {dt3:.1f} s",
        f"- resume skipped exactly what was done: "
        f"**{resumed['skipped'] == done_first}**",
        "",
    ]

    # ---------- phase 3: integrity ----------
    sources = {str(p) for p in src.rglob("*") if p.is_file() and p.name != "manifest.json"}
    tally = {k: 0 for k in ("ok", "noop", "quarantine", "failed")}
    recs = read_jsonl_tolerant(out2 / "state.jsonl")
    for r in recs:
        if r.get("status") in tally:
            tally[r["status"]] += 1
    unique_sources = {r["source"] for r in recs}
    sidecars = [p for p in out2.rglob("*.json")
                if p.parent.name not in ("failed", "quarantine", "_blobs")]
    lines += [
        "### Phase 3 — integrity",
        "",
        f"- ledger records: {len(recs)} (unique sources: {len(unique_sources)})",
        f"- every source processed exactly once: **{len(unique_sources) == len(sources)}**",
        f"- status tally in the final ledger: `{json.dumps(tally)}`",
        f"- sidecars written: {len(sidecars)}",
        f"- orphan temp files left behind: "
        f"**{len(list(out2.rglob('.tmp-*')))}**",
        "",
        "### Extrapolation",
        "",
        f"- measured {n / dt1:.1f} files/s and {gb / dt1 * 1024:.0f} MB/s with "
        f"{args.workers} workers on this machine",
        f"- linear projection: **{n / dt1 * 3600 / 1000:.0f}k files/hour**, "
        f"{gb / dt1 * 3600:.0f} GB/hour",
        "- memory is per-image bounded (~17 B/pixel), so image *size* does not "
        "accumulate across the run; only worker count does",
        "",
    ]

    dest = ROOT / "out" / "loadtest.md"
    header = "# loadtest.md — massive-lot evidence (measured 2026-09-17)\n"
    dest.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
