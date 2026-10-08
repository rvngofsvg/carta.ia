from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from pathlib import Path

APP = Path("app.py")
REPORT = Path("AUDIT_STABILIZATION.md")


def remove_duplicate_top_level_functions(source: str):
    tree = ast.parse(source)
    groups = defaultdict(list)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            groups[node.name].append(node)

    duplicate_names = {name: nodes for name, nodes in groups.items() if len(nodes) > 1}
    if not duplicate_names:
        return source, {}

    lines = source.splitlines()
    removals = []
    removed_summary = {}
    for name, nodes in duplicate_names.items():
        removed_summary[name] = len(nodes) - 1
        for node in nodes[:-1]:
            start_line = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
            end_line = node.end_lineno
            removals.append((start_line, end_line, name))

    for start, end, _ in sorted(removals, reverse=True):
        del lines[start:end]

    compact = "\n".join(lines).rstrip() + "\n"
    return compact, removed_summary


def replace_function(source: str, name: str, replacement: str) -> str:
    tree = ast.parse(source)
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one top-level function {name!r}, found {len(matches)}")
    node = matches[0]
    start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
    end = node.end_lineno
    lines = source.splitlines()
    new_lines = replacement.strip("\n").splitlines()
    lines[start:end] = new_lines
    return "\n".join(lines).rstrip() + "\n"


def ensure_imports(source: str) -> str:
    additions = []
    if not re.search(r"^import hashlib$", source, flags=re.M):
        additions.append("import hashlib")
    if not re.search(r"^import copy$", source, flags=re.M):
        additions.append("import copy")
    if not additions:
        return source
    anchor = "import unicodedata\n"
    if anchor not in source:
        raise RuntimeError("Import anchor not found")
    return source.replace(anchor, anchor + "\n".join(additions) + "\n", 1)


SCANNED_PDF_FUNCTION = r'''
def extract_text_from_pdf_scanned_with_gemini(file):
    """Renderiza y transcribe TODAS las páginas de un PDF escaneado.

    La versión anterior truncaba silenciosamente a seis páginas. Esta versión
    procesa el documento completo, mantiene el número de página y continúa si
    una página aislada falla, avisando al usuario de cuáles requieren revisión.
    """
    doc = None
    try:
        import fitz  # PyMuPDF
        file.seek(0)
        pdf_bytes = file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(doc)
        if total_pages == 0:
            file.seek(0)
            return ""

        model = _GeminiModelCompat(MODELO_A_USAR)
        chunks = []
        failed_pages = []
        progress = st.progress(0, text=f"Procesando PDF escaneado · 0/{total_pages} páginas")

        for i in range(total_pages):
            try:
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                img = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
                img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
                response = model.generate_content(
                    [
                        "Transcribe literalmente todo el texto visible de esta página de menú. "
                        "No resumas. No inventes. Devuelve texto plano.",
                        img,
                    ],
                    request_options={"timeout": 120},
                )
                page_text = (response.text or "").strip()
                if page_text:
                    chunks.append(f"\n--- PÁGINA {i + 1} ---\n{page_text}")
                else:
                    failed_pages.append(i + 1)
            except Exception:
                failed_pages.append(i + 1)
            finally:
                progress.progress(
                    (i + 1) / total_pages,
                    text=f"Procesando PDF escaneado · {i + 1}/{total_pages} páginas",
                )

        progress.empty()
        file.seek(0)
        if failed_pages:
            st.warning(
                "No se pudo leer completamente "
                + ("la página " if len(failed_pages) == 1 else "las páginas ")
                + ", ".join(map(str, failed_pages))
                + ". Revisa esas páginas antes de entregar la carta."
            )
        return "\n".join(chunks)
    except Exception as exc:
        try:
            file.seek(0)
        except Exception:
            pass
        st.error(f"No se pudo procesar el PDF escaneado: {exc}")
        return None
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass
'''


