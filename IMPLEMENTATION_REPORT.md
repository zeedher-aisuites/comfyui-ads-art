# Implementation Report — Ads Art Creative Intelligence v2

## Compact Gemini provider contract — 2026-09-06

The provider boundary now uses a compact typed facet contract while a deterministic
local expander restores the unchanged rich master v2. For the 4–7 shot configuration,
the inline provider contract 1.3.0 measures 46 properties, 3,820 UTF-8 bytes, 83 schema
objects and 20 constraints. It avoids `$defs/$ref` after 1.0.0 was rejected; 1.1.0 was
accepted but omitted generic Seedance facets, so 1.2.0 makes those five fields explicit.
After 1.2.0 returned free-form evidence labels, 1.3.0 added canonical evidence enums.
Provider schema, expander and prompt versions enter the cache signature.
After a 1.3.0 response was truncated near the former 8,192-token ceiling, the v2 request
was bounded at 16,384 and parse failures were made recoverable with raw text, usage and
finish-reason persistence. The v1 output setting is unchanged.
The full local suite has 57 passing tests. No Higgsfield, Nano or Seedance call was made. See
`COMPACT_PROVIDER_SCHEMA_REPORT_2026-09-06.md`.

Fecha: 2026-09-06

## Arquitectura encontrada

La v1 ya tenía transporte Gemini 3.6 funcional, validación JSON, caché, detector local,
extracción de frames, persistencia, overrides y gates Higgsfield. Su error conceptual era
que el objeto maestro seguía siendo una lista de tomas del referente y el planificador
Nano adjuntaba el frame comercial como objetivo compositivo.

## Cambio realizado

La v2 convierte el sistema en:

```text
REFERENCE-DRIVEN ADVERTISING INTELLIGENCE
-> ABSTRACTION
-> ORIGINAL ADAPTATION
-> ORIGINAL SHOT PLAN
-> HUMAN-GATED ORIGINAL MEDIA GENERATION
```

Se añadieron módulos separados para schema/validación y nodos ComfyUI. La v1 no se
eliminó: queda como compatibilidad histórica y conserva todos sus registros.

## Código reutilizado

- Google Gen AI SDK + `generateContent`, modelo exacto `gemini-3.6-flash`.
- Availability preflight, Files API, 2 FPS, audio incluido, thinking low, 8192 tokens.
- Una inferencia sin retry, limpieza remota y registro de uso/costo.
- Video metadata, cut detection, nearby candidate checks y frame extraction.
- ProjectStore, fingerprint estable, request validation y manual overrides.
- Locks `nano_banana_pro` 4:5/2k y `seedance_2_5` omni_reference.
- CLI Higgsfield, submit/recovery/poll/download y montaje local.

## Código nuevo

- `ads_art_creative.py`: schema `2.0.0`, prompt v3, brief/response validation,
  provenance, originality guard y firma semántica.
- `ads_art_creative_nodes.py`: seis nodos v2.
- `scripts/build_creative_workflow_v2.py`: workflow determinista.
- `scripts/sync_creative_workflow_v2.py`: instalación no destructiva y migración de
  identidad/controles.
- `CREATIVE_INTELLIGENCE_ARCHITECTURE.md`: límites y state machine.
- `tests/test_creative_intelligence.py`: cobertura v2 con fixtures/mocks.

## Nodos nuevos

1. `AdsArtCreativeBrief`
2. `AdsArtGeminiCreativeIntelligence`
3. `AdsArtCreativeIntelligenceViewer`
4. `AdsArtOriginalShotDraft`
5. `AdsArtPrepareOriginalKeyframe`
6. `AdsArtPrepareOriginalSeedanceShot`

No se eliminó ningún nodo v1. Los nodos v1 que plantean frames del referente como
objetivos quedan deprecados para proyectos nuevos.

## Automatización y caché

El nodo Gemini v2 no tiene `confirm_gemini_analysis`. Tras validar inputs, calcula la
huella y reutiliza caché antes de consultar la clave. Sin caché y con clave/inputs válidos,
la inferencia comienza automáticamente. Un estado started/failed/unknown bloquea
repetición; no existe retry automático.

La huella incluye video, identidad, `identity_notes`, character brief, brand/product
brief, constraints, duración/rango, modo, conocimiento, detector y versiones de modelo,
configuración, prompt y schema.

## Human gates conservados

- selección/aprobación de identidad;
- aprobación visual de keyframes originales;
- `confirm_paid_submission` para Nano Banana Pro;
- aprobación del keyframe antes de Seedance;
- `confirm_paid_submission` para Seedance;
- recuperación manual tras cualquier envío incierto.

Los submits del workflow v2 están en bypass, con confirmación `false`.

## Persistencia

La v2 añade `creative_project.json`, `analysis/reference/`,
`analysis/creative_intelligence/`, `adaptation/`, `frames/reference_evidence/` y
`shots/original_plan.json`. No transforma ni borra los caches 2.5/3.6, informes, job IDs,
requests, resultados o montajes previos.

La instalación comprobó igualdad exacta de las 676 posiciones/caracteres de
`identity_notes` entre v1 y v2 y conservó `Ads Art - Madame X approved.png`.

## Validación ejecutada

- Compilación de todos los módulos Python.
- 46 pruebas unitarias/locales con video sintético y respuesta Gemini fixture.
- Caché: primera inferencia mock, segunda ejecución idéntica `CACHE HIT`.
- Invalidación por brand brief, character/identity notes y video.
- Schema, separación, timestamps, cobertura de evidencia, rango/duración y originality.
- Nano: sólo identidad aprobada; cero reference frames.
- Seedance: sólo imágenes/keyframe original y texto; cero video/audio/evidence del referente.
- Workflow v2: 19 nodos, 23 enlaces, contratos registrados y submits desactivados.
- Sincronización v2 sin modificar la v1 instalada.

## Verificación real posterior del contrato Gemini

Tras aislar el 400, una única verificación autorizada de
`gemini-3.6-flash + generateContent` completó preflight, subida, procesamiento e
inferencia. El schema proveedor compacto `1.3.0` se expandió al master `2.0.0` y pasó la
validación local. Se reportaron 16,493 tokens de entrada y 7,748 de salida; el costo
calculado fue USD 0.04142475 y sigue siendo una **estimación**, no un cargo observado.
El archivo remoto fue eliminado. No se llamó a Higgsfield, Nano Banana ni Seedance.

El brief persistido de esta ejecución tenía rango 4–7, por lo que Gemini devolvió cuatro
tomas. No hubo reintento para modificar ese parámetro.

## Workflow

- Nuevo: `workflows/ads_art_creative_intelligence_v2.json`.
- Instalado: `user/default/workflows/Ads Art/ads_art_creative_intelligence_v2.json`.
- V1 preservado: `ads_art_prepare_v1.json`.

## Deuda técnica real

- Una ejecución Gemini real será necesaria para validar que el proveedor satisface el
  schema v2 completo con el comercial/brief definitivo; no se ejecutó por control de red.
- La protección de similitud textual/routing es verificable; una medición perceptual de
  similitud visual requerirá assets generados y un evaluador independiente.
- La calidad creativa y corrección psicológica son interpretaciones del modelo, no hechos
  demostrables por unit tests.
