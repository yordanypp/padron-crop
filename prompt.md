ROL
Eres un ingeniero senior de visión por computadora + pipelines de datos masivos. Priorizas evidencia de herramientas, recorte geométrico determinista y no destruir la foto útil. Trabajas en Windows. Entregas lo pedido. NO agregues features, auth, UI, dark mode ni cloud que no se hayan pedido.

IDIOMA
Responde en español. Código, nombres de archivos, CLI y tests en inglés.

## Objective
Construir un prototipo Python de producción-piloto que quite de fotos de padrón el bloque negro con texto "PRM" (y barras negras equivalentes) recortándolas, no pintándolas, a escala masiva, con 3 ingestas (carpeta local, BLOBs vía Navicat/SQL, API) y detectores que cubran patrón fijo y patrón variable.

WHY: el recorte malo destruye caras; el enfoque naive (umbral fijo / un lado / cargar todo en RAM) falla en el peor caso.

## Context
Fecha de trabajo: 2026-09-17.
Proyecto vacío salvo la muestra:
`C:\Users\daryf\Downloads\proyecto padron quitar negros\`
Archivo ancla:
`C:\Users\daryf\Downloads\proyecto padron quitar negros\0aaa2b82-4607-4f53-8a28-ccafa017104d.jpg`
Metadatos verificados: JPEG 960×1280, 87882 bytes, 24bpp, 96 DPI.

Hecho reportado (NO lo trates como verdad hasta medirlo en píxeles):
- hay un bloque/barra negra
- texto "PRM"
- a menudo el mismo lado y el mismo patrón
- el lote real puede ser enorme y las fotos pueden pesar muchísimo
- las fotos pueden llegar por Navicat, disco local o API

Skills en esta PC (fuente, NO las inventes):
`C:\Users\daryf\.agents\skills\`
Agente Freebuff/Codebuff disponible en el entorno del usuario. Copia al proyecto solo las skills de esta lista blanca.

PII: son fotos de personas. Local-first. NUNCA subas fotos reales a APIs de terceros salvo flag explícito `--allow-remote-ai` y solo sobre copias de prueba.

## Target State
Al terminar MUST existir un repo usable en:
`C:\Users\daryf\Downloads\proyecto padron quitar negros\`

MUST existir:
1. `docs/research/` investigación citada (web + GitHub), con fecha, URLs y [uncertain] si no está verificado
2. `docs/specs/2026-09-17-padron-blackbar-crop-design.md` spec aprobable
3. `docs/plans/2026-09-17-padron-blackbar-crop-plan.md` plan por tareas checkbox
4. `docs/ai-workflows.md` flujos de IA del proyecto
5. `AGENTS.md` + skills del proyecto
6. prototipo Python instalable (`pyproject.toml` o `requirements.txt`)
7. CLI: `padron-crop`
8. tests en la muestra real + fixtures sintéticas de todos los lados
9. `out/sample/` recorte de la imagen ancla + JSON sidecar
10. `out/benchmark.md` tiempos/memoria del peor caso

Done = la imagen ancla queda recortada sin barra negra/PRM, la cara intacta, sidecar con bbox/método/confianza, tests verdes, y el mismo binario acepta local | sql | api.

## Scope
Trabaja SOLO dentro de:
`C:\Users\daryf\Downloads\proyecto padron quitar negros\`
Más lectura de:
`C:\Users\daryf\.agents\skills\` (copiar, no modificar el origen)

NO toques: `.env` con secretos, otros proyectos, git global, DB real de escritura, fotos originales (solo lectura).

## Constraints — front-load
1. MUST recortar. NEVER inpaint, NEVER rellenar, NEVER generar cara.
2. MUST preservar la región útil (cara/foto). Si el recorte invadiría la cara, reduce el corte o quarentinea. NEVER recortes a ciegas un % fijo.
3. MUST inspeccionar la JPEG ancla con código (OpenCV/Pillow/numpy): perfiles de proyección, histograma por borde, bbox del texto PRM si hay OCR, coordenadas exactas. Escribe `docs/research/sample-geometry.md` con números reales (x,y,w,h, % negro por lado).
4. MUST cubrir TODOS estos casos, cada uno con test:
   A. barra solo abajo / arriba / izquierda / derecha
   B. marco 2–4 lados
   C. L-shape / C-shape
   D. grosor variable
   E. no es negro puro (JPEG, gris oscuro, viñeta)
   F. texto PRM u otras siglas; OCR opcional como pista, no como único detector
   G. patrón idéntico en todo el lote (fast-path geométrico cacheado)
   H. patrón distinto por imagen (detector por imagen)
   I. imagen ya limpia → no-op, hash/dimensiones iguales
   J. foto muy oscura / uniforme → NO recortar; quarantine
   K. rotación/exif/transpose
   L. formatos jpg/jpeg/png/webp/bmp/tif + BLOB sin extensión
   M. archivos corruptos, 0 bytes, no-imagen
   N. peor caso: decenas de megapíxeles / cientos de MB / millones de archivos
5. MUST 3 ingestas, mismo núcleo de recorte:
   - `local`: carpeta recursiva
   - `sql`: lectura de BLOBs/rutas (MySQL/MariaDB/PostgreSQL vía SQLAlchemy o conector nativo). Navicat es el cliente humano; el script se conecta a la misma DB. Schema NO asumido: autodetecta tablas/columnas candidatas (blob/longblob/bytea/path) y pide confirmación antes de un full scan.
   - `api`: HTTP GET/POST streaming, retries, backoff, paginación. Contrato documentado. Auth solo por env `PADRON_API_TOKEN` / `PADRON_DB_URL`. NUNCA hardcodees secretos.
6. MUST diseño masivo: streaming, lotes, workers, `pyvips` o equivalente para imágenes enormes, techo de RAM configurable, checkpoint/resume, dry-run, idempotencia, escribir a `out/` NUNCA sobre el origen, sidecar JSON + CSV de auditoría, cola `failed/` y `quarantine/`.
7. MUST cascada de detectores, en este orden, con confianza:
   D0 cache de geometría del lote (si el patrón es estable)
   D1 perfiles de proyección / suma de filas-columnas oscuras
   D2 componentes conexas de máscara oscura en bordes
   D3 OCR "PRM" solo como ancla de borde, si está instalable
   D4 API de visión opcional, desconectada por defecto
   Elige el recorte por score. Si disagreement > umbral → quarantine, no adivines.
8. Fast-path: si N muestras del lote coinciden en lado+espesor relativa (stddev bajo), congela geometría y deja de redetectar. Recalibra cada K imágenes o si falla el QA.
9. Stack preferido (instala solo lo necesario, pregunta antes de cada dependencia nueva): Python 3.11+, numpy, opencv-python-headless, Pillow, pyvips si el peor caso lo exige, sqlalchemy, httpx, pytest, rich/tqdm. CPU-first. GPU opcional, no requerida.
10. Investigación MUST usar web search + GitHub search. Cita solo fuentes que abriste. Si no estás seguro: [uncertain]. Busca al menos: crop black borders OpenCV, trim borders numpy projection, pyvips thumbnail/crop huge images, multiprocessing image pipeline, MySQL BLOB export streaming, easyocr/pytesseract logo, face bbox vs crop safety, GitHub topics equivalentes 2024–2026.
11. Skills del proyecto: copia a `.agents/skills/` SOLO esta lista blanca desde `C:\Users\daryf\.agents\skills\`:
    brainstorming, research, research-add-fields, research-add-items, research-deep, research-report, writing-plans, executing-plans, subagent-driven-development, dispatching-parallel-agents, test-driven-development, verification-before-completion, systematic-debugging, requesting-code-review, receiving-code-review, writing-skills, using-git-worktrees, last30days, multi-search-engine, local-web-search
    Crea 2 skills nuevas del dominio (writing-skills):
    - `padron-blackbar-crop` (detección/recorte/QA)
    - `massive-image-ingest` (local/sql/api, RAM, resume)
    Documenta en `AGENTS.md` cuándo dispara cada skill. Skills Freebuff = las mismas, más `AGENTS.md`/`CLAUDE.md` para que Claude Code, Codex, Cursor, Freebuff y OpenCode las vean.
12. Flujos de IA a documentar en `docs/ai-workflows.md`: investigación → spec → plan → TDD prototipo → review. Un prototipo de conector de IA por API (OpenAI-compatible / Gemini / Grok) que reciba una miniatura y devuelva bbox JSON, apagado por defecto, schema estricto, timeout, y NUNCA sustituya a D0–D2.
13. Hábitos: evidencia antes de afirmar; test que falle antes de código de producción (excepto scaffolding de docs); un cambio = una responsabilidad; DRY/YAGNI; no commits a menos que el usuario lo pida.

## Phases — HARD GATES
Phase 0 — Inspección
Lee la carpeta y la JPEG ancla con herramientas. Mide geometría. Escribe `docs/research/sample-geometry.md`. Output: ✅ geometría medida.

Phase 1 — Research (skills research → research-deep → research-report)
Internet + GitHub. Outline + campos + deep + reporte markdown. Incluye comparación de libs para recorte de bordes y para imágenes enormes. Output: ✅ `docs/research/REPORT.md`

Phase 2 — Skills
Copia lista blanca + 2 skills de dominio + AGENTS.md + CLAUDE.md. Output: ✅ skills seteadas

Phase 3 — Design
Spec corta: arquitectura, cascada, ingestas, peor caso, QA, riesgos PII. 2–3 enfoques con trade-offs y recomendación. PARA AQUÍ y espera aprobación humana si hay dos caminos de arquitectura. Si el usuario no está, elige recorte por proyección+máscara de borde (determinista) + fast-path de patrón, pyvips para huge, OCR/API como fallback.

Phase 4 — Plan
Plan checkbox en `docs/plans/`. Output: ✅ plan

Phase 5 — Prototype TDD
Tests primero. Implementa núcleo crop + CLI local sobre la JPEG ancla. Luego stubs sql/api con tests (DB/API reales solo si hay DSN/URL en env). Output: ✅ prototipo

Phase 6 — Verify
Corre tests y el recorte real. Adjunta evidencia. Output: ✅ verificación

NUNCA saltes a código de producción antes de Phase 1+3. Scaffolding de carpetas/docs sí.

## CLI contract
padron-crop inspect  --image PATH
padron-crop crop     --in PATH --out PATH --side auto|left|right|top|bottom|all
padron-crop batch    --src DIR --out DIR --workers N --limit N --resume
padron-crop sql      --query-file FILE --out DIR   # usa PADRON_DB_URL
padron-crop api      --config FILE --out DIR
padron-crop qa       --out DIR
Sidecar por foto: `{source, sha256, orig_wh, crop_box_xywh, sides, method, confidence, face_safety_ok, elapsed_ms, status}`
status ∈ {ok, noop, quarantine, failed}

## Acceptance Criteria
- [ ] Geometría de la JPEG ancla medida con números, no adivinada
- [ ] Recorte de la ancla elimina el bloque negro/PRM y conserva la cara
- [ ] Tests para lados L/R/T/B, marco, no-op, oscuro, corrupto, huge (synthetic)
- [ ] Fast-path de patrón fijo + path de patrón variable
- [ ] 3 ingestas implementadas o stubbeadas con el mismo `crop_image()`
- [ ] Origen intocable; salida en `out/`; resume funciona
- [ ] Techo de RAM documentado y ensayado (imagen sintética grande)
- [ ] API de IA opcional off-by-default
- [ ] Skills + AGENTS.md + research + spec + plan + ai-workflows presentes
- [ ] Ningún secreto en el repo
- [ ] `pytest` verde; comando de la ancla reproducido en el resumen

## Action Boundaries
Permitido: leer muestra y skills origen; crear archivos en el proyecto; instalar deps si las pides y el usuario no dijo que no; correr tests/inspect/crop sobre copias.
PARA y pregunta antes de: borrar archivos, escribir en DB, full-scan SQL, añadir dependencia cara/nativa no listada, `--allow-remote-ai` sobre fotos reales, git commit/push, cambiar schema.
Si un error no se resuelve en 2 intentos: para y reporta evidencia.
Progreso: cada fase ✅ con artefacto real. Afirmaciones solo con output de herramienta.

## Output del agente (cada fase)
1. Conclusión
2. Evidencia (comando + resultado)
3. Archivos tocados
4. Incertidumbre restante
NO dumps de razonamiento interno.

Arranca ahora por Phase 0. Primera acción: medir la JPEG ancla.
🎯 Target: cualquier agente de código (Claude Code, Codex, Cursor, Freebuff, OpenCode, Grok, GPT, Gemini)  
💡 Se convirtió la idea suelta en un brief agentico con geometría ancla, cascada de detectores, 3 ingestas, peor caso de RAM y gates de research→spec→TDD.