QUICK_OUTPUTS_AND_PREFLIGHT = r'''
def menu_preflight(data):
    """Auditoría previa a exportación centrada en riesgos que sí afectan al cliente."""
    blocking = []
    warnings = []
    review_items = []
    dishes = []

    for category in data.get("categories", []):
        category_name = str(category.get("name") or "Sin categoría").strip()
        seen_names = Counter()
        for dish in category.get("dishes", []):
            dishes.append(dish)
            name = str(dish.get("name") or "").strip()
            label = dish_display_name(dish) if name else "Plato sin nombre"
            if not name:
                blocking.append(f"{category_name}: hay un plato sin nombre.")
            else:
                seen_names[normalize_text(name)] += 1
            if not str(dish.get("price") or "").strip():
                warnings.append(f"{category_name} · {label}: sin precio detectado.")

            notes = [str(n).strip() for n in (dish.get("review_notes") or []) if str(n).strip()]
            if notes:
                review_items.append({
                    "category": category_name,
                    "dish": label,
                    "notes": notes,
                })

        for normalized_name, count in seen_names.items():
            if normalized_name and count > 1:
                warnings.append(
                    f"{category_name}: hay {count} platos con el mismo nombre; comprobar si es un duplicado real."
                )

    if not dishes:
        blocking.append("No hay platos detectados en la carta.")

    return {
        "dishes": len(dishes),
        "blocking": list(dict.fromkeys(blocking)),
        "warnings": list(dict.fromkeys(warnings)),
        "review_items": review_items,
        "review_count": len(review_items),
    }


def render_export_preflight(data, key_prefix="export", compact=False):
    """Muestra el preflight y devuelve True solo si la salida con alérgenos es entregable."""
    report = menu_preflight(data)
    signature = menu_signature(data)[:16]
    ack_key = f"{key_prefix}_allergen_review_ack_{signature}"

    if not compact:
        st.markdown("#### Control previo a descarga")
        c1, c2, c3 = st.columns(3)
        c1.metric("Platos", report["dishes"])
        c2.metric("Revisiones pendientes", report["review_count"])
        c3.metric("Avisos de contenido", len(report["warnings"]))

    if report["blocking"]:
        for issue in report["blocking"]:
            st.error(f"⛔ {issue}")

    if report["warnings"]:
        with st.expander(f"⚠️ Avisos de contenido ({len(report['warnings'])})", expanded=False):
            for issue in report["warnings"]:
                st.write(f"• {issue}")

    acknowledged = True
    if report["review_items"]:
        with st.expander(
            f"🧾 Platos que requieren validar receta/proveedor ({report['review_count']})",
            expanded=True,
        ):
            for item in report["review_items"]:
                st.markdown(f"**{item['category']} · {item['dish']}**")
                for note in item["notes"]:
                    st.caption(f"• {note}")
        acknowledged = st.checkbox(
            "He revisado estos casos con la receta, ficha técnica o responsable del establecimiento.",
            key=ack_key,
            help="Esta confirmación se reinicia automáticamente si cambia el contenido de la carta.",
        )
        if not acknowledged:
            st.warning("La descarga final con alérgenos permanece bloqueada hasta confirmar esta revisión.")

    can_export = not report["blocking"] and acknowledged
    if can_export and (report["review_items"] or report["warnings"]):
        st.success("Preflight superado para la salida con alérgenos.")
    return can_export


def render_quick_outputs(data):
    st.subheader("📦 Descargas")
    st.caption("Tres salidas claras: trabajo editable, carta final sin alérgenos y carta final validada con alérgenos.")
    can_export_allergens = render_export_preflight(data, key_prefix="quick")

    c1, c2, c3 = st.columns(3)
    restaurant = slugify_filename(data.get("restaurant_name", "menu"))
    with c1:
        st.markdown("**1 · Texto limpio para editar**")
        st.caption("Word clásico de trabajo, sin símbolos.")
        st.download_button(
            "⬇️ Descargar texto limpio",
            create_clean_word(data),
            file_name=f"Texto_Limpio_{restaurant}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="v11_2_quick_clean",
        )
    with c2:
        st.markdown("**2 · Carta final sin alérgenos**")
        st.caption("Mismo contenido final, sin símbolos ni leyenda.")
        st.download_button(
            "⬇️ Descargar sin alérgenos",
            create_client_word_without_allergens(data),
            file_name=f"Carta_Sin_Alergenos_{restaurant}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="v11_2_quick_no_allergens",
        )
    with c3:
        st.markdown("**3 · Carta final con alérgenos**")
        st.caption(
            "Disponible cuando el control previo está validado."
            if not can_export_allergens
            else "Plato → símbolos confirmados → precio."
        )
        st.download_button(
            "⬇️ Descargar con alérgenos",
            create_word(data),
            file_name=f"Carta_Con_Alergenos_{restaurant}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="v11_2_quick_allergens",
            disabled=not can_export_allergens,
        )
'''


