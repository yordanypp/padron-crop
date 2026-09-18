"""Rojo: entrega/ no debe acumular basura de corridas previas."""
from pathlib import Path
import shutil


def _rec(src, did, st="ok"):
    return {"source": str(src), "status": st, "out_path": str(src)}


def test_entrega_sweeps_stale_files(tmp_path):
    import sys
    sys.path.insert(0, str(Path(r"C:\Users\daryf\Downloads\proyecto padron quitar negros\src")))
    from padron_crop.entrega import build_delivery
    from PIL import Image
    out = tmp_path / "out"
    out.mkdir()
    a = out / "a.jpg"
    Image.new("RGB", (20, 20), (10, 10, 10)).save(a)
    d1 = build_delivery(out, [_rec(a, "AAA")])
    assert d1["fotos_entregadas"] == 1
    # segunda corrida con OTRO set: el archivo viejo debe desaparecer
    (out / "a.jpg").unlink()
    b = out / "b.jpg"
    Image.new("RGB", (20, 20), (10, 10, 10)).save(b)
    d2 = build_delivery(out, [_rec(b, "BBB")])
    names = sorted(p.name for p in (out / "entrega").iterdir())
    assert d2["fotos_entregadas"] == 1, names
    assert names == ["000001_b_crop.jpg"], names


def test_entrega_dedupes_records_by_source(tmp_path):
    import sys
    sys.path.insert(0, str(Path(r"C:\Users\daryf\Downloads\proyecto padron quitar negros\src")))
    from padron_crop.entrega import build_delivery
    from PIL import Image
    out = tmp_path / "out"
    out.mkdir()
    a = out / "a.jpg"
    Image.new("RGB", (20, 20), (10, 10, 10)).save(a)
    d = build_delivery(out, [_rec(a, "AAA"), _rec(a, "AAA")])
    assert d["total_manifest"] == 1
