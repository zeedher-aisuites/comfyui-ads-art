# Integración Gemini de Ads Art

Fecha de verificación documental: 2026-09-06

## Modelo y transporte

Ads Art solicita exactamente `gemini-2.5-flash` mediante el SDK oficial de Google
Gen AI para Python (`google-genai>=2.22.0,<3`). No usa el alias `latest`, no cambia de
modelo si falla y no contiene fallback silencioso.

La documentación oficial del modelo declara entradas de texto, imagen, video y audio,
salida de texto y soporte de structured outputs:

- <https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash>
- <https://ai.google.dev/gemini-api/docs/structured-output>
- <https://ai.google.dev/gemini-api/docs/video-understanding>
- <https://ai.google.dev/api/files>

El módulo `ads_art_gemini.py` usa Files API para el video, una parte de imagen inline
para la identidad aprobada y `response_json_schema` para la respuesta. La inferencia
tiene una sola llamada y no se reintenta. La subida admite como máximo dos intentos;
el sondeo de procesamiento del archivo también está acotado. El archivo remoto se
elimina en best effort al finalizar.

## Autenticación privada

El proceso que inicia ComfyUI debe recibir `GEMINI_API_KEY` en su entorno. El nodo no
lee claves desde el workflow, no las acepta como widget y nunca las guarda en prompts,
respuestas, registros ni Git.

Ejemplo para una sesión privada de PowerShell, introduciendo el valor sólo en esa
terminal y sin guardarlo en el historial del proyecto:

```powershell
$env:GEMINI_API_KEY = Read-Host -MaskInput 'GEMINI_API_KEY'
& .\venv_comfy\Scripts\python.exe .\main.py
```

Instale el SDK en el mismo entorno de ComfyUI antes de activar una llamada:

```powershell
& .\venv_comfy\Scripts\python.exe -m pip install -r .\custom_nodes\ComfyUI-Ads-Art\requirements.txt
```

La preparación local funciona sin el SDK y sin clave. `confirm_gemini_analysis=false`
garantiza que el nodo no intente red, subida ni inferencia.

## Nodo de análisis

**Ads Art — Gemini Commercial Analysis** recibe proyecto, video local, modelo fijo,
modo `faithful_reference` o `creative_reinterpretation`, máximo de tomas, parámetros
del detector local, aprobación explícita de identidad y una identidad opcional.

El prompt incluye los cuatro controles del proyecto, los 31 conceptos cinematográficos,
la duración y cortes observados localmente, y estas reglas:

- observación del comercial y propuesta creativa son objetos JSON distintos;
- las instrucciones explícitas del usuario prevalecen;
- datos de producto no definidos se registran como faltantes, no se inventan;
- ningún frame queda aprobado por inferencia;
- Nano Banana Pro permanece en `4:5` y `2k`;
- Seedance sólo puede recibir imágenes aprobadas y texto, nunca el video ni audio fuente.

Por toma, el esquema exige ID, inicio/fin, candidatos, descripción observada, motivo,
objetivo, acción, encuadre, iluminación, IDs del catálogo, listas de conservar/eliminar/
sustituir, prompt Nano Banana Pro, dirección Seedance e incertidumbres/contradicciones.
La validación rechaza intervalos fuera de la duración y candidatos fuera de su toma.

Después de la respuesta, Ads Art comprueba candidatos cercanos (`±0.30 s`), evita los
que queden a menos de `0.18 s` de un corte cuando hay alternativa, compara nitidez y
extrae el frame elegido desde el archivo original. Todo resultado conserva
`review.approved=false` hasta la acción del usuario.

## Edición, caché y reanudación

**Ads Art — Gemini Shot Draft & Manual Overrides** transforma una toma en los campos
del planificador. Un `manual_*` no vacío gana sobre Gemini y se guarda en
`analysis/gemini/manual_overrides/<shot_id>.json`; una reejecución con widgets vacíos
recupera esos cambios.

La huella de caché incluye SHA-256 del video y la identidad, cuatro controles,
conocimiento, modelo exacto, versión del prompt, esquema, detector, límite de tomas y
modo de adaptación. Una respuesta completa con la misma huella se reutiliza. Un estado
`analysis_started` o `analysis_unknown` bloquea repeticiones; sólo puede reintentarse
tras revisión manual activando el override explícito.

Antes de preparar Seedance, el usuario puede añadir observaciones sobre el frame
recreado ya aprobado y ajustes posteriores. Esos campos se compilan en el prompt que
describe lo que realmente aparece en la imagen, sin adjuntar el comercial ni su audio.

## Registros y costes

El registro privado por análisis conserva identificador y versión del modelo, parámetros,
versión del prompt, instrucciones de sistema, respuesta JSON, tiempos de subida/
procesamiento/inferencia, uso de tokens reportado y resultado de validaciones locales.

La estimación monetaria sólo se calcula después de recibir tokens reportados. Usa la
tarifa Standard verificada para Gemini 2.5 Flash: USD 0.30 por millón de tokens de
entrada de texto/imagen/video y USD 2.50 por millón de tokens de salida, incluido
thinking. Se etiqueta como estimación; `observed_charge_usd` queda `null` porque la
respuesta de generación no constituye una factura.

Fuente: <https://ai.google.dev/gemini-api/docs/pricing>

## Preflight Dior preparado

El workflow instalado referencia `J' ADORE - DIOR.mp4` y la copia de la identidad
aprobada `Ads Art - Madame X approved.png`
desde `ComfyUI/input`. Está limitado a tres tomas y conserva
`confirm_gemini_analysis=false`.

El preflight local real midió 40.0 s, 1280 × 720, detectó 17 cortes y extrajo tres
candidatos a 1.72 s, 20.60 s y 39.28 s. No ejecutó llamadas remotas; los tres siguen
pendientes de revisión visual.
