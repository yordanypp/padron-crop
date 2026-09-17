"""Exploratory Data Analysis (EDA) & pre-flight profiling for padrón image datasets.

Analyzes a dataset before batch processing:
- File formats, sizes, and total disk volume
- Image resolution distribution and aspect ratios
- Preliminary black bar prevalence & noise estimation
- Hardware throughput & estimated completion time (ETA) projection
- Generates both console summary and markdown/JSON reports
"""
from __future__ import annotations

import json
import math
import os
import random
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from padron_crop import geometry, opencv_ext
from padron_crop.crop import load_luma_ready
from padron_crop.ingest.local import iter_local


@dataclass
class EdaReport:
    total_files: int
    total_bytes: int
    total_mb: float
    total_gb: float
    formats: dict[str, int]
    sampled_count: int
    resolutions: dict[str, int]
    avg_width: int
    avg_height: int
    aspect_ratios: dict[str, int]
    black_bar_candidates: int
    clean_candidates: int
    quarantine_risks: int
    corrupt_count: int
    estimated_seconds_1_worker: float
    estimated_seconds_4_workers: float
    estimated_seconds_8_workers: float
    recommended_workers: int
    disk_space_required_mb: float


def run_eda(src_dir: Path, out_dir: Path | None = None,
            sample_size: int = 100) -> EdaReport:
    """Run an automated exploratory analysis on the source image dataset."""
    src_dir = Path(src_dir)
    files = list(iter_local(src_dir))
    total_files = len(files)

    if total_files == 0:
        return EdaReport(
            total_files=0, total_bytes=0, total_mb=0.0, total_gb=0.0,
            formats={}, sampled_count=0, resolutions={}, avg_width=0,
            avg_height=0, aspect_ratios={}, black_bar_candidates=0,
            clean_candidates=0, quarantine_risks=0, corrupt_count=0,
            estimated_seconds_1_worker=0.0, estimated_seconds_4_workers=0.0,
            estimated_seconds_8_workers=0.0, recommended_workers=1,
            disk_space_required_mb=0.0
        )

    total_bytes = 0
    formats_counter = Counter()

    for p in files:
        ext = p.suffix.lower() or ".unknown"
        formats_counter[ext] += 1
        try:
            total_bytes += p.stat().st_size
        except OSError:
            pass

    total_mb = round(total_bytes / (1024 * 1024), 2)
    total_gb = round(total_bytes / (1024 * 1024 * 1024), 3)

    # Sample selection
    if total_files <= sample_size:
        sample_files = files
    else:
        # Uniform sampling across dataset
        random.seed(42)
        sample_files = random.sample(files, sample_size)

    sampled_count = len(sample_files)
    widths, heights = [], []
    resolutions_counter = Counter()
    aspect_counter = Counter()
    black_bar_count = 0
    clean_count = 0
    quarantine_count = 0
    corrupt_count = 0

    benchmark_times = []

    for p in sample_files:
        t0 = time.perf_counter()
        im = None
        try:
            im, arr = load_luma_ready(p)
            elapsed = time.perf_counter() - t0
            benchmark_times.append(elapsed)

            h, w = arr.shape[:2]
            widths.append(w)
            heights.append(h)
            resolutions_counter[f"{w}x{h}"] += 1

            # Aspect ratio classification
            gcd = math.gcd(w, h)
            rw, rh = w // gcd, h // gcd
            if abs(w / h - 0.75) < 0.05:
                ratio_name = "3:4 (Retrato Cédula)"
            elif abs(w / h - 1.0) < 0.05:
                ratio_name = "1:1 (Cuadrado)"
            elif abs(w / h - 0.8) < 0.05:
                ratio_name = "4:5 (Foto Estudio)"
            elif abs(w / h - 1.33) < 0.05:
                ratio_name = "4:3 (Paisaje)"
            else:
                ratio_name = f"{w}:{h} (Otro)"
            aspect_counter[ratio_name] += 1

            # Quick preliminary detection
            det = geometry.decide_crop(arr)
            if det.status == "crop":
                black_bar_count += 1
            elif det.status == "noop":
                clean_count += 1
            elif det.status == "quarantine":
                quarantine_count += 1

        except Exception:
            corrupt_count += 1
        finally:
            if im is not None:
                try:
                    im.close()
                except Exception:
                    pass

    avg_w = int(sum(widths) / len(widths)) if widths else 0
    avg_h = int(sum(heights) / len(heights)) if heights else 0

    # Project times based on sample average
    avg_img_time = (sum(benchmark_times) / len(benchmark_times)) if benchmark_times else 0.05
    est_sec_1 = round(total_files * avg_img_time, 1)
    # Multiprocessing scaling efficiency (~3.4x on 4 workers, ~5.8x on 8 workers)
    est_sec_4 = round(est_sec_1 / 3.4, 1)
    est_sec_8 = round(est_sec_1 / 5.8, 1)

    # Detect CPU cores for recommendation
    cpu_cores = os.cpu_count() or 4
    recommended_workers = min(max(1, cpu_cores - 1), 8)

    # Estimate required output space (roughly 85% of input size with JPEG quality 95)
    disk_space_required_mb = round(total_mb * 0.90, 2)

    report = EdaReport(
        total_files=total_files,
        total_bytes=total_bytes,
        total_mb=total_mb,
        total_gb=total_gb,
        formats=dict(formats_counter),
        sampled_count=sampled_count,
        resolutions=dict(resolutions_counter.most_common(5)),
        avg_width=avg_w,
        avg_height=avg_h,
        aspect_ratios=dict(aspect_counter),
        black_bar_candidates=black_bar_count,
        clean_candidates=clean_count,
        quarantine_risks=quarantine_count,
        corrupt_count=corrupt_count,
        estimated_seconds_1_worker=est_sec_1,
        estimated_seconds_4_workers=est_sec_4,
        estimated_seconds_8_workers=est_sec_8,
        recommended_workers=recommended_workers,
        disk_space_required_mb=disk_space_required_mb,
    )

    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "eda_report.json").write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
        _save_eda_markdown(report, out_dir / "eda_report.md", src_dir)

    return report


