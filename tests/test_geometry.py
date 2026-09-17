"""Geometry cascade tests — brief cases A..J (synthetic fixtures)."""
from __future__ import annotations

import numpy as np
import pytest

from helpers import add_bar, add_dark_zone, add_glyphs, photo
from padron_crop.geometry import decide_crop

# ---------- A: single-side bars ----------


@pytest.mark.parametrize(
    "side,expected",
    [
        ("top", (0, 60, 400, 240)),
        ("bottom", (0, 0, 400, 240)),
        ("left", (60, 0, 340, 300)),
        ("right", (0, 0, 340, 300)),
    ],
)
def test_a_single_side_bar(side, expected):
    arr = add_bar(photo(), side, 60)
    det = decide_crop(arr)
    assert det.status == "crop"
    assert det.confidence > 0.8
    assert side in det.sides
    assert det.crop_box == expected


# ---------- B: frame 2-4 sides ----------

def test_b_two_sides_frame():
    arr = add_bar(add_bar(photo(), "left", 40), "right", 40)
    det = decide_crop(arr)
    assert det.status == "crop"
    assert {"left", "right"} <= set(det.sides)
    assert det.crop_box == (40, 0, 320, 300)


def test_b_full_frame():
    arr = photo()
    for s in ("top", "bottom", "left", "right"):
        arr = add_bar(arr, s, 30)
    det = decide_crop(arr)
    assert det.status == "crop"
    assert set(det.sides) == {"top", "bottom", "left", "right"}
    assert det.crop_box == (30, 30, 340, 240)


# ---------- C: L-shape and mid-lower anchor-like block ----------

def test_c_l_shape():
    # bar on bottom + bar on right half of left edge (L shape)
    arr = add_bar(photo(), "bottom", 50)
    arr[0:150, 0:50] = 8
    det = decide_crop(arr)
    assert det.status == "crop"
    assert "bottom" in det.sides
    assert det.crop_box[3] <= 250  # bottom bar removed


def test_c_anchor_like_mid_lower_block():
    # photo 400x300: dark zone rows 200..260 + glyphs at 210..240 + solid black 260..300
    arr = add_dark_zone(photo(), 200, 260, value=40)
    arr = add_glyphs(arr, y0=210)
    arr = add_bar(arr, "bottom", 40)
    det = decide_crop(arr)
    assert det.status == "crop"
    # must remove the glyphs: bottom <= 210 - margin
    x, y, w, h = det.crop_box
    assert y + h <= 205
    # face (rows 40..150) untouched
    assert y == 0


# ---------- D: variable thickness ----------

@pytest.mark.parametrize("t", [5, 20, 80, 120])
def test_d_variable_thickness(t):
    arr = add_bar(photo(), "bottom", t)
    det = decide_crop(arr)
    assert det.status == "crop"
    assert det.crop_box[3] == 300 - t


# ---------- E: not pure black (dark gray / vignette) ----------

def test_e_dark_gray_bar():
    arr = add_bar(photo(), "top", 50, value=38)
    det = decide_crop(arr)
    assert det.status == "crop"
    assert "top" in det.sides
    assert det.crop_box[1] == 50


def test_e_low_contrast_vignette_side_not_a_bar():
    # mid-dark column strip but with bright pixels inside -> NOT cropped
    arr = photo()
    arr[:, 0:30] = 100  # grayish, and includes bright face pixels at cols 120+? no, face starts 120
    arr[40:150, 0:30] = 250  # bright content inside the strip -> not a bar
    det = decide_crop(arr)
    assert det.status != "crop" or "left" not in det.sides


# ---------- F: glyphs (PRM-like) over dark zone ----------

def test_f_glyphs_are_anchor():
    arr = add_dark_zone(photo(), 220, 280, value=35)
    arr = add_glyphs(arr, y0=230)
    arr = add_bar(arr, "bottom", 20)
    det = decide_crop(arr)
    assert det.status == "crop"
    assert det.crop_box[3] <= 225  # glyphs (230) removed with margin
    assert det.method in ("projection+glyphs", "projection")


# ---------- lighting: under-exposed photos ----------

def test_normal_photo_is_not_rescaled():
    """Guard: a clean photo has no near-black either, so it must NOT trigger
    exposure normalization (that regression made every clean photo quarantine)."""
    from padron_crop.geometry import exposure_norm, luma

    assert exposure_norm(luma(photo())) is None


def test_underexposed_photo_bar_still_detected():
    # whole shot dim (bg 60, face 90); the bar at 20 is not near-black absolutely
    arr = np.full((300, 400, 3), 60, np.uint8)
    arr[40:150, 120:280] = 90
    arr = add_bar(arr, "bottom", 50, value=20)
    det = decide_crop(arr)
    assert det.status == "crop"
    assert det.crop_box == (0, 0, 400, 250)


def test_underexposed_photo_without_bar_is_not_cropped():
    arr = np.full((300, 400, 3), 60, np.uint8)
    arr[40:150, 120:280] = 90
    det = decide_crop(arr)
    assert det.status in ("noop", "quarantine")
    assert det.crop_box == (0, 0, 400, 300)


def test_normalization_can_be_disabled(monkeypatch):
    import padron_crop.geometry as g

    monkeypatch.setattr(g, "NORM_HIGH_TRIGGER", 0.0)
    dim = np.full((10, 10, 3), 60, np.uint8)
    assert g.exposure_norm(g.luma(dim)) is None


# ---------- G/H: fast-path is batch-level; geometry stays per-image ----------

def test_h_different_patterns_per_image():
    a = decide_crop(add_bar(photo(), "bottom", 40))
    b = decide_crop(add_bar(photo(), "left", 40))
    assert a.sides == ["bottom"]
    assert b.sides == ["left"]


# ---------- I: clean image -> noop ----------

def test_i_clean_image_noop():
    det = decide_crop(photo())
    assert det.status == "noop"
    assert det.crop_box == (0, 0, 400, 300)


# ---------- J: dark/uniform -> quarantine ----------

def test_j_uniform_dark_quarantine():
    arr = np.full((300, 400, 3), 20, np.uint8)
    det = decide_crop(arr)
    assert det.status == "quarantine"
    assert det.quarantine_reason is not None


def test_j_dark_photo_with_face_not_fully_cropped():
    # mostly dark but with a bright face region: must not crop half the image
    arr = np.full((300, 400, 3), 35, np.uint8)
    arr[100:200, 150:250] = 240
    det = decide_crop(arr)
    assert det.status != "crop" or det.crop_box[3] >= 250
