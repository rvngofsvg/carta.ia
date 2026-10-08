from __future__ import annotations

import ast
import textwrap
from collections import Counter
from pathlib import Path

APP = Path("app.py")
PATCH = Path("serval_eider_patch/sitecustomize.py")
SETUP = Path("serval_eider_patch/setup.py")


def replace_function(source: str, name: str, replacement: str) -> str:
    tree = ast.parse(source)
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one function {name!r}, found {len(matches)}")
    node = matches[0]
    start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
    end = node.end_lineno
    lines = source.splitlines()
    lines[start:end] = textwrap.dedent(replacement).strip("\n").splitlines()
    return "\n".join(lines).rstrip() + "\n"


QUICK_OUTPUTS = r'''
def render_quick_outputs(data):
    st.subheader("⬇️ Descargar")
    st.caption("Elige una opción. Si quieres la carta lista para entregar, usa la primera.")
    restaurant = slugify_filename(data.get("restaurant_name", "menu"))
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("### ✅ Carta con alérgenos")
        st.caption("La opción principal: platos, precios, iconos y leyenda inferior.")
        st.download_button(
            "⬇️ DESCARGAR CARTA CON ALÉRGENOS",
            create_word(data),
            file_name=f"Carta_Con_Alergenos_{restaurant}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="v11_3_quick_allergens",
            use_container_width=True,
        )

    with c2:
        st.markdown("### 📄 Carta sin alérgenos")
        st.caption("Mismo contenido, sin iconos ni leyenda de alérgenos.")
        st.download_button(
            "⬇️ DESCARGAR SIN ALÉRGENOS",
            create_client_word_without_allergens(data),
            file_name=f"Carta_Sin_Alergenos_{restaurant}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="v11_3_quick_no_allergens",
            use_container_width=True,
        )

    with c3:
        st.markdown("### ✏️ Word para editar")
        st.caption("Para cambiar manualmente textos, precios o detalles en Word.")
        st.download_button(
            "⬇️ DESCARGAR WORD EDITABLE",
            create_clean_word(data),
            file_name=f"Texto_Editable_{restaurant}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="v11_3_quick_clean",
            use_container_width=True,
        )
'''


TRANSLATION = r'''
def render_translation(data):
    st.subheader("🌍 Traducir carta")
    st.caption("Elige idioma, traduce y descarga. No modifica precios, numeración ni el nombre del restaurante.")
    current_signature = menu_signature(data)
    stored_signature = st.session_state.get("translated_source_signature")
    if st.session_state.get("translated_menu_data") and stored_signature != current_signature:
        invalidate_translation()

    target = st.selectbox(
        "Idioma",
        ["Catalán", "Inglés", "Francés", "Italiano", "Alemán", "Portugués"],
        key="v11_3_translate_target",
    )
    if st.button("🌍 TRADUCIR", type="primary", key="v11_3_translate_button", use_container_width=True):
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
        slug = slugify_filename(language)
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "⬇️ CON ALÉRGENOS",
                create_word(translated),
                file_name=f"Carta_{slug}_Con_Alergenos.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="v11_3_translate_allergens",
                use_container_width=True,
            )
        with c2:
            st.download_button(
                "⬇️ SIN ALÉRGENOS",
                create_client_word_without_allergens(translated),
                file_name=f"Carta_{slug}_Sin_Alergenos.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="v11_3_translate_no_allergens",
                use_container_width=True,
            )
'''


