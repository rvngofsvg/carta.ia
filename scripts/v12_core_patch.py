from __future__ import annotations

import ast
import textwrap
from pathlib import Path

APP = Path("app.py")
PATCH = Path("serval_eider_patch/sitecustomize.py")
REQ = Path("requirements.txt")


def replace_function(source: str, name: str, replacement: str) -> str:
    tree = ast.parse(source)
    matches = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {name}, found {len(matches)}")
    node = matches[0]
    start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
    end = node.end_lineno
    lines = source.splitlines()
    lines[start:end] = textwrap.dedent(replacement).strip("\n").splitlines()
    return "\n".join(lines).rstrip() + "\n"


def insert_before_function(source: str, name: str, block: str) -> str:
    tree = ast.parse(source)
    matches = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {name}, found {len(matches)}")
    lines = source.splitlines()
    idx = matches[0].lineno - 1
    lines[idx:idx] = textwrap.dedent(block).strip("\n").splitlines() + [""]
    return "\n".join(lines).rstrip() + "\n"


BUILD_PROMPT = r'''
def build_ai_prompt():
    allergen_keys = ", ".join(ALLERGEN_ORDER)
    return f"""
Eres un transcriptor experto de cartas de restaurante en España y la UE.

OBJETIVO:
1) Transcribe fielmente categorías, platos, descripciones, precios, numeración y textos auxiliares.
2) No inventes platos, precios ni ingredientes que no aparezcan.
3) Puedes proponer una primera estimación de alérgenos entre estas claves: {allergen_keys}.
4) Una segunda pasada especializada revisará los alérgenos con mayor capacidad de razonamiento, así que prioriza la fidelidad de la carta.

REGLAS:
- Conserva el nombre del restaurante/marca tal como aparece.
- Conserva teléfonos, dirección, horarios, suplementos y avisos en texto_extra.
- Si una nota pertenece claramente a una categoría, usa category_text.
- Conserva number vacío si no existe numeración.
- Devuelve SOLO JSON válido conforme al esquema de la aplicación.
"""
'''


GEMINI_MENU_JSON = r'''
def _gemini_menu_json(contents):
    response = GENAI_CLIENT.models.generate_content(
        model=MODELO_A_USAR,
        contents=contents,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=MENU_JSON_SCHEMA,
            thinking_config=genai_types.ThinkingConfig(thinking_level="medium"),
        ),
    )
    return parse_json_response(response.text)
'''


