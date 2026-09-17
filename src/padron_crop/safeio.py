"""Failure-resistant I/O helpers: atomic writes, disk guards, cancellation.

Everything the pipeline writes goes through here so that a crash, a full disk
or a Ctrl-C can never leave a half-written file that a later ``--resume`` would
mistake for finished work.
"""
from __future__ import annotations

import contextlib
import json
import os
import random
import shutil
import signal
import tempfile
import time
from pathlib import Path

MB = 1 << 20


class InsufficientSpace(RuntimeError):
    """Not enough free space to continue safely."""


def free_mb(path: Path) -> float:
    """Free megabytes on the filesystem holding ``path`` (nearest existing dir)."""
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        return shutil.disk_usage(p).free / MB
    except OSError:
        return float("inf")


def require_space(path: Path, needed_mb: float = 0.0,
                  reserve_mb: float = 0.0) -> float:
    """Raise InsufficientSpace if writing ``needed_mb`` would break the reserve."""
    free = free_mb(path)
    if free - needed_mb < reserve_mb:
        raise InsufficientSpace(
            f"only {free:.0f} MB free at {path}; need {needed_mb:.0f} MB "
            f"plus {reserve_mb:.0f} MB reserve"
        )
    return free


def _fsync_dir(d: Path) -> None:
    """Best-effort directory fsync so a rename survives a power loss."""
    try:
        fd = os.open(str(d), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes via a temp file in the same dir + fsync + atomic replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-",
                               suffix=path.suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


@contextlib.contextmanager
def atomic_path(path: Path, suffix: str | None = None):
    """Yield a temp path in the target dir; on success atomically rename it.

    Any exception (including KeyboardInterrupt) removes the temp file, so the
    destination is either absent or complete — never half-written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-",
                               suffix=path.suffix or suffix or "")
    os.close(fd)
    try:
        yield Path(tmp)
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, obj) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False))


def append_jsonl(path: Path, obj) -> None:
    """Append one JSON record and fsync, so resume never loses or half-writes it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def read_jsonl_tolerant(path: Path) -> list[dict]:
    """Read a JSONL ledger, ignoring a truncated/corrupt tail line."""
    path = Path(path)
    if not path.exists():
        return []
    out: list[dict] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue          # torn last line after a crash: skip it
    return out


class Stop:
    """Cooperative cancellation driven by SIGINT/SIGTERM.

    Handlers are installed only in the main process; workers keep the default
    so they die immediately and the pool shutdown stays bounded.
    """

    def __init__(self):
        self.requested = False
        self.reason: str | None = None
        self._installed = False

    def request(self, reason: str) -> None:
        self.requested = True
        self.reason = reason

    def install(self) -> "Stop":
        if self._installed:
            return self

        def handler(signum, _frame):
            self.request(signal.Signals(signum).name)

        for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            sig = getattr(signal, name, None)
            if sig is None:
                continue
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass          # not the main thread / unsupported platform
        self._installed = True
        return self


TRANSIENT_STATUS = (408, 425, 429, 500, 502, 503, 504)


def backoff_delay(attempt: int, base: float = 0.5, cap: float = 30.0,
                  retry_after: float | None = None) -> float:
    """Jittered exponential backoff, honouring an explicit Retry-After."""
    if retry_after is not None and retry_after >= 0:
        return min(cap, retry_after)
    return min(cap, base * (2 ** attempt)) * (0.5 + random.random() / 2)


def retry_call(fn, *, attempts: int = 3, base: float = 0.5, cap: float = 30.0,
               on_error=None, sleep=time.sleep):
    """Call ``fn`` with jittered backoff; last error is re-raised.

    ``on_error(exc)`` may return a float to use as the next delay (e.g. a
    Retry-After value) or None to fall back to the computed backoff.
    """
    last: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — caller decides what is fatal
            last = e
            if attempt + 1 >= attempts:
                break
            hint = None
            if on_error is not None:
                hint = on_error(e)
            sleep(backoff_delay(attempt, base, cap, hint))
    assert last is not None
    raise last
