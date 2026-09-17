# CLAUDE.md

Claude Code: lee y sigue **AGENTS.md** (fuente única de verdad de este proyecto).

Resumen mínimo:

- Prototipo Python `padron-crop`: recorta bloque negro/PRM de fotos de padrón. Nunca inpaint. Origen read-only, salida a `out/`.
- Skills del proyecto: `.agents/skills/` — dispara `padron-blackbar-crop` para detección/recorte/QA y `massive-image-ingest` para ingestas masivas local/sql/api (tabla de disparo en AGENTS.md).
- PII: fotos reales nunca a servicios remotos; D4 OFF por defecto (`--allow-remote-ai` solo copias de prueba).
- Sin secretos en el repo (`PADRON_DB_URL`, `PADRON_API_TOKEN` por env). SQL full-scan solo con confirmación humana.
- Tests primero (TDD). Evidencia antes de afirmar. Docs: `docs/research/`, `docs/specs/`, `docs/plans/`, `docs/ai-workflows.md`.