TRANSLATION_FUNCTION = r'''
def render_translation(data):
    st.subheader("🌍 Traducción de carta")
    st.caption("Traduce textos sin tocar el nombre comercial, precios, numeración ni alérgenos revisados.")
    current_signature = menu_signature(data)
    stored_signature = st.session_state.get("translated_source_signature")
    if st.session_state.get("translated_menu_data") and stored_signature != current_signature:
        invalidate_translation()
        st.info("La carta original cambió. Se ha descartado la traducción anterior para evitar mezclar versiones.")

    target = st.selectbox(
        "Idioma de salida",
        ["Catalán", "Inglés", "Francés", "Italiano", "Alemán", "Portugués"],
        key="v11_2_translate_target",
    )
    if st.button("🌍 Traducir carta", type="primary", key="v11_2_translate_button"):
        try:
            with st.spinner(f"Traduciendo al {target}..."):
                translated = translate_menu_data(data, target)
                st.session_state.translated_menu_data = translated
                st.session_state.translated_language = target
                st.session_state.translated_source_signature = current_signature
            st.success(f"Carta traducida al {target}.")
        except Exception as exc:
            invalidate_translation()
            st.error(f"No se pudo traducir la carta: {exc}")

    translated = st.session_state.get("translated_menu_data")
    if translated:
        language = st.session_state.get("translated_language", target)
        st.markdown(f"**Vista traducida: {language}**")
        preview_lines = []
        for category in translated.get("categories", [])[:4]:
            preview_lines.append(f"### {category.get('name', '')}")
            for dish in category.get("dishes", [])[:5]:
                preview_lines.append(f"- {dish_display_name(dish)} · {format_price(dish.get('price', ''))}")
        st.markdown("\n".join(preview_lines) if preview_lines else "Sin platos detectados.")

        can_export_allergens = render_export_preflight(
            translated,
            key_prefix=f"translation_{slugify_filename(language)}",
            compact=True,
        )
        c1, c2 = st.columns(2)
        slug = slugify_filename(language)
        with c1:
            st.download_button(
                "⬇️ Traducción sin alérgenos",
                create_client_word_without_allergens(translated),
                file_name=f"Carta_{slug}_Sin_Alergenos.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="v11_2_translate_no_allergens",
            )
        with c2:
            st.download_button(
                "⬇️ Traducción con alérgenos",
                create_word(translated),
                file_name=f"Carta_{slug}_Con_Alergenos.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="v11_2_translate_allergens",
                disabled=not can_export_allergens,
            )
'''


