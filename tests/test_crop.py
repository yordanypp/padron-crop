"""Core crop_image tests: anchor, noop, corrupt, EXIF, formats, blob."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from conftest import ANCHOR
from helpers import add_bar, photo, save

from padron_crop.crop import crop_image


def _copy_src(tmp_path: Path, src: Path, name="src.jpg") -> Path:
    dst = tmp_path / name
    dst.write_bytes(src.read_bytes())
    return dst


def _src_arr(tmp_path: Path, arr, name="src.jpg", **kw) -> Path:
    p = tmp_path / name
    save(arr, p, **kw)
    return p


def test_anchor_real_image_cropped(tmp_path):
    """Anchor: 960x1280 with mid-lower PRM block -> 960x1004, glyphs gone."""
    src = _copy_src(tmp_path, ANCHOR)
    res = crop_image(src, tmp_path)
    assert res["status"] == "ok"
    assert res["crop_box"] == [0, 0, 960, 1004]
    assert res["orig_wh"] == [960, 1280]
    out = Image.open(res["out_path"])
    assert out.size == (960, 1004)
    # no bright glyphs in output
    l = np.asarray(out.convert("RGB")).astype(np.float32) @ np.array([0.2126, 0.7152, 0.0722]) / 255.0
    ys, xs = np.where(l > 0.6)
    # face is bright; check the removed strip is gone: nothing bright below y=980
    assert (ys > 980).sum() == 0


def test_noop_preserves_bytes(tmp_path):
    src = _src_arr(tmp_path, photo())
    data = src.read_bytes()
    res = crop_image(src, tmp_path)
    assert res["status"] == "noop"
    assert res["out_path"] == str(src)  # not rewritten
    assert src.read_bytes() == data  # byte-identical
    assert res["crop_box"] == [0, 0, 400, 300]


def test_quarantine_dark_image(tmp_path):
    src = _src_arr(tmp_path, np.full((300, 400, 3), 15, np.uint8))
    res = crop_image(src, tmp_path)
    assert res["status"] == "quarantine"
    assert res["face_safety_ok"] is False


def test_failed_corrupt_bytes(tmp_path):
    src = tmp_path / "corrupt.jpg"
    src.write_bytes(b"not an image at all " * 100)
    res = crop_image(src, tmp_path)
    assert res["status"] == "failed"
    assert res["error"]


def test_failed_zero_bytes(tmp_path):
    src = tmp_path / "zero.jpg"
    src.write_bytes(b"")
    res = crop_image(src, tmp_path)
    assert res["status"] == "failed"


def test_crop_dry_run_writes_nothing(tmp_path):
    src = tmp_path / "src.jpg"
    save(add_bar(photo(), "bottom", 50), src)
    out = tmp_path / "out"
    rec = crop_image(src, out, dry_run=True)
    assert rec["status"] == "ok"
    assert rec["dry_run"] is True
    assert not out.exists()
    assert not (tmp_path / "src.json").exists()


def test_max_pixels_guard_is_configurable(monkeypatch, tmp_path):
    """PADRON_MAX_PIXELS bounds decoding; above it the image fails cleanly."""
    from padron_crop.crop import set_max_pixels

    src = tmp_path / "big.png"
    save(photo(), src, fmt="PNG")
    monkeypatch.setenv("PADRON_MAX_PIXELS", "10")
    set_max_pixels()
    try:
        rec = crop_image(src, tmp_path)
        assert rec["status"] == "failed"
        assert rec["error"]
    finally:
        set_max_pixels(512_000_000)


def test_huge_synthetic_single_side(tmp_path):
    """Case N: multi-megapixel image with a bottom bar still crops.

    Kept at ~6 MP so the unit suite stays fast; the true worst case (80 MP,
    memory) is measured in out/benchmark.md instead.
    """
    h, w, bar = 2000, 3000, 200
    arr = np.full((h, w, 3), 200, np.uint8)
    arr[300:900, 1500:2500] = 250          # face-sized bright region
    arr[h - bar:, :] = 8                   # bottom bar
    src = tmp_path / "huge.jpg"
    save(arr, src, quality=85)
    rec = crop_image(src, tmp_path)
    assert rec["status"] == "ok"
    assert rec["crop_box_xywh"] == [0, 0, w, h - bar]


def test_failed_truncated_jpeg(tmp_path):
    # valid header, truncated body
    buf = io.BytesIO()
    save(photo(), buf, fmt="JPEG")
    data = buf.getvalue()[: len(buf.getvalue()) // 2]
    src = tmp_path / "trunc.jpg"
    src.write_bytes(data)
    res = crop_image(src, tmp_path)
    assert res["status"] in ("failed", "quarantine")


def test_exif_rotated_input(tmp_path):
    """6 = 90 CW rotation needed; content 400x300 becomes 300x400."""
    src = _src_arr(tmp_path, photo(), name="rot.jpg", exif_orientation=6)
    res = crop_image(src, tmp_path)
    assert res["status"] == "noop"
    assert res["orig_wh"] == [300, 400]  # after transpose
    assert res["crop_box"] == [0, 0, 300, 400]


def test_formats(tmp_path):
    for name, fmt, kwargs in [
        ("a.jpg", "JPEG", {"quality": 95}),
        ("b.jpeg", "JPEG", {"quality": 95}),
        ("c.png", "PNG", {}),
        ("d.webp", "WEBP", {"quality": 95}),
        ("e.bmp", "BMP", {}),
        ("f.tif", "TIFF", {}),
    ]:
        src = _src_arr(tmp_path, add_bar(photo(), "bottom", 30), name=name, fmt=fmt, **kwargs)
        res = crop_image(src, tmp_path)
        assert res["status"] == "ok", f"{name}: {res}"
        assert res["crop_box"] == [0, 0, 400, 270], name


def test_blob_without_extension(tmp_path):
    src = _src_arr(tmp_path, add_bar(photo(), "bottom", 30), name="blobfile")
    res = crop_image(src, tmp_path)
    assert res["status"] == "ok"
    assert res["crop_box"] == [0, 0, 400, 270]


def test_output_never_written_to_source_dir(tmp_path):
    """ok results go to out_dir; noop leaves source untouched."""
    src = _src_arr(tmp_path, add_bar(photo(), "bottom", 40))
    out_dir = tmp_path / "out"
    res = crop_image(src, out_dir)
    assert Path(res["out_path"]).parent == out_dir
    assert res["status"] == "ok"


def test_sidecar_fields(tmp_path):
    src = _src_arr(tmp_path, add_bar(photo(), "bottom", 40))
    res = crop_image(src, tmp_path)
    for k in ("source", "sha256", "orig_wh", "crop_box_xywh", "sides", "method", "confidence", "face_safety_ok", "elapsed_ms", "status"):
        assert k in res, k
    assert res["sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()
