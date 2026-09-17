"""Local ingest: recursive folder walk, magic-byte sniffing, relative paths."""
from __future__ import annotations

import os
from pathlib import Path

MAGIC = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF8", ".gif"),
    (b"BM", ".bmp"),
    (b"II*\x00", ".tif"),
    (b"MM\x00*", ".tif"),
)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def sniff_ext(p: Path) -> bool:
    """True if the file looks like an image (known ext or magic bytes)."""
    if p.suffix.lower() in IMAGE_EXTS:
        return True
    try:
        with open(p, "rb") as f:
            head = f.read(16)
    except OSError:
        return False
    if not head:
        return False
    if head[:4] in (b"RIFF",) and head[8:12] == b"WEBP":
        return True
    return any(head.startswith(m) for m, _ in MAGIC)


def iter_local(src: Path, limit: int | None = None):
    """Yield image-like files under src (recursive), optionally capped."""
    n = 0
    for root, _dirs, files in os.walk(src):
        for name in sorted(files):
            p = Path(root) / name
            if sniff_ext(p):
                yield p
                n += 1
                if limit and n >= limit:
                    return
