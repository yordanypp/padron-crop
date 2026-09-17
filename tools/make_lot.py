"""Build a large, realistic lot from the real anchor photo.

Two families, both derived from the real image (never invented content):

* **clones** — the anchor exactly as it came, in volume
* **side/lighting variants** — the same photo with a black PRM block synthesized
  on top / left / right, thicker or thinner bars, frames, L-shapes, exposure
  shifts, other formats, plus the unusable cases (clean, dark, corrupt, rotated)

Files are written by copying already-encoded bytes, so reaching gigabytes is
fast while every file is still a full-size photo the pipeline must decode.

NOTE: the base for the synthesized variants is the *cropped* anchor (the PRM
block is gone). The pipeline itself never inpaints anything; this is only a
fixture generator.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parents[1]
ANCHOR = ROOT / "0aaa2b82-4607-4f53-8a28-ccafa017104d.jpg"

BLACK = 8
GLYPH = 245


def _block(arr: np.ndarray, side: str, thickness: int, glyphs: bool,
           glyph_frac: float = 0.04) -> np.ndarray:
    """Draw a solid dark block (optionally with 3 PRM-like glyphs) on one side."""
    a = arr.copy()
    h, w = a.shape[:2]
    if side in ("top", "bottom"):
        y0, y1 = (0, thickness) if side == "top" else (h - thickness, h)
        a[y0:y1, :] = BLACK
        if glyphs and thickness >= 40:
            gh = max(12, int(thickness * 0.30))
            gw = max(8, int(w * glyph_frac))
            gap = max(6, int(w * glyph_frac * 0.6))
            x0 = int(w * 0.36)
            gy = (y0 + thickness // 2 - gh // 2) if side == "bottom" else \
                 (y1 - thickness // 2 - gh // 2)
            for i in range(3):
                xs = x0 + i * (gw + gap)
                a[gy:gy + gh, xs:xs + gw] = GLYPH
    else:
        x0, x1 = (0, thickness) if side == "left" else (w - thickness, w)
        a[:, x0:x1] = BLACK
        if glyphs and thickness >= 40:
            gw = max(12, int(thickness * 0.30))
            gh = max(8, int(h * glyph_frac))
            gap = max(6, int(h * glyph_frac * 0.6))
            y0 = int(h * 0.75)
            gx = (x0 + thickness // 2 - gw // 2) if side == "left" else \
                 (x1 - thickness // 2 - gw // 2)
            for i in range(3):
                ys = y0 + i * (gh + gap)
                a[ys:ys + gh, gx:gx + gw] = GLYPH
    return a


def _encode(arr: np.ndarray, fmt: str, quality: int = 88,
            exif_orientation: int | None = None) -> bytes:
    im = Image.fromarray(arr)
    if fmt == "CMYK":
        im = im.convert("CMYK")
    elif fmt == "P":
        im = im.convert("P")
    kwargs: dict = {}
    if fmt in ("JPEG", "WEBP", "CMYK", "P"):
        kwargs["quality"] = quality
    if exif_orientation:
        ex = Image.Exif()
        ex[274] = exif_orientation
        kwargs["exif"] = ex
    from io import BytesIO

    buf = BytesIO()
    im.save(buf, format={"CMYK": "JPEG", "P": "PNG"}.get(fmt, fmt), **kwargs)
    return buf.getvalue()


def build_variants() -> dict[str, bytes]:
    """Return {variant_name: encoded bytes} for one photo each."""
    anchor = np.asarray(Image.open(ANCHOR).convert("RGB"))
    h, w = anchor.shape[:2]
    clean = anchor[:1004]                       # the anchor without the block
    base = np.asarray(Image.fromarray(clean).resize((w, h)))

    v: dict[str, bytes] = {}
    v["clone_bottom_prm.jpg"] = ANCHOR.read_bytes()
    v["clean.jpg"] = _encode(base, "JPEG")

    for side in ("top", "bottom", "left", "right"):
        v[f"prm_{side}.jpg"] = _encode(_block(base, side, 300, glyphs=True), "JPEG")
        v[f"bar_{side}.jpg"] = _encode(_block(base, side, 90, glyphs=False), "JPEG")

    v["prm_bottom_thick.jpg"] = _encode(_block(base, "bottom", 420, True), "JPEG")
    v["prm_bottom_thin.jpg"] = _encode(_block(base, "bottom", 60, True), "JPEG")
    v["frame_tb.jpg"] = _encode(_block(_block(base, "top", 80, False),
                                       "bottom", 80, False), "JPEG")
    v["frame_all.jpg"] = _encode(
        _block(_block(_block(_block(base, "top", 60, False), "bottom", 60, False),
                      "left", 60, False), "right", 60, False), "JPEG")
    v["l_shape.jpg"] = _encode(_block(_block(base, "bottom", 70, False),
                                      "left", 70, False), "JPEG")

    # exposure: over/under exposed versions of a PRM photo
    prm = _block(base, "bottom", 300, True)
    im = Image.fromarray(prm)
    for name, factor in (("bright", 1.5), ("dark", 0.45)):
        v[f"exposure_{name}.jpg"] = _encode(
            np.asarray(ImageEnhance.Brightness(im).enhance(factor)), "JPEG")

    v["format.png"] = _encode(_block(base, "bottom", 300, True), "PNG")
    v["format.webp"] = _encode(_block(base, "bottom", 300, True), "WEBP")
    v["format.bmp"] = _encode(_block(base, "bottom", 300, True), "BMP")
    v["format.tiff"] = _encode(_block(base, "bottom", 300, True), "TIFF")
    v["format_gray.jpg"] = _encode(
        np.stack([np.asarray(Image.fromarray(_block(base, "bottom", 300, True))
                             .convert("L"))] * 3, axis=-1), "JPEG")
    v["exif_rotated.jpg"] = _encode(_block(base, "bottom", 300, True), "JPEG",
                                    exif_orientation=6)

    v["dark_uniform.jpg"] = _encode(np.full((h, w, 3), 18, np.uint8), "JPEG")
    v["noise_clean.jpg"] = _encode(base, "JPEG", quality=60)
    return v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=6000, help="number of files to write")
    ap.add_argument("--seed", type=int, default=20260917)
    ap.add_argument("--corrupt-every", type=int, default=200,
                    help="write a corrupt file every N (0 to disable)")
    args = ap.parse_args()

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    variants = build_variants()
    names = list(variants)
    rng = random.Random(args.seed)

    counts: dict[str, int] = {k: 0 for k in names}
    total = 0
    for i in range(args.n):
        if args.corrupt_every and i % args.corrupt_every == args.corrupt_every - 1:
            name, data = f"img_{i:07d}_corrupt.jpg", b"\xff\xd8\xff\xe0broken" + b"0" * 300
            counts["corrupt"] = counts.get("corrupt", 0) + 1
        else:
            vname = names[rng.randrange(len(names))]
            name, data = f"img_{i:07d}_{vname}", variants[vname]
            counts[vname] += 1
        (out / name).write_bytes(data)
        total += len(data)

    manifest = {
        "generated_from": str(ANCHOR),
        "files": args.n,
        "bytes": total,
        "gb": round(total / 2**30, 3),
        "variants": counts,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
