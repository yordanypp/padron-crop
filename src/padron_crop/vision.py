"""D4 — optional vision-model connector (OpenAI-compatible / Gemini / Grok).

Hard rules enforced here:

* **OFF by default.** Nothing is instantiated or called unless the operator
  passes ``allow_remote=True`` *and* the image is a test copy.
* **It can only veto.** The connector never supplies the crop geometry; it is
  consulted when the deterministic detectors disagree, and a disagreement
  above ``DISAGREE_TOL`` sends the image to quarantine instead of guessing.
* **Strict schema.** Any extra field, wrong type or out-of-range coordinate
  discards the response.
* **No secrets in code.** The token comes from the environment only.

Real padrón photos must never be sent: see ``assert_test_copy``.
"""
from __future__ import annotations

import base64
import json
import math
import os
import time
import urllib.request
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

THUMB_MAX_PX = 512          # longest side of the thumbnail sent to the model
THUMB_QUALITY = 80
TEXT_KINDS = ("blackbar", "text", "unknown")
DISAGREE_TOL = 0.03         # relative box difference that counts as disagreement

# provider -> (default base_url, default model)
PROVIDERS = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai",
               "gemini-2.0-flash"),
    "grok": ("https://api.x.ai/v1", "grok-2-vision-1212"),
}
TOKEN_ENV = {
    "openai": "OPENAI_API_KEY",
    "gemini": "PADRON_API_TOKEN",
    "grok": "PADRON_API_TOKEN",
}

# path parts / prefixes accepted as a non-personal (test) copy
TEST_COPY_MARKERS = ("tests", "test", "out", "fixtures", "synthetic", "sample")
TEST_COPY_PREFIXES = ("test_", "sample_", "synth_", "synthetic_")


def assert_test_copy(path: Path) -> None:
    """Refuse to send anything that is not clearly a test copy (PII guard)."""
    p = Path(path)
    parts = {part.lower() for part in p.parts[:-1]}
    name = p.name.lower()
    if parts & set(TEST_COPY_MARKERS) or name.startswith(TEST_COPY_PREFIXES):
        return
    raise RuntimeError(
        f"refusing to send non-test image to a remote model: {p} "
        "(only synthetic/test copies may leave the machine)"
    )


def build_thumbnail(arr: np.ndarray) -> bytes:
    """Downscale to <= THUMB_MAX_PX on the longest side and encode JPEG q80."""
    im = Image.fromarray(arr)
    im.thumbnail((THUMB_MAX_PX, THUMB_MAX_PX))
    buf = BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=THUMB_QUALITY)
    return buf.getvalue()


def scale_bbox(bbox, thumb_wh, orig_wh):
    """Map a bbox from thumbnail pixels back to original image pixels."""
    x, y, w, h = bbox
    tw, th = thumb_wh
    ow, oh = orig_wh
    sx, sy = ow / float(tw or 1), oh / float(th or 1)
    return [int(round(x * sx)), int(round(y * sy)),
            int(round(w * sx)), int(round(h * sy))]


def validate_response(obj) -> dict:
    """Strict validator for the model response; raises ValueError otherwise."""
    if not isinstance(obj, dict):
        raise ValueError("response is not a JSON object")
    extra = set(obj) - {"bbox_xywh", "kind", "confidence"}
    if extra:
        raise ValueError(f"unexpected fields: {sorted(extra)}")
    for field in ("bbox_xywh", "kind", "confidence"):
        if field not in obj:
            raise ValueError(f"missing field: {field}")
    bbox = obj["bbox_xywh"]
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise ValueError("bbox_xywh must be a list of 4 integers")
    for v in bbox:
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("bbox_xywh must contain integers")
        if v < 0:
            raise ValueError("bbox_xywh must be non-negative")
    if obj["kind"] not in TEXT_KINDS:
        raise ValueError(f"kind must be one of {TEXT_KINDS}")
    conf = obj["confidence"]
    if isinstance(conf, bool) or not isinstance(conf, (int, float)):
        raise ValueError("confidence must be a number")
    if not 0.0 <= float(conf) <= 1.0:
        raise ValueError("confidence must be within [0, 1]")
    return {"bbox_xywh": [int(v) for v in bbox], "kind": obj["kind"],
            "confidence": float(conf)}


