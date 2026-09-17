"""Measure black-bar geometry of an image (Phase 0 evidence tool).

Pure numpy + Pillow. Read-only with respect to the source image:
all outputs (JSON report, plot PNGs) go to the requested output dir.

Usage:
    python tools/inspect_sample.py --image PATH --out-dir PATH
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

# Luminance thresholds (0..1 Rec.709 luma)
STRICT_T = 16 / 255   # near-pure black
DARK_T = 48 / 255     # dark gray / JPEG-noisy black
BRIGHT_T = 0.60       # for text anchor inside dark bars
SCAN_FRAC = 0.35      # max scan depth as fraction of the dimension
SCAN_MAX_PX = 480     # absolute cap on scan depth


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_image(path: Path) -> Image.Image:
    """Load image, apply EXIF orientation, return a detached RGB image."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im.load()
        return im.convert("RGB")


def luma(arr: np.ndarray) -> np.ndarray:
    """(H,W,3) uint8 -> (H,W) float32 in 0..1 (Rec.709 luma)."""
    weights = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    return arr.astype(np.float32) @ weights / 255.0


def run_length_from_edge(dark_frac: np.ndarray, thresh: float) -> int:
    """Consecutive lines from the edge whose dark fraction stays > thresh.

    Line 0 is the outermost. Returns 0 if the very first line is not dark
    enough; returns len() when the whole scanned depth is dark (capped run).
    """
    mask = dark_frac > thresh
    if not mask.any():
        return 0
    if bool(mask.all()):
        return int(len(mask))
    return int(np.argmax(~mask))


