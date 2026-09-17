# Spec — padron-blackbar-crop (diseño aprobable)

Fecha: 2026-09-17. Estado: **pendiente de aprobación (gate de arquitectura)**.
Insumos: `docs/research/sample-geometry.md` (geometría medida del ancla), `docs/research/REPORT.md` (research citado).

## 1. Objetivo

Quitar de fotos de padrón el bloque negro con texto "PRM" (y barras negras equivalentes) **recortando** (nunca pintando/rellenando/generando), a escala masiva, preservando la región útil (cara/foto), con 3 ingestas (`local`, `sql`, `api`) que comparten **un único núcleo** `crop_image()`.

## 2. Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│  INGESTA (una de tres, misma interfaz iteradora de items)       │
│  local: os.walk recursivo    sql: SQLAlchemy stream (RO)        │
│  api: httpx streaming + paginación + backoff                     │
└──────────────┬──────────────────────────────────────────────────┘
               │  bytes + source_id (streaming, lote a lote)
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  NÚCLEO crop_image(bytes|path) — único, compartido              │
│  1. load (Pillow + EXIF transpose; pyvips si >30MP)             │
│  2. cascada D0→D3 (D4 off) → crop_box + método + confianza      │
│  3. QA de seguridad (cara/brillo) → ok | quarantine             │
│  4. crop + save + sidecar JSON (nunca sobre el origen)          │
└──────────────┬──────────────────────────────────────────────────┘
               ▼
   out/<run>/…img + sidecar.json + audit.csv
   cola quarantine/ (desacuerdo u oscura) y failed/ (corruptas)
   estado: state.jsonl (resume/idempotencia, sha256 como clave)
