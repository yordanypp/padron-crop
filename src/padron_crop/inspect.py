"""inspect: per-side dark-run measurement of one image (CLI inspect)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from padron_crop.crop import load_luma_ready
from padron_crop.geometry import _edge_run, _side_lines, luma
from padron_crop import opencv_ext

SIDES = ("top", "bottom", "left", "right")


def inspect_summary(path: Path) -> dict:
    im, arr = load_luma_ready(Path(path))
    H, W = arr.shape[:2]
    l = luma(arr)
    sides = {}
    for s in SIDES:
        dim = H if s in ("top", "bottom") else W
        depth = min(int(0.35 * dim), 480)
        df, sf = _side_lines(arr, s, depth)
        run = _edge_run(df)
        sides[s] = {
            "bar_run_px": run,
            "bar_run_frac": round(run / dim, 4),
            "first_line_dark_frac": round(float(df[0]), 4),
            "first_line_strict_frac": round(float(sf[0]), 4),
        }

    skew = opencv_ext.detect_skew_angle(arr) if opencv_ext.is_opencv_available() else 0.0
    face = opencv_ext.detect_face_and_chin(arr)

    return {
        "file": str(path),
        "width": W,
        "height": H,
        "opencv_available": opencv_ext.is_opencv_available(),
        "skew_angle_deg": round(skew, 2),
        "face_detected": face is not None,
        "face_info": face,
        "interior_mean_luma": round(
            float(l[H // 4 : 3 * H // 4, W // 4 : 3 * W // 4].mean()), 4
        ),
        "sides": sides,
    }