class VisionClient:
    """Minimal OpenAI-compatible chat client used only as a D4 veto.

    ``transport`` is injectable so tests never touch the network.
    """

    def __init__(self, provider: str = "openai", *, allow_remote: bool = False,
                 base_url: str | None = None, model: str | None = None,
                 api_key: str | None = None, timeout: float = 8.0,
                 retries: int = 2, backoff: float = 0.2, transport=None):
        if provider not in PROVIDERS:
            raise ValueError(f"unknown provider: {provider}")
        default_url, default_model = PROVIDERS[provider]
        self.provider = provider
        self.allow_remote = allow_remote
        self.base_url = (base_url or default_url).rstrip("/")
        self.model = model or default_model
        self.api_key = api_key or os.environ.get(TOKEN_ENV[provider], "")
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self._transport = transport

    def _call(self, url: str, payload: dict, headers: dict, timeout: float) -> dict:
        if self._transport is not None:
            return self._transport(url, payload, headers, timeout)
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def propose_bbox(self, arr: np.ndarray, src: Path | None = None) -> dict | None:
        """Return a validated bbox in *original* pixel coords, or None.

        None means: not enabled, no token, or the response was rejected.
        """
        if not self.allow_remote or not self.api_key:
            return None
        if src is not None:
            assert_test_copy(src)
        thumb = build_thumbnail(arr)
        thumb_wh = Image.open(BytesIO(thumb)).size
        orig_wh = (arr.shape[1], arr.shape[0])
        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": (
                        "Return ONLY JSON {\"bbox_xywh\":[x,y,w,h],"
                        "\"kind\":\"blackbar|text|unknown\",\"confidence\":0..1} "
                        "for the black bar / text block, in these image pixels."
                    )},
                    {"type": "image_url", "image_url": {
                        "url": "data:image/jpeg;base64,"
                               + base64.b64encode(thumb).decode("ascii")}},
                ],
            }],
            "temperature": 0,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.base_url}/chat/completions"
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                raw = self._call(url, payload, headers, self.timeout)
                content = raw["choices"][0]["message"]["content"]
                obj = json.loads(content) if isinstance(content, str) else content
                bbox = validate_response(obj)["bbox_xywh"]
                tw, th = thumb_wh
                if bbox[0] >= tw or bbox[1] >= th:
                    raise ValueError("bbox outside the thumbnail")
                return scale_bbox(bbox, thumb_wh, orig_wh)
            except Exception as e:  # noqa: BLE001 — schema/transport/HTTP
                last = e
                if attempt < self.retries:
                    time.sleep(self.backoff * (2 ** attempt))
        del last
        return None


def resolve_with_vision(det, arr: np.ndarray, client: VisionClient | None,
                        src: Path | None = None):
    """Let D4 veto a deterministic crop when the two clearly disagree.

    The deterministic box always wins when they agree; D4 can only push the
    image to quarantine, never redefine the geometry.

    ``src`` is forwarded so the PII guard (``assert_test_copy``) runs before
    anything leaves the machine.
    """
    from padron_crop.geometry import Detection  # local import: no cycle

    if client is None or det is None or det.status != "crop":
        return det
    proposal = client.propose_bbox(arr, src=src)
    if proposal is None:
        return det
    x, y, w, h = det.crop_box
    H, W = arr.shape[:2]
    diff = max(abs(proposal[0] - x) / W, abs(proposal[1] - y) / H,
               abs(proposal[2] - w) / W, abs(proposal[3] - h) / H)
    if math.isfinite(diff) and diff > DISAGREE_TOL:
        return Detection("quarantine", (0, 0, W, H), [], "d4-disagreement", 0.0,
                         "detector_disagreement", False)
    return det
