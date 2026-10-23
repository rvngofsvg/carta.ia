# Auditoría local de Carta IA y leyenda Eider

Fecha: 23 de octubre de 2026. Cambios locales, sin publicación, despliegue ni envío de claves.

## Actualización tras configurar Secrets locales

Se completaron **cinco llamadas reales autenticadas a qwen3.8-flash**, todas satisfactorias: extracción de texto, clasificación de alérgenos, extracción de imagen, segunda clasificación y traducción al inglés. Consumo reportado por la API: 9.576 tokens. No hubo fallback a reglas locales por fallo de API.

Se usó una carta sintética conocida con ocho platos, tres categorías e ingredientes explícitos que cubren los 14 grupos de alérgenos. Texto e imagen conservaron platos, orden, descripciones y precios. No se detectaron alérgenos omitidos ni añadidos frente a los ingredientes esperados. La traducción mantuvo precios, numeración y alérgenos. Esta prueba confirma ese caso controlado; no certifica la precisión de cualquier foto o receta ambigua, ni prueba los modelos de fallback Max/Omni, audio o generación de fondos.

Se generaron y renderizaron con los datos reales: Word con alérgenos, sin alérgenos, limpio, plantilla editable, libro horizontal y Word traducido. También se generaron los PDF con y sin alérgenos y el ZIP de 13 plantillas. La interfaz con la respuesta real mostró siete pestañas y once controles de descarga, sin excepciones en Streamlit AppTest.

La prueba real descubrió un defecto adicional: Qwen conservaba correctamente el sufijo `EUR`, pero el formateador añadía `€`, produciendo `12,50 EUR€`. Se corrigió en `app.py` y `ai_design.py` para representar `12,50 €`. Los archivos se regeneraron a partir de las respuestas guardadas, sin repetir las llamadas pagadas. La suite ampliada pasa **12 pruebas de regresión**.

Evidencia local: `qa/after/live/results.json`, `ui_results.json`, `export_checks.json`, respuestas JSON, documentos y renderizados. Script reproducible con llamadas reales: `qa/live_qwen_check.py`. El fichero de Secrets continúa ignorado y no versionado; no se modificó Cloud ni producción.

## Resultado y alcance

La leyenda Word utiliza el PNG HD entregado por el usuario, sin recorte, redibujo, recomprensión ni cambio de colores. Se inserta en los pies reales de Word, con dimensiones proporcionales y margen inferior reservado. Hay una leyenda por página física, incluido el modo libro horizontal. Las versiones explícitamente sin alérgenos no incluyen la imagen. El Word limpio clásico conserva su función previa: cuerpo editable sin símbolos y leyenda inferior, ahora con el original HD.

SHA256 del archivo adjunto y de su copia en Public:
`0615d954e9c94f359ce994cede0328d41ccfc374194e72418b45a34db6d31fea`.

En la auditoría inicial todavía no había DASHSCOPE_API_KEY local y solo se comprobaron respuestas simuladas. Esa limitación se resolvió posteriormente para texto, imagen, alérgenos y traducción, según la actualización anterior. Voz y generación de fondos siguen sin prueba remota.

## Funciones conservadas

Entrada por imagen, PDF, DOCX y audio; revisión de restaurante, platos, precios y alérgenos; Word con y sin alérgenos; Word limpio clásico; plantillas editables y ZIP; modo libro horizontal; PDF con y sin alérgenos; diseños HTML/PDF y fondos IA; traducción; diagnóstico de alérgenos; Radar de Clientes y extractor universal. Se mantienen las siete pestañas del generador y los tres modos de navegación.

## Fallos reproducidos y correcciones

| Fallo | Causa | Corrección |
|---|---|---|
| La app no mostraba navegación sin clave | `st.stop()` antes de definir el resto de la aplicación | Aviso visible; las funciones locales siguen disponibles y las llamadas IA conservan su control de credenciales |
| Leyenda Word distinta de Eider | Reconstrucción en tabla de 2 × 7, con tipografías y colores propios | Imagen HD original en footer, sin reconstrucción |
| Word premium colocaba la guía en el cuerpo | Tabla y párrafos añadidos con `doc.add_table/add_paragraph` | Mismo footer compartido que las demás salidas |
| Horizontal repetía dos guías de 14 iconos | Construcción independiente por cada mitad | Una sola imagen horizontal por página física |
| Word limpio conservaba una imagen antigua | Herencia de la plantilla base | Sustitución por el PNG HD en los pies |
| Cabecera de plantilla cortada por la mitad | Las dos columnas se aplicaban también a una tabla de cabecera de ancho completo | Cabecera en una sección de una columna y contenido en sección continua de dos columnas |
| Precio antes de los símbolos en libro y premium | Orden de creación de los runs contradictorio con la descripción del modo | Plato, símbolos y precio; tabulador del libro ajustado al ancho de columna |
| PDF ausentes en Windows | WeasyPrint Python no encontraba `libgobject-2.0-0`/Pango; la excepción se ocultaba | Distribución portátil oficial de WeasyPrint 69, aislada en `.runtime`; backend compartido para diseños y PDF; aviso si falla |
| Borde del pie PDF en el límite de la hoja | Alineación inferior de la caja de margen sin separación exterior | Centrado vertical dentro del margen inferior reservado |
| Clasificación incompleta aceptada | Solo se verificaba que `items` fuera una lista | Validación de cobertura exacta, índices, duplicados y tipo de alérgenos; fallback al modelo de revisión |
| Fallo del clasificador quedaba poco visible | Solo se guardaba un error interno | Nota de revisión por plato cuando no se completa la clasificación |
| Textos auxiliares desaparecían al normalizar | Se descartaban `header_text`, `footer_text` y `notes` | Conservación de esos campos y notas de categoría |
| IDs duplicados de traducción se aceptaban | Conversión a diccionario sobrescribía duplicados | Comprobación adicional del número de elementos |

