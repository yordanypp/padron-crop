"""Batch orchestration: D0 fast-path, resume, audit CSV, failure queues.

Hardened for unattended runs on large lots:

* every ledger write is atomic or fsynced, so a crash never corrupts resume
* free disk space is checked before the run and periodically during it
* SIGINT/SIGTERM stop the run gracefully at a chunk boundary (resume afterwards)
"""
from __future__ import annotations

import csv
import multiprocessing as mp
import os
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from padron_crop import safeio
from padron_crop.crop import crop_image
from padron_crop.ingest.local import iter_local

FREEZE_N = int(os.environ.get("PADRON_FREEZE_N", 5))        # samples to freeze D0
RECALIBRATE_K = int(os.environ.get("PADRON_RECALIBRATE_K", 25))
WINDOW_MAX = 10
TOL = float(os.environ.get("PADRON_PATTERN_TOL", 0.15))
CHUNK = int(os.environ.get("PADRON_CHUNK", 25))
DISK_CHECK_EVERY = int(os.environ.get("PADRON_DISK_CHECK_EVERY", 20))  # chunks
MIN_FREE_MB = float(os.environ.get("PADRON_MIN_FREE_MB", 200))


def _pool_usable() -> tuple[bool, str]:
    """Can a ProcessPool be used from this entry point?

    With the ``spawn`` start method (Windows, macOS) every worker re-imports the
    ``__main__`` module. When the program was started from stdin, ``-c`` or a
    REPL/notebook there is no importable file, and the pool dies mid-run with
    ``BrokenProcessPool``. Detecting it up front turns a runtime crash into a
    clear, safe downgrade to sequential processing.
    """
    method = mp.get_start_method(allow_none=True)
    if method not in (None, "spawn"):
        return True, ""
    main = sys.modules.get("__main__")
    path = getattr(main, "__file__", None)
    if not path or not os.path.isfile(path):
        return False, (
            "entry point has no importable file (stdin/-c/REPL); "
            "workers>1 is unsafe with the spawn start method"
        )
    return True, ""


def _one_job(args):
    """Worker entry: process one file; returns its sidecar record."""
    if len(args) == 6:
        src_root, path_str, out_root, frozen, vision, dry_run = args
        deskew, face_safety, quality, aspect_ratio = False, True, 95, None
    else:
        src_root, path_str, out_root, frozen, vision, dry_run, deskew, face_safety, quality, aspect_ratio = args
    path = Path(path_str)
    rel = path.relative_to(src_root)
    out_dir = Path(out_root) / rel.parent
    return crop_image(path, out_dir, frozen=frozen, out_name=path.name,
                      vision=vision, dry_run=dry_run, deskew=deskew,
                      face_safety=face_safety, quality=quality, aspect_ratio=aspect_ratio)


def _pattern(rec):
    """Normalized pattern (sides, relative thickness) from a record."""
    if rec["status"] != "ok":
        return None
    box, wh = rec.get("crop_box_xywh"), rec.get("orig_wh")
    if not box or not wh:
        return None
    W, H = wh
    x, y, w, h = box
    sides, th = [], []
    if y > 2:
        sides.append("top"); th.append(("top", y / H))
    if H - (y + h) > 2:
        sides.append("bottom"); th.append(("bottom", (H - y - h) / H))
    if x > 2:
        sides.append("left"); th.append(("left", x / W))
    if W - (x + w) > 2:
        sides.append("right"); th.append(("right", (W - x - w) / W))
    return (tuple(sides), tuple(th))


def _compat(a, b):
    if a is None or b is None:
        return a is None and b is None
    if set(a[0]) != set(b[0]):
        return False
    da, db = dict(a[1]), dict(b[1])
    return all(k in db and abs(v - db[k]) <= TOL for k, v in da.items())


def _update_d0(rec, frozen, window, since):
    """D0 state machine: freeze after N stable samples, recalibrate every K."""
    st, m = rec["status"], rec["method"]
    if st == "ok" and m == "d0-cache":
        since += 1
        if since >= RECALIBRATE_K:
            return (None, [], 0)
        return (frozen, window, since)
    pat = _pattern(rec)
    window.append(pat)
    if len(window) > WINDOW_MAX:
        window.pop(0)
    if frozen is None:
        if len(window) >= FREEZE_N:
            last = window[-FREEZE_N:]
            base = last[0]
            if base is not None and all(_compat(p, base) for p in last):
                frozen = {"sides": list(base[0]), "thickness": dict(base[1])}
    else:
        fpat = (tuple(frozen["sides"]), tuple(frozen["thickness"].items()))
        if pat is not None and not _compat(pat, fpat):
            return (None, [pat], 0)
    return (frozen, window, since)


