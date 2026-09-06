# Gemini Creative Intelligence Integration

> Compact-provider update (2026-09-06): Gemini now receives inline provider schema `1.3.0`;
> deterministic expander `1.3.0` restores internal master `2.0.0`. See
> `COMPACT_PROVIDER_SCHEMA_REPORT_2026-09-06.md`.
> Creative Intelligence uses a bounded 16,384-token output ceiling; v1 remains at 8,192.

Fecha de implementación v2: 2026-09-06

## Contrato de producto

Gemini analiza el comercial como evidencia y produce inteligencia transferible para una
pieza original. No elige frames para copiarlos, no sustituye personajes/escenas y no
instruye motion transfer.

```text
REFERENCE EVIDENCE
  -> OBJECTIVE OBSERVATION
  -> EVIDENCE-BACKED INTERPRETATION
  -> ABSTRACT STRATEGY
  -> TRANSFER / DO-NOT-COPY RULES
  -> ORIGINAL ADAPTATION
  -> ORIGINAL SHOT PLAN
```

## Modelo, transporte y parámetros

- Modelo exacto: `gemini-3.6-flash`.
- SDK: `google-genai>=2.22.0,<3`.
- Método: `models.generate_content` / `generateContent`.
- Structured output: JSON Schema estricto.
- Thinking: `thinking_level=low`.
- Salida: `max_output_tokens=8192`.
- Video: Files API, modo estático, 2 FPS.
- Audio: incluido dentro del MP4 para análisis; nunca se envía a Seedance.
- Inferencia: una llamada, sin retry automático.
- Subida: un intento; procesamiento acotado; eliminación remota best effort.

No hay alias, fallback ni migración a Interactions API. El preflight autenticado del
modelo ocurre antes de subir el archivo y exige el nombre exacto y soporte
`generateContent`.

## Ejecución automática segura

`AdsArtGeminiCreativeIntelligence` no contiene `confirm_gemini_analysis`. La operación
es automática sólo cuando se cumplen todos estos puntos:

1. creative brief válido;
2. video local legible;
3. identidad central conectada y `identity_approved=true`;
4. `GEMINI_API_KEY` disponible en el entorno privado;
5. no existe caché completa para la huella;
6. no existe un estado started/failed/unknown sin override manual.

La caché se consulta antes de comprobar la clave o tocar la red. Una coincidencia
devuelve `CACHE HIT`; una llamada nueva se identifica como `REMOTE ANALYSIS`. Si falta la
clave y no hay caché, el nodo detiene indicando que no subió ningún medio.

La ausencia del gate humano afecta sólo al análisis Gemini. Nano Banana Pro, Seedance y
cualquier generación Higgsfield conservan confirmación explícita.

## Huella semántica

`analysis/creative_intelligence/cache/<sha256>.json` usa una serialización estable de:

- SHA-256 y bytes del video;
- SHA-256 de la identidad aprobada;
- nombre, `identity_notes`, personalidad, arquetipo y restricciones del character;
- modo/nombre de marca, product brief, audiencia, positioning, promise y brand world;
- elementos requeridos/prohibidos y user constraints;
- duración objetivo y rango de tomas;
- modo de análisis;
- conocimiento cinematográfico completo;
- detector local y cortes;
- modelo/configuración y versiones de prompt/schema.

Cualquier cambio material invalida la huella. Los estados inciertos no se repiten
automáticamente.

## Schema maestro 2.0.0

`ads_art_creative.py` define y valida ocho secciones independientes:

1. `reference_observation`
2. `reference_interpretation`
3. `reference_strategy`
4. `evidence`
5. `transfer_rules`
6. `original_adaptation`
7. `original_shot_plan`
8. `provenance`

Los elementos de evidencia incluyen ID, timestamp, intervalo, candidatos, hecho
observado y categorías respaldadas. La validación exige cobertura para hook, psicología,
gramática visual, cámara, luz, edición, audio, reveal, memoria y progresión emocional.
Cada frame extraído queda marcado:

```text
REFERENCE_EVIDENCE_ONLY_NOT_GENERATION_TARGET
```

Cada toma original contiene duración, purpose, función psicológica/retención, acción,
expresión, ambiente, composición, framing, cámara, perspectiva, movimiento, luz, color,
producto, audio, continuidad, prompt Nano, dirección Seedance y tres campos de auditoría:

- `reference_principles_used`
- `literal_reference_elements_avoided`
- `differentiation_notes`

La suma de las duraciones debe coincidir con el target y el número de tomas debe quedar
entre los límites configurados. Expresiones de copia/remake/timestamp literal en campos
de generación detienen el análisis.

`provenance` exige prefijos explícitos:

- `USER_PROVIDED:`
- `AI_PROPOSED:`
- `USER_APPROVED:`

Los datos faltantes quedan en `unresolved_inputs`. Esta validación comprueba estructura,
trazabilidad y cobertura declarada; no convierte una inferencia semántica en un hecho
verificado por sí sola.

## Evidencia local

La detección de cortes y extracción existente se reutiliza. Gemini devuelve candidatos
dentro de intervalos observados; Ads Art prueba muestras cercanas, evita transiciones
cuando existe alternativa y guarda el frame más estable bajo:

```text
frames/reference_evidence/<cache_key>/<evidence_id>.png
```

Estos archivos alimentan exclusivamente la visualización **03 — Reference Evidence**.
No existe conexión desde ese puerto a Nano o Seedance.

## Generación original

`AdsArtPrepareOriginalKeyframe` usa character, brand/product brief, adaptación y toma
original. Adjunta sólo `approved_ai_character`; nunca adjunta video o evidence frames.
Mantiene `nano_banana_pro`, `4:5`, `2k`.

`AdsArtPrepareOriginalSeedanceShot` acepta únicamente un keyframe original aprobado,
identidad aprobada y texto. Mantiene `seedance_2_5`, `omni_reference`; registra
explícitamente que referencia visual, video y audio no fueron enviados.

Los dos `AdsArtSubmitJob` de la v2 están en bypass y
`confirm_paid_submission=false`.

## Persistencia y compatibilidad

La v2 añade rutas nuevas y no toca:

- `analysis/gemini/cache/` y `state/` históricos;
- `analysis/commercial.json` de v1;
- requests/jobs/results previos;
- `GEMINI_TEST_REPORT_2026-09-06.md`;
- `GEMINI_36_TEST_REPORT_2026-09-06.md`.

La v1 se conserva como workflow histórico/deprecado. La instalación inicial de v2
importa exactamente `identity_notes`, la imagen aprobada, project ID y controles previos,
marcando estos últimos como contexto v1 subordinado al paradigma actual.

## Costos y registros

Los registros nuevos conservan modelo, configuración, prompt/schema version, respuesta,
timings, uso y costo estimado. La tarifa sigue la configuración verificada de Gemini 3.6
y `observed_charge_usd` permanece separado. Un costo calculado desde tokens no prueba un
cargo de facturación.

La implementación v2 se verificó con mocks/fixtures. No se realizó otra llamada remota
a Gemini y no se ejecutó ninguna operación Higgsfield durante esta migración.

## Provider-response cache

Desde provider schema `1.4.0`, cada JSON recibido tras un `generateContent` satisfactorio
se escribe primero en `analysis/creative_intelligence/provider_responses/`. Sólo después
se ejecutan expansión, validación master y extracción de evidencia. El fingerprint de
esa respuesta excluye la versión del expander, permitiendo corregir y reprocesar lógica
local sin otra inferencia, pero incluye modelo, prompt, provider schema y los inputs del
request para impedir reutilización incompatible.
