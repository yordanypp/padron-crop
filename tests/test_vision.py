"""D4 vision connector: schema, PII guard, retries, veto-only behaviour."""
from __future__ import annotations

from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from helpers import add_bar, photo, save

from padron_crop.geometry import Detection, decide_crop
from padron_crop.vision import (THUMB_MAX_PX, VisionClient, assert_test_copy,
                                build_thumbnail, resolve_with_vision,
                                scale_bbox, validate_response)


def _resp(obj) -> dict:
    """OpenAI-shaped response whose content is a JSON string."""
    import json

    content = obj if isinstance(obj, str) else json.dumps(obj)
    return {"choices": [{"message": {"content": content}}]}


# ---------- thumbnail ----------

def test_thumbnail_bounded_and_jpeg():
    arr = np.zeros((900, 1400, 3), np.uint8)
    arr[100:200, 100:300] = 255
    data = build_thumbnail(arr)
    im = Image.open(BytesIO(data))
    assert max(im.size) <= THUMB_MAX_PX
    assert im.format == "JPEG"


def test_scale_bbox_roundtrip():
    # thumbnail 256x128 -> original 1024x512 (4x)
    assert scale_bbox([10, 5, 20, 10], (256, 128), (1024, 512)) == [40, 20, 80, 40]


# ---------- strict schema ----------

def test_validate_response_ok():
    out = validate_response({"bbox_xywh": [1, 2, 3, 4], "kind": "blackbar",
                             "confidence": 0.5})
    assert out == {"bbox_xywh": [1, 2, 3, 4], "kind": "blackbar", "confidence": 0.5}


@pytest.mark.parametrize("bad", [
    {"bbox_xywh": [1, 2, 3, 4], "kind": "blackbar", "confidence": 0.5, "extra": 1},
    {"bbox_xywh": [1, 2, 3], "kind": "blackbar", "confidence": 0.5},
    {"bbox_xywh": [1, 2, 3, 4], "kind": "face", "confidence": 0.5},
    {"bbox_xywh": [1, 2, 3, 4], "kind": "text", "confidence": 1.5},
    {"bbox_xywh": [1, 2, -3, 4], "kind": "text", "confidence": 0.5},
    {"bbox_xywh": [1.5, 2, 3, 4], "kind": "text", "confidence": 0.5},
    {"kind": "text", "confidence": 0.5},
    "not an object",
])
def test_validate_response_rejects(bad):
    with pytest.raises(ValueError):
        validate_response(bad)


# ---------- PII guard ----------

def test_test_copy_guard_refuses_real_photo(tmp_path):
    real = tmp_path / "padron_real.jpg"
    real.write_bytes(b"x")
    with pytest.raises(RuntimeError):
        assert_test_copy(real)


def test_test_copy_guard_allows_marked_paths(tmp_path):
    assert_test_copy(tmp_path / "tests" / "a.jpg") is None
    assert_test_copy(tmp_path / "sample_anchor.jpg") is None


# ---------- off by default ----------

def test_disabled_by_default_never_calls_transport():
    calls = []

    def transport(*a):
        calls.append(a)
        raise AssertionError("transport must not be called when disabled")

    arr = photo()
    client = VisionClient(api_key="k", allow_remote=False, transport=transport)
    assert client.propose_bbox(arr) is None
    assert calls == []


def test_no_token_means_no_call(monkeypatch):
    for var in ("OPENAI_API_KEY", "PADRON_API_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    calls = []
    client = VisionClient(api_key=None, allow_remote=True,
                          transport=lambda *a: calls.append(a))
    assert client.propose_bbox(photo()) is None
    assert calls == []


# ---------- retries ----------

def test_retries_then_success():
    state = {"n": 0}

    def transport(url, payload, headers, timeout):
        state["n"] += 1
        if state["n"] < 3:
            raise IOError("boom")
        return _resp({"bbox_xywh": [0, 0, 400, 50], "kind": "blackbar",
                      "confidence": 0.9})

    client = VisionClient(api_key="k", allow_remote=True, retries=2,
                          backoff=0.0, transport=transport)
    arr = add_bar(photo(), "bottom", 50)
    assert client.propose_bbox(arr) == [0, 0, 400, 50]
    assert state["n"] == 3


def test_invalid_schema_is_discarded():
    client = VisionClient(api_key="k", allow_remote=True, retries=0,
                          backoff=0.0, transport=lambda *a: _resp("not json"))
    assert client.propose_bbox(photo()) is None


# ---------- veto-only ----------

class _StubClient:
    def __init__(self, proposal):
        self.proposal = proposal

    def propose_bbox(self, arr, src=None):
        return self.proposal


def test_vision_agreement_keeps_deterministic_box():
    arr = add_bar(photo(), "bottom", 50)
    det = decide_crop(arr)
    assert det.status == "crop"
    out = resolve_with_vision(det, arr, _StubClient(list(det.crop_box)))
    assert out is det


def test_vision_disagreement_quarantines():
    arr = add_bar(photo(), "bottom", 50)
    det = decide_crop(arr)
    x, y, w, h = det.crop_box
    bad = _StubClient([0, 0, w, max(1, h // 4)])
    out = resolve_with_vision(det, arr, bad)
    assert out.status == "quarantine"
    assert out.quarantine_reason == "detector_disagreement"
    assert out.face_safety_ok is False


def test_allow_remote_ai_refuses_real_photo_path(tmp_path):
    """A non-test path must never leave the machine, transport included."""
    from padron_crop.crop import crop_image

    src = tmp_path / "padron_real.jpg"
    save(add_bar(photo(), "bottom", 50), src)
    seen = []
    client = VisionClient(api_key="k", allow_remote=True,
                          transport=lambda *a: seen.append(a))
    rec = crop_image(src, tmp_path / "out", vision=client)
    assert rec["status"] == "failed"
    assert "refusing" in (rec["error"] or "")
    assert seen == []


def test_vision_never_overrides_when_already_quarantined():
    arr = photo()
    q = Detection("quarantine", (0, 0, arr.shape[1], arr.shape[0]), [], "none",
                  0.0, "uniform_dark_image", False)
    out = resolve_with_vision(q, arr, _StubClient([0, 0, 1, 1]))
    assert out is q
