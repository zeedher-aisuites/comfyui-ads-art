# Ads Art — ComfyUI + Gemini + Higgsfield

Primera versión funcional de un flujo por tomas para recrear un comercial con una identidad hiperrealista derivada de una obra de arte. ComfyUI controla preparación, revisión, persistencia, envío, consulta y montaje; Higgsfield sólo recibe solicitudes cuando el usuario activa una confirmación explícita.

## Entorno verificado

- La carpeta padre de `custom_nodes/` es la raíz ejecutable de ComfyUI.
- Instale este repositorio como `custom_nodes/ComfyUI-Ads-Art` sin mover el resto de ComfyUI.
- ComfyUI: 0.21.1, Python 3.14.5, PyTorch 2.11.0+cu128
- Dependencias activas cargadas desde `venv_comfy\Lib\site-packages`
- Higgsfield CLI oficial: 1.1.23, instalado en `%LOCALAPPDATA%\hermes\node`
- El CLI está autenticado. Ads Art nunca solicita ni registra el token.
- PyAV está disponible para metadatos, detección visual de tomas y extracción de frames.
- El análisis semántico opcional usa el SDK oficial Google Gen AI y el identificador
  exacto `gemini-2.5-flash`. La preparación local no requiere clave ni llamada remota.

`ffmpeg` no estaba en `PATH` durante la instalación. El nodo de montaje también busca la copia de CapCut detectada y admite una ruta explícita mediante `ADS_ART_FFMPEG`. El resto del sistema no depende de `ffmpeg`.

## Análisis Gemini

**Gemini Commercial Analysis** recibe el video, la identidad aprobada opcional, los
cuatro controles del proyecto, los 31 conceptos cinematográficos, el máximo de tomas y
el modo de adaptación. Devuelve JSON estructurado con observaciones separadas de las
propuestas creativas. Los timestamps se validan contra la duración real y el detector
local de cortes; Ads Art examina frames cercanos para evitar transiciones y preferir
muestras nítidas.

El modelo está fijado a `gemini-2.5-flash`; no existe alias ni fallback. La clave sólo
se toma de `GEMINI_API_KEY` en el entorno privado que inicia ComfyUI. Consulte
[`GEMINI_INTEGRATION.md`](GEMINI_INTEGRATION.md) para esquema, caché, costes,
configuración y evidencia documental.

## Transporte real de Higgsfield

Esta versión **usa el CLI oficial de Higgsfield; no contiene un cliente MCP**. `ads_art_core.py` ejecuta directamente `node.exe` con el script instalado de `@higgsfield/cli`, evitando el shim `.cmd` cuando está disponible.

- Autenticación: `account status` comprueba la sesión local y devuelve saldo/plan sin conservar el correo ni solicitar el token.
- Catálogo: `model get nano_banana_pro` y `model get seedance_2_5`; se repite justo antes de enviar.
- Preparación: completamente local; compila prompts, valida aprobaciones/medios y escribe el request. No llama a Higgsfield.
- Envío: `upload create`, `generate cost` y una sola llamada `generate create`, únicamente con `confirm_paid_submission=true`.
- Consulta: `generate get <job_id>` una vez por ejecución de **Poll Job**.
- Descarga: Python descarga las URLs finales devueltas por el job a `user/ads_art/projects/<project_id>/results/`.

Las herramientas MCP visibles para el agente se usaron sólo para contrastar el catálogo y la autenticación durante desarrollo; los nodos de ComfyUI no pueden invocarlas. Para cumplir el requisito MCP original falta una interfaz MCP local documentada (transporte, autenticación y contrato de herramientas) que ComfyUI pueda usar. Cuando exista, podrá añadirse otro transporte conservando el esquema y las validaciones actuales.

## Workflow versionado e instalado

- Copia portable y versionada: `workflows/ads_art_prepare_v1.json`.
- Copia instalada de ComfyUI: `../../user/default/workflows/Ads Art/ads_art_prepare_v1.json`.

La copia instalada queda fuera de este repositorio. Para actualizarla desde la versión
controlada sin perder `identity_notes`, IDs de jobs ni otros widgets personales, ejecute
desde la raíz de este repositorio:

