# Ads Art — Reference-Driven Advertising Intelligence

Ads Art estudia un comercial como referencia estratégica y cinematográfica, abstrae por
qué funciona y diseña una pieza publicitaria original para un AI character y una marca o
producto nuevos. El referente aporta evidencia; nunca es un blueprint, un objetivo de
generación ni una fuente de motion transfer.

```text
REFERENCE COMMERCIAL + APPROVED AI CHARACTER + BRAND/PRODUCT BRIEF
                              + USER CONSTRAINTS + CINEMATIC KNOWLEDGE
                                           |
                                    LOCAL PREFLIGHT
                                           |
                       AUTOMATIC GEMINI CREATIVE INTELLIGENCE
                                           |
          OBSERVATION -> INTERPRETATION -> STRATEGY -> TRANSFER RULES
                                           |
                         ORIGINAL ADAPTATION + ORIGINAL SHOT PLAN
                                           |
                        NANO PROMPTS + SEEDANCE DIRECTIONS
                                           |
                              HUMAN / PAID GENERATION GATES
```

## Workflow recomendado

- Portable: `workflows/ads_art_creative_intelligence_v2.json`.
- Instalado: `user/default/workflows/Ads Art/ads_art_creative_intelligence_v2.json`.
- Compatibilidad histórica: `ads_art_prepare_v1.json` permanece instalado y versionado,
  pero no debe usarse como arquitectura para proyectos nuevos.

La v2 organiza el canvas en estas fases:

1. **00 — Project / Fictional Brand / AI Character**
2. **01–02 — Reference Commercial / Automatic Creative Intelligence**
3. **03 — Reference Evidence — NOT GENERATION TARGETS**
4. **04 — Transfer Rules / Original Adaptation**
5. **05 — Original Shot Plan**
6. **06 — Original Nano Keyframes**
7. **07 — Approved Original Keyframes**
8. **08 — Seedance Original Shots**
9. **09 — Assembly / Final**

## Inputs centrales

**Ads Art v2 — Project / Brand / Character** separa:

- AI character, `identity_notes`, personalidad, arquetipo y restricciones visuales;
- `fictional_brand_name`, modo `user_defined` o autorización explícita `ai_propose`;
- categoría y descripción del producto;
- audiencia, positioning, emotional promise y visual brand world;
- brand constraints, elementos obligatorios/prohibidos y restricciones del usuario;
- duración objetivo entre 5 y 40 segundos y rango de 1 a 16 tomas originales.

`ai_propose` permite proponer una marca/producto ficticios y exige etiquetarlos
`AI_PROPOSED`. En `user_defined`, la marca debe venir del usuario. El resultado distingue
`USER_PROVIDED`, `AI_PROPOSED`, `USER_APPROVED` y datos sin resolver.

## Gemini automático y caché

La v2 mantiene exactamente:

- `gemini-3.6-flash`, sin alias ni fallback;
- Google Gen AI SDK + `generateContent`;
- structured output con JSON Schema y validación local;
- `thinking_level=low`, `max_output_tokens=8192` y video estático a 2 FPS;
- audio incluido en el MP4;
- preflight de disponibilidad antes de subir medios;
- una inferencia, un intento de subida, sin reintento automático de inferencia;
- limpieza best effort del archivo remoto y bloqueo de estados inciertos;
- `GEMINI_API_KEY` exclusivamente desde el entorno privado.

No existe `confirm_gemini_analysis` en el nodo v2. Al ejecutar:

1. valida brief, identidad y video;
2. calcula una huella semántica;
3. si existe respuesta completa, devuelve **CACHE HIT** sin red;
4. si no existe y falta la clave, detiene con error antes de subir;
5. si no existe, la clave está disponible y los inputs son válidos, ejecuta
   automáticamente una sola inferencia y muestra **REMOTE ANALYSIS**.

La huella incluye video, identidad, `identity_notes`, character/brand/product brief,
restricciones, duración/rango de tomas, modo, conocimiento cinematográfico, detector,
modelo, configuración y versiones de prompt/schema.