AI_ALLERGEN_BLOCK = r'''
ALLERGEN_AI_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category_index": {"type": "integer"},
                    "dish_index": {"type": "integer"},
                    "allergens": {"type": "array", "items": {"type": "string", "enum": ALLERGEN_ORDER}},
                    "confidence": {"type": "string", "enum": ["alta", "media", "baja"]},
                    "reason": {"type": "string"},
                },
                "required": ["category_index", "dish_index", "allergens", "confidence", "reason"],
            },
        }
    },
    "required": ["items"],
}


def infer_allergens_with_best_model(data):
    dishes = []
    for c_idx, category in enumerate(data.get("categories", [])):
        for d_idx, dish in enumerate(category.get("dishes", [])):
            dishes.append({
                "category_index": c_idx,
                "dish_index": d_idx,
                "category": str(category.get("name") or ""),
                "name": str(dish.get("name") or ""),
                "description": str(dish.get("description") or ""),
            })
    if not dishes:
        return data

    system_instruction = """
Eres un especialista en clasificación de los 14 alérgenos de declaración obligatoria del Reglamento (UE) 1169/2011 y en cocina de restauración española e internacional.
Tu trabajo es estimar qué alérgenos contiene normalmente cada plato usando TODA la información disponible: nombre, descripción, categoría y conocimiento culinario de preparaciones estándar.
No te limites a buscar palabras literales: razona sobre la composición habitual de platos reconocibles (por ejemplo croquetas, tiramisú, carbonara, rebozados, pesto, hummus, salsas, panes y masas).
No inventes contaminación cruzada ni trazas si no están indicadas. Respeta expresiones explícitas como "sin gluten". Distingue cacahuete de frutos de cáscara y crustáceos de moluscos.
Si una receta tiene variantes razonables, elige la clasificación más probable y baja la confianza, en vez de omitir automáticamente todos los alérgenos.
Devuelve únicamente los 14 grupos permitidos por el esquema. La selección podrá ser corregida manualmente después por el establecimiento.
"""
    prompt = (
        "Analiza todos estos platos en una sola pasada y devuelve la clasificación más probable de alérgenos. "
        "Mantén category_index y dish_index exactamente.\n\n" + json.dumps(dishes, ensure_ascii=False)
    )

    errors = []
    for model_name in (MODELO_ALERGENOS, MODELO_A_USAR):
        try:
            response = GENAI_CLIENT.models.generate_content(
                model=model_name,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_json_schema=ALLERGEN_AI_SCHEMA,
                    thinking_config=genai_types.ThinkingConfig(thinking_level="high"),
                ),
            )
            result = parse_json_response(response.text)
            seen = 0
            for item in result.get("items", []):
                c_idx = int(item.get("category_index", -1))
                d_idx = int(item.get("dish_index", -1))
                if c_idx < 0 or d_idx < 0:
                    continue
                try:
                    dish = data["categories"][c_idx]["dishes"][d_idx]
                except (KeyError, IndexError, TypeError):
                    continue
                dish["allergens"] = get_ordered_allergens(item.get("allergens", []))
                dish["_allergen_ai_confidence"] = item.get("confidence", "")
                dish["_allergen_ai_reason"] = item.get("reason", "")
                seen += 1
            if seen:
                data["_allergen_model"] = model_name
                return data
        except Exception as exc:
            errors.append(f"{model_name}: {exc}")

    data["_allergen_model"] = "fallback"
    data["_allergen_model_error"] = " | ".join(errors)[-800:]
    return data
'''


APPLY_DISH = r'''
def apply_allergen_rules_to_dish(dish):
    name = dish.get("name") or ""
    desc = dish.get("description") or ""
    text = f"{name} {desc}"

    # La IA especializada es la autoridad principal. Las reglas deterministas
    # solo añaden evidencia explícita y corrigen negaciones inequívocas.
    inferred = get_ordered_allergens(dish.get("allergens", []))
    explicit, rule_notes = _evidence_from_text(text)
    combined = get_ordered_allergens(inferred + explicit)

    normalized = normalize_text(text)
    if re.search(r"\bsin\s+gluten\b|\bgluten\s*free\b", normalized, flags=re.IGNORECASE):
        combined = [a for a in combined if a != "gluten"]

    dish["allergens"] = combined
    # Las notas quedan como información opcional; nunca bloquean descargas.
    old_notes = dish.get("review_notes", []) or []
    merged = []
    for note in old_notes + rule_notes:
        if note and note not in merged:
            merged.append(note)
    dish["review_notes"] = merged
    return dish
'''


ANALYZE_CONTENT = r'''
def analyze_content(content, content_type="image"):
    try:
        with st.spinner(f"🧠 Analizando carta con {MODELO_A_USAR} + motor experto de alérgenos..."):
            prompt = build_ai_prompt()
            if content_type == "image":
                data = _gemini_menu_json([prompt, content])
            else:
                data = _gemini_menu_json(prompt + "\n\nMENÚ:\n" + str(content))
            data = infer_allergens_with_best_model(data)
            data = apply_allergen_rules(data)
            data["_generated_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            data["_system_mode"] = f"{MODELO_A_USAR} + {data.get('_allergen_model', MODELO_ALERGENOS)} para alérgenos"
            return data
    except Exception as exc:
        st.error(f"Error IA/análisis: {exc}")
        return None
'''


