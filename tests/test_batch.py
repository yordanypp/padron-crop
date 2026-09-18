"""Batch (local ingest), fast-path, resume, sql/api stubs, CLI smoke."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from helpers import add_bar, photo, save

from padron_crop.batch import run_batch
from padron_crop.crop import crop_image


def _write_photo_set(dir_path: Path, n=6, bar=50, side="bottom"):
    dir_path.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(n):
        p = dir_path / f"p{i:03d}.jpg"
        save(add_bar(photo(), side, bar), p)
        paths.append(p)
    return paths


# ---------- local batch ----------

def test_batch_recursive_and_sidecars(tmp_path):
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    _write_photo_set(src, 4)
    _write_photo_set(src / "sub", 3)
    out = tmp_path / "out"
    summary = run_batch(src, out, workers=2, limit=None, resume=False, state_path=out / "state.jsonl", audit_path=out / "audit.csv")
    assert summary["ok"] == 7
    assert len([x for x in out.rglob("*.jpg") if x.parent.name != "entrega"]) == 7
    sidecars = list(out.rglob("*.json"))
    assert len(sidecars) == 7
    sc = json.loads(sidecars[0].read_text(encoding="utf-8"))
    for k in ("source", "sha256", "crop_box_xywh", "status"):
        assert k in sc


def test_batch_fast_path_same_pattern(tmp_path):
    src = tmp_path / "src"
    _write_photo_set(src, 6, bar=50, side="bottom")
    out = tmp_path / "out"
    summary = run_batch(src, out, workers=1, resume=False, state_path=out / "state.jsonl", audit_path=out / "audit.csv")
    assert summary["ok"] == 6
    methods = {json.loads(sc.read_text(encoding="utf-8"))["method"] for sc in out.rglob("*.json")}
    assert "d0-cache" in methods


def test_batch_mixed_patterns_no_wrong_fastpath(tmp_path):
    src = tmp_path / "src"
    _write_photo_set(src, 3, bar=50, side="bottom")
    _write_photo_set(src / "x", 3, bar=40, side="left")
    out = tmp_path / "out"
    summary = run_batch(src, out, workers=1, resume=False, state_path=out / "state.jsonl", audit_path=out / "audit.csv")
    assert summary["ok"] == 6
    m1 = json.loads((out / "p000.json").read_text(encoding="utf-8"))["method"]
    m2 = json.loads((out / "x" / "p000.json").read_text(encoding="utf-8"))["method"]
    assert m1 != "d0-cache" or m2 != "d0-cache"


def test_batch_resume_skips_done(tmp_path):
    src = tmp_path / "src"
    _write_photo_set(src, 4)
    out = tmp_path / "out"
    st, au = out / "state.jsonl", out / "audit.csv"
    run_batch(src, out, workers=1, resume=False, state_path=st, audit_path=au)
    before = st.read_text(encoding="utf-8")
    summary = run_batch(src, out, workers=1, resume=True, state_path=st, audit_path=au)
    assert summary["skipped"] == 4
    assert st.read_text(encoding="utf-8") == before


def test_batch_dry_run_writes_nothing(tmp_path):
    src = tmp_path / "src"
    _write_photo_set(src, 3)
    out = tmp_path / "out"
    summary = run_batch(src, out, workers=1, dry_run=True,
                        state_path=out / "s.jsonl", audit_path=out / "a.csv")
    assert summary["ok"] == 3
    assert not list(out.rglob("*.jpg"))
    assert not (out / "s.jsonl").exists()
    assert not (out / "a.csv").exists()


def test_batch_sources_untouched(tmp_path):
    src = tmp_path / "src"
    _write_photo_set(src, 3)
    digests = {p: p.read_bytes() for p in src.rglob("*.jpg")}
    out = tmp_path / "out"
    # single worker: this test is about source integrity, not parallelism
    run_batch(src, out, workers=1, resume=False, state_path=out / "s.jsonl", audit_path=out / "a.csv")
    for p, d in digests.items():
        assert p.read_bytes() == d


def test_batch_quarantine_and_failed(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    save(np.full((300, 400, 3), 12, np.uint8), src / "dark.jpg")
    (src / "corrupt.jpg").write_bytes(b"junk" * 50)
    _write_photo_set(src, 2)
    out = tmp_path / "out"
    summary = run_batch(src, out, workers=1, resume=False, state_path=out / "s.jsonl", audit_path=out / "a.csv")
    assert summary["quarantine"] >= 1
    assert summary["failed"] >= 1
    q = json.loads((out / "quarantine" / "dark.json").read_text(encoding="utf-8"))
    assert q["status"] == "quarantine"
    f = json.loads((out / "failed" / "corrupt.json").read_text(encoding="utf-8"))
    assert f["status"] == "failed"


def test_batch_fastpath_correct_crops(tmp_path):
    src = tmp_path / "src"
    _write_photo_set(src, 6, bar=50, side="bottom")
    out = tmp_path / "out"
    summary = run_batch(src, out, workers=1, resume=False, state_path=out / "s.jsonl", audit_path=out / "a.csv")
    assert summary["ok"] == 6
    for im in out.rglob("p*.jpg"):
        assert Image.open(im).size == (400, 250)


# ---------- sql stub ----------

def test_sql_requires_env(monkeypatch):
    monkeypatch.delenv("PADRON_DB_URL", raising=False)
    from padron_crop.ingest.sql import SqlIngest
    with pytest.raises(RuntimeError):
        SqlIngest()


def test_sql_introspection_clean_without_db(monkeypatch):
    monkeypatch.setenv("PADRON_DB_URL", "sqlite://")
    from padron_crop.ingest.sql import SqlIngest
    try:
        ing = SqlIngest()
        cols = ing.introspect_candidates()
        assert isinstance(cols, list)
    except RuntimeError:
        pass  # sqlalchemy missing -> clean error is acceptable


# ---------- api stub ----------

def test_api_config_validation(tmp_path):
    from padron_crop.ingest.api import load_api_config
    cfg = tmp_path / "api.json"
    cfg.write_text(json.dumps({"base_url": "http://x", "list_endpoint": "/api/photos", "id_field": "id", "file_url_field": "url"}))
    conf = load_api_config(cfg)
    assert conf["base_url"] == "http://x"


def test_api_config_missing_fields(tmp_path):
    from padron_crop.ingest.api import load_api_config
    cfg = tmp_path / "api.json"
    cfg.write_text(json.dumps({"base_url": "http://x"}))
    with pytest.raises(ValueError):
        load_api_config(cfg)


def test_api_stream_download_retries(tmp_path):
    """Local http.server: first response 500, then 200 -> retry succeeds."""
    import http.server
    import socketserver
    import threading

    from padron_crop.ingest.api import stream_download

    payload = b"\xff\xd8\xff\xe0" + b"x" * 100
    hits = {"n": 0}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits["n"] += 1
            if hits["n"] < 2:
                self.send_response(500)
                self.end_headers()
            else:
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        def log_message(self, *a):
            pass

    # default HTTPServer.server_bind() calls socket.getfqdn(), which on Windows
    # can stall for hundreds of ms; the test only needs the socket bound.
    class FastHTTPServer(http.server.HTTPServer):
        def server_bind(self):
            socketserver.TCPServer.server_bind(self)
            host, port = self.server_address[:2]
            self.server_name, self.server_port = host, port

    srv = FastHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        dst = tmp_path / "dl.bin"
        stream_download(f"http://127.0.0.1:{srv.server_port}/f", dst, retries=3, backoff=0.01)
        assert dst.read_bytes() == payload
        assert hits["n"] == 2
    finally:
        srv.shutdown()


# ---------- CLI smoke ----------

def test_cli_crop_and_inspect(tmp_path, capsys):
    from padron_crop.cli import main

    src = tmp_path / "src.jpg"
    save(add_bar(photo(), "bottom", 50), src)
    out = tmp_path / "out.jpg"

    assert main(["crop", "--in", str(src), "--out", str(out)]) == 0
    assert out.exists()
    assert Image.open(out).size == (400, 250)
    assert '"status": "ok"' in capsys.readouterr().out

    assert main(["inspect", "--image", str(src)]) == 0
    assert "width" in capsys.readouterr().out
