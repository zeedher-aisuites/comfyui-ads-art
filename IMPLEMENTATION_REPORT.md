# Informe de implementación — Ads Art Gemini v1

Fecha de verificación: 2026-09-06

## Resultado

Ads Art incorpora una primera integración funcional con Gemini para preparar el análisis
del comercial, proponer hasta el número configurado de tomas, generar borradores de
prompts de frame y movimiento y conectarlos con los planificadores existentes. La
implementación está lista para una prueba remota, pero durante esta etapa sólo se ejecutó
el preflight local: cero llamadas a Gemini y cero generaciones Higgsfield.

El modelo está fijado a `gemini-2.5-flash`. La documentación oficial vigente declara
entradas de video e imagen y structured outputs para este identificador. No hay alias,
sustitución ni fallback silencioso.

## Implementado

- Transporte Gemini mediante el SDK oficial `google-genai`, cargado sólo al confirmar
  una llamada remota.
- Autenticación exclusiva con `GEMINI_API_KEY` del entorno; no existe campo de clave en
  el nodo ni persistencia del secreto.
- Prompt versionado `ads_art_gemini_commercial_v1` con los cuatro controles del proyecto,
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
  una llamada incierta queda bloqueada para impedir duplicados.
- Una sola inferencia por intento confirmado, dos intentos máximos de subida, sondeo
  acotado del archivo y eliminación best effort del archivo remoto.
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
- Instalación local de `google-genai==2.22.0` en `venv_comfy` y comprobación, sin red
  de inferencia, de las firmas `files.upload/get/delete`, `models.generate_content`,
  `response_json_schema` y `Part.from_bytes`.
- 26 pruebas automatizadas: políticas de
  imagen/video, anti-duplicado, recuperación, detector local, modelo y esquema Gemini,
  timestamps, coste, clave ausente, preflight con cero llamadas y persistencia de
  overrides, actualización del prompt Seedance y sincronización segura del workflow.
- Fixture sintético de dos planos: corte detectado y frames extraídos.
- Preflight real del comercial Dior copiado a `ComfyUI/input`:

  - archivo de 11,081,299 bytes; SHA-256 idéntico a la fuente conservada en Downloads;
  - duración 40.0 s, 1280 × 720;
  - 17 cortes locales detectados;
  - máximo de tres muestras, seleccionadas a 1.72 s, 20.60 s y 39.28 s;
  - los tres archivos se inspeccionaron visualmente y quedaron `approved=false`;
  - estado `prepared_not_called`, `remote_calls=0`.

- La copia de Madame X en `ComfyUI/input` coincide por SHA-256 con el resultado aprobado
  conservado en el proyecto.
- El workflow instalado preserva exactamente las `identity_notes` y los IDs de request/
  job de la generación de identidad anterior.
- El preflight detectó que `GEMINI_API_KEY` existe en el entorno del proceso de prueba,
  sin leer ni registrar su valor. La autenticación efectiva no se comprobó porque eso
  habría requerido una llamada a Google.

## Costes y medición

La tarifa Standard documentada para Gemini 2.5 Flash usada por esta integración es USD
0.30/M tokens de entrada de texto/imagen/video y USD 2.50/M tokens de salida, incluido
thinking, verificada el 2026-09-06. La estimación se calcula únicamente tras recibir uso
reportado; antes de una llamada su valor es `null`. `observed_charge_usd` permanece
separado y `null` porque una respuesta de inferencia no prueba el cargo de facturación.

No hubo tokens, coste estimado ni cargo observado en esta etapa porque Gemini no se
invocó.

## Qué falta probar

- Asegurar que la instancia reiniciada de ComfyUI herede la `GEMINI_API_KEY` detectada;
  si usa otro lanzador, configurarla allí de forma privada.
- Reiniciar la instancia habitual para cargar las nuevas clases.
- Ejecutar una llamada Gemini confirmada sobre Dior, inspeccionar el JSON real, tokens,
  tiempos y versión de modelo reportada, y revisar manualmente las tres propuestas.
- Aprobar un frame y comprobar el ciclo completo Gemini → planificador → Nano Banana Pro
  sin enviar todavía, seguido más tarde por una generación autorizada explícitamente.
- La calidad semántica, los prompts reales y el coste real no se afirman como probados.
- Ningún envío o consulta Higgsfield se probó en esta etapa; sus registros históricos se
  conservaron sin tocarlos.

## Primer análisis real, cuando se autorice

1. Verificar `google-genai==2.22.0` en `venv_comfy` y definir `GEMINI_API_KEY` sólo en
   la terminal privada que iniciará ComfyUI.
2. Reiniciar ComfyUI y abrir el workflow instalado de Ads Art.
3. Verificar en **Gemini Commercial Analysis**: Dior, Madame X conectada,
   `gemini-2.5-flash`, `faithful_reference`, máximo `3`, reutilización activa y reintento
   incierto desactivado.
4. Ejecutar una vez con `confirm_gemini_analysis=false` para revisar el preflight local.
5. Cambiar únicamente `confirm_gemini_analysis=true` y ejecutar el nodo una vez.
6. Devolver inmediatamente la confirmación a `false`. Si el estado queda incierto, no
   repetir: revisar `analysis/gemini/inflight/` y decidir manualmente.
7. Revisar los tres frames, observaciones, motivos, prompts e incertidumbres; no aprobar
   visualmente ninguno por defecto.