ANALYZE_AUDIO = r'''
def analyze_audio_menu(audio_file):
    if not audio_file:
        return None
    audio_file.seek(0)
    audio_bytes = audio_file.read()
    audio_file.seek(0)
    if not audio_bytes:
        raise ValueError("La grabación está vacía.")
    if len(audio_bytes) > 18 * 1024 * 1024:
        raise ValueError("El audio es demasiado grande para el dictado rápido. Divide el menú en una grabación más corta.")

    audio_prompt = build_ai_prompt() + """

INSTRUCCIONES PARA DICTADO:
- Ignora muletillas, pausas, dudas y repeticiones.
- Si corrige algo, conserva la última versión claramente indicada.
- Crea un plato solo si se nombra explícitamente.
- Convierte precios hablados a decimal; si no hay precio, deja price vacío.
- No inventes ingredientes para completar recetas.
"""
    part = genai_types.Part.from_bytes(data=audio_bytes, mime_type=_audio_mime(audio_file))
    data = _gemini_menu_json([audio_prompt, part])
    data = _normalize_audio_menu_prices(data)
    data = infer_allergens_with_best_model(data)
    data = apply_allergen_rules(data)
    data["_generated_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    data["_system_mode"] = f"Dictado · {MODELO_A_USAR} + {data.get('_allergen_model', MODELO_ALERGENOS)} para alérgenos"
    data["_input_mode"] = "audio"
    return data
'''


DIRECT_FOOTER = r'''
def add_docx_allergen_legend(doc, data, theme):
    """Crea directamente la leyenda en el pie real del Word, sin post-parches."""
    legal_text = (
        "Informamos de acuerdo con el Reglamento de la UE 1169/2011, que nuestros productos "
        "contienen o pueden contener los siguientes alérgenos."
    )
    legend_labels = {
        "gluten": "GLUTEN", "crustaceos": "CRUSTÁCEOS", "huevos": "HUEVOS", "pescado": "PESCADO",
        "cacahuetes": "CACAHUETES", "soja": "SOJA", "lacteos": "LÁCTEOS",
        "frutos de cascara": "FRUTOS DE CÁSCARA", "apio": "APIO", "mostaza": "MOSTAZA",
        "sesamo": "GRANOS DE SÉSAMO", "sulfitos": "DIÓXIDO DE AZUFRE Y SULFITOS",
        "altramuces": "ALTRAMUCES", "moluscos": "MOLUSCOS",
    }

    def clear(container):
        for child in list(container._element):
            container._element.remove(child)

    def compact(p):
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1

    def set_outer_border(table, color):
        tbl_pr = table._tbl.tblPr
        borders = tbl_pr.first_child_found_in("w:tblBorders")
        if borders is None:
            borders = OxmlElement("w:tblBorders")
            tbl_pr.append(borders)
        for edge in ("top", "start", "bottom", "end"):
            node = borders.find(qn(f"w:{edge}"))
            if node is None:
                node = OxmlElement(f"w:{edge}")
                borders.append(node)
            node.set(qn("w:val"), "single")
            node.set(qn("w:sz"), "10")
            node.set(qn("w:space"), "0")
            node.set(qn("w:color"), color)
        for edge in ("insideH", "insideV"):
            node = borders.find(qn(f"w:{edge}"))
            if node is None:
                node = OxmlElement(f"w:{edge}")
                borders.append(node)
            node.set(qn("w:val"), "nil")

    for section in doc.sections:
        if section.bottom_margin < Cm(5.2):
            section.bottom_margin = Cm(5.2)
        section.footer_distance = Cm(0.18)
        usable_cm = max(12.0, (section.page_width - section.left_margin - section.right_margin) / 360000.0)
        for footer in (section.footer, section.first_page_footer, section.even_page_footer):
            footer.is_linked_to_previous = False
            clear(footer)
            wrapper = footer.add_table(rows=1, cols=1, width=Cm(usable_cm))
            wrapper.alignment = WD_TABLE_ALIGNMENT.CENTER
            wrapper.autofit = False
            set_outer_border(wrapper, theme.get("cat", "444444"))
            cell = wrapper.cell(0, 0)
            cell.text = ""
            legal = cell.paragraphs[0]
            legal.alignment = 1
            compact(legal)
            legal.paragraph_format.space_after = Pt(3)
            lr = legal.add_run(legal_text)
            lr.font.size = Pt(9.0)
            lr.bold = True
            set_run_color(lr, theme.get("text", "111111"))

            grid = cell.add_table(rows=2, cols=7)
            grid.alignment = WD_TABLE_ALIGNMENT.CENTER
            grid.autofit = True
            for idx, allergen in enumerate(ALLERGEN_ORDER):
                r, c = divmod(idx, 7)
                item = grid.cell(r, c)
                item.text = ""
                item.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                p = item.paragraphs[0]
                p.alignment = 1
                compact(p)
                icon_path = ICON_MAP.get(allergen)
                if icon_path and os.path.exists(icon_path):
                    try:
                        p.add_run().add_picture(icon_path, width=Cm(1.25))
                    except Exception:
                        pass
                lp = item.add_paragraph()
                lp.alignment = 1
                compact(lp)
                lp.paragraph_format.space_before = Pt(1)
                label = lp.add_run(legend_labels.get(allergen, ALLERGEN_LABELS.get(allergen, allergen)))
                label.font.size = Pt(9.3)
                label.bold = True
                set_run_color(label, theme.get("text", "111111"))
'''