```powershell
& ..\..\venv_comfy\Scripts\python.exe .\scripts\sync_workflow.py
```

El sincronizador conserva nodos instalados adicionales y fuerza de nuevo a `false`
todo envío de pago y toda confirmación Gemini.

## Uso breve

1. Reinicie ComfyUI y cargue `workflows/ads_art_prepare_v1.json`. El workflow abre con análisis/revisión activos y las fases posteriores desactivadas; habilite sólo la fase que esté revisando para respetar las aprobaciones entre etapas.
2. En **Project & Conflicts**, introduzca los cuatro controles. Corrija cualquier conflicto con nivel `ERROR`; las sugerencias creativas nunca anulan restricciones explícitas.
3. En **Gemini Commercial Analysis**, indique una ruta absoluta o un archivo de
   `input`, elija el modo y limite tomas. Con `confirm_gemini_analysis=false`, ejecute el
   preflight local y revise cortes/candidatos. Configure `GEMINI_API_KEY` fuera del
   workflow y active la confirmación sólo cuando decida hacer el análisis remoto.
4. En **Gemini Shot Draft & Manual Overrides**, seleccione una toma. Los campos
   `manual_*` no vacíos prevalecen y sobreviven a reanálisis; el frame sigue sin aprobar.
5. Cargue la obra y ejecute **Prepare Identity**. Revise la solicitud. Sólo active `confirm_paid_submission` en **Submit Job** cuando decida generar.
6. Recupere el registro mediante **Recover Job Record** y consulte el mismo job con **Poll Job**. Cargue y apruebe visualmente la identidad descargada.
7. Use **Plan & Prepare Frame** por toma. Un borrador Gemini conectado llena valores
   vacíos; cualquier texto manual no vacío gana. La solicitud permanece bloqueada hasta
   aprobar identidad y frame fuente.
8. Apruebe cada frame recreado y use **Prepare Seedance Shot**. Describa lo que
   realmente aparece en él en `approved_frame_observations` y ajuste el movimiento en
   `seedance_prompt_adjustments`. `auto` evita asumir que 4:5 sea formato de video.
9. Genere y consulte cada toma por separado. Las tomas aceptadas conservan su job y no se repiten.
10. Pase las rutas de clips seleccionados, una por línea, a **Assemble Clips**. `original` reutiliza el audio del comercial sólo en el montaje local.

## Garantías aplicadas en código

- Imágenes: exactamente `nano_banana_pro`, `4:5`, `2k`.
- Video: exactamente `seedance_2_5`, modo `omni_reference`.
- Seedance: sólo archivos de imagen con roles `image`, `start_image` y `end_image`.
- `video`, `audio`, `video_edit`, `video_extension` y formato de video `4:5` se bloquean antes del envío.
- `positive`, `restrictive`, `negative` y `creative` son controles internos compilados dentro del prompt. Nunca se inventa un parámetro nativo `negative_prompt`.
- El catálogo local se consulta de nuevo justo antes de un envío.
- El envío se realiza una sola vez. Un timeout queda como `submission_unknown` y no se reintenta automáticamente.
- Uploads y consultas tienen reintentos limitados; generación no.
- Los prompts no se imprimen en logs y los secretos no se guardan en código ni workflows.
- Gemini usa una huella del video, identidad, controles y configuración para reutilizar
  análisis idénticos. Una inferencia incierta no se repite automáticamente.
- Toda respuesta Gemini se valida por esquema y timestamps; ninguna aprobación visual
  se infiere automáticamente.

## Envío, recuperación y reanudación

Cada ejecución de **Submit Job** guarda primero `jobs/<request_id>.json`. Si ya contiene `job_id`, devolverá ese registro y no creará otro. Si el envío quedó como `submission_unknown`, la misma request queda bloqueada para impedir un reintento potencialmente duplicado.

Para recuperar un trabajo:

