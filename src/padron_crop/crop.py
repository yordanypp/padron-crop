"""Single shared crop core: load -> decide -> QA -> crop -> save + sidecar."""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from padron_crop import safeio, opencv_ext


def set_max_pixels(n: int | None = None) -> int:
    """Set the decode ceiling (configurable RAM guard).

    Order of precedence: explicit argument > env ``PADRON_MAX_PIXELS`` >
    default 512 MP. Pillow raises a clean error above it instead of an OOM.
    """
    env = os.environ.get("PADRON_MAX_PIXELS")
    val = int(n if n is not None else (env or 512_000_000))
    Image.MAX_IMAGE_PIXELS = val
    return val


set_max_pixels()

from padron_crop.geometry import apply_frozen, decide_crop

FMT_BY_EXT = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
    ".bmp": "BMP",
    ".tif": "TIFF",
    ".tiff": "TIFF",
}


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_luma_ready(path: Path) -> tuple[Image.Image, np.ndarray]:
    """Open, EXIF-transpose, RGB; returns (pil image, rgb array).

    The numpy array aliases the PIL raster (mode RGB, no convert copy) so
    there is a single pixel buffer. The PIL object stays open for saving.
    Transparent images (RGBA, LA, PA, palette with alpha) are composited over a
    clean white background to prevent transparent edges from becoming false
    black bars.
    """
    im = Image.open(path)
    im.load()
    im = ImageOps.exif_transpose(im)
    is_cmyk = (im.mode == "CMYK")
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im_rgba = im.convert("RGBA")
        bg = Image.new("RGBA", im_rgba.size, (255, 255, 255, 255))
        bg.alpha_composite(im_rgba)
        im = bg.convert("RGB")
    elif im.mode != "RGB":
        im = im.convert("RGB")
    if is_cmyk and "icc_profile" in im.info:
        im.info.pop("icc_profile", None)
    arr = np.asarray(im)              # single buffer: numpy aliases PIL raster
    return im, arr


def _clean_exif(im: Image.Image) -> bytes:
    """Serialize EXIF without orientation tag (orientation already baked in)."""
    exif = im.getexif()
    if not exif:
        return b""
    exif.pop(274, None)
    try:
        return exif.tobytes() or b""
    except Exception:
        return b""