```

Paralelismo: `ProcessPoolExecutor` por lotes, workers limitados por techo de RAM (`--max-workers`, `--ram-ceiling-mb`). Cada worker procesa item completo y libera; sin cachés de píxeles.

## 3. Cascada de detectores (orden y confianza)

| Nivel | Qué hace | Confianza base | Costo |
|---|---|---|---|
| **D0** fast-path | Si ≥N muestras del lote coinciden en lado(es)+espesor relativo con stddev bajo → geometría congelada; aplicar directa. Recalibrar cada K imágenes o si QA falla | alta (con lote homogéneo) | ~0 |
| **D1** proyección | Fracción oscura estricta por fila/columna desde cada borde; líneas candidatas = runs consecutivos por encima de umbral | media | O(banda) |
| **D2** máscara de borde | Regiones conexas oscuras (grid downscale) que tocan bordes; bbox + fill | media-alta | O(grid) |
| **D3** ancla de glifos | Píxeles claros (luma>0.6) pequeños dentro de zona oscura → tope del bloque; OCR opcional solo para leer el texto, no para posicionar | alta cuando existe | bajo |
| **D4** IA remota | Off por defecto (`--allow-remote-ai`, solo copias de prueba). Nunca sustituye D0–D2 | — | red |

**Decisión:** el crop final es la **intersección/min de las líneas propuestas** por los detectores que acuerdan (por lado), − margen de seguridad. Reglas de aceptación por lado: fill oscuro alto + toca borde + sin píxeles brillantes significativos dentro + D1 y D2 coinciden (tolerancia configurable). Desacuerdo > tolerancia → `quarantine`, no adivinar. Caso especial validado en el ancla: si D3 encuentra glifos y D1 no detecta barra de borde, la línea es `min(tope_glifos, inicio_negro_sólido) − margen`.

**No-op:** si ningún lado califica → `status=noop` (copia byte-identical o registro sin reescribir; dimensiones/hash iguales).
**Oscura uniforme:** media oscura + varianza baja en todo el marco → `quarantine`.

## 4. Ingestas

- **local**: `os.walk` recursivo, extensiones `jpg/jpeg/png/webp/bmp/tif` + sin extensión (sniff magic bytes), `--limit`, `--resume`, `--workers`.
- **sql**: `PADRON_DB_URL` (env). Autodetección de tablas/columnas candidatas (blob/longblob/mediumblob/bytea/image/foto/path) vía introspección; **lista y pide confirmación antes de full scan**. Streaming: `yield_per`/`stream_results` (o SSCursor). Read-only. Soporta BLOB y columnas de ruta.
- **api**: archivo de config YAML/JSON (URL base, endpoint list, cursor/paginación, headers extra no secretos). Token por env `PADRON_API_TOKEN`. GET/POST streaming a disco temporal, retries exponenciales + jitter, checkpoint por página. Contrato documentado en `docs/specs/api-contract.md` (stub con tests).

## 5. Peor caso (masividad)

- Decenas de MP / cientos de MB: backend pyvips (`pip install "pyvips[binary]"`) cuando `pixels > 30 MP` o `bytes > 100 MB`; Pillow para el resto. Detección sobre bandas de borde + franja central y grid downscale (nunca decode completo dos veces).
- Millones de archivos: iteración perezosa por lotes, `state.jsonl` append-only, techo RAM configurable, reintentos desde `failed/`.
- Idempotencia: nombre de salida determinista por `sha256`/source_id; re-corrida no duplica trabajo.
- **Benchmark** en `out/benchmark.md`: tiempos/RSS con imagen sintética grande (p. ej. 12000×16000 ≈ 192 MP) y con lote de 500 synthetic JPEGs.

## 6. QA y contratos de salida

- Sidecar por foto: `{source, sha256, orig_wh, crop_box_xywh, sides, method, confidence, face_safety_ok, elapsed_ms, status}`; `status ∈ {ok, noop, quarantine, failed}`.
- `audit.csv` acumulado por corrida; `failed/` y `quarantine/` con motivo en el sidecar.
- `face_safety_ok`: false si la zona a recortar contiene brillo/piel significativa → quarantine.
- CLI: `padron-crop inspect|crop|batch|sql|api|qa` (contrato del brief, sin cambios).

## 7. Riesgos PII y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Fotos reales a APIs externas | D4 off; `--allow-remote-ai` solo con copias de prueba; sin flag el conector no se instancia |
| Secretos en repo | Solo env vars; nunca en config ni logs |
| Escritura accidental sobre origen | Salida siempre `out/`; origen read-only; test lo verifica |
| DB de escritura | Usuario RO esperado; el código nunca INSERT/UPDATE |

## 8. Enfoques considerados (trade-offs)

### A. Determinista numpy/Pillow (proyección + máscara de borde) — **RECOMENDADO**
- Pros: cero dependencias nuevas (ya instaladas), auditable píxel a píxel, determinista, rápido en <30 MP, la cascada D1+D2+D3 ya resolvió el ancla real en Phase 0.
- Contras: para >30 MP depende de escaneo por bandas (o pyvips opcional); CC casero en grid es aproximado (suficiente para barras grandes).
- Riesgo: falso positivo en contenido oscuro → cubierto por reglas de aceptación + quarantine.

### B. OpenCV-centric (connectedComponents nativo + floodfill)
- Pros: CC exacto y rápido; ecosistema de visión.
- Contras: dependencia nueva grande no instalada (requiere aprobación); benchmark libvips muestra ~8× RAM de libvips a 100 MP; no aporta determinismo extra.
- Cuándo reconsiderar: si D2-grid demostrara insuficiencia en el lote real.

### C. IA-first (OCR/vision para todo)
- Pros: robusto a variabilidad extrema.
- Contras: no determinista, costo, latencia, riesgo PII, dependencia pesada (EasyOCR≈PyTorch); el ancla ya se resolvió sin IA.
- Rol final: D4 opcional apagado; D3 (glifos claros) sin OCR ya posiciona el texto.

**Recomendación: A**, con pyvips como engine opcional para huge y D3 sin OCR. B queda como plan B documentado; C queda relegado a D4.

## 9. Fuera de alcance

Auth/UI/dark-mode/cloud, inpainting, escritura a DB, detección ML de caras (queda como mejora futura), GPU.