CREATE_WORD = r'''
def create_word(data, theme_key="neutral"):
    return _create_client_word(data, with_allergens=True, theme_key=theme_key, two_columns=False)
'''


CREATE_NO_ALLERGENS = r'''
def create_client_word_without_allergens(data, theme_key="neutral", two_columns=False):
    return _create_client_word(data, with_allergens=False, theme_key=theme_key, two_columns=two_columns)
'''


PDF_AND_DOWNLOADS = r'''
def create_client_pdf_html(data, theme_key="neutral", with_allergens=True):
    theme = EDITABLE_WORD_THEMES.get(theme_key, EDITABLE_WORD_THEMES["neutral"])
    cat = "#" + theme.get("cat", "374151")
    text = "#" + theme.get("text", "111827")
    muted = "#" + theme.get("muted", "6B7280")
    header = "#" + theme.get("header", "1F2937")
    light = "#" + theme.get("light", "F9FAFB")
    rest = html_escape(str(data.get("restaurant_name") or "MENÚ"))

    category_html = []
    for category in data.get("categories", []):
        dishes_html = []
        for dish in category.get("dishes", []):
            icons = ""
            if with_allergens:
                for allergen in get_ordered_allergens(dish.get("allergens", [])):
                    src = file_to_data_uri(ICON_MAP.get(allergen))
                    if src:
                        icons += f'<img class="dish-icon" src="{src}" alt="{html_escape(ALLERGEN_LABELS.get(allergen, allergen))}">'
            desc = html_escape(str(dish.get("description") or ""))
            desc_html = f'<div class="desc">{desc}</div>' if desc else ""
            dishes_html.append(
                '<div class="dish">'
                f'<div class="dish-main"><span class="dish-name">{html_escape(dish_display_name(dish))}</span>'
                f'<span class="dish-icons">{icons}</span><span class="dots"></span>'
                f'<span class="price">{html_escape(format_price(dish.get("price", "")))}</span></div>{desc_html}</div>'
            )
        cat_note = html_escape(str(category.get("category_text") or ""))
        note_html = f'<div class="cat-note">{cat_note}</div>' if cat_note else ""
        category_html.append(
            f'<section class="category"><h2>{html_escape(str(category.get("name") or "Categoría"))}</h2>{note_html}{"".join(dishes_html)}</section>'
        )

    footer_html = ""
    footer_css = ""
    page_bottom = "16mm"
    if with_allergens:
        items = []
        labels = {
            "gluten": "GLUTEN", "crustaceos": "CRUSTÁCEOS", "huevos": "HUEVOS", "pescado": "PESCADO",
            "cacahuetes": "CACAHUETES", "soja": "SOJA", "lacteos": "LÁCTEOS", "frutos de cascara": "FRUTOS DE CÁSCARA",
            "apio": "APIO", "mostaza": "MOSTAZA", "sesamo": "GRANOS DE SÉSAMO", "sulfitos": "DIÓXIDO DE AZUFRE Y SULFITOS",
            "altramuces": "ALTRAMUCES", "moluscos": "MOLUSCOS",
        }
        for allergen in ALLERGEN_ORDER:
            src = file_to_data_uri(ICON_MAP.get(allergen))
            icon = f'<img src="{src}">' if src else ""
            items.append(f'<div class="legend-item">{icon}<span>{labels[allergen]}</span></div>')
        footer_html = (
            '<footer class="allergen-footer">'
            '<div class="legal">Informamos de acuerdo con el Reglamento de la UE 1169/2011, que nuestros productos contienen o pueden contener los siguientes alérgenos.</div>'
            f'<div class="legend-grid">{"".join(items)}</div></footer>'
        )
        page_bottom = "56mm"
        footer_css = """
        .allergen-footer{position:fixed;left:0;right:0;bottom:-50mm;height:46mm;border:1.2px solid #4b4038;padding:3mm 4mm 2mm;box-sizing:border-box;background:#fff;}
        .legal{text-align:center;font-size:8.8pt;font-weight:700;margin-bottom:2.2mm;line-height:1.15;}
        .legend-grid{display:grid;grid-template-columns:repeat(7,1fr);grid-template-rows:repeat(2,1fr);gap:1.2mm 1.5mm;}
        .legend-item{text-align:center;font-size:8.2pt;font-weight:700;line-height:1.05;min-width:0;}
        .legend-item img{display:block;width:10mm;height:10mm;object-fit:contain;margin:0 auto .7mm;}
        """

    extra = html_escape(str(data.get("texto_extra") or ""))
    extra_html = f'<div class="extra">{extra}</div>' if extra else ""
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
    @page{{size:A4;margin:15mm 15mm {page_bottom} 15mm;}}
    *{{box-sizing:border-box}} body{{font-family:Arial,Helvetica,sans-serif;color:{text};margin:0;background:#fff;font-size:10.5pt;}}
    h1{{font-size:24pt;text-align:center;color:{header};margin:0 0 8mm;letter-spacing:.3px;}}
    h2{{font-size:14pt;color:{cat};border-bottom:1px solid {cat};padding-bottom:1.5mm;margin:6mm 0 2.5mm;}}
    .cat-note,.extra{{color:{muted};font-size:9pt;margin:1.5mm 0 3mm;}}
    .dish{{margin:0 0 2.2mm;break-inside:avoid;}}
    .dish-main{{display:flex;align-items:center;gap:1.6mm;font-size:11pt;}}
    .dish-name{{font-weight:700;}} .dish-icons{{display:inline-flex;gap:.8mm;align-items:center;}}
    .dish-icon{{width:7.5mm;height:7.5mm;object-fit:contain;}}
    .dots{{flex:1;border-bottom:1px dotted {muted};height:0;min-width:8mm;}} .price{{font-weight:700;white-space:nowrap;}}
    .desc{{font-size:9.2pt;color:{muted};font-style:italic;margin-top:.5mm;}}
    .extra{{padding:2.5mm;background:{light};border:1px solid #ddd;margin-top:6mm;}}
    {footer_css}
    </style></head><body><h1>{rest}</h1>{''.join(category_html)}{extra_html}{footer_html}</body></html>'''


