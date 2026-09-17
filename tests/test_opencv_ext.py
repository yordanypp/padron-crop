"""Tests for OpenCV extensions, face/chin safety gate, deskew, and aspect ratio."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from helpers import add_bar, photo, save
from padron_crop import opencv_ext
from padron_crop.crop import _apply_aspect_ratio, crop_image


def test_opencv_available_flag():
    # Should report boolean and version string
    assert isinstance(opencv_ext.is_opencv_available(), bool)
    if opencv_ext.is_opencv_available():
        assert opencv_ext.opencv_version() is not None


def test_fast_grayscale_threshold_matches_shape_and_type():
    arr = np.random.randint(0, 256, (100, 120, 3), dtype=np.uint8)
    dark, gray = opencv_ext.fast_grayscale_threshold(arr, threshold=48)
    assert dark.shape == (100, 120)
    assert dark.dtype == bool
    assert gray.shape == (100, 120)
    assert gray.dtype == np.uint8


def test_fast_connected_components():
    mask = np.zeros((100, 100), dtype=np.uint8)
    # create two bright islands
    mask[10:30, 10:30] = 1
    mask[60:80, 60:80] = 1
    boxes = opencv_ext.fast_connected_components(mask, min_cells=10)
    if opencv_ext.is_opencv_available():
        assert len(boxes) == 2
        assert boxes[0] == (10, 10, 20, 20)
        assert boxes[1] == (60, 60, 20, 20)


def test_detect_skew_angle_flat():
    # An un-tilted synthetic image with horizontal bar should have near-zero skew
    arr = add_bar(photo(w=400, h=300), "bottom", 60)
    angle = opencv_ext.detect_skew_angle(arr)
    assert abs(angle) < 1.0


def test_detect_skew_angle_and_deskew():
    if not opencv_ext.is_opencv_available():
        pytest.skip("OpenCV required for deskew test")
    # Create image with horizontal line, rotate it, detect angle
    im = Image.new("RGB", (400, 400), (220, 220, 220))
    arr = np.asarray(im).copy()
    arr[300:350, :] = 10  # wide dark bar
    im = Image.fromarray(arr).rotate(4.0, resample=Image.BICUBIC)
    arr_rot = np.asarray(im)
    detected = opencv_ext.detect_skew_angle(arr_rot)
    # Detected angle should be roughly -4 deg (+/- 2 deg tolerance)
    assert abs(abs(detected) - 4.0) < 2.5

    # Deskewing should bring it back
    deskewed = opencv_ext.deskew_image(im, detected)
    assert deskewed.size == (400, 400)


def test_face_safety_gate_prevents_cutting_chin():
    face_info = {
        "bbox": (100, 40, 200, 180),
        "chin_y": 200,
        "confidence": 0.9,
    }
    # Crop cutting at y=180 would invade chin at 200
    unsafe_box = (0, 0, 400, 180)
    safe, reason = opencv_ext.verify_face_safety_margin(unsafe_box, face_info, 300, 400, safety_margin_px=15)
    assert safe is False
    assert "invades chin" in reason

    # Crop cutting at y=250 is safe (below chin)
    safe_box = (0, 0, 400, 250)
    safe, reason = opencv_ext.verify_face_safety_margin(safe_box, face_info, 300, 400, safety_margin_px=15)
    assert safe is True
    assert reason is None


def test_crop_image_with_face_safety_quarantine(tmp_path, monkeypatch):
    # If face detection indicates the crop would cut the face, crop_image should quarantine
    src = tmp_path / "portrait.jpg"
    arr = add_bar(photo(w=400, h=300), "bottom", 150)  # very thick bar cutting deep
    save(arr, src)

    # Mock face info where chin is at y=220
    monkeypatch.setattr(
        opencv_ext,
        "detect_face_and_chin",
        lambda a: {"bbox": (120, 40, 160, 180), "chin_y": 220, "confidence": 0.95},
    )

    out_dir = tmp_path / "out"
    rec = crop_image(src, out_dir, face_safety=True)
    # The bar is 150px tall (from 150 to 300), so proposed crop bottom is 150 < chin 220
    assert rec["status"] == "quarantine"
    assert "face_safety_violation" in str(rec.get("quarantine_reason"))


def test_apply_aspect_ratio():
    # 800x1000 is 4:5 -> target 3:4 (0.75)
    # For height 1000, target width is 750 (less than 800)
    box = (0, 0, 800, 1000)
    new_box = _apply_aspect_ratio(box, "3:4", max_w=800, max_h=1000)
    nx, ny, nw, nh = new_box
    assert nh == 1000
    assert nw == 750
    assert nx == 25  # centered: (800 - 750) // 2

    # Target 1:1
    sq_box = _apply_aspect_ratio(box, "1:1", max_w=800, max_h=1000)
    assert sq_box[2] == 800
    assert sq_box[3] == 800


def test_crop_with_deskew_and_aspect_ratio_cli(tmp_path):
    from padron_crop.cli import main

    src = tmp_path / "input.jpg"
    arr = add_bar(photo(w=400, h=400), "bottom", 60)
    save(arr, src)

    out = tmp_path / "out.jpg"
    ret = main(["crop", "--in", str(src), "--out", str(out), "--deskew", "--aspect-ratio", "1:1"])
    assert ret == 0
    assert out.exists()
    im = Image.open(out)
    assert im.size[0] == im.size[1]  # 1:1 square