1. Copie `request_id` y `job_id` de la salida del nodo o del JSON en `user/ads_art/projects/<project_id>/jobs/`.
2. Habilite **Recover Job Record** y **Poll Job**, que vienen desactivados.
3. En **Recover Job Record**, use `request_id` para cargar el registro persistido. Si sólo conoce el job ID, deje `request_id` vacío y escriba `job_id`, `shot_id` y `stage`.
4. Ejecute **Poll Job**. Cada ejecución hace una consulta no bloqueante. Repítala hasta `completed`, `failed`, `canceled`, `nsfw` o `ip_detected`.
5. Con `download_completed=true`, un estado `completed` descarga automáticamente los archivos y devuelve sus rutas.
6. Para resultados de imagen, habilite **Load Image Result** y **Preview Image**. Para video, use la ruta `.mp4` devuelta en el montaje.

Si no se obtuvo job ID por un timeout, ejecute `higgsfield generate list`, identifique el trabajo sin reenviarlo y registre ese ID en **Recover Job Record**.

Pasos exactos para la primera generación real de identidad:

1. Complete proyecto, análisis y revisión del frame; corrija todos los errores de contradicción.
2. Habilite **Prepare Identity**, cargue la obra y revise el prompt preparado.
3. Habilite su **Submit Job**, deje `minimum_credits_after` en el límite deseado y cambie `confirm_paid_submission` a `true` sólo para esa ejecución.
4. Anote `request_id`/`job_id` del registro y vuelva inmediatamente `confirm_paid_submission` a `false`.
5. Recupere y consulte el job con los pasos anteriores hasta `completed`; no vuelva a ejecutar una solicitud nueva para intentar consultarlo.
6. Revise visualmente la imagen descargada. Sólo después cargue esa imagen como **Approved generated identity** y active `identity_approved` para preparar el primer frame.
7. Repita el mismo ciclo para el frame y después para Seedance. El video original y su audio nunca se envían a Seedance.

## Persistencia

Cada proyecto se guarda en `user/ads_art/projects/<project_id>/`:

- `project.json`: controles y conflictos.
- `analysis/commercial.json`: datos verificados, interpretaciones manuales y tomas.
- `analysis/gemini/`: preflights, respuestas validadas, huellas y overrides manuales.
- `frames/`: frames originales/revisados.
- `references/`: identidad y referencias por toma.
- `shots/<shot_id>/plan.json`: plan editorial explícito.
- `requests/`: prompt, parámetros, referencias y aprobaciones.
- `jobs/`: job ID, estado, coste estimado y resultados.
- `results/` y `montages/`: archivos recuperados y registros de montaje.

## Separación de transportes

Gemini se integra mediante el SDK oficial Google Gen AI. Higgsfield continúa usando su
CLI oficial y no existe un puente MCP dentro de ComfyUI. Son transportes independientes:
Gemini prepara el plan; los envíos de generación siguen sujetos a las protecciones y
confirmaciones de Higgsfield descritas arriba.

## Archivos

- `ads_art_core.py`: políticas, persistencia, CLI y protección contra duplicados.
- `ads_art_gemini.py`: transporte Google Gen AI, esquema, validación, uso y coste estimado.
- `ads_art_nodes.py`: 14 nodos ComfyUI, incluidos análisis Gemini y borrador editable.
- `knowledge/ads_art_camera_knowledge_v1.json`: catálogo editorial adjunto, 31 conceptos.
- `knowledge/higgsfield_catalog_snapshot_v1.json`: evidencia offline; no sustituye la consulta vigente.
- `workflows/ads_art_prepare_v1.json`: workflow importable de preparación, con envíos desactivados.
- `scripts/sync_workflow.py`: actualiza la copia instalada conservando widgets personales.
- `tests/test_ads_art.py`: restricciones, Gemini local, conocimiento y conexiones del workflow.

## Pruebas que requieren medios o autorización

La integración y el preflight Dior se probaron sin llamadas remotas. El SDK
`google-genai==2.22.0` ya quedó instalado y sus interfaces usadas por Ads Art fueron
comprobadas localmente. Se detectó `GEMINI_API_KEY` sin leer su valor, pero no se probó
la autenticación efectiva. Para el primer análisis Gemini real falta reiniciar ComfyUI
asegurando que herede esa variable y activar una sola vez
`confirm_gemini_analysis`. No se lanzó ninguna generación Higgsfield. El montaje sigue
necesitando clips resultantes reales y un `ffmpeg` compatible.