def create_client_pdf_bytes(data, theme_key="neutral", with_allergens=True):
    return html_to_pdf_bytes(create_client_pdf_html(data, theme_key=theme_key, with_allergens=with_allergens))


def render_quick_outputs(data):
    st.subheader("⬇️ Descargar")
    st.caption("Elige el diseño una vez y descarga la versión que necesites. Los Word son editables.")
    theme_keys = list(EDITABLE_WORD_THEMES.keys())
    default_idx = theme_keys.index("neutral") if "neutral" in theme_keys else 0
    theme_key = st.selectbox(
        "Diseño de la carta",
        theme_keys,
        index=default_idx,
        format_func=lambda k: EDITABLE_WORD_THEMES[k]["name"],
        key="v12_main_theme",
    )
    restaurant = slugify_filename(data.get("restaurant_name", "menu"))
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("### 🛡️ Con alérgenos")
        st.caption(f"Alérgenos calculados por {data.get('_allergen_model', MODELO_ALERGENOS)} y editables en Revisar.")
        word_all = create_word(data, theme_key=theme_key)
        pdf_all = create_client_pdf_bytes(data, theme_key=theme_key, with_allergens=True)
        st.download_button("⬇️ WORD CON ALÉRGENOS", word_all, file_name=f"Carta_Con_Alergenos_{restaurant}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", key="v12_word_all", use_container_width=True)
        if pdf_all:
            st.download_button("⬇️ PDF CON ALÉRGENOS", pdf_all, file_name=f"Carta_Con_Alergenos_{restaurant}.pdf", mime="application/pdf", key="v12_pdf_all", use_container_width=True)

    with c2:
        st.markdown("### 📄 Sin alérgenos")
        st.caption("Mismo diseño y contenido, sin iconos ni leyenda.")
        word_clean = create_client_word_without_allergens(data, theme_key=theme_key)
        pdf_clean = create_client_pdf_bytes(data, theme_key=theme_key, with_allergens=False)
        st.download_button("⬇️ WORD SIN ALÉRGENOS", word_clean, file_name=f"Carta_Sin_Alergenos_{restaurant}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", key="v12_word_clean", use_container_width=True)
        if pdf_clean:
            st.download_button("⬇️ PDF SIN ALÉRGENOS", pdf_clean, file_name=f"Carta_Sin_Alergenos_{restaurant}.pdf", mime="application/pdf", key="v12_pdf_clean", use_container_width=True)

    st.info("Para cambiar un alérgeno manualmente, vuelve a Revisar y usa el selector del plato. No hay validaciones obligatorias.")
