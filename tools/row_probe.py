"""Per-row probe of an image: where does the dark block start?

Outputs a table of row bands with mean luma / strict-dark fraction /
bright fraction, plus connected bright-region bboxes. Evidence for
deciding the crop line without destroying the portrait.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

STRICT_T = 16 / 255
DARK_T = 48 / 255
BRIGHT_T = 0.60


def load_image(path: Path) -> Image.Image:
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im.load()
        return im.convert("RGB")


def luma(arr: np.ndarray) -> np.ndarray:
    weights = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    return arr.astype(np.float32) @ weights / 255.0


def bright_regions(l: np.ndarray, min_area: int = 200) -> list[dict]:
    bright = l > BRIGHT_T
    f = max(1, int(max(l.shape) / 256))
    g = bright[::f, ::f]
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
                if (by1 - by0) * (bx1 - bx0) >= min_area:
                    boxes.append(
                        {
                            "bbox_xywh": [int(bx0), int(by0), int(bx1 - bx0), int(by1 - by0)],
                            "bright_frac": round(float(bright[by0:by1, bx0:bx1].mean()), 4),
                        }
                    )
    boxes.sort(key=lambda b: b["bbox_xywh"][2] * b["bbox_xywh"][3], reverse=True)
    return boxes[:12]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--band", type=int, default=10, help="row band height in px")
    ap.add_argument("--from-row", type=int, default=None)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    im = load_image(args.image)
    l = luma(np.asarray(im))
    h, w = l.shape
    b = args.band
    start = args.from_row if args.from_row is not None else 0

    rows = []
    for y in range(start, h, b):
        band = l[y : y + b, :]
        rows.append(
            {
                "y": y,
                "mean_luma": round(float(band.mean()), 4),
                "strict_dark_frac": round(float((band < STRICT_T).mean()), 4),
                "dark_frac": round(float((band < DARK_T).mean()), 4),
                "bright_frac": round(float((band > BRIGHT_T).mean()), 4),
            }
        )

    out = {
        "image": str(args.image),
        "size_wh": [w, h],
        "row_bands": rows,
        "bright_regions_min_area_200": bright_regions(l),
    }
    (args.out_dir / "row_probe.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"{'y':>5} {'mean':>7} {'strict':>7} {'dark':>7} {'bright':>7}")
    for r in rows:
        print(
            f"{r['y']:>5} {r['mean_luma']:>7.4f} {r['strict_dark_frac']:>7.4f} "
            f"{r['dark_frac']:>7.4f} {r['bright_frac']:>7.4f}"
        )
    print("\nBright regions (luma>0.6):")
    for r in out["bright_regions_min_area_200"]:
        print(" ", r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