def format_duration(seconds: float) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    s = int(round(seconds))
    hrs = s // 3600
    mins = (s % 3600) // 60
    secs = s % 60
    if hrs > 0:
        return f"{hrs:02d}h {mins:02d}m {secs:02d}s"
    return f"{mins:02d}m {secs:02d}s"


def _save_eda_markdown(r: EdaReport, target: Path, src_dir: Path):
    md = f"""# Reporte de Análisis Exploratorio de Datos (EDA)

**Carpeta analizada:** `{src_dir}`  
**Fecha:** `{time.strftime('%Y-%m-%d %H:%M:%S')}`  

## 1. Volumen y Archivos
* **Total de imágenes:** {r.total_files:,}
* **Tamaño total en disco:** {r.total_mb:,} MB ({r.total_gb} GB)
* **Espacio libre requerido en destino:** ~{r.disk_space_required_mb:,} MB
* **Formatos encontrados:** {r.formats}

## 2. Geometría y Resoluciones (Muestra de {r.sampled_count} fotos)
* **Resolución promedio:** {r.avg_width} x {r.avg_height} px
* **Top Resoluciones:** {r.resolutions}
* **Relaciones de aspecto:** {r.aspect_ratios}

## 3. Diagnóstico Preliminar de Barras
* **Con barra negra / PRM (candidatas a corte):** {r.black_bar_candidates} / {r.sampled_count} ({round(r.black_bar_candidates / max(1, r.sampled_count) * 100, 1)}%)
* **Ya limpias (noop):** {r.clean_candidates} / {r.sampled_count}
* **Riesgos a cuarentena (oscuros / borde cara):** {r.quarantine_risks} / {r.sampled_count}
* **Archivos corruptos / ilegibles:** {r.corrupt_count}

## 4. Tiempos Estimados de Procesamiento (ETA)
* **1 núcleo (secuencial):** {format_duration(r.estimated_seconds_1_worker)}
* **4 núcleos (paralelo estándar):** {format_duration(r.estimated_seconds_4_workers)}
* **8 núcleos (alta potencia):** {format_duration(r.estimated_seconds_8_workers)}
* **Workers recomendados para este equipo:** `{r.recommended_workers}`
"""
    target.write_text(md, encoding="utf-8")


def print_eda_summary(r: EdaReport, src_dir: Path):
    """Print an eye-friendly, structured summary to terminal."""
    pct_bar = round(r.black_bar_candidates / max(1, r.sampled_count) * 100, 1)
    pct_clean = round(r.clean_candidates / max(1, r.sampled_count) * 100, 1)

    print("\n" + "=" * 65)
    print("      REPORTE DE ANÁLISIS EXPLORATORIO (EDA) DEL PADRÓN")
    print("=" * 65)
    print(f" Directorio analizado : {src_dir}")
    print(f" Total de imágenes    : {r.total_files:,} archivos")
    print(f" Volumen en disco     : {r.total_mb:,} MB ({r.total_gb} GB)")
    print(f" Formatos de archivo  : {dict(r.formats)}")
    print("-" * 65)
    print(f" Muestra analizada    : {r.sampled_count} fotos representativas")
    print(f" Resolución promedio  : {r.avg_width} x {r.avg_height} px")
    print(f" Aspect ratios        : {dict(r.aspect_ratios)}")
    print(f" - Fotos con barra PRM: {r.black_bar_candidates} ({pct_bar}% de la muestra)")
    print(f" - Fotos ya limpias   : {r.clean_candidates} ({pct_clean}% de la muestra)")
    print(f" - Fotos a cuarentena : {r.quarantine_risks}")
    print(f" - Archivos corruptos : {r.corrupt_count}")
    print("-" * 65)
    print(" PROYECCIÓN DE TIEMPO ESTIMADO (ETA):")
    print(f" - Con 1 worker (mono-hilo) : ~{format_duration(r.estimated_seconds_1_worker)}")
    print(f" - Con 4 workers (recomendado) : ~{format_duration(r.estimated_seconds_4_workers)}")
    print(f" - Con 8 workers (servidor) : ~{format_duration(r.estimated_seconds_8_workers)}")
    print(f" Espacio libre sugerido en salida : ~{r.disk_space_required_mb:,.0f} MB")
    print("=" * 65 + "\n")
