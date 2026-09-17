# REPORT.md — Investigación (Fase 1)

Fecha: 2026-09-17. Método: web search (fallback local Bing vía skill `local-web-search`, porque `web_search` devolvió errores 3 veces consecutivas) + apertura de páginas con `read_url`. **Solo se cita como verificada la fuente cuya página se abrió**; las conocidas solo por snippet se marcan `[snippet-only]`. Búsqueda de GitHub: hecha vía consultas Bing con operadores (`github …`); repos abiertos vía resultado de búsqueda `[snippet-only]` salvo indicación.

## Preguntas de investigación

1. ¿Cómo se detectan/recortan bordes negros de forma determinista?
2. ¿Qué librería para imágenes enormes (cientos de MB) sin reventar la RAM?
3. ¿OCR como ancla de texto (PRM)? ¿Costo?
4. ¿Cómo transmitir BLOBs MySQL/PostgreSQL sin cargar la tabla en RAM?
5. ¿Paralelización de pipeline de imágenes en CPU?
6. ¿Casos conocidos de "barra que no es negra pura"?
7. ¿Seguridad de recorte vs. cara?

## Hallazgos y evidencia

### 1. Detección de bordes negros (proyección / threshold)

- **SO 13538748 "Crop black edges with OpenCV"** — https://stackoverflow.com/questions/13538748/crop-black-edges-with-opencv `[snippet-only, 403 al abrir]` — patrón estándar: convertir a gris, umbral, sumar por filas/columnas (proyección), recortar donde la suma cae bajo umbral. Coincide con el enfoque D1.
- **loglux/remove_black_borders** (GitHub) — https://github.com/loglux/remove_black_borders `[snippet-only]` — script Python que detecta y recorta bordes de imágenes en una carpeta; útil como referencia de batch simple. Carece de: cascada, QA, fast-path, ingestas múltiples.
- **z80z80z80/autocrop** — https://github.com/z80z80z80/autocrop `[snippet-only]` — recorte+rotación automática de escaneos con OpenCV. Referencia de escaneos.
- **cgbur/croppy** — https://github.com/cgbur/croppy/ `[snippet-only]` — batch auto-crop para escaneos de película; **detecta límites de frame con heurísticas de procesamiento de señal ligeras** y escribe sidecars XMP sin tocar los RAW. Patrón de diseño relevante: **sidecar + origen intocable** (igual a nuestro requisito).
- **martymcmodding gist "Batch cropping images (black bar removal)"** — https://gist.github.com/martymcmodding/5ee690ed5aae0cc338a9302903ccef9f `[snippet-only]` — batch removal de barras negras.
- **FFmpeg cropdetect guide** — https://ffmpeg-cookbook.com/en/articles/crop-black-bars/ (abierta 2026-09-17) — lecciones verificadas:
  - `limit` (luma upper bound para "negro", default 24/255) es el parámetro clave: *"Lowering limit too far makes dark scene content look like black bars"* → confirma el riesgo de falso positivo sobre contenido oscuro legítimo (nuestro caso "left" medido en sample-geometry.md).
  - Distinción letterbox/pillarbox/burned-in: solo los píxeles realmente codificados (burned-in) se recortan — coincide con nuestro caso (el bloque PRM es píxel real).
  - Recomendación: umbral configurable por corrida, no hardcodeado.

**Conclusión 1:** D1 (proyección) es el estándar del sector; el valor agregado del prototipo es la **cascada + QA de seguridad de cara + fast-path de lote**, que ninguno de los repos públicos revisados combina.

### 2. Imágenes enormes (RAM)

- **pyvips (PyPI)** — https://pypi.org/project/pyvips/ (abierta 2026-09-17):
  - *"it doesn't need to keep entire images in memory"*, streaming por secciones, paralelo.
  - Instalación Windows fácil: `pip install "pyvips[binary]"` — paquete binario autocontenido con librerías incluidas (3.2.0 actual). Esto reduce el riesgo de dependencia nativa: es un extra, no compilación manual.
- **libvips Speed & memory benchmark** — https://github.com/libvips/libvips/wiki/Speed-and-memory-use (abierta 2026-09-17): test 10,000×10,000 TIFF (100 MP): **libvips ~94–95 MB peak** vs **OpenCV 797.67 MB peak** (y Pillow 1040 MB). libvips 5–8× menos RAM y más rápido en este test.
- **vipsthumbnail docs** — https://www.libvips.org/API/current/using-vipsthumbnail.html `[snippet-only]` — procesa imágenes una tras otra con paralelismo; patrón para batch.
- **multiprocessing (Python docs)** — https://docs.python.org/3/library/multiprocessing.html (abierta vía snippet de búsqueda, dominio oficial) — ProcessPool para CPU-bound; trabajo por lotes con `map`. `[snippet-only]`
- Guía de pipeline multiprocessing — https://pythonz2h.com/chapter_09_concurrency_and_parallelism/series_02_multiprocessing_and_parallelism/python-multiprocessing-image-processing-pipeline-real-world `[snippet-only]` — patrón: pool + error handling + progress + cleanup.

**Conclusión 2:** para el peor caso, **pyvips[binary]** como backend opcional de carga/corte (lazy + streaming), con Pillow como backend por defecto para imágenes normales. OpenCV queda descartado como obligatorio: 8× la RAM de libvips en el benchmark de 100 MP y no está instalado en esta PC.

### 3. OCR como ancla (D3)

