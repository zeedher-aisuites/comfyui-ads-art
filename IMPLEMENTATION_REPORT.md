# Informe de implementación — Ads Art Gemini 3.6

Fecha de verificación: 2026-09-06

## Resultado

Ads Art incorpora una integración funcional con Gemini para analizar el comercial,
proponer hasta el número configurado de tomas, generar borradores de prompts de frame y
movimiento y conectarlos con los planificadores existentes. La migración explícita está
fijada a `gemini-3.6-flash`; no hay alias, sustitución ni fallback silencioso.

El intento anterior con `gemini-2.5-flash` se conserva como fallo histórico separado.
Después de comprobar el catálogo con la misma credencial, Ads Art ejecutó una sola
inferencia autorizada de `gemini-3.6-flash` mediante el nodo de ComfyUI. Terminó con tres
tomas y tres frames locales, sin reintentos y sin generaciones Higgsfield.

## Implementado

- Transporte Gemini mediante el SDK oficial `google-genai`, cargado sólo al confirmar
  una llamada remota.
- Autenticación exclusiva con `GEMINI_API_KEY` del entorno; no existe campo de clave en
  el nodo ni persistencia del secreto.
- Prompt versionado `ads_art_gemini_commercial_v2` con los cuatro controles del proyecto,
  catálogo completo de 31 conceptos, evidencia del detector local, máximo de tomas y
  modo fiel/creativo.
- Esquema JSON estricto que separa `observed` de `proposal` y exige timestamps,
  candidatos, motivo, objetivo, acción, encuadre, luz, cámara, cambios, prompts,
  dirección Seedance, incertidumbres y contradicciones.
- Validación de intervalos contra la duración real, candidatos dentro de su toma e IDs
  cinematográficos contra el catálogo local.
- Detector local de cortes y selección de frame desde el video original. Se revisan
  muestras cercanas, se evita una zona de 0.18 s alrededor de cortes cuando hay
  alternativa y se compara una métrica local de nitidez.
- Estado visible y salida de frames en ComfyUI. El nodo de borrador muestra motivo,
  campos y prompts, y expone widgets editables por toma.
- Overrides manuales persistentes: un campo no vacío gana sobre Gemini y se conserva si
  el análisis se ejecuta otra vez.
- Conexión del borrador al planificador Nano Banana Pro. Los widgets manuales del
  planificador continúan teniendo precedencia.
- Campos posteriores a aprobación en el planificador Seedance para describir el frame
  recreado real y ajustar actuación/movimiento antes de preparar video.
- Caché por SHA-256 y configuración completa. Una coincidencia terminada se reutiliza;
  una llamada incierta queda bloqueada para impedir duplicados. El modelo exacto forma
  parte de la huella, de modo que el intento 2.5 no colisiona con el resultado 3.6.
- Preflight remoto del descriptor exacto mediante `models.get`; exige
  `models/gemini-3.6-flash` y la acción `generateContent` antes de subir el video.
- Configuración específica de Gemini 3.6: structured output, video estático a 2 FPS,
  `thinking_level=low` y `max_output_tokens=8192`; no conserva `thinking_budget`,
  `temperature` ni precios del modelo anterior.
- Una sola inferencia por intento confirmado, un intento de subida, sondeo acotado del
  archivo y eliminación best effort del archivo remoto.
- Registro privado de modelo, versiones, parámetros, prompt, respuesta, timings, uso de
  tokens, coste estimado y verificaciones locales.
- Workflow portable actualizado y sincronizador que preserva widgets personales al
  refrescar el workflow instalado.

## Restricciones conservadas

- Nano Banana Pro permanece exactamente en `nano_banana_pro`, `4:5`, `2k`.
- Seedance permanece en `seedance_2_5`, modo `omni_reference`.
- Seedance sólo recibe roles de imagen y texto. El comercial y su audio nunca aparecen
  en los medios de una solicitud Seedance.
- No se infiere aprobación de identidad, frame fuente ni frame recreado.
- Los tres nodos Higgsfield de envío permanecen desactivados y con
  `confirm_paid_submission=false`.
- El nodo Gemini instalado permanece con `confirm_gemini_analysis=false` y el override
  de reintento incierto también está desactivado.
- La integración Higgsfield sigue usando su CLI oficial; implementar Gemini no crea ni
  implica un puente MCP.

## Pruebas ejecutadas realmente

