"""Synthetic image builders for padron-crop tests."""
from __future__ import annotations

import hashlib
from io import BytesIO

import numpy as np
from PIL import Image

KNOWN_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def photo(w: int = 400, h: int = 300) -> np.ndarray:
    """A 'portrait-like' image: mid background + bright face box + mid shadow."""
    arr = np.full((h, w, 3), 200, np.uint8)
    arr[40:150, 120:280] = 250      # bright face
    arr[150:170, 170:230] = 90      # shadow/neck (mid-dark, not a bar)
    return arr


def add_bar(arr: np.ndarray, side: str, t: int, value: int = 8) -> np.ndarray:
    """Add a dark bar of thickness t on the given side."""
    a = arr.copy()
    h, w = a.shape[:2]
    if side == "bottom":
        a[h - t :, :] = value
    elif side == "top":
        a[:t, :] = value
    elif side == "left":
        a[:, :t] = value
    elif side == "right":
        a[:, w - t :] = value
    else:
        raise ValueError(side)
    return a


def add_dark_zone(arr: np.ndarray, y0: int, y1: int, value: int = 40) -> np.ndarray:
    a = arr.copy()
    a[y0:y1, :] = value
    return a


def add_glyphs(arr: np.ndarray, y0: int, x0: int = 150, gh: int = 30, gw: int = 20, gap: int = 15, value: int = 245) -> np.ndarray:
    """Three white glyph blobs (PRM-like) starting at row y0."""
    a = arr.copy()
    for i in range(3):
        xs = x0 + i * (gw + gap)
        a[y0 : y0 + gh, xs : xs + gw] = value
    return a


# Encoding the same synthetic image is a common pattern across tests; the
# encoder is by far the slowest step, so identical pixels are encoded once.
_ENCODE_CACHE: dict[tuple, bytes] = {}


def _pil_and_kwargs(arr: np.ndarray, fmt: str, quality: int,
                    exif_orientation: int | None):
    im = Image.fromarray(arr)
    kwargs: dict = {"format": fmt}
    if fmt in ("JPEG", "WEBP"):
        kwargs["quality"] = quality
    if exif_orientation:
        exif = Image.Exif()
        exif[274] = exif_orientation
        kwargs["exif"] = exif
    return im, kwargs


def _encode(arr: np.ndarray, fmt: str, quality: int,
            exif_orientation: int | None) -> bytes:
    key = (fmt, quality, exif_orientation, arr.shape, arr.dtype.str,
           hashlib.blake2b(arr.tobytes(), digest_size=16).digest())
    data = _ENCODE_CACHE.get(key)
    if data is not None:
        return data
    im, kwargs = _pil_and_kwargs(arr, fmt, quality, exif_orientation)
    buf = BytesIO()
    im.save(buf, **kwargs)
    data = buf.getvalue()
    _ENCODE_CACHE[key] = data
    return data


def save(arr: np.ndarray, path, fmt: str = "JPEG", quality: int = 95, exif_orientation: int | None = None):
    """Save an array as an image file (or into a file-like object).

    Writes to paths are memoized per identical pixel buffer, so repeated
    fixtures across tests cost one encode instead of one per call.
    """
    if hasattr(path, "write"):          # file-like target (e.g. BytesIO)
        im, kwargs = _pil_and_kwargs(arr, fmt, quality, exif_orientation)
        im.save(path, **kwargs)
        return path
    from pathlib import Path

    Path(path).write_bytes(_encode(arr, fmt, quality, exif_orientation))
    return path