def _append_audit(audit_path: Path, rec: dict) -> None:
    """Append one audit row and fsync (append-only, never rewritten)."""
    is_new = not audit_path.exists() or audit_path.stat().st_size == 0
    with open(audit_path, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["source", "sha256", "status", "method", "confidence",
                        "crop_box", "elapsed_ms", "error"])
        w.writerow([rec["source"], rec.get("sha256"), rec["status"], rec["method"],
                    rec.get("confidence"), rec.get("crop_box_xywh"),
                    rec.get("elapsed_ms"), rec.get("error")])
        f.flush()
        os.fsync(f.fileno())


def run_batch(src: Path, out: Path, workers: int = 1, limit: int | None = None,
              resume: bool = False, state_path: Path | None = None,
              audit_path: Path | None = None, dry_run: bool = False,
              vision=None, stop: "safeio.Stop | None" = None,
              deskew: bool = False, face_safety: bool = True,
              quality: int = 95, aspect_ratio: str | None = None) -> dict:
    src, out = Path(src), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    state_path = Path(state_path) if state_path else out / "state.jsonl"
    audit_path = Path(audit_path) if audit_path else out / "audit.csv"

    # pre-flight: fail loudly rather than filling the disk halfway through
    if not dry_run:
        safeio.require_space(out, reserve_mb=MIN_FREE_MB)

    done: set[str] = set()
    if resume:
        done = {r["source"] for r in safeio.read_jsonl_tolerant(state_path)
                if isinstance(r, dict) and "source" in r}

    files = list(iter_local(src, limit))
    todo = [p for p in files if str(p) not in done]
    summary = {"ok": 0, "noop": 0, "quarantine": 0, "failed": 0, "skipped": 0,
               "interrupted": False, "stop_reason": None}
    summary["skipped"] = sum(1 for p in files if str(p) in done)

    frozen, window, since = None, [], 0

    def _finish(rec):
        summary[rec["status"]] = summary.get(rec["status"], 0) + 1
        if dry_run:
            return
        if rec["status"] == "failed":
            fdir = out / "failed"
            fdir.mkdir(parents=True, exist_ok=True)
            stem = Path(rec["source"]).stem
            name = stem + ".json"
            i = 0
            while (fdir / name).exists():
                i += 1
                name = f"{stem}_{i}.json"
            safeio.atomic_write_json(fdir / name, rec)
        safeio.append_jsonl(state_path, rec)
        _append_audit(audit_path, rec)

    i, chunks_done = 0, 0
    pool = None
    if workers > 1:
        usable, why = _pool_usable()
        if usable:
            pool = ProcessPoolExecutor(max_workers=workers)
        else:
            warnings.warn(f"falling back to 1 worker: {why}", RuntimeWarning,
                          stacklevel=2)
            summary["workers_downgraded"] = why
    try:
        while i < len(todo):
            if stop is not None and stop.requested:
                summary["interrupted"] = True
                summary["stop_reason"] = stop.reason
                break
            # calibration: FREEZE_N images in parallel so D0 freezes on real
            # samples without serializing; once frozen, bigger chunks.
            size = CHUNK if frozen is not None else FREEZE_N
            chunk = todo[i:i + size]
            jobs = [(str(src), str(p), str(out), frozen, vision, dry_run, deskew, face_safety, quality, aspect_ratio)
                    for p in chunk]
            if pool:
                futs = [pool.submit(_one_job, j) for j in jobs]
                recs = [f.result() for f in futs]
            else:
                recs = [_one_job(j) for j in jobs]
            for rec in recs:
                _finish(rec)
                frozen, window, since = _update_d0(rec, frozen, window, since)
            i += len(chunk)
            chunks_done += 1
            if not dry_run and chunks_done % DISK_CHECK_EVERY == 0:
                try:
                    safeio.require_space(out, reserve_mb=MIN_FREE_MB)
                except safeio.InsufficientSpace as e:
                    summary["interrupted"] = True
                    summary["stop_reason"] = f"disk: {e}"
                    break
    finally:
        if pool:
            pool.shutdown(wait=True, cancel_futures=True)
    return summary
