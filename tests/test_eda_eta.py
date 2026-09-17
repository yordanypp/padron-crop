"""Tests for EDA (Exploratory Data Analysis), Live ETA, and Checkpoint tracking."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
from PIL import Image

from padron_crop.batch import format_duration, run_batch
from padron_crop.cli import main
from padron_crop.eda import run_eda


def _make_dummy_image(path: Path, width: int = 100, height: int = 150,
                      bar_height: int = 0):
    arr = np.full((height, width, 3), 180, dtype=np.uint8)
    if bar_height > 0:
        arr[height - bar_height:, :] = 10
    im = Image.fromarray(arr)
    im.save(path, "JPEG", quality=90)


def test_format_duration():
    assert format_duration(30) == "00m 30s"
    assert format_duration(95) == "01m 35s"
    assert format_duration(3665) == "01h 01m 05s"


def test_eda_empty_dir(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    rep = run_eda(empty)
    assert rep.total_files == 0
    assert rep.total_mb == 0.0


def test_eda_sample_run(tmp_path):
    src = tmp_path / "dataset"
    src.mkdir()
    # 6 images with bar, 4 clean
    for i in range(6):
        _make_dummy_image(src / f"bar_{i:02d}.jpg", 300, 400, bar_height=80)
    for i in range(4):
        _make_dummy_image(src / f"clean_{i:02d}.jpg", 300, 400, bar_height=0)

    out_rep = tmp_path / "eda_out"
    rep = run_eda(src, out_dir=out_rep, sample_size=10)

    assert rep.total_files == 10
    assert rep.formats == {".jpg": 10}
    assert rep.avg_width == 300
    assert rep.avg_height == 400
    assert rep.black_bar_candidates == 6
    assert rep.clean_candidates == 4
    assert rep.disk_space_required_mb > 0
    assert (out_rep / "eda_report.json").exists()
    assert (out_rep / "eda_report.md").exists()

    data = json.loads((out_rep / "eda_report.json").read_text(encoding="utf-8"))
    assert data["total_files"] == 10
    assert data["black_bar_candidates"] == 6


def test_batch_checkpoint_saving_and_resuming(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    for i in range(6):
        _make_dummy_image(src / f"img_{i:02d}.jpg", 200, 300, bar_height=50)

    out = tmp_path / "out"
    ckpt_file = out / "custom_checkpoint.json"

    # Run first batch with limit=3
    res1 = run_batch(src, out, limit=3, checkpoint=True, checkpoint_path=ckpt_file, progress=False)
    assert res1["ok"] == 3
    assert ckpt_file.exists()

    ckpt1 = json.loads(ckpt_file.read_text(encoding="utf-8"))
    assert ckpt1["total_files"] == 3
    assert ckpt1["total_completed"] == 3
    assert "eta_formatted" in ckpt1
    assert ckpt1["status"] == "completed"

    # Resume full batch
    res2 = run_batch(src, out, resume=True, checkpoint=True, checkpoint_path=ckpt_file, progress=False)
    assert res2["skipped"] == 3
    assert res2["ok"] == 3

    ckpt2 = json.loads(ckpt_file.read_text(encoding="utf-8"))
    assert ckpt2["total_files"] == 6
    assert ckpt2["already_completed"] == 3
    assert ckpt2["total_completed"] == 6
    assert ckpt2["status"] == "completed"


def test_cli_eda_command(tmp_path, capsys):
    src = tmp_path / "photos"
    src.mkdir()
    _make_dummy_image(src / "test1.jpg", 100, 150, bar_height=30)

    # Test text summary output
    code = main(["eda", "--src", str(src)])
    assert code == 0
    captured = capsys.readouterr()
    assert "REPORTE DE AN" in captured.out
    assert "Total de im" in captured.out

    # Test json output
    code_json = main(["eda", "--src", str(src), "--json"])
    assert code_json == 0
    captured_json = capsys.readouterr()
    data = json.loads(captured_json.out)
    assert data["total_files"] == 1