## Salida maestra

El schema `2.0.0` separa obligatoriamente:

- `reference_observation`: hechos visuales, de edición, audio y producto/marca;
- `reference_interpretation`: concepto, tesis, hook, deseo, arquetipo, psicología,
  retención y progresión emocional;
- `reference_strategy`: gramática visual, cámara, luz, ritmo, audio, reveal y memoria;
- `evidence`: timestamps e intervalos válidos que respaldan categorías concretas;
- `transfer_rules`: principios transferibles, elementos literales prohibidos y riesgos;
- `original_adaptation`: nueva tesis, hook, rol, mundo, arco y reglas;
- `original_shot_plan`: tomas nuevas, duración, función, acción, composición, cámara,
  audio, prompts y auditoría de diferenciación;
- `provenance`: aportado por usuario, propuesto por IA, aprobado y no resuelto.

La validación comprueba timestamps, cobertura de evidencia, campos obligatorios, suma de
duraciones, rango de tomas y expresiones explícitas de copia literal. Un fallo detiene el
workflow; no inicia un retry correctivo oculto.

## Nano Banana Pro y Seedance

**Prepare Original Nano Keyframe** genera localmente una solicitud para una toma nueva.
Adjunta sólo el AI character aprobado. No adjunta el comercial ni sus frames de evidencia.

- Modelo exacto: `nano_banana_pro`.
- Formato: `4:5`.
- Resolución: `2k`.
- El nodo de envío Higgsfield permanece desactivado y requiere
  `confirm_paid_submission=true` para gastar.

**Prepare Seedance from Original Keyframe** anima exclusivamente un keyframe original
aprobado con texto y referencias de imagen:

- `seedance_2_5`, modo `omni_reference`;
- ningún video/audio/frame de evidencia del referente;
- dirección derivada de función de toma, actuación, cámara, ritmo y objetivo emocional;
- aprobación visual y envío pagado siempre humanos.

## Persistencia y compatibilidad

La v2 escribe sin tocar los históricos existentes:

```text
user/ads_art/projects/<project_id>/
  creative_project.json
  analysis/reference/latest.json
  analysis/creative_intelligence/master.json
  analysis/creative_intelligence/cache/<fingerprint>.json
  analysis/creative_intelligence/state/<fingerprint>.json
  analysis/creative_intelligence/manual_overrides/<shot_id>.json
  adaptation/original_adaptation.json
  frames/reference_evidence/<fingerprint>/
  shots/original_plan.json
  requests/ jobs/ results/ montages/
```

Los registros y cachés Gemini 2.5/3.6 anteriores no se migran ni sobrescriben. El
sincronizador v2 importa las `identity_notes`, identidad aprobada y controles v1 cuando
se instala por primera vez, y luego preserva los widgets v2 por nombre.

```powershell
& ..\..\venv_comfy\Scripts\python.exe .\scripts\build_creative_workflow_v2.py
& ..\..\venv_comfy\Scripts\python.exe .\scripts\sync_creative_workflow_v2.py
```

## Transporte Higgsfield

Los nodos de generación continúan usando el CLI oficial de Higgsfield; no existe un
cliente MCP dentro de ComfyUI. Preparación, validación y persistencia son locales. Sólo
**Submit Job (Explicit)** puede ejecutar upload/cost/create y únicamente tras
confirmación explícita. Un envío incierto no se repite.

## Autenticación y pruebas

Defina `GEMINI_API_KEY` sólo en el proceso privado que inicia ComfyUI. Nunca la escriba
en el workflow, Git o logs.

```powershell
& ..\..\venv_comfy\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
```

La migración v2 se validó localmente con fixtures/mocks y sin otra llamada Gemini, sin
uploads Higgsfield y sin generaciones de pago. Los informes remotos históricos se
conservan en `GEMINI_TEST_REPORT_2026-09-06.md` y
`GEMINI_36_TEST_REPORT_2026-09-06.md`.