def side_stats(l: np.ndarray, side: str) -> dict:
    """Dark-run analysis for one side. l is (H,W) luma."""
    h, w = l.shape
    depth = min(int(min(h, w) * SCAN_FRAC), SCAN_MAX_PX)
    strict = (l < STRICT_T).astype(np.float32)
    dark = (l < DARK_T).astype(np.float32)

    if side == "top":
        strict_lines = strict[:depth, :].mean(axis=1)
        dark_lines = dark[:depth, :].mean(axis=1)
        margin = l[: max(1, h // 20), :]
    elif side == "bottom":
        strict_lines = strict[-depth:, :][::-1].mean(axis=1)
        dark_lines = dark[-depth:, :][::-1].mean(axis=1)
        margin = l[-max(1, h // 20) :, :]
    elif side == "left":
        strict_lines = strict[:, :depth].mean(axis=0)
        dark_lines = dark[:, :depth].mean(axis=0)
        margin = l[:, : max(1, w // 20)]
    else:  # right
        strict_lines = strict[:, -depth:][:, ::-1].mean(axis=0)
        dark_lines = dark[:, -depth:][:, ::-1].mean(axis=0)
        margin = l[:, -max(1, w // 20) :]

    strict_frac = float(margin.size and (margin < STRICT_T).mean())
    dark_frac = float(margin.size and (margin < DARK_T).mean())
    return {
        "side": side,
        "edge_dark_frac_strict": round(strict_frac, 4),
        "edge_dark_frac_dark": round(dark_frac, 4),
        "edge_mean_luma": round(float(margin.mean()), 4),
        "strict_line_profile_first20": [round(float(x), 3) for x in strict_lines[:20]],
        "dark_run_len_strict@0.5": run_length_from_edge(strict_lines, 0.5),
        "dark_run_len_strict@0.9": run_length_from_edge(strict_lines, 0.9),
        "dark_run_len_dark@0.9": run_length_from_edge(dark_lines, 0.9),
        "scan_depth": depth,
    }


def interior_stats(l: np.ndarray) -> dict:
    h, w = l.shape
    core = l[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4]
    return {
        "interior_mean_luma": round(float(core.mean()), 4),
        "interior_dark_frac_strict": round(float((core < STRICT_T).mean()), 4),
    }


def dark_bboxes(l: np.ndarray, thresh: float, min_area: int) -> list[dict]:
    """Connected dark regions on a downscaled grid; bboxes in full-res px."""
    dark = l < thresh
    f = max(1, int(max(l.shape) / 256))
    g = dark[::f, ::f]
    seen = np.zeros_like(g, dtype=bool)
    boxes = []
    hh, ww = g.shape
    for y0 in range(hh):
        for x0 in range(ww):
            if g[y0, x0] and not seen[y0, x0]:
                q = deque([(y0, x0)])
                seen[y0, x0] = True
                ys, xs = [y0], [x0]
                while q:
                    y, x = q.popleft()
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < hh and 0 <= nx < ww and g[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            q.append((ny, nx))
                            ys.append(ny)
                            xs.append(nx)
                by0, by1, bx0, bx1 = min(ys) * f, (max(ys) + 1) * f, min(xs) * f, (max(xs) + 1) * f
                area = (by1 - by0) * (bx1 - bx0)
                if area >= min_area:
                    boxes.append(
                        {
                            "bbox_xywh": [int(bx0), int(by0), int(bx1 - bx0), int(by1 - by0)],
                            "fill_frac": round(float(dark[by0:by1, bx0:bx1].mean()), 4),
                            "mean_luma": round(float(l[by0:by1, bx0:bx1].mean()), 4),
                            "touches": [
                                s
                                for s, cond in (
                                    ("top", by0 == 0),
                                    ("bottom", by1 >= l.shape[0] - f),
                                    ("left", bx0 == 0),
                                    ("right", bx1 >= l.shape[1] - f),
                                )
                                if cond
                            ],
                        }
                    )
    boxes.sort(key=lambda b: b["bbox_xywh"][2] * b["bbox_xywh"][3], reverse=True)
    return boxes[:8]


def bright_anchor_bbox(l: np.ndarray, box: dict) -> dict | None:
    """Bbox of bright pixels (likely the white 'PRM' text) inside a dark region."""
    x, y, w, h = box["bbox_xywh"]
    sub = l[y : y + h, x : x + w]
    bright = sub > BRIGHT_T
    if bright.mean() < 0.001:
        return None
    ys, xs = np.where(bright)
    bx, by, bw, bh = int(xs.min()), int(ys.min()), int(xs.max() - xs.min()), int(ys.max() - ys.min())
    return {
        "bbox_xywh_in_region": [bx, by, bw, bh],
        "bbox_xywh_abs": [x + bx, y + by, bw, bh],
        "bright_frac": round(float(bright.mean()), 4),
    }


def profile_plot(l: np.ndarray, out_path: Path) -> None:
    """Render row/col dark-fraction profiles as a simple PNG (PIL only)."""
    W, H = 800, 300
    img = Image.new("RGB", (W, H), "white")
    px = img.load()
    strict = (l < STRICT_T).astype(np.float32)
    row_s = strict.mean(axis=1)  # horizontal axis = y (rows)
    col_s = strict.mean(axis=0)  # horizontal axis = x (cols)

    def draw(curve, color):
        n = len(curve)
        for i in range(n):
            x = int(i / n * (W - 1))
            y = int(H - 1 - min(1.0, float(curve[i])) * (H - 1))
            px[x, y] = color
            if curve[i] >= 0.5:
                for yy in range(y, H):
                    px[x, yy] = color

    draw(col_s, (200, 0, 0))   # red = columns (left->right)
    draw(row_s, (0, 0, 200))   # blue = rows (top->bottom)
    for t in (0.5,):
        y = int(H - 1 - t * (H - 1))
        for x in range(W):
            if px[x, y] == (255, 255, 255):
                px[x, y] = (180, 180, 180)
    img.save(out_path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    src = args.image
    im = load_image(src)
    arr = np.asarray(im)
    l = luma(arr)
    h, w = l.shape

    strict_regions = dark_bboxes(l, STRICT_T, 400)
    dark_regions = dark_bboxes(l, DARK_T, 400)

    # Derived: bottom bar (largest strict region touching bottom) + text anchor
    derived: dict = {}
    bar = next((r for r in strict_regions if "bottom" in r["touches"]), None)
    if bar is not None:
        x, y, bw, bh = bar["bbox_xywh"]
        derived["bottom_bar_bbox_xywh"] = bar["bbox_xywh"]
        derived["bottom_bar_height_px"] = int(bh)
        derived["bottom_bar_height_frac_of_H"] = round(bh / h, 4)
        derived["bottom_bar_width_frac_of_W"] = round(bw / w, 4)
        anchor = bright_anchor_bbox(l, bar)
        if anchor:
            derived["bright_text_anchor"] = anchor

    report = {
        "file": str(src),
        "sha256": sha256_file(src),
        "size_bytes": src.stat().st_size,
        "width": w,
        "height": h,
        "mode_after_transpose": im.mode,
        "exif_orientation": int(im.getexif().get(274, 1) or 1),
        "dpi": im.info.get("dpi"),
        "sides": [side_stats(l, s) for s in ("top", "bottom", "left", "right")],
        "interior": interior_stats(l),
        "dark_regions_strict_min_area_400px": strict_regions,
        "dark_regions_dark_min_area_400px": dark_regions,
        "derived": derived,
    }

    (args.out_dir / "inspect.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    profile_plot(l, args.out_dir / "profiles.png")
    ImageOps.contain(im, (320, 320)).save(args.out_dir / "thumb.png")

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
