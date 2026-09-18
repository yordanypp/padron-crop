"""Navicat integration helper: process database data without direct DB credentials.

Supports:
1. Processing photos from a Navicat CSV/JSON export containing Base64, hex, or URLs.
2. Processing a folder of raw files exported via Navicat's Export Wizard.
3. Parsing SQL dump files containing INSERT statements with hex or BLOB data.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import re
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from padron_crop import safeio
from padron_crop.crop import crop_image
from padron_crop.gallery import build_gallery
from padron_crop.ingest.sql import decode_db_image


def process_navicat_csv(csv_path: Path, out_dir: Path, image_column: str,
                        id_column: str | None = None, deskew: bool = False,
                        face_safety: bool = True, aspect_ratio: str | None = None,
                        quality: int = 95, limit: int | None = None) -> dict:
    """Process photos directly from a CSV exported by Navicat.
    
    The column can contain:
    - Base64 strings (with or without data:image prefix)
    - Hex strings (0x...)
    - Local file paths
    """
    csv_path = Path(csv_path)
    out_dir = Path(out_dir)

    # Si el usuario ingresó una carpeta en vez de un archivo CSV
    if csv_path.is_dir():
        csv_candidates = sorted(list(csv_path.glob("*.csv")))
        if csv_candidates:
            print(f"[INFO] Carpeta detectada. Usando archivo CSV encontrado: {csv_candidates[0]}")
            csv_path = csv_candidates[0]
        else:
            print(f"[INFO] Carpeta detectada con imágenes directas: {csv_path}")
            print(f"[INFO] Procesando fotos con motor masivo...")
            from padron_crop.batch import run_batch
            return run_batch(
                csv_path,
                out_dir,
                workers=4,
                deskew=deskew,
                face_safety=face_safety,
                aspect_ratio=aspect_ratio,
                quality=quality,
                limit=limit,
            )

    out_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = out_dir / "_temp_navicat"
    temp_dir.mkdir(parents=True, exist_ok=True)

    summary = {"total": 0, "ok": 0, "quarantine": 0, "failed": 0, "noop": 0}

    # Elevate CSV field size limit safely across 32/64-bit platforms (supports huge Base64)
    max_limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(max_limit)
            break
        except OverflowError:
            max_limit = int(max_limit / 10)

    with open(csv_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
        # Sniff delimiter (comma, semicolon, tab, pipe)
        sample = f.read(8192)
        f.seek(0)
        first_line = sample.splitlines()[0] if sample else ""
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        except Exception:
            if ";" in first_line and "," not in first_line:
                dialect = csv.excel
                dialect.delimiter = ";"
            elif "\t" in first_line:
                dialect = csv.excel_tab
            else:
                dialect = csv.excel

        reader = csv.DictReader(f, dialect=dialect)
        if not reader.fieldnames:
            print(f"[ERROR] El archivo CSV {csv_path} está vacío.", file=sys.stderr)
            return summary

        # Find best matching image column if not exact
        img_col = image_column
        if img_col not in reader.fieldnames:
            candidates = [c for c in reader.fieldnames if img_col.lower() in c.lower()]
            if candidates:
                img_col = candidates[0]
            else:
                print(f"[ERROR] Columna '{image_column}' no encontrada en el CSV. Disponibles: {reader.fieldnames}", file=sys.stderr)
                return summary

        print(f"[INFO] Leyendo CSV: usando columna de imagen '{img_col}'")
        if id_column and id_column in reader.fieldnames:
            print(f"[INFO] Usando columna ID para nombrar archivos: '{id_column}'")

        count = 0
        for row in reader:
            if limit and count >= limit:
                break
            raw_val = row.get(img_col)
            if not raw_val:
                continue

            # Handle unquoted CSV where data:image/...;base64, was split by comma.
            # The base64 payload then lands in the NEXT named column(s)
            # (misaligned by one), while row[None] holds only the true surplus
            # (trailing columns shifted). Recovery: rebuild the payload as
            #   raw_val + ',' + <values of all columns after img_col> + <b64-like extras>
            # and stop before the first non-base64 fragment (date, id, name...).
            # If nothing base64-like is found, leave raw_val untouched and let
            # the row fail loudly instead of fabricating bytes.
            if "data:image/" in raw_val and ";base64" in raw_val:
                try:
                    cols_after = reader.fieldnames[reader.fieldnames.index(img_col) + 1:]
                except ValueError:
                    cols_after = []
                shifted = [row.get(c, "") or "" for c in cols_after]
                extras = list(row.get(None) or [])
                frags: list[str] = []
                for frag in shifted + extras:
                    frag = frag if isinstance(frag, str) else str(frag)
                    s = frag.strip()
                    if s == "":
                        continue
                    if len(s) >= 16 and re.fullmatch(r"[A-Za-z0-9+/=_-]+", s):
                        frags.append(s)
                    else:
                        break  # first real trailing column (date, id...) -> stop
                if frags:
                    raw_val = raw_val + "," + ",".join(frags)

            count += 1
            row_id = str(row.get(id_column, f"rec_{count:07d}")).strip() if id_column else f"rec_{count:07d}"
            # Clean safe filename
            safe_id = re.sub(r'[\\/*?:"<>|]', "_", row_id)

            raw_bytes, file_path, ext = decode_db_image(raw_val)
            target_p = None
            temp_written = False

            if file_path is not None:
                target_p = file_path
            elif raw_bytes is not None:
                target_p = temp_dir / f"{safe_id}{ext}"
                target_p.write_bytes(raw_bytes)
                temp_written = True

            if target_p is None:
                summary["failed"] += 1
                continue

            rec = crop_image(
                target_p,
                out_dir,
                out_name=f"{safe_id}_crop{ext}",
                deskew=deskew,
                face_safety=face_safety,
                aspect_ratio=aspect_ratio,
                quality=quality,
            )
            st = rec.get("status", "failed")
            summary[st] = summary.get(st, 0) + 1
            summary["total"] += 1

            if temp_written:
                try:
                    target_p.unlink(missing_ok=True)
                except OSError:
                    pass

    try:
        temp_dir.rmdir()
    except OSError:
        pass

    # Build gallery
    build_gallery(out_dir)
    return summary


def main():
    p = argparse.ArgumentParser(description="Procesador para exportaciones de Navicat sin contraseña directa")
    sub = p.add_subparsers(dest="mode", required=True)

    sp_csv = sub.add_parser("csv", help="Procesa un CSV exportado desde Navicat")
    sp_csv.add_argument("--csv", required=True, help="Ruta al archivo CSV")
    sp_csv.add_argument("--out", required=True, help="Carpeta de salida")
    sp_csv.add_argument("--col", default="foto", help="Nombre de la columna con la imagen/base64/ruta (default: foto)")
    sp_csv.add_argument("--id-col", default=None, help="Columna para nombrar la foto (ej: cedula, id)")
    sp_csv.add_argument("--deskew", action="store_true", help="Corregir inclinación")
    sp_csv.add_argument("--no-face-safety", action="store_true", help="Desactivar protección facial")
    sp_csv.add_argument("--aspect-ratio", default=None, help="Formato de proporción opcional (ej: 3:4, 1:1, 4:5)")
    sp_csv.add_argument("--quality", type=int, default=95, help="Calidad JPEG (1-100, default: 95)")
    sp_csv.add_argument("--limit", type=int, default=None, help="Límite de registros")

    args = p.parse_args()
    if args.mode == "csv":
        res = process_navicat_csv(
            Path(args.csv),
            Path(args.out),
            image_column=args.col,
            id_column=args.id_col,
            deskew=args.deskew,
            face_safety=not args.no_face_safety,
            aspect_ratio=args.aspect_ratio,
            quality=args.quality,
            limit=args.limit,
        )
        print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