def _apply_aspect_ratio(box: tuple[int, int, int, int], target_ratio: str, max_w: int, max_h: int,
                        face_info: dict | None = None) -> tuple[int, int, int, int]:
    """Adjust box (x, y, w, h) to conform to target_ratio (e.g. '3:4', '1:1', '4:5')
    without exceeding bounds or cutting into the subject's face."""
    try:
        parts = target_ratio.split(":")
        rw, rh = float(parts[0]), float(parts[1])
        target = rw / rh
    except Exception:
        return box
    bx, by, bw, bh = box
    if bw <= 0 or bh <= 0 or target <= 0:
        return box
    cur = float(bw) / float(bh)
    if abs(cur - target) < 1e-3:
        return box
    if cur > target:
        new_w = min(max_w, max(1, int(round(bh * target))))
        if face_info and "bbox" in face_info:
            fx, fy, fw, fh = face_info["bbox"]
            face_center_x = fx + fw // 2
            ideal_x = face_center_x - new_w // 2
            new_x = max(0, min(max_w - new_w, ideal_x))
        else:
            diff = bw - new_w
            new_x = max(0, min(max_w - new_w, bx + diff // 2))
        return (new_x, by, new_w, bh)
    else:
        new_h = min(max_h, max(1, int(round(bw / target))))
        if face_info and "bbox" in face_info:
            fx, fy, fw, fh = face_info["bbox"]
            headroom = max(15, int(fh * 0.15))
            ideal_y = max(0, fy - headroom)
            new_y = max(0, min(max_h - new_h, ideal_y))
        else:
            diff = bh - new_h
            new_y = max(0, min(max_h - new_h, by + diff // 2))
        return (bx, new_y, bw, new_h)


def _save_output(im: Image.Image, out_path: Path, src_path: Path, quality: int = 95) -> None:
    fmt = FMT_BY_EXT.get(src_path.suffix.lower(), "JPEG")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {"format": fmt}
    if fmt in ("JPEG", "WEBP"):
        kwargs["quality"] = quality
        kwargs["optimize"] = True
    exif = _clean_exif(im)
    if exif and fmt in ("JPEG", "WEBP", "TIFF"):
        kwargs["exif"] = exif
    icc = im.info.get("icc_profile")
    if icc and fmt in ("JPEG", "PNG", "WEBP", "TIFF"):
        kwargs["icc_profile"] = icc
    # atomic: a crash can never leave a truncated image that resume counts done
    with safeio.atomic_path(out_path) as tmp:
        im.save(tmp, **kwargs)


def crop_image(src: Path, out_dir: Path, frozen: dict | None = None,
               out_name: str | None = None,
               allowed_sides: list[str] | None = None,
               vision=None, dry_run: bool = False,
               deskew: bool = False,
               face_safety: bool = True,
               quality: int = 95,
               aspect_ratio: str | None = None) -> dict:
    """Process one image. Statuses: ok | noop | quarantine | failed.

    Source is never modified. ok -> out_dir/<stem>_crop.<ext> + sidecar
    <stem>.json; quarantine -> out_dir/quarantine/; noop/failed -> no image
    output (record returned for the batch ledger).

    ``dry_run`` computes the full record but writes nothing.
    """
    t0 = time.perf_counter()
    src = Path(src)
    out_dir = Path(out_dir)
    rec = {
        "source": str(src),
        "sha256": None,
        "orig_wh": None,
        "crop_box_xywh": None,
        "crop_box": None,
        "sides": [],
        "method": "none",
        "confidence": 0.0,
        "face_safety_ok": True,
        "face_detected": False,
        "skew_angle": 0.0,
        "opencv_available": opencv_ext.is_opencv_available(),
        "elapsed_ms": 0,
        "status": "failed",
        "error": None,
    }
    im = None
    try:
        rec["sha256"] = _sha256_file(src)
        im, arr = load_luma_ready(src)
    except Exception as e:  # corrupt / 0 bytes / not an image / decompression bomb
        rec["status"] = "failed"
        kind = type(e).__name__
        msg = str(e)
        # Pillow raises DecompressionBombError / ValueError for blocked giants;
        # surface it as a clear message instead of a generic failure.
        if "DecompressionBomb" in kind or "exceeds" in msg.lower():
            rec["error"] = f"image_too_large_blocked: {kind}: {msg}"
        else:
            rec["error"] = f"{kind}: {msg}"
        rec["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        return rec

    # Optional auto-deskewing for tilted scans or phone photos
    # If the unrotated image already shows a clear bar crop, we avoid rotating to prevent wedge artifacts.
    if deskew and opencv_ext.is_opencv_available():
        det_probe = decide_crop(arr, allowed_sides=allowed_sides)
        angle = opencv_ext.detect_skew_angle(arr)
        rec["skew_angle"] = round(angle, 2)
        if det_probe.status == "noop" and abs(angle) >= 0.35:
            im = opencv_ext.deskew_image(im, angle)
            arr = np.asarray(im)

    H, W = arr.shape[:2]
    rec["orig_wh"] = [W, H]
    rec["crop_box_xywh"] = [0, 0, W, H]
    rec["crop_box"] = [0, 0, W, H]
    try:
        det = apply_frozen(arr, frozen) if frozen else None
        if det is None:
            det = decide_crop(arr, allowed_sides=allowed_sides)
        else:
            # Re-validate frozen crop: verify that the cut edges are not leaving a thick black bar behind
            # (e.g. if current image has a thicker bar than the cached template)
            det_fresh = decide_crop(arr, allowed_sides=allowed_sides)
            if det_fresh.status == "crop":
                # If fresh detection proposes a deeper cut on any side, prefer fresh
                fx, fy, fw, fh = det.crop_box
                rx, ry, rw, rh = det_fresh.crop_box
                if ry > fy or (H - ry - rh) > (H - fy - fh) or rx > fx or (W - rx - rw) > (W - fx - fw):
                    det = det_fresh
        if vision is not None:
            # D4 may only veto (quarantine); geometry stays deterministic
            from padron_crop.vision import resolve_with_vision

            det = resolve_with_vision(det, arr, vision, src=src)

        # Advanced mathematical face & chin safety gate
        face_info = None
        if face_safety and det.status == "crop":
            face_info = opencv_ext.detect_face_and_chin(arr)
            if face_info:
                rec["face_detected"] = True
                safe, reason = opencv_ext.verify_face_safety_margin(det.crop_box, face_info, H, W)
                if not safe:
                    det.status = "quarantine"
                    det.face_safety_ok = False
                    det.quarantine_reason = f"face_safety_violation: {reason}"

        rec["sides"] = det.sides
        rec["method"] = det.method
        rec["confidence"] = det.confidence
        rec["face_safety_ok"] = det.face_safety_ok

        if det.status == "noop":
            rec["status"] = "noop"
            rec["out_path"] = str(src)  # untouched, byte-identical
            rec["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
            return rec

        if det.status == "quarantine":
            rec["status"] = "quarantine"
            rec["quarantine_reason"] = det.quarantine_reason
            qdir = out_dir / "quarantine"
            qdir.mkdir(parents=True, exist_ok=True)
            ext = src.suffix.lower() or ".jpg"
            qimg = qdir / (src.stem + ext)
            if not dry_run:
                _save_output(im, qimg, src, quality=quality)
                safeio.atomic_write_json(qdir / (src.stem + ".json"), rec)
            rec["out_path"] = str(qimg)
            rec["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
            return rec

        # status == crop
        x, y, w, h = det.crop_box
        if aspect_ratio:
            adj_box = _apply_aspect_ratio((x, y, w, h), aspect_ratio, W, H, face_info=face_info)
            if face_safety and face_info:
                safe, reason = opencv_ext.verify_face_safety_margin(adj_box, face_info, H, W)
                if safe:
                    x, y, w, h = adj_box
                # if unsafe, keep the safe unadjusted crop box (det.crop_box)
            else:
                x, y, w, h = adj_box

        im_out = im.crop((x, y, x + w, y + h))
        ext = src.suffix.lower() or ".jpg"
        if out_name:
            out_path = out_dir / out_name
        else:
            out_path = out_dir / (src.stem + "_crop" + ext)
        if not dry_run:
            _save_output(im_out, out_path, src, quality=quality)
        rec["crop_box_xywh"] = [x, y, w, h]
        rec["crop_box"] = [x, y, w, h]
        rec["out_path"] = str(out_path)
        rec["status"] = "ok"
        rec["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        rec["dry_run"] = dry_run
        sidecar = out_dir / (src.stem + ".json")
        if not dry_run:
            safeio.atomic_write_json(sidecar, rec)
        return rec
    except Exception as e:
        rec["status"] = "failed"
        rec["error"] = f"{type(e).__name__}: {e}"
        rec["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        return rec
    finally:
        if im is not None:
            try:
                im.close()
            except Exception:
                pass