APP_MENU_BLOCK = r'''    if st.session_state.menu_data:
        st.markdown("---")
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "✅ Revisar carta",
            "📦 Descargas",
            "🌍 Traducción",
            "🎨 Diseños",
            "🧰 Avanzado",
        ])
        data = st.session_state.menu_data

        with tab1:
            previous_signature = st.session_state.get("_last_menu_signature")
            st.session_state.menu_data = render_editor(data)
            new_signature = menu_signature(st.session_state.menu_data)
            if previous_signature and previous_signature != new_signature:
                invalidate_translation()
            st.session_state["_last_menu_signature"] = new_signature
            render_allergen_validation(st.session_state.menu_data)

        with tab2:
            render_quick_outputs(data)

        with tab3:
            render_translation(data)

        with tab4:
            st.markdown("#### Plantillas editables")
            render_editable_clean_templates(data)
            st.markdown("---")
            st.markdown("#### Plantillas visuales con información de alérgenos")
            if render_export_preflight(data, key_prefix="visual", compact=True):
                render_visual_downloads(data)
            else:
                st.info("Valida los casos pendientes para habilitar las plantillas visuales con alérgenos.")

        with tab5:
            st.markdown("#### Formato horizontal / libro")
            if render_export_preflight(data, key_prefix="advanced", compact=True):
                render_landscape_book_word(data)
            else:
                st.info("Valida los casos pendientes para habilitar la salida horizontal con alérgenos.")

elif app_mode == "📡 Radar de Clientes":'''


def replace_app_menu_block(source: str) -> str:
    pattern = re.compile(
        r'    if st\.session_state\.menu_data:\n.*?\nelif app_mode == "📡 Radar de Clientes":',
        flags=re.S,
    )
    source, count = pattern.subn(APP_MENU_BLOCK, source, count=1)
    if count != 1:
        raise RuntimeError(f"Expected one app menu block, replaced {count}")
    return source


def main():
    original = APP.read_text(encoding="utf-8")
    source, removed = remove_duplicate_top_level_functions(original)
    source = ensure_imports(source)
    source = replace_function(source, "extract_text_from_pdf_scanned_with_gemini", SCANNED_PDF_FUNCTION)
    source = replace_function(source, "render_quick_outputs", QUICK_OUTPUTS_AND_PREFLIGHT)
    source = replace_function(source, "render_translation", TRANSLATION_FUNCTION)
    source = replace_app_menu_block(source)
    source = source.replace(
        'st.set_page_config(page_title="Sistema Integral de Cartas - Serval TECH · v11.1", layout="wide")',
        'st.set_page_config(page_title="Sistema Integral de Cartas - Serval TECH · v11.2", layout="wide")',
        1,
    )
    source = source.replace(
        'st.caption("v11.1 · Dictado por voz estabilizado + revisión prudente de alérgenos + salidas y traducción protegidas.")',
        'st.caption("v11.2 · Preflight de alérgenos + PDFs completos + interfaz simplificada + núcleo sin funciones duplicadas.")',
        1,
    )

    ast.parse(source)
    APP.write_text(source, encoding="utf-8")

    tree = ast.parse(source)
    names = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    remaining_duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    if remaining_duplicates:
        raise RuntimeError(f"Duplicate functions remain after cleanup: {remaining_duplicates}")

    removed_lines = sum(removed.values())
    removed_table = "\n".join(
        f"| `{name}` | {count} definición(es) antigua(s) eliminada(s) |"
        for name, count in sorted(removed.items())
    ) or "| — | No se encontraron duplicados en esta ejecución |"

    report = f"""# Auditoría de estabilización · Carta IA v11.2

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
{removed_table}

**Total de definiciones antiguas eliminadas:** {removed_lines}

## Criterio de entrega

Una carta con `review_notes` no se considera lista automáticamente. La aplicación exige confirmación humana de receta, ficha técnica o responsable del establecimiento antes de habilitar las salidas con alérgenos. Las salidas sin alérgenos y el Word de trabajo permanecen disponibles.

## QA automática

El workflow exige:

- `python -m py_compile app.py` correcto.
- Cero funciones top-level duplicadas.
- Ausencia del patrón histórico `doc[:6]`.
- Presencia del preflight y del bloqueo `disabled` en la descarga con alérgenos.
- Nueva navegación simplificada presente.
"""
    REPORT.write_text(report, encoding="utf-8")

    print(f"Stabilized app.py; removed {removed_lines} stale duplicate definitions")
    for name, count in sorted(removed.items()):
        print(f"  {name}: -{count}")


if __name__ == "__main__":
    main()
