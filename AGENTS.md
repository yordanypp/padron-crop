# AGENTS.md — guía para agentes de código

Proyecto: **padron-blackbar-crop** — quitar el bloque negro con texto "PRM" de fotos de padrón **recortando** (nunca inpainting/relleno/generación), a escala masiva, con ingestas `local | sql | api`.

Aplica a: Claude Code, Codex, Cursor, Freebuff, OpenCode y cualquier agente que lea este archivo. Skills del proyecto en `.agents/skills/` (formato estándar, frontmatter `name`/`description`).

## Reglas duras (no negociables)

1. **Recortar, nunca pintar**: prohibido inpaint, rellenar, generar contenido. Solo `crop`.
2. **Origen read-only**: fotos fuente jamás se modifican; toda salida a `out/`.
3. **PII local-first**: fotos reales nunca salen de la máquina. D4 (API de visión) OFF por defecto; requiere `--allow-remote-ai` explícito y solo copias de prueba.
4. **Sin secretos en el repo**: credenciales solo por env (`PADRON_DB_URL`, `PADRON_API_TOKEN`).
5. **SQL full-scan solo con confirmación humana** tras autodetectar columnas candidatas.
6. **Evidencia antes de afirmar**: geometría/rendimiento se miden con código; las afirmaciones citan comando+salida.
7. Si un error no se resuelve en 2 intentos → parar y reportar evidencia.

## Cuándo dispara cada skill

| Situación | Skill |
|---|---|
| Diseñar/ajustar detección o recorte de barras/bloques PRM, dudar si un lado oscuro es barra o ropa, decidir línea de corte cerca de caras, QA de recorte | `padron-blackbar-crop` |
| Ingesta masiva (carpeta/BLOB/API), techo de RAM, workers, checkpoint/resume, carpetas failed/quarantine, audit CSV | `massive-image-ingest` |
| Feature nueva o cambio de comportamiento | `brainstorming` → `writing-plans` |
| Investigación con citas | `research` → `research-add-fields` → `research-add-items` → `research-deep` → `research-report` |
| Implementación de núcleo/CLI | `test-driven-development` (test rojo primero) |
| Ejecutar el plan por fases | `executing-plans`, `subagent-driven-development`, `dispatching-parallel-agents` |
| Bug o test fallido inesperado | `systematic-debugging` |
| Antes de declarar "done" | `verification-before-completion` |
| Review | `requesting-code-review` (al terminar), `receiving-code-review` (al recibir feedback) |
| Crear/editar skills | `writing-skills` |
| Aislamiento de trabajo | `using-git-worktrees` |
| Búsqueda web caída (403/timeout) | `local-web-search` o `multi-search-engine` |
| Investigar qué se dice en redes/foros (≤30 días) | `last30days` |

## Arquitectura en una mirada

```
ingesta (local|sql|api) → core de recorte (único) → cascada D0..D4 → crop determinista
        → out/<run>/img + sidecar JSON + audit CSV → QA → failed/ | quarantine/
```

- Un solo `crop_image()` consumido por las 3 ingestas.
- Cascada: D0 fast-path cacheado → D1 proyección → D2 componentes conexas → D3 ancla de glifos (OCR opcional) → D4 IA remota (apagada).
- Desacuerdo entre detectores → `quarantine/`, nunca adivinar.

## Convenciones

- Código/CLI/tests en inglés; respuesta al usuario en español.
- Python 3.11+; deps mínimas (numpy, Pillow ya presentes; pyvips solo si el peor caso lo exige; preguntar antes de instalar cualquier dependencia nueva).
- Tests: `pytest`; fixtures sintéticas para todos los lados/casos (A–N del brief) + la imagen ancla real si existe.
- Un cambio = una responsabilidad. Sin commits salvo pedido explícito.

## Entradas rápidas

- Geometría medida del ancla: `docs/research/sample-geometry.md`
- Research citado: `docs/research/REPORT.md`
- Spec: `docs/specs/2026-09-17-padron-blackbar-crop-design.md`
- Plan: `docs/plans/2026-09-17-padron-blackbar-crop-plan.md`
- Flujos de IA: `docs/ai-workflows.md`
