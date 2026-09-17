"""API ingest: config validation + failure-resistant streaming downloads.

Network realities handled here:

* timeouts on every request
* jittered exponential backoff, honouring ``Retry-After`` on 429/503
* only transient HTTP statuses are retried; 4xx that mean "wrong request" fail fast
* downloads resume from a ``.part`` file (HTTP Range), so a dropped connection
  does not re-download gigabytes
* a permanently failing item is isolated (recorded, not fatal) so one bad row
  cannot stop a multi-day ingest
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from padron_crop import safeio

REQUIRED_FIELDS = ("base_url", "list_endpoint", "id_field", "file_url_field")

API_TIMEOUT = float(os.environ.get("PADRON_API_TIMEOUT", 30.0))
API_RETRIES = int(os.environ.get("PADRON_API_RETRIES", 3))
API_BACKOFF = float(os.environ.get("PADRON_API_BACKOFF", 0.5))
API_BACKOFF_CAP = float(os.environ.get("PADRON_API_BACKOFF_CAP", 30.0))


def load_api_config(path: Path) -> dict:
    """Load and validate the API contract file (no secrets inside)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        raise ValueError(f"api config missing fields: {missing}")
    return data


def _retry_after(headers) -> float | None:
    """Seconds from a Retry-After header (delta-seconds form only)."""
    if not headers:
        return None
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def _auth_headers(token_env: str) -> dict:
    headers = {"User-Agent": "padron-crop/0.1"}
    token = os.environ.get(token_env)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def stream_download(url: str, dst: Path, retries: int = API_RETRIES,
                    backoff: float = API_BACKOFF, token_env: str = "PADRON_API_TOKEN",
                    timeout: float = API_TIMEOUT, resume: bool = True) -> Path:
    """Stream ``url`` into ``dst`` atomically, resuming a partial ``.part`` file."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    part = dst.with_name(dst.name + ".part")
    headers = _auth_headers(token_env)
    last: Exception | None = None

    for attempt in range(max(1, retries) + 1):
        offset = part.stat().st_size if (resume and part.exists()) else 0
        req_headers = dict(headers)
        if offset:
            req_headers["Range"] = f"bytes={offset}-"
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = getattr(resp, "status", 200)
                if status == 206:
                    mode = "ab"
                else:
                    mode = "wb"      # server ignored Range: restart cleanly
                    offset = 0
                with open(part, mode) as out:
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
                    out.flush()
                    os.fsync(out.fileno())
            os.replace(part, dst)
            return dst
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 416:                    # our Range is past EOF
                part.unlink(missing_ok=True)
            if e.code not in safeio.TRANSIENT_STATUS or attempt >= retries:
                break
            delay = safeio.backoff_delay(attempt, backoff, API_BACKOFF_CAP,
                                         _retry_after(e.headers))
        except Exception as e:  # noqa: BLE001 — timeouts, resets, DNS
            last = e
            if attempt >= retries:
                break
            delay = safeio.backoff_delay(attempt, backoff, API_BACKOFF_CAP)
        time.sleep(delay)
    raise IOError(f"download failed after {retries + 1} attempts: {last}")


def _fetch_json(url: str, headers: dict, timeout: float,
                retries: int = API_RETRIES) -> dict:
    """GET a JSON page with retries; transient statuses back off."""
    last: Exception | None = None
    for attempt in range(max(1, retries) + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in safeio.TRANSIENT_STATUS or attempt >= retries:
                break
            delay = safeio.backoff_delay(attempt, API_BACKOFF, API_BACKOFF_CAP,
                                         _retry_after(e.headers))
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt >= retries:
                break
            delay = safeio.backoff_delay(attempt, API_BACKOFF, API_BACKOFF_CAP)
        time.sleep(delay)
    raise IOError(f"request failed after {retries + 1} attempts: {last}")


def iter_api_images(config: dict, out_dir: Path, limit: int | None = None,
                    on_failure=None):
    """Walk paginated ``list_endpoint``; download each ``file_url_field``.

    ``on_failure(item_id, error)`` is called for items that exhaust retries;
    such items are skipped instead of aborting the whole run.
    """
    base = config["base_url"].rstrip("/")
    url = base + config["list_endpoint"]
    headers = _auth_headers("PADRON_API_TOKEN")
    n = 0
    while url:
        page = _fetch_json(url, headers, API_TIMEOUT)
        for it in page.get("items", []):
            fid = it[config["id_field"]]
            furl = it[config["file_url_field"]]
            dst = Path(out_dir) / f"{fid}"
            full = furl if str(furl).startswith("http") else base + furl
            try:
                stream_download(full, dst)
            except Exception as e:  # noqa: BLE001 — isolate the bad item
                if on_failure is not None:
                    on_failure(fid, e)
                continue
            yield dst
            n += 1
            if limit and n >= limit:
                return
        url = page.get("next")
        if url and not str(url).startswith("http"):
            url = base + url
