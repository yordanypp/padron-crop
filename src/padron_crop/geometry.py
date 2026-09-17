"""Deterministic black-bar/PRM-block detection (cascade D1 + D3, D2-style checks).

Calibrated on the measured anchor (docs/research/sample-geometry.md):
- bars must touch the border, have high dark fill, and contain no bright content
- crop line for text blocks = topmost glyph row - margin (never the first dark jump)
- dark content (clothes/shadows) is never cropped: strict-evidence rule for deep runs
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

STRICT_T = 16 / 255
DARK_T = 48 / 255
BRIGHT_T = 0.60
LUMA_W = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

LINE_DARK_FRAC = 0.85   # a line qualifies as bar line
WALK_DARK_FRAC = 0.55   # walk above the bar while lines stay mostly dark
MIN_BAR_ABS = 3
MIN_BAR_FRAC = 0.004
SWALLOW_FRAC = 0.5      # run deeper than half the dim -> not a bar
DEEP_RUN_FRAC = 0.20    # deep runs need near-black evidence
DEEP_STRICT_FRAC = 0.15
WALK_MAX_FRAC = 0.25
WALK_MAX_ROWS = 600
STRIP_DARK_MIN = 0.5
GLYPH_MAX_W_FRAC = 0.30
GLYPH_MAX_H_FRAC = 0.15
GLYPH_MIN_PX = 8
MIN_CONTENT_PX = 12   # smaller bright bboxes are noise specks, ignored
STRICT_BAR_Q = 0.5    # run strip predominantly near-black -> true bar
CONTRAST_MIN = 0.18   # gray bars need a clear luma step vs inner band
SHOULDER_MAX = 0.3    # sharp transition: lines right after the run are bright
MARGIN = 5
COMP_TOL = 4            # ignore tiny content/bbar overlaps (JPEG ringing)
UNIFORM_DARK_MEAN = 0.15
UNIFORM_BRIGHT_MAX = 0.005
MAX_REMOVE_AREA = 0.5
SIDES = ("top", "bottom", "left", "right")


@dataclass
class Detection:
    status: str                 # crop | noop | quarantine
    crop_box: tuple             # (x, y, w, h)
    sides: list
    method: str
    confidence: float
    quarantine_reason: str | None = None
    face_safety_ok: bool = True


def luma(arr: np.ndarray) -> np.ndarray:
    """Rec.709 luma as float in [0, 1].

    A single float32 matmul against the weights; measured faster than a
    per-channel integer formulation (BLAS wins despite the copy).
    """
    return arr.astype(np.float32) @ LUMA_W / 255.0


# Adaptive exposure normalization for UNDER-exposed photos.
#
# Only the "nothing bright anywhere" case is used as the trigger: a clean photo
# legitimately has no near-black pixels either, so an elevated black point is
# NOT evidence of bad exposure and must not trigger a rescale. When the whole
# image is dim, though, the bar is no longer near-black in absolute terms and
# the luma step is too small for the contrast gate, so the crop is missed.
NORM_HIGH_TRIGGER = float(os.environ.get("PADRON_NORM_HIGH", 0.55))


def exposure_norm(l: np.ndarray):
    """Return affine anchors ``(lo, hi)`` for an under-exposed photo, else None.

    Disabled by setting ``PADRON_NORM_HIGH=0``.
    """
    if l.size == 0 or NORM_HIGH_TRIGGER <= 0:
        return None
    hi = float(np.percentile(l, 98))
    if hi >= NORM_HIGH_TRIGGER:
        return None
    lo = float(np.percentile(l, 2))
    if hi - lo < 1e-3:
        return None
    return (lo, hi)


def apply_norm(l: np.ndarray, norm) -> np.ndarray:
    """Stretch ``l`` so [lo, hi] maps to [0, 1]; identity when norm is None."""
    if norm is None:
        return l
    lo, hi = norm
    return np.clip((l - lo) / (hi - lo), 0.0, 1.0)


def _side_lines(arr: np.ndarray, side: str, depth: int, norm=None):
    """Per-line dark and strict-dark fractions, ordered from the edge inward.
    Computed in row chunks to bound peak memory on huge images."""
    H, W = arr.shape[:2]
    horizontal = side in ("top", "bottom")
    dim = H if horizontal else W
    depth = max(1, min(int(depth), dim))
    if side == "bottom":
        band = arr[H - depth :, :, :]
    elif side == "top":
        band = arr[:depth, :, :]
    elif side == "left":
        band = arr[:, :depth, :]
    else:
        band = arr[:, W - depth :, :]
    dark_f = np.empty(depth, np.float32)
    strict_f = np.empty(depth, np.float32)
    CH = 256
    if horizontal:
        # top/bottom: band rows are the scan lines (width pixels each)
        for s in range(0, depth, CH):
            e = min(s + CH, depth)
            l = luma(band[s:e])
            l = apply_norm(l, norm)
            dark_f[s:e] = (l < DARK_T).mean(axis=1)
            strict_f[s:e] = (l < STRICT_T).mean(axis=1)
    else:
        # left/right: scan lines are the depth columns; iterate full-width rows
        # in chunks and accumulate per-column counts (no transposed band copy)
        n_lines = band.shape[0]
        cd = np.zeros(depth, np.int64)
        cs = np.zeros(depth, np.int64)
        for s in range(0, n_lines, CH):
            e = min(s + CH, n_lines)
            l = luma(band[s:e])
            l = apply_norm(l, norm)
            cd += (l < DARK_T).sum(axis=0)
            cs += (l < STRICT_T).sum(axis=0)
        dark_f[:] = cd / float(n_lines)
        strict_f[:] = cs / float(n_lines)
    if side in ("bottom", "right"):
        dark_f = dark_f[::-1]
        strict_f = strict_f[::-1]
    return dark_f, strict_f


def _mean_luma(view: np.ndarray, norm=None) -> float:
    """Mean luma of a (sub)view, chunked to bound memory."""
    n0 = view.shape[0]
    if n0 == 0 or view.size == 0:
        return 0.0
    CH = 256
    acc, cnt = 0.0, 0
    for s in range(0, n0, CH):
        l = luma(np.ascontiguousarray(view[s : s + CH]))
        l = apply_norm(l, norm)
        acc += float(l.sum())
        cnt += l.size
    return acc / max(1, cnt)


def _edge_run(df: np.ndarray) -> int:
    run = 0
    for f in df.tolist():
        if f >= LINE_DARK_FRAC:
            run += 1
        else:
            break
    return run


def bright_components(bright: np.ndarray, min_cells: int = 6, max_comps: int = 400) -> list:
    """8-connected bright regions on a grid; returns (x, y, w, h) list.

    Run-length + union-find: each row is reduced to its contiguous bright runs,
    then runs in adjacent rows that overlap (with 1-cell diagonal expansion) are
    merged. Cost is O(number of runs) instead of O(number of pixels), which is
    what keeps the cascade fast on striped/gradient photos where a per-pixel
    Python BFS degenerates.
    """
    hh, ww = bright.shape
    if hh == 0 or ww == 0 or not bright.any():
        return []
    pad = np.zeros((hh, ww + 2), dtype=np.int8)
    pad[:, 1:ww + 1] = bright
    d = np.diff(pad, axis=1)
    sy, sx = np.nonzero(d == 1)          # run start (padded col, inclusive)
    ey, ex = np.nonzero(d == -1)         # run end   (padded col, exclusive)
    n = sy.size
    if n == 0:
        return []
    r_row, r_x0, r_x1 = np.ascontiguousarray(sy), sx - 1, ex - 2
    parent = np.arange(n, dtype=np.int64)

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return int(a)

    order = np.argsort(r_row, kind="stable")
    rows = r_row[order]
    uniq, first = np.unique(rows, return_index=True)
    bounds = list(first) + [n]
    # two-pointer overlap between consecutive rows
    for i in range(len(uniq)):
        r = int(uniq[i])
        if r == 0:
            continue
        if i == 0 or int(uniq[i - 1]) != r - 1:
            continue
        prev_i = i - 1
        a_idx = order[bounds[prev_i]:bounds[prev_i + 1]]
        b_idx = order[bounds[i]:bounds[i + 1]]
        ax0, ax1 = r_x0[a_idx], r_x1[a_idx]
        bx0, bx1 = r_x0[b_idx], r_x1[b_idx]
        p = 0
        for k in range(b_idx.size):
            b0, b1 = int(bx0[k]), int(bx1[k])
            while p < ax0.size and ax1[p] < b0 - 1:
                p += 1
            q = p
            while q < ax0.size and ax0[q] <= b1 + 1:
                ra, rb = find(int(b_idx[k])), find(int(a_idx[q]))
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
                q += 1

    boxes: dict = {}
    for k in range(n):
        root = find(k)
        x0, x1, y = int(r_x0[k]), int(r_x1[k]), int(r_row[k])
        b = boxes.get(root)
        if b is None:
            boxes[root] = [x0, y, x1, y]
        else:
            if x0 < b[0]: b[0] = x0
            if y < b[1]: b[1] = y
            if x1 > b[2]: b[2] = x1
            if y > b[3]: b[3] = y
    out = []
    for x0, ymin, x1, ymax in boxes.values():
        w, h = x1 - x0 + 1, ymax - ymin + 1
        if w * h >= min_cells:
            out.append((x0, ymin, w, h))
    out.sort(key=lambda c: (c[1], c[0]))   # discovery order (row-major)
    return out[:max_comps]


def _interval(side: str, run: int, H: int, W: int):
    """Pixel interval (lo, hi) of the solid bar strip along its own axis."""
    if side == "bottom":
        return (H - run, H)
    if side == "top":
        return (0, run)
    if side == "left":
        return (0, run)
    return (W - run, W)


def _content_intersects(content_comps, side: str, lo: int, hi: int) -> bool:
    """True if a big bright component overlaps the strip (beyond JPEG ringing)."""
    horizontal = side in ("top", "bottom")
    for (x, y, w, h) in content_comps:
        a0, a1 = (y, y + h) if horizontal else (x, x + w)
        overlap = min(a1, hi) - max(a0, lo)
        if overlap > COMP_TOL:
            return True
    return False


def _line_bright_ok(side, pos, H, W, step, ok_rows, ok_cols, bright_rows, bright_cols) -> bool:
    """A line may join the walk if its bright pixels belong to content rows/cols
    that are NOT covered by big content components (i.e., glyph-only rows)."""
    if side in ("top", "bottom"):
        r = pos if side == "top" else H - 1 - pos
        si = r // step
        if si >= len(bright_rows):
            return True
        return (not bright_rows[si]) or bool(ok_rows[si])
    c = pos if side == "left" else W - 1 - pos
    si = c // step
    if si >= len(bright_cols):
        return True
    return (not bright_cols[si]) or bool(ok_cols[si])


def _glyph_in_zone(g, side: str, L: int) -> bool:
    """Glyph fully inside the walk zone (between walk-stop L and the edge)."""
    x, y, w, h = g
    if side == "bottom":
        return y >= L
    if side == "top":
        return y + h <= L
    if side == "left":
        return x + w <= L
    return x >= L


def _glyph_extreme(gz, side: str) -> int:
    """Crop-line coordinate from the extreme glyph edge."""
    if side == "bottom":
        return min(g[1] for g in gz)
    if side == "top":
        return max(g[1] + g[3] for g in gz)
    if side == "left":
        return max(g[0] + g[2] for g in gz)
    return min(g[0] for g in gz)


def _ext_strip(side: str, ext: int, run: int, H: int, W: int):
    """Strip between the glyph crop line and the solid bar edge (for checks)."""
    if side == "bottom":
        return (ext, H - run)
    if side == "top":
        return (run, ext)
    if side == "left":
        return (run, ext)
    return (W - run, ext)


def _bar_evidence_ok(arr: np.ndarray, side: str, run: int, H: int, W: int,
                     norm=None) -> bool:
    """A run counts as a bar only with strong evidence:
    (a) the strip is predominantly near-black (true black bar), or
    (b) a clear luma step vs the adjacent inner band AND a sharp transition
        (rejects vignettes / dark clothing gradients that fade into content)."""
    dim = H if side in ("top", "bottom") else W
    _df, sf = _side_lines(arr, side, min(run + 4, dim), norm)
    if run > 0 and float(np.mean(sf[:run])) >= STRICT_BAR_Q:
        return True
    if side == "bottom":
        strip, inner = arr[H - run :, :, :], arr[max(0, H - 2 * run) : H - run, :, :]
    elif side == "top":
        strip, inner = arr[:run, :, :], arr[run : min(H, 2 * run), :, :]
    elif side == "left":
        strip, inner = arr[:, :run, :], arr[:, run : min(W, 2 * run), :]
    else:
        strip, inner = arr[:, W - run :, :], arr[:, max(0, W - 2 * run) : W - run, :]
    if strip.size == 0 or inner.size == 0:
        return False
    contrast = _mean_luma(inner, norm) - _mean_luma(strip, norm)
    df2, _sf2 = _side_lines(arr, side, min(run + 3, dim), norm)
    shoulder = df2[run : run + 3]
    sharp = bool(shoulder.size and float(np.mean(shoulder)) < SHOULDER_MAX)
    return contrast >= CONTRAST_MIN and sharp


def _refine_ext(arr: np.ndarray, side: str, gz: list, ext: int, norm=None) -> int:
    """Refine the glyph-extreme to full-res precision (grid was coarse)."""
    H, W = arr.shape[:2]
    lo_i, hi_i = max(0, ext - 6), (ext + 7)
    if side == "bottom":
        x0 = min(g[0] for g in gz); x1 = max(g[0] + g[2] for g in gz)
        window = apply_norm(luma(arr[lo_i:hi_i, x0:x1]), norm)
        rows = np.nonzero((window > BRIGHT_T).any(axis=1))[0]
        return lo_i + int(rows.min()) if rows.size else ext
    if side == "top":
        x0 = min(g[0] for g in gz); x1 = max(g[0] + g[2] for g in gz)
        window = apply_norm(luma(arr[lo_i:hi_i, x0:x1]), norm)
        rows = np.nonzero((window > BRIGHT_T).any(axis=1))[0]
        return lo_i + int(rows.max()) if rows.size else ext
    if side == "left":
        y0 = min(g[1] for g in gz); y1 = max(g[1] + g[3] for g in gz)
        window = apply_norm(luma(arr[y0:y1, lo_i:hi_i]), norm)
        cols = np.nonzero((window > BRIGHT_T).any(axis=0))[0]
        return lo_i + int(cols.max()) if cols.size else ext
    y0 = min(g[1] for g in gz); y1 = max(g[1] + g[3] for g in gz)
    window = apply_norm(luma(arr[y0:y1, lo_i:hi_i]), norm)
    cols = np.nonzero((window > BRIGHT_T).any(axis=0))[0]
    return lo_i + int(cols.min()) if cols.size else ext


def _assemble(thickness: dict, H: int, W: int):
    x0 = thickness.get("left", 0)
    y0 = thickness.get("top", 0)
    x1 = W - thickness.get("right", 0)
    y1 = H - thickness.get("bottom", 0)
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


def decide_crop(arr: np.ndarray, allowed_sides=None) -> Detection:
    H, W = arr.shape[:2]
    # coarse grid for component analysis keeps Python BFS bounded on huge images
    step = max(1, max(H, W) // 500)
    small = arr[::step, ::step]
    l = luma(small)
    norm = exposure_norm(l)      # engaged only for high/low-key photos
    l = apply_norm(l, norm)
    dark = l < DARK_T
    bright = l > BRIGHT_T

    # J: uniform dark image -> quarantine, never crop
    if float(l.mean()) < UNIFORM_DARK_MEAN and float(bright.mean()) < UNIFORM_BRIGHT_MAX:
        return Detection("quarantine", (0, 0, W, H), [], "none", 0.0,
                         "uniform_dark_image", False)

    comps = bright_components(bright)
    full = [(x * step, y * step, w * step, h * step) for (x, y, w, h) in comps]
    gmax_w = GLYPH_MAX_W_FRAC * W
    gmax_h = GLYPH_MAX_H_FRAC * H
    glyph_comps, content_comps = [], []
    for c in full:
        x, y, w, h = c
        if w >= GLYPH_MIN_PX and h >= GLYPH_MIN_PX and w <= gmax_w and h <= gmax_h:
            glyph_comps.append(c)
        elif w >= MIN_CONTENT_PX and h >= MIN_CONTENT_PX:
            content_comps.append(c)
        # else: tiny speck (JPEG noise) -> ignored entirely

    bright_rows = bright.any(axis=1)
    bright_cols = bright.any(axis=0)
    ok_rows = bright_rows.copy()
    ok_cols = bright_cols.copy()
    for (x, y, w, h) in content_comps:
        ok_rows[y // step : (y + h) // step + 1] = False
        ok_cols[x // step : (x + w) // step + 1] = False

    thickness: dict = {}
    qualities: list = []
    glyphs_used = False

    for side in (allowed_sides or SIDES):
        dim = H if side in ("top", "bottom") else W
        depth0 = min(int(0.35 * dim), 480)
        df, sf = _side_lines(arr, side, depth0, norm)
        run = _edge_run(df)
        if run < max(MIN_BAR_ABS, int(MIN_BAR_FRAC * dim)):
            continue
        walk_extra = min(int(WALK_MAX_FRAC * dim), WALK_MAX_ROWS)
        depth = depth0
        # grow the scan until the full bar run fits (never truncate the run:
        # a truncated run leaves the text block inside the output)
        while run + walk_extra > depth and depth < dim:
            depth = min(max(run + walk_extra, depth * 2), dim)
            df, sf = _side_lines(arr, side, depth, norm)
            run = _edge_run(df)
        if run > SWALLOW_FRAC * dim:
            continue
        # bar evidence gate: near-black strip or sharp contrast step
        # (protects dark clothing/shadow gradients from being cropped)
        if not _bar_evidence_ok(arr, side, run, H, W, norm):
            continue
        # deep runs additionally need near-black evidence
        if run > DEEP_RUN_FRAC * dim and float(np.mean(sf[:run])) < DEEP_STRICT_FRAC:
            continue
        lo, hi = _interval(side, run, H, W)
        if _content_intersects(content_comps, side, lo, hi):
            continue

        t = run
        # D3 walk: extend inward while lines stay mostly dark and any bright
        # pixels belong to glyph-like components (text anchor)
        pos = run
        n = len(df)
        while pos < n and df[pos] >= WALK_DARK_FRAC and _line_bright_ok(
            side, pos, H, W, step, ok_rows, ok_cols, bright_rows, bright_cols
        ):
            pos += 1
        if pos > run:
            L = pos if side in ("top", "left") else (
                H - 1 - pos if side == "bottom" else W - 1 - pos
            )
            gz = [g for g in glyph_comps if _glyph_in_zone(g, side, L)]
            if gz:
                ext = _refine_ext(arr, side, gz, _glyph_extreme(gz, side), norm)
                elo, ehi = _ext_strip(side, ext, run, H, W)
                # crop must remove at least the solid bar
                if side in ("bottom", "right"):
                    ok_guard = ext <= hi + MARGIN
                else:
                    ok_guard = ext >= hi - MARGIN
                a0 = elo // step
                a1 = max(a0 + 1, ehi // step)
                strip_dark = (
                    float(dark[a0:a1, :].mean())
                    if side in ("top", "bottom")
                    else float(dark[:, a0:a1].mean())
                )
                if ok_guard and strip_dark >= STRIP_DARK_MIN and not _content_intersects(
                    content_comps, side, elo, ehi
                ):
                    if side in ("bottom", "right"):
                        t = dim - ext + MARGIN   # keep MARGIN above glyph top
                    else:
                        t = ext + MARGIN         # keep MARGIN below glyph bottom
                    if t > 0.9 * dim:
                        t = run
                    else:
                        glyphs_used = True
        thickness[side] = t
        qualities.append(float(np.mean(df[:run])))

    if not thickness:
        return Detection("noop", (0, 0, W, H), [], "projection", 0.0, None, True)
    box = _assemble(thickness, H, W)
    if box is None:
        return Detection("noop", (0, 0, W, H), [], "projection", 0.0, None, True)
    removed = 1.0 - (box[2] * box[3]) / float(W * H)
    if removed > MAX_REMOVE_AREA:
        return Detection("quarantine", (0, 0, W, H), [], "projection", 0.0,
                         "crop_removes_majority", False)
    conf = 0.6 + 0.4 * min(qualities) if qualities else 0.0
    if glyphs_used:
        conf *= 0.92
    sides = [s for s in SIDES if s in thickness]
    return Detection("crop", box, sides,
                     "projection+glyphs" if glyphs_used else "projection",
                     round(min(1.0, conf), 3), None, True)


def apply_frozen(arr: np.ndarray, frozen: dict) -> Detection | None:
    """D0 fast path: apply a frozen geometry pattern; None if it does not verify."""
    H, W = arr.shape[:2]
    sides = list(frozen.get("sides") or [])
    thf = frozen.get("thickness") or {}
    if not sides:
        return Detection("noop", (0, 0, W, H), [], "d0-cache", 0.9, None, True)
    t = {}
    for s in sides:
        dim = H if s in ("top", "bottom") else W
        t[s] = int(round(float(thf.get(s, 0.0)) * dim))
        if t[s] <= 0:
            return None
    box = _assemble(t, H, W)
    if box is None:
        return None
    # the fast path must not bypass the safety gates of the full detector
    removed = 1.0 - (box[2] * box[3]) / float(W * H)
    if removed > MAX_REMOVE_AREA:
        return Detection("quarantine", (0, 0, W, H), [], "d0-cache", 0.0,
                         "crop_removes_majority", False)
    step = max(1, max(H, W) // 2000)
    l = luma(arr[::step, ::step])
    norm = exposure_norm(l)
    l = apply_norm(l, norm)
    bright = l > BRIGHT_T
    # J: uniform dark image -> quarantine even when the frozen bar is "verified"
    if float(l.mean()) < UNIFORM_DARK_MEAN and float(bright.mean()) < UNIFORM_BRIGHT_MAX:
        return Detection("quarantine", (0, 0, W, H), [], "d0-cache", 0.0,
                         "uniform_dark_image", False)
    dark = l < DARK_T
    for s, tv in t.items():
        if s == "bottom":
            sl_d, sl_b = dark[(H - tv) // step :, :], bright[(H - tv) // step :, :]
        elif s == "top":
            sl_d, sl_b = dark[: max(1, tv // step), :], bright[: max(1, tv // step), :]
        elif s == "left":
            sl_d, sl_b = dark[:, : max(1, tv // step)], bright[:, : max(1, tv // step)]
        else:
            sl_d, sl_b = dark[:, (W - tv) // step :], bright[:, (W - tv) // step :]
        # text glyphs may live inside the frozen crop zone -> allow modest bright
        if float(sl_d.mean()) < 0.5 or float(sl_b.mean()) > 0.10:
            return None
    return Detection("crop", box, [s for s in SIDES if s in t], "d0-cache", 0.9, None, True)
