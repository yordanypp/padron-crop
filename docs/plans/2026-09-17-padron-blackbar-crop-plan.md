# Plan — padron-blackbar-crop (Fase 4 + cierre)

Fecha: 2026-09-17. Decisión de arquitectura: **A — determinista numpy/Pillow**
(elegida por el usuario en el gate de Phase 3). Sin dependencias nuevas
obligatorias. pyvips queda documentado como opt-in (`.[huge]`); el peor caso se
cubre con escaneo por bandas + downscale en detección.

## 5. Prototipo TDD — completado

- [x] `pyproject.toml` con entry point `padron-crop` (deps: numpy, Pillow)
- [x] `conftest.py` + `tests/helpers.py`: fábrica de fixtures sintéticas — barras
      por lado (A), marco 2–4 lados (B), L-shape/bloque mid-lower tipo ancla (C),
      espesor variable (D), gris oscuro no-puro (E), glifos "PRM" (F), imagen
      limpia (I), oscura uniforme (J), EXIF rotada (K), formatos
      jpg/jpeg/png/webp/bmp/tif + blob sin extensión (L), corrupto/0 bytes/no-imagen
      (M), sintética grande (N)
- [x] `src/padron_crop/geometry.py`: luma, D1 tiras por lado (runs), D2 regiones
      conexas, D3 ancla de glifos, `decide_crop()` con confianza y quarantine
- [x] Tests de geometría: casos A–J (rojo → verde)
- [x] `src/padron_crop/crop.py`: `crop_image()` único (load EXIF-safe → decide →
      QA → crop → save + sidecar; ok/noop/quarantine/failed)
- [x] Tests de core: ancla real → 960×1004; noop preserva bytes; corrupto → failed
- [x] `src/padron_crop/batch.py`: streaming, ProcessPool, `state.jsonl` resume,
      `audit.csv`, `failed/`, `quarantine/`, D0 fast-path (congela geometría con N
      patrones estables, recalibra cada K)
- [x] Tests de batch: carpeta recursiva, resume no reprocesa, origen intocable,
      fast-path `d0-cache` en patrón fijo, detector por imagen en patrón variable
- [x] `src/padron_crop/ingest/sql.py`: `PADRON_DB_URL` por env, introspección de
      columnas candidatas, error limpio sin env/DSN
- [x] `src/padron_crop/ingest/api.py`: config JSON validada, descarga streaming,
      retries/backoff; test con `http.server` local (500 → 200)
- [x] `src/padron_crop/cli.py`: `inspect|crop|batch|sql|api|qa` + `--side
      auto|left|right|top|bottom|all` (contrato del brief) + `python -m padron_crop`
- [x] Tests CLI: smoke de inspect y crop sobre copia

## 6. Verify — completado

- [x] `pytest` verde: **43 passed** (`python -m pytest -q`)
- [x] Recorte real de la ancla a `out/sample/` con sidecar JSON:
      `status=ok`, `crop_box_xywh=[0,0,960,1004]`, `method=projection+glyphs`,
      `confidence=0.903`; origen intacto (87 882 bytes)
- [x] `out/benchmark.md`: imagen única de 80 MP y lote de 1000 imágenes, con
      tiempo y RSS pico medidos (psapi en Windows; `n/a` en otros SO)
- [x] Checklist de aceptación del brief verificada en el resumen final

## 7. Endurecimiento post-plan (pedido del usuario: pulir/optimizar/portabilidad)

- [x] **Bug de QA en el fast-path**: `apply_frozen()` se saltaba los gates de
      seguridad; una imagen oscura uniforme recibía geometría congelada y se
      recortaba. Se añadieron los gates de uniforme-oscuro y de área-eliminada al
      fast-path. Evidencia: el lote pasó de `quarantine=25` (incorrecto) a
      `quarantine=50` (correcto) sobre 50 casos oscuros.
- [x] **Chunking de calibración**: durante la calibración se procesaba de 1 en 1
      (un solo worker activo). Ahora calibra `FREEZE_N` en paralelo.
- [x] **`bright_components`**: BFS en Python sobre píxeles → run-length +
      union-find vectorizado. `decide_crop` de **1450 ms → ~120 ms** por imagen de
      1.2 MP (≈12×); suite de tests de 34 s → ~5 s.
- [x] **Lote grande**: 1000 imágenes mixtas, 4 workers → **372 s → 46 s (21.6 img/s)**,
      resumen correcto `ok=800, noop=100, quarantine=50, failed=50`.
- [x] Peor caso single 80 MP: **5.16 s, 799 MB RSS pico** (≈17 bytes/píxel).
- [x] **Portabilidad**: `requirements.txt`, `README.md` (Windows/macOS/Linux),
      `.gitignore`, `.env.example`, extras opcionales en `pyproject.toml`,
      `python -m padron_crop` además del console script. Nada hardcodeado a esta PC.