También se rechazan respuestas con `finish_reason=length`, para no aceptar como completa una respuesta truncada.

## Archivos modificados y añadidos

- `app.py`: integración del footer, secciones, orden visual, navegación sin clave, aviso PDF y validaciones.
- `qwen_core.py`: cobertura de clasificación, truncamiento y conservación de textos auxiliares.
- `ai_design.py`: generación PDF a través del backend compartido.
- `word_legend.py` (nuevo): inserción idempotente de la imagen en los tres tipos de pie de cada sección.
- `pdf_backend.py` (nuevo): WeasyPrint portátil en Windows y biblioteca Python en los demás entornos.
- `Public/leyenda_Eider_recreada_colores_HD.png` (nuevo): copia exacta del adjunto.
- `scripts/setup-local-pdf.ps1` (nuevo): instalación local reproducible del ejecutable oficial.
- `.gitignore` (nuevo): exclusión de claves, entorno, runtime portátil y artefactos de pruebas.
- `qa/audit_runtime.py` y `qa/test_regressions.py` (nuevos): reproducción y regresiones.
- Este informe.

Las funciones de exportación se conservan. El código eliminado corresponde a la reconstrucción de la leyenda sustituida por la imagen compartida. No se alteró la plantilla base ni se ejecutaron los scripts históricos de parches.

## Pruebas realizadas

1. Reproducción anterior al cambio guardada en `qa/before/results.json` y DOCX de muestra: 14 imágenes en el pie normal, 28 en libro, tabla en el cuerpo premium, PDFs fallidos y clasificación parcial aceptada.
2. Suite `qa/test_regressions.py`: contratos Qwen, fallback visual usando la misma imagen, rechazo de respuestas parciales/duplicadas/truncadas, conservación de datos, traducción sin modificar precios ni alérgenos, Word con y sin alérgenos, todas las plantillas en una y dos columnas, ZIP, PDF multipágina, PDF de diseño con fondo sintético y navegación/edición con Streamlit AppTest.
3. Las 12 pruebas de reglas locales incluidas en la app pasan.
4. Renderizado de Word con LibreOffice en modo invisible y perfil temporal, autorizado expresamente por el usuario. Inspección de las salidas normal, sin alérgenos, limpia, editable, premium, horizontal y carta de 100 platos (seis páginas).
5. Comprobación del PNG incrustado byte a byte, de la relación de aspecto, del margen reservado, de la ausencia de leyenda en cuerpo/cabecera y de que repetir la operación no la duplica.
6. Medición sobre el PDF renderizado de la carta larga: una imagen de leyenda por página; el contenido acaba al menos 29,5 puntos (10,4 mm) por encima del inicio de la imagen. La imagen queda íntegra dentro de la hoja. Los datos de geometría están en `qa/after/render_geometry.json`.
7. Compilación Python y `git diff --check` sin errores. Sin funciones top-level duplicadas en los tres módulos existentes.

Los renderizados comprueban LibreOffice; no se afirma una prueba en Microsoft Word nativo. La maquetación puede variar con las fuentes y el motor del equipo receptor. Las pruebas usan una carta sintética, no una carta real del restaurante. Los diseños automáticos se comprobaron con un fondo local; su generación remota sigue pendiente de credenciales.

## Ejecución local

Desde la raíz del proyecto:

```powershell
& .venv/Scripts/python.exe -m streamlit run app.py
& .venv/Scripts/python.exe qa/test_regressions.py
```

La instalación portátil PDF ya está preparada en este equipo. Para reproducirla en otra copia Windows:

```powershell
& scripts/setup-local-pdf.ps1
```

`DASHSCOPE_API_KEY` ya está configurada localmente en Secrets por el usuario. La prueba real con carta conocida está completada. Para repetirla explícitamente: `& .venv/Scripts/python.exe qa/live_qwen_check.py` (realiza llamadas de pago a Alibaba). No se debe pegar la clave en el código ni subirla a Git.

Referencias oficiales consultadas: [modelos de Alibaba](https://www.alibabacloud.com/help/en/model-studio/models), [instalación de WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html), [distribución WeasyPrint 69](https://github.com/Kozea/WeasyPrint/releases/tag/v69.0).
