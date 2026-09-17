# ai-workflows.md — Flujos de IA del proyecto

Cómo se usan (y no se usan) las capacidades de IA en **padron-blackbar-crop**. Regla madre: **la geometría manda; la IA solo propone; el QA decide.**

## 1. Flujo de desarrollo del propio proyecto (agente de código)

```
investigación (research → research-deep → research-report, citas con fecha/URL)
      → spec (docs/specs/, 2–3 enfoques con trade-offs) [GATE: aprobación humana si hay 2 caminos]
      → plan checkbox (docs/plans/)
      → prototipo TDD (test rojo → implementación mínima → verde, por caso A–N)
      → review (requesting-code-review) → verificación con evidencia (verification-before-completion)
```

- Cada fase termina con artefacto real (no con una afirmación).
- Skills de orquestación: `writing-plans`, `executing-plans`, `subagent-driven-development`, `dispatching-parallel-agents`.
- Debug: `systematic-debugging` antes de proponer fixes. Máximo 2 intentos por error → escalar al humano con evidencia.

## 2. Uso de IA de visión en el pipeline (D4) — APAGADO por defecto

### Contrato

Implementación: `src/padron_crop/vision.py` (tests en `tests/test_vision.py`,
con transporte inyectado — nunca hay red en la suite). El conector **solo puede
vetar**: si coincide con la geometría determinista, gana el determinista; si
discrepa más de `DISAGREE_TOL`, la imagen va a quarantine. Nunca redefine el
recorte.

- Un conector por proveedor **OpenAI-compatible** (también usable para Gemini/Grok vía endpoints compatibles o adaptadores): recibe una **miniatura** (máx 512 px, JPEG q80) de una **copia de prueba**, devuelve `bbox JSON` estricto.
- Schema de salida validado (sin campos extra, coordenadas enteras en píxeles de la miniatura, reescalables a la original):

```json
{
  "bbox_xywh": [x, y, w, h],
  "kind": "blackbar|text|unknown",
  "confidence": 0.0
}
```

- Timeout duro por request, 2 retries con backoff, y si el schema no valida → se descarta la respuesta.
- **Jamás sustituye a D0–D2**: solo se consulta si D1+D2 discrepan y el operador pasó `--allow-remote-ai` explícito.

### Reglas PII

- Fotos reales **nunca** salen de la máquina. Sin flag → el conector ni se instancia.
- Con flag → solo imágenes marcadas como copias de prueba (prefijo/directorio sintético), y se registra en el sidecar `method: "d4-remote"` + proveedor.
- Sin secretos en código: token por env `PADRON_API_TOKEN` (o `OPENAI_API_KEY` del proveedor elegido).

### Cuándo NO usar IA

- D1 y D2 coinciden (caso normal): la respuesta es determinista y gratuita.
- Imagen oscura uniforme → quarantine, no consultas.
- Cualquier duda de privacidad.

## 3. Skills de IA del repo (para agentes)

Ver `AGENTS.md` para la tabla de disparo. Resumen: `padron-blackbar-crop` (detección/QA) y `massive-image-ingest` (escalado) son las skills de dominio; el resto son de proceso (research, TDD, verification, review).