LEGEND = r'''
def add_docx_allergen_legend(doc, data, theme):
    # Leyenda base legible incluso si el parche de footer no llegara a ejecutarse.
    doc.add_paragraph()
    title = doc.add_paragraph()
    title.alignment = 1
    tr = title.add_run('GUÍA DE ALÉRGENOS')
    tr.bold = True
    tr.font.size = Pt(12)
    set_run_color(tr, theme['cat'])

    table = doc.add_table(rows=2, cols=7)
    table.autofit = True
    for idx, allergen in enumerate(ALLERGEN_ORDER):
        row = 0 if idx < 7 else 1
        col = idx if idx < 7 else idx - 7
        cell = table.cell(row, col)
        set_cell_shading(cell, theme.get('light', 'FFFFFF'))
        par = cell.paragraphs[0]
        par.alignment = 1
        icon_path = ICON_MAP.get(allergen)
        if icon_path and os.path.exists(icon_path):
            try:
                par.add_run().add_picture(icon_path, width=Cm(0.95))
                par.add_run('\n')
            except Exception:
                pass
        txt = par.add_run(ALLERGEN_LABELS.get(allergen, allergen))
        txt.font.size = Pt(9.2)
        txt.bold = True
        set_run_color(txt, theme['text'])
    notice = doc.add_paragraph()
    notice.alignment = 1
    nr = notice.add_run(build_notice(data))
    nr.font.size = Pt(9.0)
    set_run_color(nr, theme['muted'])
'''


SIMPLE_TABS = textwrap.indent(
    textwrap.dedent(
        r'''
if st.session_state.menu_data:
    st.markdown("---")
    tab1, tab2, tab3 = st.tabs([
        "✏️ Revisar",
        "⬇️ Descargar",
        "⋯ Más opciones",
    ])
    data = st.session_state.menu_data

    with tab1:
        st.caption("Corrige solo lo que necesites. Los cambios se aplican directamente a las descargas.")
        previous_signature = st.session_state.get("_last_menu_signature")
        st.session_state.menu_data = render_editor(data)
        new_signature = menu_signature(st.session_state.menu_data)
        if previous_signature and previous_signature != new_signature:
            invalidate_translation()
        st.session_state["_last_menu_signature"] = new_signature

    with tab2:
        render_quick_outputs(st.session_state.menu_data)

    with tab3:
        st.caption("Estas herramientas son opcionales. No necesitas entrar aquí para descargar una carta normal.")
        with st.expander("🌍 Traducir la carta", expanded=False):
            render_translation(st.session_state.menu_data)
        with st.expander("🎨 Diseños y plantillas", expanded=False):
            render_editable_clean_templates(st.session_state.menu_data)
            st.markdown("---")
            render_visual_downloads(st.session_state.menu_data)
        with st.expander("📖 Formato horizontal / modo libro", expanded=False):
            render_landscape_book_word(st.session_state.menu_data)
        with st.expander("🧪 Revisión técnica de alérgenos (opcional)", expanded=False):
            render_allergen_validation(st.session_state.menu_data)
'''
    ).lstrip("\n"),
    "    ",
)


def replace_if_present(source: str, old: str, new: str) -> str:
    if old in source:
        return source.replace(old, new, 1)
    if new in source:
        return source
    raise RuntimeError(f"Expected token not found: {old!r}")


