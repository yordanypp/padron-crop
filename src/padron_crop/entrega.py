"""Delivery pack: carpeta entrega/ + manifest_import.csv ordenado.

Al terminar un batch o un proceso Navicat, genera:
- ``entrega/``: solo fotos limpias, copiadas con nombre estable y ordenado
  ``<orden>_<id>_crop.<ext>`` (ej: ``000001_402-1111111-1_crop.jpg``).
- ``manifest_import.csv``: ``orden,id,archivo_limpio,estado,origen`` ordenado
  por id, listo para Excel o para reimportar a Navicat.

El ``id`` sale del sidecar (campo ``delivery_id``) cuando el flujo Navicat lo
conoce (columna cedula/id elegida en el momento); si no, se usa el stem del
archivo original. Nunca falla: si algo falta, usa el nombre disponible.
"""
from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path


def _safe_id(raw: str) -> str:
    """Limpia un id para usarlo como nombre de archivo (conserva guiones)."""
    s = (raw or "").strip()
    s = re.sub(r'[\\/*?:"<>|]', "_", s)
    s = re.sub(r"\s+", "_", s)
    return s or "sin_id"


def _delivery_id(rec: dict) -> str:
    """Id de entrega: delivery_id del sidecar, o stem del origen."""
    did = rec.get("delivery_id")
    if did:
        return _safe_id(str(did))
    src = rec.get("source", "")
    return _safe_id(Path(src).stem if src else "sin_id")


def _resolve_quarantine_image(out_dir: Path, rec: dict) -> Path | None:
    """Localiza la imagen de un registro en quarantine/ por stem del origen."""
    stem = _safe_id(Path(rec.get("source", "")).stem or "")
    qdir = Path(out_dir) / "quarantine"
    if stem and qdir.is_dir():
        for cand in sorted(qdir.iterdir()):
            if cand.is_file() and cand.stem == stem and cand.suffix.lower() != ".json":
                return cand
    out_p = rec.get("out_path", "")
    return Path(out_p) if out_p else None


def build_delivery(out_dir: Path, records: list[dict] | None = None) -> dict:
    """Construye entrega/ + manifest_import.csv dentro de out_dir.

    Si ``records`` es None, lee los sidecars JSON del directorio (como qa).
    Solo incluye registros ok/noop (fotos utilizables). Quarantine/failed
    van al manifest con su estado pero sin copiar archivo.
    """
    import json

    out_dir = Path(out_dir)
    if records is None:
        records = []
        ignored = {"checkpoint.json", "checkpoint.jsonl", "eda_report.json",
                   "inspect.json", "row_probe.json"}
        for sc in sorted(out_dir.rglob("*.json")):
            if sc.name.startswith(".") or sc.name in ignored:
                continue
            try:
                rec = json.loads(sc.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(rec, dict) and "source" in rec:
                records.append(rec)

    usable = [r for r in records if r.get("status") in ("ok", "noop", "quarantine")]
    usable.sort(key=lambda r: _delivery_id(r).lower())

    entrega = out_dir / "entrega"
    entrega.mkdir(parents=True, exist_ok=True)

    manifest_path = out_dir / "manifest_import.csv"
    rows = []
    for i, rec in enumerate(usable, 1):
        did = _delivery_id(rec)
        st = rec.get("status", "")
        if st == "quarantine":
            # quarantine: la imagen vive en out/quarantine/<stem>.ext (el sidecar
            # out_path puede apuntar a otro nombre); resolver por stem.
            src_file = _resolve_quarantine_image(out_dir, rec)
        else:
            # ok: out_path es el crop; noop: out_path es el propio origen
            out_p = rec.get("out_path", "")
            src_file = Path(out_p) if out_p else None
        ext = src_file.suffix.lower() if src_file and src_file.suffix else ".jpg"
        dest_name = f"{i:06d}_{did}_crop{ext}"
        dest = entrega / dest_name
        copied = False
        if src_file and src_file.exists():
            try:
                if src_file.resolve() != dest.resolve():
                    shutil.copy2(src_file, dest)
                copied = True
            except OSError:
                copied = False
        rows.append({
            "orden": i,
            "id": did,
            "archivo_limpio": dest_name if copied else "",
            "estado": rec.get("status", ""),
            "origen": rec.get("source", ""),
        })

    # failed también al manifest (sin archivo copiado; quarantine ya va arriba)
    rest = [r for r in records if r.get("status") not in ("ok", "noop", "quarantine")]
    rest.sort(key=lambda r: _delivery_id(r).lower())
    for r in rest:
        rows.append({
            "orden": "",
            "id": _delivery_id(r),
            "archivo_limpio": "",
            "estado": r.get("status", ""),
            "origen": r.get("source", ""),
        })

    with open(manifest_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["orden", "id", "archivo_limpio", "estado", "origen"])
        w.writeheader()
        w.writerows(rows)

    return {
        "entrega_dir": str(entrega),
        "manifest": str(manifest_path),
        "fotos_entregadas": len([r for r in rows if r["archivo_limpio"]]),
        "total_manifest": len(rows),
    }
