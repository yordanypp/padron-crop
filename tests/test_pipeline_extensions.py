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


def test_navicat_csv_huge_base64_field_limit(tmp_path):
    from tools.navicat_helper import process_navicat_csv

    # Default python csv field_size_limit is 131,072 bytes.
    # We test with a base64 field exceeding 160,000 bytes.
    # Create valid JPEG data with padding
    im = Image.new("RGB", (60, 60), (220, 220, 220))
    for y in range(48, 60):
        for x in range(60):
            im.putpixel((x, y), (0, 0, 0))
    img_io = Path(tmp_path / "small.jpg")
    im.save(img_io, "JPEG")
    real_jpg_bytes = img_io.read_bytes()
    # Pad so total size is > 160 KB (> 131,072 bytes limit)
    padded_jpg_bytes = real_jpg_bytes + (b"\x00" * 150000)
    raw_b64 = base64.b64encode(padded_jpg_bytes).decode()
    b64_padded = "data:image/jpeg;base64," + raw_b64
    assert len(b64_padded) > 140000

    csv_file = tmp_path / "huge_export.csv"
    csv_file.write_text(f'id,foto\nREC01,"{b64_padded}"\n', encoding="utf-8")

    out = tmp_path / "out_huge"
    res = process_navicat_csv(csv_file, out, image_column="foto", id_column="id")
    assert res["total"] == 1
    # Successfully parsed without CSV field_size_limit crash
    assert res["ok"] == 1


def test_navicat_csv_semicolon_delimiter(tmp_path):
    from tools.navicat_helper import process_navicat_csv

    im = Image.new("RGB", (60, 60), (220, 220, 220))
    for y in range(48, 60):
        for x in range(60):
            im.putpixel((x, y), (0, 0, 0))
    img_io = Path(tmp_path / "semi.jpg")
    im.save(img_io, "JPEG")
    b64 = "data:image/jpeg;base64," + base64.b64encode(img_io.read_bytes()).decode()

    csv_file = tmp_path / "spanish_excel_navicat.csv"
    # Semicolon separated, common in Spanish Windows locale; fields with delimiters quoted
    csv_file.write_text(f'id;cedula;foto;nombre\n1;402-1234567-8;"{b64}";JUAN PEREZ\n', encoding="utf-8")

    out = tmp_path / "out_semi"
    res = process_navicat_csv(csv_file, out, image_column="foto", id_column="cedula")
    assert res["total"] == 1
    assert res["ok"] == 1
    assert (out / "402-1234567-8_crop.jpg").exists()


def test_cmyk_image_conversion_and_icc_cleanup(tmp_path):
    # Create a CMYK image
    im_cmyk = Image.new("CMYK", (80, 80), (0, 100, 100, 0))
    p = tmp_path / "sample_cmyk.jpg"
    im_cmyk.save(p, "JPEG")

    im, arr = crop.load_luma_ready(p)
    assert im.mode == "RGB"
    assert "icc_profile" not in im.info

    out_dir = tmp_path / "out_cmyk"
    rec = crop.crop_image(p, out_dir)
    assert rec["status"] in ("ok", "noop")


def test_palette_transparency_composited_to_white(tmp_path):
    # Palette with transparent pixels saved to PNG
    p = tmp_path / "test_p_transparency.png"
    im_p = Image.new("P", (60, 60), color=0)
    im_p.save(p, transparency=0)

    im, arr = crop.load_luma_ready(p)
    # The transparent pixels must be white (255, 255, 255), not black (0, 0, 0)
    assert np.all(arr[30, 30] > 250)


def test_aspect_ratio_clamping():
    # Box with wide aspect ratio on small canvas
    box = (10, 10, 100, 50)
    # Request 1:1 square
    new_box = crop._apply_aspect_ratio(box, "1:1", max_w=120, max_h=120)
    x, y, w, h = new_box
    assert x >= 0 and y >= 0
    assert x + w <= 120 and y + h <= 120
    assert w == h

    # Extreme ratio
    new_box2 = crop._apply_aspect_ratio((0, 0, 200, 100), "3:4", max_w=200, max_h=100)
    x2, y2, w2, h2 = new_box2
    assert x2 >= 0 and y2 >= 0
    assert x2 + w2 <= 200 and y2 + h2 <= 100


def test_deskew_white_fill():
    from padron_crop.opencv_ext import deskew_image

    # Create solid blue image
    im = Image.new("RGB", (100, 100), (0, 0, 255))
    rotated = deskew_image(im, angle_deg=5.0)
    # Corner at (0, 0) should be white (255, 255, 255) rather than black (0, 0, 0)
    corner_pixel = rotated.getpixel((0, 0))
    assert corner_pixel == (255, 255, 255), f"Expected white fill, got {corner_pixel}"