'''


def patch_app() -> None:
    src = APP.read_text(encoding="utf-8")
    src = src.replace('MODELO_A_USAR = "gemini-3.6-flash"', 'MODELO_A_USAR = "gemini-3.8-flash"\nMODELO_ALERGENOS = "gemini-3.1-pro-preview"')

    if "'neutral': {'name':'Neutra'" not in src:
        src = src.replace(
            "EDITABLE_WORD_THEMES = {",
            "EDITABLE_WORD_THEMES = {\n    'neutral': {'name':'Neutra', 'header':'1F2937', 'cat':'374151', 'text':'111827', 'muted':'6B7280', 'bg':'FFFFFF', 'light':'F9FAFB'},",
            1,
        )

    src = replace_function(src, "build_ai_prompt", BUILD_PROMPT)
    src = replace_function(src, "_gemini_menu_json", GEMINI_MENU_JSON)
    src = replace_function(src, "apply_allergen_rules_to_dish", APPLY_DISH)
    src = replace_function(src, "analyze_content", ANALYZE_CONTENT)
    src = replace_function(src, "analyze_audio_menu", ANALYZE_AUDIO)
    src = replace_function(src, "add_docx_allergen_legend", DIRECT_FOOTER)
    src = replace_function(src, "create_word", CREATE_WORD)
    src = replace_function(src, "create_client_word_without_allergens", CREATE_NO_ALLERGENS)
    src = replace_function(src, "render_quick_outputs", PDF_AND_DOWNLOADS.split("\ndef render_quick_outputs", 1)[1].join(["def render_quick_outputs", ""]) if False else "")

    # Restore render_quick_outputs replacement plus insert PDF helpers before it.
    # The empty replacement above is never used; this branch is intentionally handled below.
    APP.write_text(src, encoding="utf-8")


def patch_app_complete() -> None:
    src = APP.read_text(encoding="utf-8")
    # Undo-safe: if render_quick_outputs was not yet replaced, use AST directly.
    pdf_block, quick_body = PDF_AND_DOWNLOADS.rsplit("\ndef render_quick_outputs", 1)
    if "def create_client_pdf_html(" not in src:
        src = insert_before_function(src, "render_quick_outputs", pdf_block)
    src = replace_function(src, "render_quick_outputs", "def render_quick_outputs" + quick_body)
    src = src.replace('def _create_client_word(data, with_allergens=False, theme_key="cafe", two_columns=False):', 'def _create_client_word(data, with_allergens=False, theme_key="neutral", two_columns=False):')
    if "ALLERGEN_AI_SCHEMA =" not in src:
        src = insert_before_function(src, "_word_or_phrase", AI_ALLERGEN_BLOCK)
    APP.write_text(src, encoding="utf-8")


def patch_sitecustomize() -> None:
    src = PATCH.read_text(encoding="utf-8")
    src = src.replace(
        "def _install():\n    _install_inline_icon_minimum()\n    _install_document_footer_patch()",
        "def _install():\n    # El footer lo crea app.py directamente; aquí solo mantenemos el mínimo visual de iconos inline.\n    _install_inline_icon_minimum()",
    )
    PATCH.write_text(src, encoding="utf-8")


def patch_requirements() -> None:
    src = REQ.read_text(encoding="utf-8")
    src = src.replace("google-genai==2.16.0", "google-genai==2.29.0")
    REQ.write_text(src, encoding="utf-8")


def validate() -> None:
    src = APP.read_text(encoding="utf-8")
    ast.parse(src)
    assert 'MODELO_A_USAR = "gemini-3.8-flash"' in src
    assert 'MODELO_ALERGENOS = "gemini-3.1-pro-preview"' in src
    assert "thinking_level=\"high\"" in src
    assert "infer_allergens_with_best_model" in src
    assert "dish[\"allergens\"] = combined" in src
    assert "def create_client_pdf_bytes" in src
    assert "WORD CON ALÉRGENOS" in src and "PDF CON ALÉRGENOS" in src
    assert "WORD SIN ALÉRGENOS" in src and "PDF SIN ALÉRGENOS" in src
    assert "'neutral': {'name':'Neutra'" in src
    assert "footer.add_table" in src and "width=Cm(1.25)" in src
    patch = PATCH.read_text(encoding="utf-8")
    assert "_install_document_footer_patch()" not in patch.split("def _install():", 1)[1].split("_install()", 1)[0]
    assert "google-genai==2.29.0" in REQ.read_text(encoding="utf-8")


if __name__ == "__main__":
    # First pass modifies the existing functions/constants.
    src = APP.read_text(encoding="utf-8")
    src = src.replace('MODELO_A_USAR = "gemini-3.6-flash"', 'MODELO_A_USAR = "gemini-3.8-flash"\nMODELO_ALERGENOS = "gemini-3.1-pro-preview"')
    if "'neutral': {'name':'Neutra'" not in src:
        src = src.replace("EDITABLE_WORD_THEMES = {", "EDITABLE_WORD_THEMES = {\n    'neutral': {'name':'Neutra', 'header':'1F2937', 'cat':'374151', 'text':'111827', 'muted':'6B7280', 'bg':'FFFFFF', 'light':'F9FAFB'},", 1)
    src = replace_function(src, "build_ai_prompt", BUILD_PROMPT)
    src = replace_function(src, "_gemini_menu_json", GEMINI_MENU_JSON)
    src = replace_function(src, "apply_allergen_rules_to_dish", APPLY_DISH)
    src = replace_function(src, "analyze_content", ANALYZE_CONTENT)
    src = replace_function(src, "analyze_audio_menu", ANALYZE_AUDIO)
    src = replace_function(src, "add_docx_allergen_legend", DIRECT_FOOTER)
    src = replace_function(src, "create_word", CREATE_WORD)
    src = replace_function(src, "create_client_word_without_allergens", CREATE_NO_ALLERGENS)
    src = src.replace('def _create_client_word(data, with_allergens=False, theme_key="cafe", two_columns=False):', 'def _create_client_word(data, with_allergens=False, theme_key="neutral", two_columns=False):')
    APP.write_text(src, encoding="utf-8")
    patch_app_complete()
    patch_sitecustomize()
    patch_requirements()
    validate()
    print("PASS v12 core: 3.8 Flash + Pro allergens + direct footer + Word/PDF pairs")