- Compilación de `ads_art_core.py`, `ads_art_gemini.py` y `ads_art_nodes.py`.
- SDK `google-genai==2.22.0` en `venv_comfy`; verificación de las firmas
  `files.upload/get/delete`, `models.get`, `models.generate_content`,
  `response_json_schema`, `ThinkingConfig` y `VideoMetadata`.
- 30 pruebas automatizadas: políticas de imagen/video, anti-duplicado, recuperación,
  detector local, modelo y esquema Gemini, timestamps, configuración 3.6, preflight de
  catálogo, coste y separación de audio, clave ausente, preflight local sin llamadas,
  persistencia de overrides, actualización Seedance y sincronización segura.
- Fixture sintético de dos planos: corte detectado y frames extraídos.
- Preflight real del comercial Dior copiado a `ComfyUI/input`:

  - 11,081,299 bytes, duración 40.0 s y 1280 × 720;
  - SHA-256 idéntico a la fuente conservada;
  - 17 cortes locales detectados;
  - máximo de tres propuestas;
  - estado local `prepared_not_called`, `remote_calls=0`.

- La copia de Madame X coincide por SHA-256 con el resultado aprobado conservado en el
  proyecto. El workflow preserva exactamente sus `identity_notes` y los IDs de la
  generación de identidad anterior.
- La instancia habitual detectó `GEMINI_API_KEY` sin leer ni registrar su valor.
- Intento histórico mediante el nodo 23 con `gemini-2.5-flash`:

  - ID `b7007d5e-660b-47a4-941b-412fd917c60c`;
  - Files API aceptó el video, pero un único `generateContent` respondió 404;
  - archivo remoto eliminado, sin uso reportado ni reintento;
  - estado conservador separado `analysis_unknown`.

- Consulta previa del catálogo, con la misma credencial y configuración que ComfyUI:

  - `models/gemini-3.6-flash` disponible;
  - acciones `generateContent`, `countTokens`, `createCachedContent` y
    `batchGenerateContent`;
  - límites de 1,048,576 tokens de entrada y 65,536 de salida;
  - la comprobación no subió ningún medio.

- Una sola ejecución real con `gemini-3.6-flash` mediante el nodo 23:

  - ID de prompt ComfyUI `69e8cc9a-0384-474f-b495-533d5825b9f2`;
  - disponibilidad 0.484 s, subida 11.195 s, procesamiento 6.654 s e inferencia
    22.746 s;
  - etapa remota total 41.095 s, extracción 6.070 s y nodo completo 63.179 s;
  - 14,303 tokens de entrada, 1,545 de salida y thinking no desglosado por el
    proveedor;
  - tres tomas/frames extraídos a 8.2 s, 24.8 s y 34.0 s;
  - archivo remoto eliminado, sin reintento y todas las aprobaciones en `false`.

## Costes y medición

La tarifa Standard documentada para Gemini 3.6 Flash, vigente hasta 2026-12-31, es USD
0.75/M tokens de entrada para todas las modalidades y USD 3.75/M tokens de salida,
incluido thinking. La estimación se calcula únicamente tras recibir uso reportado;
`observed_charge_usd` permanece separado y `null` porque una respuesta de inferencia no
prueba el cargo de facturación.

El proveedor reportó 14,303 tokens de entrada. Conservamos su desglose original
(`IMAGE=1110`, `TEXT=6914`, `VIDEO=6279`) y, para no contabilizar audio como video,
registramos aparte la estimación documentada de 32 tokens de audio/s: 1,280 tokens de
audio y 4,999 de video visual. Audio y video usan la misma tarifa de entrada del modelo.
Con 1,545 tokens de salida, el coste estimado total es USD 0.016521. Thinking no fue
desglosado; no se afirma que sea cero. No hay cargo observado.

## Qué falta probar

- Revisión visual humana y eventual aprobación de una de las tres propuestas. La toma 1
  tiene gafas oscuras y no cumple completamente la preferencia de rostro despejado; se
  dejó marcada para revisión, no aprobada.
- Aprobar un frame y comprobar el ciclo Gemini → planificador → Nano Banana Pro sólo
  cuando exista una autorización de generación independiente.
- El débito real de facturación: USD 0.016521 es una estimación derivada de tokens, no un
  cargo observado.
- Ningún envío o consulta Higgsfield se ejecutó en esta migración; sus registros
  históricos se conservaron sin tocarlos.

## Reutilización segura

Con `reuse_matching_analysis=true`, ejecutar la rama con confirmación desactivada muestra
el resultado ya validado sin subir medios ni generar otro cargo. Si una llamada futura
queda incierta, no se repite automáticamente: se revisa primero el registro privado.
