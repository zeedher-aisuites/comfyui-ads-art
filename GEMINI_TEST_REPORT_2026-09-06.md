# Primera prueba remota de Gemini — 2026-09-06

> Registro histórico del intento con Gemini 2.5. La migración autorizada y la primera
> prueba completada con Gemini 3.6 están documentadas en
> [`GEMINI_36_TEST_REPORT_2026-09-06.md`](GEMINI_36_TEST_REPORT_2026-09-06.md).

## Resultado

La instancia habitual de ComfyUI aceptó una única ejecución del nodo
**Ads Art — Gemini Commercial Analysis**. Google aceptó la subida del comercial y lo
marcó disponible, pero la llamada de inferencia terminó con este mensaje íntegro, que no
contiene ningún secreto:

```text
404 NOT_FOUND. {'error': {'code': 404, 'message': 'This model models/gemini-2.5-flash is no longer available to new users. Please update your code to use models/gemini-3.6-flash for the latest features and improvements. We recommend you to use the Interactions API.', 'status': 'NOT_FOUND'}}
```

Quedó confirmado por Google el código 404, el estado `NOT_FOUND`, que 2.5 ya no está
disponible para “new users” y las dos recomendaciones explícitas. Que la política de
“new users” se aplicó a esta credencial es una inferencia a partir de haber recibido ese
mensaje; el error no expone por separado la clasificación interna de la cuenta. Tampoco
confirmaba por sí mismo la disponibilidad de 3.6, su compatibilidad ni que Interactions
fuera el único método permitido.

Ads Art no sustituyó el modelo, no repitió la inferencia y eliminó el archivo remoto.
Por tanto, esta ejecución no produjo tomas semánticas, prompts ni frames seleccionados
por Gemini.

## Controles previos

- ComfyUI reconoció `AdsArtGeminiAnalyzeCommercial` y `AdsArtGeminiShotDraft`.
- El proceso recibió `GEMINI_API_KEY`; sólo se comprobó su presencia y nunca se leyó,
  mostró ni registró su valor.
- Modelo exacto: `gemini-2.5-flash`, sin alias ni fallback.
- Comercial: 40.0 s, 1280 × 720, AAC estéreo a 44.1 kHz.
- Identidad aprobada de Madame X conectada y verificada por huella.
- Máximo de tres tomas; modo `faithful_reference`.
- Detector local: 6 FPS. Muestreo enviado en `VideoMetadata`: 2 FPS.
- `max_output_tokens=8192` y `thinking_budget=2048`.
- El audio viajó dentro del archivo de video para el análisis multimodal. La
  contabilización implementada usa la modalidad `AUDIO` a su tarifa propia y nunca la
  suma como entrada de video.
- La firma `c6a3185741a64aea8964a8dd2189b0c537f99ccbff6ec9c0d9d6a4c384ba8d9b`
  no tenía caché ni marcador antes del envío.

## Ejecución única

- ID de ComfyUI: `b7007d5e-660b-47a4-941b-412fd917c60c`.
- Inicio de ejecución: `2026-09-06T04:57:55.329-06:00`.
- Inicio de la etapa remota: `2026-09-06T04:58:06.587-06:00`.
- Fallo detectado: `2026-09-06T04:58:28.426-06:00`.
- Intentos de inferencia: 1.
- Reintentos automáticos de inferencia: 0.
- Files API: subida aceptada, procesamiento consultado y archivo remoto eliminado.
- Generate Content: una solicitud; respuesta `404 NOT_FOUND` antes de generar contenido.

## Tiempos y uso

| Medida | Resultado |
|---|---:|
| Preflight local antes de la etapa remota | 11.258 s |
| Etapa remota total hasta detectar el fallo | 21.838 s |
| Ejecución total de ComfyUI | 33.195 s |
| Extracción posterior de frames elegidos por Gemini | no ejecutada |

La ruta de excepción de esta versión no conservó por separado los segundos de subida y
procesamiento del archivo; sólo quedó el total de la etapa remota y la secuencia HTTP.
Gemini no devolvió `usageMetadata`, por lo que tokens de entrada, audio, salida y
thinking son `null`. El coste estimado por uso real también es `null`, y no existe un
cargo observado desde la API de inferencia. Esto no equivale a una comprobación del
estado de facturación de la cuenta.

## Estado visible y seguridad final

Al no existir respuesta Gemini, ComfyUI muestra el error en el nodo 23. Los únicos
frames disponibles siguen siendo los candidatos del preflight local a 1.72 s, 20.60 s
y 39.28 s; no son elecciones semánticas de Gemini y permanecen sin aprobación.

El workflow instalado conserva `confirm_gemini_analysis=false`,
`allow_retry_after_unknown=false`, las tres confirmaciones Higgsfield en `false` y las
ramas de generación desactivadas. No hubo llamadas ni generaciones de Higgsfield.

Para continuar hace falta autorizar explícitamente un identificador de modelo distinto.
La respuesta del proveedor recomendó `gemini-3.6-flash`, pero Ads Art no lo adopta sin
verificar antes documentación, entradas multimodales, structured output, thinking y
tarifas vigentes, y sin una nueva autorización del usuario.
