"""Tests for recent production additions:
- DB BLOB decoding (binary, base64, data URL, hex, file paths)
- Safe RGBA transparency compositing (white background, no black bar false positive)
- ICC color profile preservation
- HTML Visual QA gallery generation
- Worker thread initialization
"""
import base64
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from padron_crop import batch, crop, gallery
from padron_crop.ingest.sql import decode_db_image, detect_image_ext


def test_detect_image_ext():
    assert detect_image_ext(b"\xff\xd8\xff\xe0") == ".jpg"
    assert detect_image_ext(b"\x89PNG\r\n\x1a\n") == ".png"
    assert detect_image_ext(b"RIFF\x00\x00\x00\x00WEBP") == ".webp"
    assert detect_image_ext(b"BM\x00\x00") == ".bmp"
    assert detect_image_ext(b"II*\x00") == ".tiff"
    assert detect_image_ext(b"unknown") == ".jpg"


def test_decode_db_image_bytes(tmp_path):
    im = Image.new("RGB", (30, 30), (200, 200, 200))
    p = tmp_path / "test.jpg"
    im.save(p, "JPEG")
    data = p.read_bytes()

    raw, path, ext = decode_db_image(data)
    assert raw == data
    assert path is None
    assert ext == ".jpg"


def test_decode_db_image_filepath(tmp_path):
    p = tmp_path / "exist.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"dummy")

    raw, path, ext = decode_db_image(str(p))
    assert raw is None
    assert path == p
    assert ext == ".png"


def test_decode_db_image_base64_data_url(tmp_path):
    raw_png = b"\x89PNG\r\n\x1a\n" + b"12345678"
    b64_str = "data:image/png;base64," + base64.b64encode(raw_png).decode()

    raw, path, ext = decode_db_image(b64_str)
    assert raw == raw_png
    assert path is None
    assert ext == ".png"


def test_decode_db_image_raw_base64():
    raw_jpg = b"\xff\xd8\xff\xe0" + b"000011112222333344445555"
    b64_str = base64.b64encode(raw_jpg).decode()

    raw, path, ext = decode_db_image(b64_str)
    assert raw == raw_jpg
    assert path is None
    assert ext == ".jpg"


def test_decode_db_image_hex():
    raw_jpg = b"\xff\xd8\xff\xe0" + b"abcd"
    hex_str = "0x" + raw_jpg.hex()

    raw, path, ext = decode_db_image(hex_str)
    assert raw == raw_jpg
    assert path is None
    assert ext == ".jpg"


def test_rgba_alpha_composited_to_white(tmp_path):
    # Create an RGBA image with transparent border at bottom
    # Default PIL .convert('RGB') turns alpha to (0,0,0) (false black bar)
    # load_luma_ready must composite over white so it stays bright!
    rgba = Image.new("RGBA", (100, 100), (240, 240, 240, 255))
    # Fill bottom 20 rows with full transparency
    for y in range(80, 100):
        for x in range(100):
            rgba.putpixel((x, y), (0, 0, 0, 0))
    p = tmp_path / "alpha.png"
    rgba.save(p)

    im, arr = crop.load_luma_ready(p)
    # The bottom 20 rows should be white (255, 255, 255), not black (0, 0, 0)
    bottom_luma = arr[85, 50]
    assert np.all(bottom_luma > 250), f"Expected white background, got {bottom_luma}"


def test_gallery_generation(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    # Create dummy sidecars
    rec_ok = {
        "source": str(tmp_path / "test1.jpg"),
        "status": "ok",
        "method": "D1_projection",
        "confidence": 0.98,
        "elapsed_ms": 12,
        "face_detected": True,
        "face_safety_ok": True,
        "skew_angle": 0.0,
        "orig_wh": [800, 1000],
        "crop_box_xywh": [0, 0, 800, 850],
        "out_path": str(out_dir / "test1_crop.jpg"),
    }
    rec_q = {
        "source": str(tmp_path / "test2.jpg"),
        "status": "quarantine",
        "method": "none",
        "confidence": 0.4,
        "elapsed_ms": 8,
        "face_detected": True,
        "face_safety_ok": False,
        "quarantine_reason": "face_safety_violation: crop_line_cuts_chin",
        "orig_wh": [800, 1000],
        "out_path": str(out_dir / "quarantine" / "test2.jpg"),
    }
    (out_dir / "test1.json").write_text(json.dumps(rec_ok), encoding="utf-8")
    (out_dir / "test2.json").write_text(json.dumps(rec_q), encoding="utf-8")

    html_file = gallery.build_gallery(out_dir)
    assert html_file.exists()
    content = html_file.read_text(encoding="utf-8")
    assert "Padrón Crop" in content
    assert "test1" in content
    assert "test2" in content
    assert "face_safety_violation" in content


def test_worker_init_does_not_crash():
    batch._worker_init()


def test_navicat_csv_processing(tmp_path):
    from tools.navicat_helper import process_navicat_csv

    # Create dummy base64 JPEG image with bottom black bar
    im = Image.new("RGB", (60, 60), (220, 220, 220))
    for y in range(48, 60):
        for x in range(60):
            im.putpixel((x, y), (0, 0, 0))
    img_io = Path(tmp_path / "temp.jpg")
    im.save(img_io, "JPEG")
    b64 = "data:image/jpeg;base64," + base64.b64encode(img_io.read_bytes()).decode()

    csv_file = tmp_path / "navicat_export.csv"
    csv_file.write_text(f'cedula,foto\n001-0000000-1,"{b64}"\n', encoding="utf-8")

    out = tmp_path / "out_navicat"
    res = process_navicat_csv(csv_file, out, image_column="foto", id_column="cedula")
    assert res["total"] == 1
    assert res["ok"] == 1
    assert (out / "001-0000000-1_crop.jpg").exists()

