"""Failure-mode tests: disk, crash, cancel, network flakiness, DB errors."""
from __future__ import annotations

import http.server
import json
import socketserver
import threading

import pytest

from helpers import add_bar, photo, save

from padron_crop import safeio
from padron_crop.batch import run_batch

# ---------- atomic writes ----------

def test_atomic_write_leaves_no_partial_file(tmp_path):
    dst = tmp_path / "out.json"
    with pytest.raises(RuntimeError):
        with safeio.atomic_path(dst) as tmp:
            tmp.write_text("half", encoding="utf-8")
            raise RuntimeError("boom")
    assert not dst.exists()
    assert list(tmp_path.glob(".tmp-*")) == []


def test_atomic_write_replaces_complete_file(tmp_path):
    dst = tmp_path / "out.bin"
    safeio.atomic_write_bytes(dst, b"first")
    safeio.atomic_write_bytes(dst, b"second")
    assert dst.read_bytes() == b"second"
    assert list(tmp_path.glob(".tmp-*")) == []


# ---------- tolerant resume ----------

def test_state_with_torn_last_line_still_resumes(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    for i in range(3):
        save(add_bar(photo(), "bottom", 50), src / f"p{i}.jpg")
    out = tmp_path / "out"
    state, audit = out / "s.jsonl", out / "a.csv"
    run_batch(src, out, workers=1, state_path=state, audit_path=audit)

    # simulate a crash mid-write: append a truncated JSON line
    with open(state, "a", encoding="utf-8") as f:
        f.write('{"source": "src/p2.jpg", "stat')

    summary = run_batch(src, out, workers=1, resume=True, state_path=state,
                        audit_path=audit)
    assert summary["skipped"] == 3          # torn line did not break resume
    assert summary["ok"] == 0


# ---------- disk guard ----------

def test_require_space_raises_when_reserve_is_impossible(tmp_path):
    with pytest.raises(safeio.InsufficientSpace):
        safeio.require_space(tmp_path, reserve_mb=float("inf"))


def test_batch_aborts_cleanly_when_disk_reserve_unreachable(tmp_path, monkeypatch):
    import padron_crop.batch as batch

    src = tmp_path / "src"
    src.mkdir()
    save(add_bar(photo(), "bottom", 50), src / "p0.jpg")
    monkeypatch.setattr(batch, "MIN_FREE_MB", float("inf"))
    with pytest.raises(safeio.InsufficientSpace):
        run_batch(src, tmp_path / "out", workers=1)


def test_disk_check_mid_run_stops_gracefully(tmp_path, monkeypatch):
    import padron_crop.batch as batch

    src = tmp_path / "src"
    src.mkdir()
    for i in range(6):
        save(add_bar(photo(), "bottom", 50), src / f"p{i}.jpg")
    out = tmp_path / "out"
    monkeypatch.setattr(batch, "MIN_FREE_MB", 0.0)
    monkeypatch.setattr(batch, "DISK_CHECK_EVERY", 1)
    calls = {"n": 0}
    real = safeio.require_space

    def flaky(path, needed_mb=0.0, reserve_mb=0.0):
        calls["n"] += 1
        if calls["n"] > 1:                       # first call is the pre-flight
            raise safeio.InsufficientSpace("simulated full disk")
        return real(path, needed_mb, reserve_mb)

    monkeypatch.setattr(batch.safeio, "require_space", flaky)
    summary = run_batch(src, out, workers=1)
    assert summary["interrupted"] is True
    assert "disk" in summary["stop_reason"]
    assert summary["ok"] + summary["noop"] + summary["failed"] >= 1


# ---------- unsafe multiprocessing entry points ----------

def test_workers_downgrade_when_main_is_not_importable(tmp_path, monkeypatch):
    """Windows spawn re-imports __main__; with stdin/-c the pool would crash.
    Instead of a BrokenProcessPool we must degrade to 1 worker cleanly."""
    import sys
    import types

    import padron_crop.batch as batch

    src = tmp_path / "src"
    src.mkdir()
    save(add_bar(photo(), "bottom", 50), src / "p0.jpg")
    monkeypatch.setattr(batch.mp, "get_start_method", lambda allow_none=False: "spawn")
    monkeypatch.setitem(sys.modules, "__main__", types.SimpleNamespace(__file__=None))
    with pytest.warns(RuntimeWarning):
        summary = run_batch(src, tmp_path / "out", workers=2)
    assert summary["ok"] == 1
    assert "workers_downgraded" in summary


def test_pool_usable_true_for_real_script(monkeypatch):
    import sys
    import types
    from padron_crop.batch import _pool_usable

    monkeypatch.setitem(sys.modules, "__main__", types.SimpleNamespace(__file__=__file__))
    assert _pool_usable()[0] is True


# ---------- cooperative cancellation ----------

def test_stop_flag_stops_before_any_work(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    for i in range(4):
        save(add_bar(photo(), "bottom", 50), src / f"p{i}.jpg")
    stop = safeio.Stop()
    stop.request("SIGINT")
    out = tmp_path / "out"
    summary = run_batch(src, out, workers=1, stop=stop)
    assert summary["interrupted"] is True
    assert summary["stop_reason"] == "SIGINT"
    assert summary["ok"] == 0
    assert not list(out.rglob("*.jpg"))


# ---------- backoff ----------

def test_backoff_honours_retry_after_and_caps():
    assert safeio.backoff_delay(0, retry_after=7.0) == 7.0
    assert safeio.backoff_delay(20, base=1.0, cap=5.0) <= 5.0
    assert safeio.backoff_delay(0, base=2.0) <= 2.0


def test_retry_call_retries_then_succeeds():
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise IOError("transient")
        return "ok"

    assert safeio.retry_call(flaky, attempts=3, sleep=lambda _s: None) == "ok"
    assert state["n"] == 3


def test_retry_call_raises_last_error():
    with pytest.raises(IOError):
        safeio.retry_call(lambda: (_ for _ in ()).throw(IOError("nope")),
                          attempts=2, sleep=lambda _s: None)


# ---------- api: resumable download ----------

class _RangeServer(http.server.HTTPServer):
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name, self.server_port = host, port


def test_stream_download_resumes_from_part_file(tmp_path):
    from padron_crop.ingest.api import stream_download

    payload = b"0123456789" * 100          # 1000 bytes
    seen = {"range": None}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen["range"] = self.headers.get("Range")
            start = int(seen["range"].split("=")[1].split("-")[0]) if seen["range"] else 0
            body = payload[start:]
            self.send_response(206 if seen["range"] else 200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = _RangeServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        dst = tmp_path / "dl.bin"
        (tmp_path / "dl.bin.part").write_bytes(payload[:400])   # a dropped download
        stream_download(f"http://127.0.0.1:{srv.server_port}/f", dst,
                        retries=1, backoff=0.0)
        assert dst.read_bytes() == payload
        assert seen["range"] == "bytes=400-"
        assert not (tmp_path / "dl.bin.part").exists()
    finally:
        srv.shutdown()


# ---------- sql: read-only guard ----------

@pytest.mark.parametrize("bad", ["DELETE FROM t", "UPDATE t SET x=1",
                                 "DROP TABLE t", "INSERT INTO t VALUES (1)"])
def test_sql_rejects_non_read_only_statements(bad):
    from padron_crop.ingest.sql import assert_read_only

    with pytest.raises(ValueError):
        assert_read_only(bad)


def test_sql_accepts_select_and_with():
    from padron_crop.ingest.sql import assert_read_only

    assert assert_read_only("  SELECT a FROM t")
    assert assert_read_only("WITH x AS (SELECT 1) SELECT * FROM x")


def test_sql_uses_configured_dsn_and_clean_error(monkeypatch):
    monkeypatch.delenv("PADRON_DB_URL", raising=False)
    from padron_crop.ingest.sql import SqlIngest

    with pytest.raises(RuntimeError):
        SqlIngest()
