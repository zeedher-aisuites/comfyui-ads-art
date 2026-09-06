# Informe de implementación — Ads Art v1

Fecha de verificación: 2026-09-06

## Implementado

- Extensión aislada en `custom_nodes/ComfyUI-Ads-Art`; no se modificó el núcleo de ComfyUI ni ningún workflow existente.
- Registro de proyecto con los cuatro controles de prompt, detección previa de contradicciones y precedencia de restricciones explícitas sobre creatividad.
- Análisis local del comercial con PyAV: duración, dimensiones, FPS, pistas de audio, detección de cambios visuales, timestamps y extracción de frames representativos.
- Revisión, aprobación y sustitución de cada frame por timestamp o por otra imagen.
- Preparación de identidad con Nano Banana Pro y aprobación obligatoria antes de preparar tomas.
- Planificación por toma usando IDs elegidos explícitamente de la base cinematográfica de 31 conceptos. Las láminas no se envían al proveedor.
- Preparación de frames con `nano_banana_pro`, `4:5`, `2k` bloqueados en código.
- Preparación de video con `seedance_2_5`, modo `omni_reference`, referencias exclusivamente de imagen y formato independiente.
- Separación de solicitud, envío y consulta. Cada request/job se persiste por proyecto y toma.
- Recuperación local por `request_id` persistido o por un `job_id` conocido, sin crear una nueva generación.
- Prevención de duplicados por `request_id`; un envío incierto no se reintenta automáticamente.
- Preflight de coste y reserva configurable de créditos antes de crear un job.
- Consulta no bloqueante mediante `generate get`, descarga de resultados y regeneración aislada por toma.
- Montaje local de clips con audio original por defecto, añadido después de la generación.
- Workflow ComfyUI importable con los tres interruptores de generación de pago desactivados.

## Validaciones de seguridad y contrato

- Se bloquean sustituciones de los modelos obligatorios.
- Seedance rechaza extensiones de video/audio aunque se intenten etiquetar como imagen.
- Seedance rechaza roles `video` y `audio`.
- Seedance rechaza `video_edit`, `video_extension` y cualquier modo distinto de `omni_reference`.
- Seedance rechaza `4:5`; `auto` es el valor inicial para no imponer recorte o deformación.
- La adaptación de aspecto explícita requiere una casilla de aprobación cuando no coincide con el frame.
- `negative_prompt` no se transporta como parámetro nativo: se compila dentro del prompt admitido.
- El catálogo live del CLI se consulta nuevamente antes de un envío.
- No se invoca `auth token`, no se registran secretos y los prompts no se imprimen a consola.

## Probado realmente

- JSON de conocimiento cargado y comparado estructuralmente con el adjunto: idéntico, 31 conceptos.
- 18 pruebas automatizadas en `venv_comfy`, incluidas todas las restricciones anteriores, el modo preparación sin envío, la recuperación de jobs y el bloqueo de reintentos inciertos.
- Importación de Python y compilación de los tres módulos.
- Arranque temporal de ComfyUI 0.21.1 en puerto 8190: los 11 nodos iniciales se importaron y aparecieron en `/object_info`. El nodo de recuperación añadido después queda cubierto por importación y pruebas, no por un segundo arranque del servidor.
- Validación estructural de los 22 enlaces del workflow y confirmación de que los tres nodos de envío inician en `false`; la cadena de recuperación también inicia desactivada.
- Análisis local con un fixture sintético de dos planos: se detectó el corte y se extrajeron dos frames. Esto sólo prueba la infraestructura local, no la calidad sobre un comercial real.
- Catálogo vigente contrastado por dos vías durante el desarrollo: el CLI oficial que ejecutan los nodos y, separadamente, las herramientas MCP disponibles al agente. Nano Banana Pro admite 4:5/2k y hasta 14 imágenes; Seedance 2.5 admite `auto, 21:9, 16:9, 4:3, 1:1, 3:4, 9:16`, 4–30 s y roles de imágenes de inicio/fin/referencia.
- Autenticación comprobada por CLI para la sesión que usarán los nodos. La autenticación MCP sólo se comprobó como capacidad separada del agente; no constituye el transporte de la extensión. El correo de cuenta no se conserva en el proyecto ni en este informe.

## Transporte de Higgsfield realmente implementado

Los nodos usan exclusivamente el CLI oficial `@higgsfield/cli` mediante un subproceso local de `node.exe`; no implementan ni invocan un cliente MCP. Preparar una solicitud es local. Enviar usa `upload create`, `generate cost` y `generate create`; consultar usa `generate get`; la descarga de URLs de resultados se realiza en Python. Las herramientas MCP de esta sesión se usaron únicamente como contraste externo durante el desarrollo.

Por tanto, el requisito original de un puente MCP sigue pendiente. Harían falta un servidor o cliente MCP accesible desde el proceso de ComfyUI, su transporte y autenticación documentados, y un contrato de herramientas equivalente para catálogo, upload, coste, creación y consulta. La integración CLI funcional se conserva mientras no exista ese contrato.

## No probado / requiere medios reales

- No se cargó un comercial ni una obra, porque aún no fueron proporcionados.
- No se ejecutó análisis semántico remoto. El plugin MCP de la sesión ofrece `video_analysis_create/status`, pero el CLI local 1.1.23 no documenta un comando equivalente; la v1 ofrece análisis manual editable y no inventa un endpoint.
- No se enviaron uploads, jobs de imagen ni jobs de video.
- No se consumieron créditos ni generaciones ilimitadas.
- No se probó todavía la consulta ni la descarga contra un job real de Ads Art. Sí se probaron su persistencia, recuperación y protecciones localmente.
- No se validó calidad visual, continuidad de identidad, geometría del producto, cumplimiento de prompts ni audio con resultados reales.
- El montaje final necesita clips reales compatibles. `ffmpeg` no estaba en `PATH`, aunque se detectó una copia utilizable de CapCut; también puede definirse `ADS_ART_FFMPEG`.

## Próximo paso concreto

Reiniciar la instancia habitual de ComfyUI, importar `workflows/ads_art_prepare_v1.json`, cargar un comercial corto y la obra, ejecutar sólo preparación/análisis, revisar conflictos y frames, y aprobar explícitamente identidad y primera toma antes de activar un único envío de pago.
