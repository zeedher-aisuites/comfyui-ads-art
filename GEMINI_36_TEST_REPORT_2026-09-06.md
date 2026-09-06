# Migración y primera prueba de Gemini 3.6 — 2026-09-06

## Disponibilidad y método

El error 404 histórico confirmó que Google rechazó `gemini-2.5-flash`, indicó que el
modelo ya no estaba disponible para “new users” y recomendó `gemini-3.6-flash` y la
Interactions API. Inferimos que esa política se aplicó a esta credencial; el error no
expuso por separado la clasificación interna de la cuenta. Tampoco confirmó por sí solo
que 3.6 estuviera habilitado ni que Interactions fuera obligatorio.

La consulta autenticada posterior, realizada con el mismo SDK, API key y Developer API
que usa ComfyUI, confirmó:

- `models/gemini-3.6-flash` disponible;
- acciones `generateContent`, `countTokens`, `createCachedContent` y
  `batchGenerateContent`;
- límite de entrada 1,048,576 y salida 65,536 tokens;
- ningún medio subido durante esta comprobación.

Ads Art conserva `generateContent`: el catálogo lo admite y la documentación oficial
lo muestra con Gemini 3.6 y thinking. No usa fallback de modelo.

## Configuración migrada

- Modelo exacto: `gemini-3.6-flash`.
- Prompt: `ads_art_gemini_commercial_v2`.
- Structured output: JSON Schema validado localmente y por el proveedor.
- Thinking: `thinking_level=low`; no se reutilizó `thinking_budget` de Gemini 2.5.
- Salida máxima: 8,192 tokens frente al límite del modelo de 65,536.
- `temperature` eliminado porque está obsoleto/no admitido por Gemini 3.6.
- Video: procesamiento estático, muestreo explícito a 2 FPS.
- Audio: incluido con el MP4; procesamiento documental a 1 Kbps mono y 32 tokens/s.
- Intentos: una inferencia y un intento de subida, sin reintentos automáticos.

Tarifa Standard verificada para el 2026-09-06 y vigente hasta el 2026-12-31: USD
0.75/M tokens de entrada para texto, imagen, video y audio; USD 3.75/M tokens de salida,
incluido thinking. La estimación nunca se etiqueta como cargo observado.

## Ejecución única

- ID ComfyUI: `69e8cc9a-0384-474f-b495-533d5825b9f2`.
- Inicio ComfyUI: `2026-09-06T05:28:36.498-06:00`.
- Inicio remoto: `2026-09-06T05:28:52.222-06:00`.
- Respuesta remota: `2026-09-06T05:29:33.317-06:00`.
- Finalización ComfyUI: `2026-09-06T05:29:40.079-06:00`.
- Modelo reportado: `gemini-3.6-flash`.
- Estado: `completed`; archivo remoto eliminado.
- Caché: `79bf741c627667fe4f1bb4423b2c799595d28c11a859d015b75e2880d8556922`.
- El intento 2.5 permanece separado bajo la firma histórica
  `c6a3185741a64aea8964a8dd2189b0c537f99ccbff6ec9c0d9d6a4c384ba8d9b`.

| Medida | Tiempo |
|---|---:|
| Preflight local | 14.138 s |
| Catálogo antes de subir | 0.484 s |
| Subida | 11.195 s |
| Procesamiento Files API | 6.654 s |
| Inferencia | 22.746 s |
| Etapa remota total | 41.095 s |
| Extracción y validación de frames | 6.070 s |
| Nodo completo | 63.179 s |

## Tokens y coste

El proveedor reportó 14,303 tokens de entrada: imagen 1,110, texto 6,914 y un grupo
`VIDEO` de 6,279. No devolvió una fila `AUDIO`. Ads Art aplicó explícitamente el cálculo
documentado de 32 tokens/s × 40 s = 1,280 tokens de audio y normalizó el grupo restante
a 4,999 tokens visuales de video. Esta separación es una inferencia documentada; los
totales originales del proveedor se conservan sin alterar.

- Entrada total: 14,303 tokens → USD 0.01072725.
- Audio dentro de la entrada: 1,280 tokens → USD 0.00096000.
- Salida: 1,545 tokens → USD 0.00579375.
- Thinking: no reportado (`null`).
- Total reportado: 15,848 tokens.
- Coste Standard estimado: **USD 0.016521**.
- Cargo observado: `null`; la respuesta de inferencia no es una factura.

## Tomas y revisión

### shot_1 — 8.0–9.0 s; frame 8.2 s

- Observado: primer plano de una mujer rubia con gafas oscuras ajustándolas hacia cámara.
- Motivo Gemini: protagonista adulta sola en primer plano.
- Propuesta: establecer identidad y postura de perfil con elegancia visual.
- Nano Banana Pro: `Close-up portrait of the woman from the reference image in Madame X style, profile angle, neutral background with warm directional lighting.`
- Seedance: giro lento de cabeza, mirada segura y acercamiento suave a la altura de ojos.
- Revisión local: las gafas tapan los ojos; no cumple plenamente “rostro despejado”.

### shot_2 — 24.0–25.0 s; frame 24.8 s

- Observado: primer plano medio, giro por encima del hombro y rostro despejado.
- Motivo Gemini: ángulo facial directo y limpio compatible con perfil.
- Propuesta: destacar perfil y vestuario desde una vista sobre el hombro.
- Nano Banana Pro: `Medium close-up profile shot of the woman from the reference image, turned over her shoulder, wearing a black velvet dress against a warm studio backdrop.`
- Seedance: ligero movimiento de hombro, cámara fija y ritmo controlado.
- Revisión local: es la toma más compatible con el perfil de Madame X; sigue pendiente
  de aprobación del usuario.

### shot_3 — 33.8–35.08 s; frame 34.0 s

- Observado: primer plano frontal, rostro despejado y fondo exterior de agua al atardecer.
- Motivo Gemini: vista facial frontal clara para comparar identidad.
- Propuesta: presentar expresión y estructura facial.
- Nano Banana Pro: `Frontal bust shot of the woman from the reference image, looking forward, wearing a black velvet gown, warm cinematic lighting.`
- Seedance: mirada directa, movimiento mínimo y acercamiento muy sutil.
- Revisión local: rostro claro, pero menos compatible con el perfil que `shot_2`.

Gemini registró como pendiente la identidad del producto, especificaciones del frasco,
tipografía y claims de marca. No se aprobó ninguna toma ni se ejecutó Higgsfield.

## ComfyUI y seguridad final

Tras el reinicio final, la ejecución visible de ComfyUI
`f05d72dd-62d3-4a26-88af-c3f9f9789280` reutilizó la caché sin otra llamada remota y
expone los tres frames en **Review representative frames**, además de motivos,
observaciones, propuestas y prompts en los nodos de borrador 24–26.

El workflow instalado conserva Madame X, sus notas y registros, y termina con
`confirm_gemini_analysis=false`, `allow_retry_after_unknown=false`, un intento de subida,
las tres confirmaciones Higgsfield en `false` y todas las revisiones visuales en `false`.