- **EasyOCR** — https://blog.roboflow.com/how-to-use-easyocr/ y https://medium.com/@nelsonizah95/... `[snippet-only]` — API simple: `Reader(['en']).readtext(img)` devuelve `(bbox, text, prob)`; filtro por `prob > 0.7`. Pesado (PyTorch, ~cientos de MB) → solo opcional.
- **pytesseract** (no buscado con éxito, [uncertain] detalles de instalación Windows) — binario externo + wrapper. Ligero pero instalación frágil en Windows.
- Decisión: **D3 OFF por defecto**. El detector de glifos claros (luma>0.6, área pequeña, dentro de zona oscura) ya ancla el texto sin OCR en la muestra (medido: 3 glifos y 1009–1081, x 352–509). OCR solo añadiría *lectura* del texto, no la *posición*.

### 4. BLOBs SQL

- **GeeksforGeeks "Retrieve Image and File stored as a BLOB from MySQL Table"** — https://www.geeksforgeeks.org/python/retrieve-image-and-file-stored-as-a-blob-from-mysql-table-using-python/ (abierta 2026-09-17): patrón con `mysql-connector-python`, tipos BLOB→LONGBLOB, `Image.open(io.BytesIO(binary_data))`. Riesgo del tutorial: `fetchall()` carga todo → nuestro diseño usa **cursor stream / SSCursor / fetchmany**. [uncertain] PostgreSQL `bytea` vía psycopg3 server-side cursor: pendiente de verificar con DSN real.
- **Bomberbot guía BLOBs MySQL** — https://www.bomberbot.com/python/retrieving-images-and-files-stored-as-blobs-from-mysql-using-python-a-comprehensive-guide/ `[snippet-only]`.

**Conclusión 4:** SQLAlchemy con `yield_per`/`stream_results` sobre la tabla autodetectada; conexión SOLO lectura; `PADRON_DB_URL` por env; autodetección de columnas candidatas (`blob|longblob|bytea|image|photo|foto`) y confirmación antes del full scan (requisito del brief).

### 5. EXIF / rotación

- **alexwlchan** — https://alexwlchan.net/notes/2024/photos-can-have-orientation-in-exif/ `[snippet-only]` — "bake in" la rotación con `ImageOps.exif_transpose` antes de procesar. Ya aplicado en las tools de Phase 0.
- **Pillow issue #4537** — https://github.com/python-pillow/Pillow/issues/4537 `[snippet-only]` — al guardar tras transpose hay que limpiar/actualizar el tag de orientación → nuestro writer de salida debe eliminar el tag 274 o escribir 1.

### 6. Comparación de librerías para recorte de bordes

| Opción | Pros | Contras | Veredicto |
|---|---|---|---|
| numpy + Pillow (puro) | ya instalado; cero deps nativas; suficiente para ≤100 MP con escaneo por bandas | RAM = 3 bytes/px al decodificar (≈3 GB @1000 MP) | **backend default** |
| OpenCV | rápido, `connectedComponents` nativo | no instalado en la PC; 8× RAM de libvips en 100 MP (benchmark); deps binarias grandes | opcional, si el peor caso lo pide |
| pyvips[binary] | streaming real, ~95 MB @100 MP, wheel con binarios | otra dep; API lazy menos directa | **backend para huge (>30 MP) / modo --engine vips** |
| skimage | CC + filtros cómodos | no instalado; no aporta lo que numpy no dé | descartado |

Para ingestión: `httpx` (streaming HTTP, retries con backoff manual) `[snippet-only, estándar de facto]`; `rich`/`tqdm` para progreso `[snippet-only]`; `pytest` ya instalado (9.1.1).

### 7. Cara vs recorte

- Ninguna fuente abierta específica revisada en profundidad para "face bbox safety" (búsqueda con timeout; [uncertain]). Mitigación adoptada sin depender de detección de caras ML: **regla geométrica conservadora** — no recortar filas/columnas que contengan píxeles brillantes significativos (luma>0.6) ni skin-tone aproximado, y la zona de recorte debe ser oscura y tocar el borde. La ancla confirma que la cara (zona brillante y 65–860) queda lejos del corte (y=1004).
- Detector de caras opcional (p. ej. `cv2.CascadeClassifier`) queda como mejora futura, no requisito del prototipo [uncertain, no evaluado].

## Repos GitHub relevantes (referencia de diseño, no dependencias)

| Repo | Qué tomar | Qué NO copiar |
|---|---|---|
| cgbur/croppy `[snippet-only]` | sidecars + no tocar origen + heurísticas de señal | dominio film-scan |
| loglux/remove_black_borders `[snippet-only]` | simplicidad batch | umbral único sin QA |
| wanfungtsui/video-letterbox-detector `[snippet-only]` | detección de barras por franjas | dominio video |
| martymcmodding gist `[snippet-only]` | referencia de remoción por lotes | falta cascada |

## Riesgos identificados para la spec

1. Contenido oscuro legítimo (ropa/sombra) → falso positivo de "barra". Mitigación: fill oscuro + tocar borde + sin brillos + coincidencia entre D1 y D2.
2. Texto sobre fondo intermedio (no negro puro) → umbral fijo lo pierde. Mitigación: ancla de glifos claros + negro sólido como piso, línea = min(tope_texto, inicio_negro_sólido) − margen.
3. Patrones mixtos en el lote → fast-path no válido. Mitigación: stddev de lado+espesor en N muestras; si no converge, detector por imagen siempre.
4. RAM en lotes de millones → streaming + techo configurable + resume.
5. PII: fotos reales jamás a servicios externos sin `--allow-remote-ai`; D4 OFF por defecto.
