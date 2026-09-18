"""Autotune adaptativo: la maquina decide sus workers (potente=max, lenta=seguro)."""
import os

from padron_crop import autotune


def test_profile_reports_cpu_and_ram():
    p = autotune.machine_profile()
    assert p["cpu"] >= 1
    assert p["ram_gb"] > 0


def test_recommend_workers_within_bounds():
    p = autotune.machine_profile()
    w = autotune.recommend_workers()
    assert 1 <= w <= max(1, p["cpu"])


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("PADRON_WORKERS", "2")
    assert autotune.effective_workers(0) == 2
    assert autotune.effective_workers(7) == 7  # explicito manda


def test_zero_means_auto():
    w = autotune.effective_workers(0)
    assert w == autotune.recommend_workers()


def test_weak_machine_gets_few_workers(monkeypatch):
    monkeypatch.setattr(autotune, "machine_profile",
                        lambda: {"cpu": 2, "ram_gb": 1.5, "free_gb": 0.8})
    assert autotune.recommend_workers() <= 2


def test_remote_sync_resumes_from_checkpoint(tmp_path):
    """remote_sync: sin red (--no-pull) reanuda y reconstruye la entrega."""
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "tools"))
    from PIL import Image
    from padron_crop.batch import run_batch
    from remote_sync import run as sync_run
    import numpy as _np

    src = tmp_path / "src"
    src.mkdir()
    arr = _np.full((200, 200, 3), 180, _np.uint8)
    arr[170:, :, :] = 5
    arr[175:195, 60:140] = 230
    Image.fromarray(arr).save(src / "b.jpg", "JPEG")
    out = tmp_path / "out"
    run_batch(src, out, workers=1, progress=False)
    rc = sync_run(["--out", str(out), "--no-pull"])
    assert rc == 0
    assert (out / "manifest_import.csv").exists()
    assert len(list((out / "entrega").iterdir())) == 1


def test_batch_accepts_workers_zero(tmp_path):
    """run_batch(workers=0) usa autotune y procesa."""
    from PIL import Image
    from padron_crop.batch import run_batch
    src = tmp_path / "src"
    src.mkdir()
    Image.new("RGB", (60, 60), (200, 200, 200)).save(src / "a.jpg", "JPEG")
    out = tmp_path / "out"
    s = run_batch(src, out, workers=0, progress=False, entrega=False,
                  checkpoint=False, state_path=out / "s.jsonl",
                  audit_path=out / "a.csv")
    assert s["noop"] == 1
    assert s["workers_used"] >= 1