- [x] **Optimización de tests** (sin quitar cobertura: 43 → 68 tests): memoización
      del encode JPEG por buffer idéntico en `tests/helpers.py`, `sources_untouched`
      a 1 worker (el multiproceso sigue cubierto por el test recursivo), y
      `FastHTTPServer` sin `socket.getfqdn()` (evita el parón de cientos de ms en
      Windows). Suite: ~5-7 s para 68 tests.

### 8. Auditoría del brief (punto por punto, 2026-09-17)

- [x] **`--dry-run`** en `crop`/`batch` (detecta y reporta, no escribe nada)
- [x] **Techo de RAM configurable**: `PADRON_MAX_PIXELS` + `--max-mp N`
- [x] **Conector D4 de IA** implementado (`vision.py`) con schema estricto,
      timeout/retries/backoff, guard de copia de prueba y veto-only
- [x] **`sql --query-file`** realmente usado (statement) y BLOBs crudos aislados
      en `out/_blobs/` para no mezclar con la salida recortada
- [x] **Caso N (huge)** añadido como test (~6 MP); el peor caso de 80 MP queda en
      `out/benchmark.md` con mediana de 3 corridas
- [x] **Benchmark con repeticiones** (mediana + mejor) porque un solo número es
      ruido de carga de máquina
- [x] Verificación de que **una foto real nunca sale a la red**: `resolve_with_vision`
      propaga `src` y `assert_test_copy` se ejecuta antes de construir el request
- [ ] (Opcional, requiere permiso) prueba de install limpio en venv aislado.

### 9. Endurecimiento para producción y pruebas a escala (ronda 2)

- [x] **E/S atómica**: `safeio.atomic_path` / `atomic_write_*` (tmp + fsync +
      `os.replace`); el sidecar, la imagen, el state y el audit nunca quedan a
      medias. Test: `test_atomic_write_leaves_no_partial_file`.
- [x] **Resume a prueba de crash**: `read_jsonl_tolerant` ignora la última línea
      truncada. Test: `test_state_with_torn_last_line_still_resumes`.
- [x] **Guardia de disco**: preflight + chequeo periódico; aborta limpio (exit 3).
      Tests: `test_require_space_raises_when_reserve_is_impossible`,
      `test_disk_check_mid_run_stops_gracefully`.
- [x] **Ctrl-C / SIGTERM**: parada cooperativa por chunk, ledgers volcados, exit
      130 y `--resume` continúa. Test: `test_stop_flag_stops_before_any_work`.
- [x] **Multiprocessing inseguro** (stdin/`-c`/REPL en Windows): antes moría con
      `BrokenProcessPool`; ahora degrada a 1 worker con aviso. Tests:
      `test_workers_downgrade_when_main_is_not_importable`.
- [x] **Red**: timeouts, backoff con jitter, `Retry-After`, solo estados
      transitorios, descargas reanudables por Range (`.part`), ítem malo
      aislado. Tests: `test_stream_download_resumes_from_part_file`,
      `test_backoff_honours_retry_after_and_caps`.
- [x] **DB**: `pool_pre_ping`, reintento que nunca repite filas, solo
      `SELECT`/`WITH`, y quoting por dialecto (el `SELECT "col"` anterior era
      inválido en MySQL). Tests: `test_sql_rejects_non_read_only_statements`.
- [x] **Luz**: normalización adaptativa solo para fotos subexpuestas (una foto
      limpia NO se reescala: eso fue una regresión que detecté y cerré con
      test). Tests: `test_underexposed_photo_bar_still_detected`,
      `test_normal_photo_is_not_rescaled`.
- [x] **Tunables por entorno** (`PADRON_*`): chunk, freeze, tol, disco, SQL,
      API, normalización, techo de píxeles.
- [x] **Pruebas a escala reales**: `tools/make_lot.py` (lote mixto desde la foto
      real), `tools/loadtest.py` (interrupción + resume + RSS del árbol),
      `tools/scale_test.py` (escalado por workers) → `out/loadtest.md`:
      **2500 archivos / 0.98 GB**, 9.1 files/s, 267 MB de árbol, resume exacto,
      0 temporales huérfanos.
- [x] **Instalación limpia probada**: venv nuevo → `pip install -e ".[dev]"` →
      91 tests verdes y recorte del ancla idéntico.
- [x] **SQL real (Navicat)**: tabla temporal `padron_crop_test_blobs` en
      `bd_pruebas_pep`, 240 filas de bytes reales por la ruta real del CLI
      (ok=180 noop=40 quarantine=20), tabla temporal eliminada → `out/sqltest.md`.

## Fuera de alcance (explícito)

pyvips/OpenCV/OCR instalados (opt-in documentado), auth/UI/cloud, escritura a DB,
commits (salvo pedido), `--allow-remote-ai` sobre fotos reales.