def patch_app() -> None:
    src = APP.read_text(encoding="utf-8")
    src = replace_function(src, "render_quick_outputs", QUICK_OUTPUTS)
    src = replace_function(src, "render_translation", TRANSLATION)
    src = replace_function(src, "add_docx_allergen_legend", LEGEND)

    src = src.replace(
        "def _add_allergen_icons_to_run(paragraph, allergens, width_cm=0.36):",
        "def _add_allergen_icons_to_run(paragraph, allergens, width_cm=0.75):",
    )
    src = src.replace(
        '_add_allergen_icons_to_run(p, dish.get("allergens", []), width_cm=0.36)',
        '_add_allergen_icons_to_run(p, dish.get("allergens", []), width_cm=0.75)',
    )
    src = src.replace(
        "p.add_run().add_picture(icon_path, width=Cm(0.36))",
        "p.add_run().add_picture(icon_path, width=Cm(0.75))",
    )

    src = src.replace(
        'st.set_page_config(page_title="Sistema Integral de Cartas - Serval TECH · v11.2", layout="wide")',
        'st.set_page_config(page_title="Carta IA · Serval TECH", layout="wide")',
    )
    src = src.replace(
        'st.caption("v11.2 · Preflight de alérgenos + PDFs completos + interfaz simplificada + núcleo sin funciones duplicadas.")',
        'st.caption("Crea, revisa y descarga tu carta de forma sencilla.")',
    )
    src = src.replace(
        'st.success("✅ Menú analizado. Revisa los alérgenos antes de descargar.")',
        'st.success("✅ Carta preparada. Revisa lo que quieras cambiar y después pulsa Descargar.")',
    )
    src = src.replace(
        'st.info("La app usa revisión unificada: IA + reglas de hostelería + edición manual final. Revisa especialmente salsas, fritos, caldos y productos industriales.")',
        'st.info("Puedes editar cualquier plato, precio o alérgeno directamente aquí antes de descargar.")',
    )
    src = src.replace(
        '                if dish.get("review_notes"):\n                    st.warning(" · ".join(dish.get("review_notes", [])))',
        '                if dish.get("review_notes"):\n                    with st.expander("ℹ️ Sugerencia opcional", expanded=False):\n                        st.caption(" · ".join(dish.get("review_notes", [])))',
    )

    anchor = src.index('if app_mode == "📝 Generador de Cartas":')
    start = src.index("    if st.session_state.menu_data:\n", anchor)
    end = src.index('\nelif app_mode == "📡 Radar de Clientes":', start)
    src = src[:start] + SIMPLE_TABS.rstrip() + "\n" + src[end:]

    APP.write_text(src, encoding="utf-8")


def patch_footer() -> None:
    src = PATCH.read_text(encoding="utf-8")
    pairs = [
        ("INLINE_ICON_MIN_CM = 0.52", "INLINE_ICON_MIN_CM = 0.75"),
        (
            "if section.bottom_margin < Cm(5.0):\n        section.bottom_margin = Cm(5.0)",
            "if section.bottom_margin < Cm(6.1):\n        section.bottom_margin = Cm(6.1)",
        ),
        ("icon_cm=1.05,", "icon_cm=1.35,"),
        ("label_pt=8.8,", "label_pt=10.2,"),
        ("legal_pt=8.8,", "legal_pt=9.6,"),
        (
            "if section.bottom_margin < Cm(4.7):\n        section.bottom_margin = Cm(4.7)",
            "if section.bottom_margin < Cm(5.4):\n        section.bottom_margin = Cm(5.4)",
        ),
        ("icon_cm=0.82,", "icon_cm=1.00,"),
        ("label_pt=7.2,", "label_pt=8.3,"),
        ("legal_pt=7.0,", "legal_pt=8.0,"),
    ]
    for old, new in pairs:
        src = replace_if_present(src, old, new)
    PATCH.write_text(src, encoding="utf-8")


def patch_setup() -> None:
    src = SETUP.read_text(encoding="utf-8")
    src = replace_if_present(src, 'version="1.0.4"', 'version="1.0.5"')
    SETUP.write_text(src, encoding="utf-8")


def validate() -> None:
    src = APP.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    dupes = sorted(name for name, count in Counter(names).items() if count > 1)
    assert not dupes, dupes
    assert 'tab1, tab2, tab3 = st.tabs' in src
    assert '"✏️ Revisar"' in src and '"⬇️ Descargar"' in src and '"⋯ Más opciones"' in src
    assert 'disabled=not can_export_allergens' not in src
    assert 'render_export_preflight(data, key_prefix="quick")' not in src
    assert 'width_cm=0.75' in src
    assert 'width=Cm(0.95)' in src and 'txt.font.size = Pt(9.2)' in src

    patch = PATCH.read_text(encoding="utf-8")
    assert "INLINE_ICON_MIN_CM = 0.75" in patch
    assert "icon_cm=1.35" in patch
    assert "label_pt=10.2" in patch
    assert "legal_pt=9.6" in patch

    setup = SETUP.read_text(encoding="utf-8")
    assert 'version="1.0.5"' in setup


if __name__ == "__main__":
    patch_app()
    patch_footer()
    patch_setup()
    validate()
    print("PASS client UX + larger allergen visuals")