def test_sql_assert_read_only_with_bom():
    from padron_crop.ingest.sql import assert_read_only

    # UTF-8 BOM prefix \ufeff
    stmt = "\ufeffSELECT foto FROM ciudadanos WHERE id = 1"
    res = assert_read_only(stmt)
    assert res == stmt

    with pytest.raises(ValueError):
        assert_read_only("\ufeffDELETE FROM ciudadanos")


def test_sql_decode_base64_with_newlines_and_urlsafe():
    raw_png = b"\x89PNG\r\n\x1a\n" + b"SAMPLE_IMAGE_DATA_12345"
    b64 = base64.b64encode(raw_png).decode()
    # Add newlines every 10 chars
    b64_with_newlines = "\r\n".join([b64[i:i+10] for i in range(0, len(b64), 10)])

    raw, path, ext = decode_db_image(b64_with_newlines)
    assert raw == raw_png
    assert ext == ".png"


def test_grayscale_monochromatic_face_detection():
    from padron_crop.opencv_ext import detect_face_and_chin

    # Synthetic portrait: gray background (180), dark hair/face oval in center (80)
    arr = np.full((300, 200, 3), 180, dtype=np.uint8)
    # Draw dark oval/head in upper region
    for y in range(40, 180):
        for x in range(50, 150):
            arr[y, x] = [70, 70, 70]

    info = detect_face_and_chin(arr)
    assert info is not None
    assert "bbox" in info
    assert "chin_y" in info
    assert info["chin_y"] > 100


def test_iter_local_single_file(tmp_path):
    from padron_crop.ingest.local import iter_local

    img_p = tmp_path / "single.jpg"
    Image.new("RGB", (50, 50), (200, 200, 200)).save(img_p)

    results = list(iter_local(img_p))
    assert len(results) == 1
    assert results[0] == img_p


def test_face_centered_aspect_ratio():
    from padron_crop import crop

    # Image is 200x200, face is located at x=40..80 (center 60), y=20..70
    face_info = {"bbox": (40, 20, 40, 50), "chin_y": 70}
    # Original crop box: (0, 0, 200, 200)
    # Target 3:4 (w = 150, h = 200)
    box = crop._apply_aspect_ratio((0, 0, 200, 200), "3:4", max_w=200, max_h=200, face_info=face_info)
    x, y, w, h = box
    # Face center is at 60. Box width is 150. Ideal left is 60 - 75 = -15 -> clamped to 0.
    assert x == 0
    assert w == 150
    assert h == 200


def test_aspect_ratio_safety_fallback(tmp_path):
    from padron_crop.crop import crop_image

    # Create synthetic image with face and bottom bar
    im = Image.new("RGB", (200, 200), (200, 200, 200))
    # Head in center
    for y in range(30, 90):
        for x in range(70, 130):
            im.putpixel((x, y), (210, 160, 120))
    # Black bar at bottom (160..200)
    for y in range(160, 200):
        for x in range(200):
            im.putpixel((x, y), (5, 5, 5))

    p = tmp_path / "test_safety.jpg"
    im.save(p)

    # Crop with 1:1 aspect ratio
    rec = crop_image(p, tmp_path / "out", aspect_ratio="1:1", face_safety=True)
    assert rec["status"] == "ok"
    # Ensure bottom cut does not cut the head (y < 90)
    cb = rec["crop_box_xywh"]
    assert cb[1] + cb[3] >= 90


def test_navicat_csv_with_aspect_ratio_and_quality(tmp_path):
    from tools.navicat_helper import process_navicat_csv

    # Create dummy image
    im_path = tmp_path / "test_photo.jpg"
    Image.new("RGB", (100, 100), (220, 220, 220)).save(im_path)

    csv_path = tmp_path / "export.csv"
    csv_path.write_text(f"id,foto\n001,{im_path.as_posix()}\n", encoding="utf-8")

    out_dir = tmp_path / "navicat_aspect_out"
    summary = process_navicat_csv(
        csv_path,
        out_dir,
        image_column="foto",
        id_column="id",
        aspect_ratio="3:4",
        quality=90,
    )
    assert summary["total"] == 1
    assert (out_dir / "gallery.html").exists()


def test_api_server_live_endpoints(tmp_path):
    import io
    import threading
    import urllib.request
    from tools.serve_api import PadronCropHandler, ThreadingHTTPServer

    out_dir = tmp_path / "api_out"
    PadronCropHandler.out_dir = out_dir
    server = ThreadingHTTPServer(("127.0.0.1", 0), PadronCropHandler)
    port = server.server_port

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        # Test /health
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health") as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["engine"] == "padron-crop"

        # Test /crop/json
        im_bytes = io.BytesIO()
        Image.new("RGB", (60, 60), (220, 220, 220)).save(im_bytes, format="JPEG")
        b64_str = base64.b64encode(im_bytes.getvalue()).decode()

        req_body = json.dumps({"image_base64": b64_str, "aspect_ratio": "1:1"}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/crop/json",
            data=req_body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode())
            assert res["status"] in ("ok", "noop")
            assert "crop_box_xywh" in res
    finally:
        server.shutdown()
        server.server_close()





