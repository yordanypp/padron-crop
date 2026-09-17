"""Benchmark + big-load simulation. Writes evidence to out/benchmark.md.

Modes:
  single  --width W --height H : one huge synthetic image through crop_image
  batch   --n N --width W --height H : synthetic lot with mixed cases,
          processed by run_batch (workers configurable)

Memory methodology:
  - wall time    : single mode repeats --repeat times and reports the median
                   and best, because a single sample is pure load noise.
  - peak RSS     : true peak working set of THIS process (Windows psapi).
                   numpy native buffers are included; worker subprocesses are not.
  - current RSS  : resident memory right now (psutil if available).
  - python-tracked : tracemalloc peak (python objects only; misses numpy native).
"""
from __future__ import annotations

import argparse
import ctypes
import gc
import json
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from helpers import add_bar, add_dark_zone, add_glyphs, photo, save  # noqa: E402


def peak_rss_mb() -> float | None:
    """True peak working set of this process (Windows only)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes.wintypes as wt

        class PMC(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetCurrentProcess.argtypes = []
        k32.GetCurrentProcess.restype = wt.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
        psapi.GetProcessMemoryInfo.restype = wt.BOOL
        getmem = psapi.GetProcessMemoryInfo
        if not ctypes.windll.kernel32.GetModuleHandleW("psapi.dll"):
            # Windows >= 7 exposes it inside kernel32 as K32GetProcessMemoryInfo
            k32.K32GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
            k32.K32GetProcessMemoryInfo.restype = wt.BOOL
            getmem = k32.K32GetProcessMemoryInfo
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        h = k32.GetCurrentProcess()
        if getmem(h, ctypes.byref(pmc), pmc.cb):
            return pmc.PeakWorkingSetSize / (1 << 20)
        if getmem is psapi.GetProcessMemoryInfo:
            k32.K32GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
            k32.K32GetProcessMemoryInfo.restype = wt.BOOL
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            if k32.K32GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
                return pmc.PeakWorkingSetSize / (1 << 20)
    except Exception:
        pass
    return None


def current_rss_mb() -> float | None:
    try:
        import psutil

        return psutil.Process().memory_info().rss / (1 << 20)
    except Exception:
        return None


def base_portrait(w: int, h: int) -> np.ndarray:
    """Portrait-like synthetic image scaled to w x h."""
    arr = np.full((h, w, 3), 205, np.uint8)
    fw, fh = int(w * 0.45), int(h * 0.30)
    x0, y0 = int(w * 0.28), int(h * 0.06)
    arr[y0 : y0 + fh, x0 : x0 + fw] = 250          # face
    arr[y0 + fh : y0 + fh + int(h * 0.04), int(w * 0.42) : int(w * 0.58)] = 95
    y1 = int(h * 0.55)
    # subtle clothing gradient: row-varying, broadcast (no giant temporaries)
    arr[y1:, :] = ((np.arange(y1, h, dtype=np.int16) % 60)[:, None, None] + 130).astype(np.uint8)
    return arr


def gen_lot(folder: Path, n: int, w: int, h: int) -> dict:
    """Mixed-case lot: 70% bottom PRM block, 10% side bars, 10% clean, 5% dark, 5% corrupt."""
    folder.mkdir(parents=True, exist_ok=True)
    counts = {"prm": 0, "side": 0, "clean": 0, "dark": 0, "corrupt": 0}
    for i in range(n):
        r = i % 20
        p = folder / f"img_{i:06d}.jpg"
        if r < 14:      # PRM-like block (anchor pattern)
            arr = add_dark_zone(base_portrait(w, h), int(h * 0.68), int(h * 0.85), 40)
            arr = add_glyphs(arr, int(h * 0.70), x0=int(w * 0.36), gh=int(h * 0.05), gw=int(w * 0.03))
            arr = add_bar(arr, "bottom", int(h * 0.15))
            counts["prm"] += 1
        elif r < 16:    # simple side bar
            arr = add_bar(base_portrait(w, h), "left" if r == 14 else "right", int(w * 0.08))
            counts["side"] += 1
        elif r < 18:    # clean
            arr = base_portrait(w, h)
            counts["clean"] += 1
        elif r == 18:   # dark -> quarantine
            arr = np.full((h, w, 3), 18, np.uint8)
            counts["dark"] += 1
        else:           # corrupt -> failed
            p.write_bytes(b"\xff\xd8\xff\xe0corrupt" + b"0" * 200)
            counts["corrupt"] += 1
            continue
        save(arr, p, quality=90)
    return counts


def run_single(args, lines: list[str]) -> None:
    from padron_crop.crop import crop_image

    w, h = args.width, args.height
    inp = ROOT / "out" / "bench-input"
    inp.mkdir(parents=True, exist_ok=True)
    src = inp / f"prm_{w}x{h}.jpg"
    if not src.exists():
        print(f"generating {w}x{h} JPEG with PRM block ...")
        t0 = time.perf_counter()
        arr = add_dark_zone(base_portrait(w, h), int(h * 0.68), int(h * 0.85), 40)
        arr = add_glyphs(arr, int(h * 0.70), x0=int(w * 0.36), gh=int(h * 0.05), gw=int(w * 0.03))
        arr = add_bar(arr, "bottom", int(h * 0.15))
        save(arr, src, quality=88)
        gen_s = time.perf_counter() - t0
    else:
        gen_s = 0.0
    mb = src.stat().st_size / (1 << 20)
    print(f"input: {src.name} {mb:.1f} MB")

    # wall time is load-sensitive, so repeat and report the distribution
    gc.collect()
    times: list[float] = []
    for _ in range(max(1, args.repeat)):
        t0 = time.perf_counter()
        rec = crop_image(src, ROOT / "out" / "bench-single")
        times.append(time.perf_counter() - t0)
    times.sort()
    dt, best = times[len(times) // 2], times[0]
    tracemalloc.start()
    crop_image(src, ROOT / "out" / "bench-single")
    py_peak = tracemalloc.get_traced_memory()[1] / (1 << 20)
    tracemalloc.stop()
    peak = peak_rss_mb()
    cur = current_rss_mb()

    lines += [
        "## Single huge image",
        "",
        f"- input: `{src.name}` {w}x{h} = {w * h / 1e6:.0f} MP, {mb:.1f} MB",
        f"- generation: {gen_s:.1f} s (synthetic)",
        f"- crop status: `{rec['status']}` method `{rec['method']}` box {rec['crop_box_xywh']}",
        f"- wall time: {dt:.2f} s median of {len(times)} "
        f"(best {best:.2f} s -> {(w * h / 1e6) / best:.1f} MP/s)",
        f"- peak RSS: {f'{peak:.0f} MB' if peak else 'n/a'} (this process, incl. numpy native)"
        + (f" | current RSS: {cur:.0f} MB" if cur else "")
        + f" | python-tracked peak: {py_peak:.0f} MB",
        "",
    ]


def run_batch(args, lines: list[str]) -> None:
    from padron_crop.batch import run_batch

    w, h, n = args.width, args.height, args.n
    inp = ROOT / "out" / "bench-input" / f"lot_{n}x{w}x{h}"
    if not inp.exists():
        print(f"generating lot: {n} images {w}x{h} ...")
        t0 = time.perf_counter()
        counts = gen_lot(inp, n, w, h)
        gen_s = time.perf_counter() - t0
    else:
        counts = {}
        gen_s = 0.0
    total_mb = sum(p.stat().st_size for p in inp.rglob("*.jpg")) / (1 << 20)

    gc.collect()
    t0 = time.perf_counter()
    summary = run_batch(inp, ROOT / "out" / "bench-batch", workers=args.workers,
                        resume=False,
                        state_path=ROOT / "out" / "bench-batch" / "state.jsonl",
                        audit_path=ROOT / "out" / "bench-batch" / "audit.csv")
    dt = time.perf_counter() - t0
    peak = peak_rss_mb()
    cur = current_rss_mb()

    done = summary["ok"] + summary["noop"] + summary["quarantine"] + summary["failed"]
    lines += [
        "## Big batch simulation",
        "",
        f"- lot: {n} synthetic images {w}x{h} ({w * h / 1e6:.1f} MP each), {total_mb:.0f} MB on disk",
        (f"- lot composition: `{json.dumps(counts)}`" if counts else "- lot reused from bench-input (already generated)"),
        f"- generation: {gen_s:.1f} s (synthetic)",
        f"- workers: {args.workers}",
        f"- summary: `{json.dumps(summary)}`",
        f"- wall time: {dt:.1f} s -> {done / dt:.1f} img/s",
        f"- peak RSS main proc: {f'{peak:.0f} MB' if peak else 'n/a'}"
        + (f" | current RSS: {cur:.0f} MB" if cur else ""),
        "",
        "Notes:",
        "- worker subprocess RSS is not included in the main-process peak;",
        "  per-worker ceiling is bounded by the single-image profile above.",
        "- wall time is load-sensitive: it depends on machine load and OS cache",
        "  state, so treat it as an order of magnitude, not a constant.",
        "",
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["single", "batch"])
    ap.add_argument("--width", type=int, default=10000)
    ap.add_argument("--height", type=int, default=8000)
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--repeat", type=int, default=3,
                    help="repetitions for the single-image mode (load noise)")
    args = ap.parse_args()

    out_md = ROOT / "out" / "benchmark.md"
    lines = []
    if args.mode == "single":
        run_single(args, lines)
    else:
        run_batch(args, lines)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    header_needed = not out_md.exists() or out_md.stat().st_size == 0
    with open(out_md, "a", encoding="utf-8") as f:
        if header_needed:
            f.write("# benchmark.md — tiempos y memoria (medido 2026-09-17)\n")
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
