# Integración Gemini de Ads Art

Fecha de verificación documental: 2026-09-06

## Modelo y transporte

Ads Art solicita exactamente `gemini-3.6-flash` mediante el SDK oficial de Google
Gen AI para Python (`google-genai>=2.22.0,<3`). No usa el alias `latest`, no cambia de
modelo si falla y no contiene fallback silencioso.

La documentación oficial del modelo declara entradas de texto, imagen, video y audio,
salida de texto y soporte de structured outputs:

- <https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash>
- <https://ai.google.dev/gemini-api/docs/structured-output>
- <https://ai.google.dev/gemini-api/docs/video-understanding>
- <https://ai.google.dev/api/files>

El módulo `ads_art_gemini.py` usa Files API para el video, una parte de imagen inline
para la identidad aprobada y `response_json_schema` para la respuesta. Antes de subir
medios consulta el descriptor exacto con la misma credencial y exige que el catálogo
devuelva `models/gemini-3.6-flash` con la acción `generateContent`. El catálogo real de
esta cuenta confirmó esa acción; Interactions API es una alternativa recomendada por
Google, no un requisito exclusivo para este modelo.

La inferencia tiene una sola llamada y no se reintenta. El workflow establece un solo
intento de subida; el sondeo de procesamiento del archivo está acotado. El archivo
remoto se elimina en best effort al finalizar.

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
garantiza que el nodo no intente red, catálogo, subida ni inferencia. Al confirmar, la
consulta de disponibilidad ocurre primero y registra explícitamente que aún no se ha
subido ningún medio.

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
`analysis_started`, `analysis_failed` o `analysis_unknown` bloquea repeticiones; sólo
puede reintentarse tras revisión manual activando el override explícito.

Antes de preparar Seedance, el usuario puede añadir observaciones sobre el frame
recreado ya aprobado y ajustes posteriores. Esos campos se compilan en el prompt que
describe lo que realmente aparece en la imagen, sin adjuntar el comercial ni su audio.

## Registros y costes

El registro privado por análisis conserva identificador y versión del modelo, parámetros,
versión del prompt, instrucciones de sistema, respuesta JSON, tiempos de subida/
procesamiento/inferencia, uso de tokens reportado y resultado de validaciones locales.

La estimación monetaria sólo se calcula después de recibir tokens reportados. Usa la
tarifa Standard vigente de Gemini 3.6 Flash hasta el 31 de diciembre de 2026: USD 0.75
por millón de tokens de entrada para todas las modalidades y USD 3.75 por millón de
tokens de salida, incluido thinking. Aunque la tarifa de entrada es común, los tokens
de audio se muestran separados de video. Si el proveedor omite `AUDIO`, la estimación
marca y aplica el cálculo documental de 32 tokens de audio por segundo, restándolo del
grupo de video informado. Se etiqueta como estimación;
`observed_charge_usd` queda `null` porque la respuesta de generación no constituye una
factura.

Fuente: <https://ai.google.dev/gemini-api/docs/pricing>

## Preflight Dior preparado

El workflow instalado referencia `J' ADORE - DIOR.mp4` y la copia de la identidad
aprobada `Ads Art - Madame X approved.png`
desde `ComfyUI/input`. Está limitado a tres tomas y conserva
`confirm_gemini_analysis=false`.

El preflight local real midió 40.0 s, 1280 × 720, detectó 17 cortes y extrajo tres
candidatos a 1.72 s, 20.60 s y 39.28 s. No ejecutó llamadas remotas; los tres siguen
pendientes de revisión visual.

## Intento histórico con Gemini 2.5

El 2026-09-06 se confirmó una sola ejecución sobre Dior. Files API aceptó y procesó el
video, pero `generateContent` respondió `404 NOT_FOUND` e indicó que
`gemini-2.5-flash` ya no estaba disponible para “new users”. Inferimos que esa política
se aplicó a esta credencial; el error no reveló una clasificación de cuenta separada.
No hubo fallback, reintento ni respuesta estructurada; el archivo remoto se eliminó. El workflow volvió a
`confirm_gemini_analysis=false` y el marcador conservador `analysis_unknown` bloquea
una repetición accidental.

Consulte [`GEMINI_TEST_REPORT_2026-09-06.md`](GEMINI_TEST_REPORT_2026-09-06.md) para
la cronología, tiempos, uso no reportado y estado final. Cambiar al modelo recomendado
por la respuesta del proveedor requiere verificación documental y autorización expresa;
Ads Art no sustituye el modelo silenciosamente.

## Primera prueba completada con Gemini 3.6

El mismo 2026-09-06, tras autorización expresa, el catálogo autenticado confirmó
`models/gemini-3.6-flash`, `generateContent`, entrada máxima de 1,048,576 tokens y salida
máxima de 65,536. Ads Art migró a `thinking_level=low`, eliminó el parámetro obsoleto
`temperature`, limitó salida a 8,192 tokens y mantuvo procesamiento estático a 2 FPS.

Una única inferencia sobre Dior terminó correctamente y devolvió tres tomas. Se
registraron 14,303 tokens de entrada, 1,545 de salida y thinking no reportado. La
estimación Standard fue USD 0.016521; no es un cargo observado. Consulte
[`GEMINI_36_TEST_REPORT_2026-09-06.md`](GEMINI_36_TEST_REPORT_2026-09-06.md) para la
evidencia completa.
