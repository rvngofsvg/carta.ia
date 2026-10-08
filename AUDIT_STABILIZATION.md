# Auditoría de estabilización · Carta IA v11.2

Generado automáticamente por `scripts/stabilize_app.py`.

## Cambios aplicados

- Se eliminan definiciones top-level repetidas y se conserva únicamente la última versión efectiva de cada función.
- Los PDF escaneados dejan de truncarse en 6 páginas: se procesan todas las páginas y se informa de páginas fallidas.
- Se añade un **preflight de entrega** que detecta platos sin nombre, precios ausentes, nombres duplicados y casos con `review_notes`.
- Las descargas finales **con alérgenos** quedan bloqueadas hasta confirmar la revisión de receta/ficha técnica cuando existan dudas.
- La confirmación se invalida automáticamente si cambia el contenido de la carta, porque la clave depende de la firma del menú.
- La navegación principal pasa de 8 pestañas a 5: Revisar, Descargas, Traducción, Diseños y Avanzado.
- Se añaden explícitamente `hashlib` y `copy`, usados por firma de menú y traducción.

## Funciones repetidas eliminadas

| Función | Limpieza |
|---|---|
| `analyze_content` | 1 definición(es) antigua(s) eliminada(s) |
| `apply_allergen_rules` | 1 definición(es) antigua(s) eliminada(s) |
| `apply_allergen_rules_to_dish` | 1 definición(es) antigua(s) eliminada(s) |
| `build_ai_prompt` | 1 definición(es) antigua(s) eliminada(s) |
| `create_word` | 1 definición(es) antigua(s) eliminada(s) |
| `render_visual_downloads` | 1 definición(es) antigua(s) eliminada(s) |

**Total de definiciones antiguas eliminadas:** 6

## Criterio de entrega

Una carta con `review_notes` no se considera lista automáticamente. La aplicación exige confirmación humana de receta, ficha técnica o responsable del establecimiento antes de habilitar las salidas con alérgenos. Las salidas sin alérgenos y el Word de trabajo permanecen disponibles.

## QA automática

El workflow exige:

- `python -m py_compile app.py` correcto.
- Cero funciones top-level duplicadas.
- Ausencia del patrón histórico `doc[:6]`.
- Presencia del preflight y del bloqueo `disabled` en la descarga con alérgenos.
- Nueva navegación simplificada presente.
