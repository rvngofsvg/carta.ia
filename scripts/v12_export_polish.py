from __future__ import annotations

import ast
import textwrap
from pathlib import Path

APP = Path("app.py")


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


WORD_BUILDER = r'''
def _create_client_word(data, with_allergens=False, theme_key="neutral", two_columns=False):
    """Genera las dos cartas Word desde la misma plantilla visual.

    La versión con alérgenos añade iconos y footer; la versión sin alérgenos
    limpia cualquier leyenda heredada de la plantilla base.
    """
    theme = EDITABLE_WORD_THEMES.get(theme_key, EDITABLE_WORD_THEMES["neutral"])
    doc = new_doc_from_template() if not two_columns else Document()

    def clear_footer(footer):
        footer.is_linked_to_previous = False
        for child in list(footer._element):
            footer._element.remove(child)

    # La plantilla histórica llevaba una imagen de leyenda en el footer.
    # Se elimina siempre y solo se reconstruye si la salida pide alérgenos.
    for sec in doc.sections:
        for footer in (sec.footer, sec.first_page_footer, sec.even_page_footer):
            clear_footer(footer)
        if two_columns:
            set_docx_margins(sec)
            set_docx_two_columns(sec)
        else:
            sec.bottom_margin = Cm(1.8)

    rest_name = data.get("restaurant_name", "MENÚ")
    p_title = doc.add_heading(rest_name, 0)
    release_paragraph_constraints(p_title, SANGRIA_CATEGORIA)
    for run in p_title.runs:
        run.bold = True
        run.font.size = Pt(24)
        set_run_color(run, theme["header"])

    for block in unique_text_blocks(data.get("texto_extra"), data.get("header_text"), data.get("footer_text"), data.get("notes")):
        add_text_block_to_doc(doc, block, SANGRIA_CATEGORIA, font_size=10.5, italic=True, color=theme["muted"])

    for category in data.get("categories", []):
        p_cat = doc.add_heading(category.get("name", "Categoría"), level=1)
        release_paragraph_constraints(p_cat, SANGRIA_CATEGORIA)
        p_cat.paragraph_format.space_before = Pt(6)
        for run in p_cat.runs:
            run.bold = True
            run.font.size = Pt(16)
            set_run_color(run, theme["cat"])

        for block in unique_text_blocks(category.get("category_text"), category.get("texto_extra"), category.get("notes")):
            add_text_block_to_doc(doc, block, SANGRIA_PLATOS, font_size=10.0, italic=True, color=theme["muted"])

        for dish in category.get("dishes", []):
            p = doc.add_paragraph()
            release_paragraph_constraints(p, SANGRIA_PLATOS, is_dish=True)
            p.paragraph_format.tab_stops.add_tab_stop(Cm(15.0 if not two_columns else 7.8), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            name_run = p.add_run(dish_display_name(dish))
            name_run.bold = True
            name_run.font.size = Pt(11.5)
            set_run_color(name_run, theme["text"])

            if with_allergens and get_ordered_allergens(dish.get("allergens", [])):
                p.add_run("  ")
                _add_allergen_icons_to_run(p, dish.get("allergens", []), width_cm=0.75)

            price_run = p.add_run("\t" + format_price(dish.get("price", "")))
            price_run.bold = True
            price_run.font.size = Pt(11.2)
            set_run_color(price_run, theme["cat"])

            if dish.get("description"):
                pd = doc.add_paragraph()
                release_paragraph_constraints(pd, SANGRIA_PLATOS, is_dish=True)
                rd = pd.add_run(str(dish.get("description") or ""))
                rd.italic = True
                rd.font.size = Pt(10)
                set_run_color(rd, theme["muted"])

    if with_allergens:
        add_docx_allergen_legend(doc, data, theme)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
'''


WORD_FOOTER = r'''
def add_docx_allergen_legend(doc, data, theme):
    """Leyenda nativa 2x7 insertada directamente en el footer real de Word."""
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

    def set_cell_width(cell, width_cm):
        width = Cm(width_cm)
        cell.width = width
        tc_pr = cell._tc.get_or_add_tcPr()
        tc_w = tc_pr.find(qn("w:tcW"))
        if tc_w is None:
            tc_w = OxmlElement("w:tcW")
            tc_pr.append(tc_w)
        tc_w.set(qn("w:w"), str(int(width.twips)))
        tc_w.set(qn("w:type"), "dxa")

    def set_grid_widths(table, widths_cm):
        grid_cols = table._tbl.tblGrid.findall(qn("w:gridCol"))
        for idx, width_cm in enumerate(widths_cm):
            if idx < len(grid_cols):
                grid_cols[idx].set(qn("w:w"), str(int(Cm(width_cm).twips)))

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
            set_grid_widths(wrapper, [usable_cm])
            set_outer_border(wrapper, theme.get("cat", "444444"))
            cell = wrapper.cell(0, 0)
            set_cell_width(cell, usable_cm)
            cell.text = ""

            legal = cell.paragraphs[0]
            legal.alignment = 1
            compact(legal)
            legal.paragraph_format.space_after = Pt(3)
            lr = legal.add_run(legal_text)
            lr.font.size = Pt(9.0)
            lr.bold = True
            set_run_color(lr, theme.get("text", "111111"))

            col_cm = usable_cm / 7.0
            grid = cell.add_table(rows=2, cols=7)
            grid.alignment = WD_TABLE_ALIGNMENT.CENTER
            grid.autofit = False
            set_grid_widths(grid, [col_cm] * 7)

            for idx, allergen in enumerate(ALLERGEN_ORDER):
                r, c = divmod(idx, 7)
                item = grid.cell(r, c)
                set_cell_width(item, col_cm)
                item.text = ""
                item.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

                p = item.paragraphs[0]
                p.alignment = 1
                compact(p)
                icon_path = ICON_MAP.get(allergen)
                if icon_path and os.path.exists(icon_path):
                    p.add_run().add_picture(icon_path, width=Cm(1.25))

                lp = item.add_paragraph()
                lp.alignment = 1
                compact(lp)
                lp.paragraph_format.space_before = Pt(1)
                label = lp.add_run(legend_labels.get(allergen, ALLERGEN_LABELS.get(allergen, allergen)))
                label.font.size = Pt(9.0)
                label.bold = True
                set_run_color(label, theme.get("text", "111111"))
'''


PDF_BUILDER = r'''
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
        labels = {
            "gluten": "GLUTEN", "crustaceos": "CRUSTÁCEOS", "huevos": "HUEVOS", "pescado": "PESCADO",
            "cacahuetes": "CACAHUETES", "soja": "SOJA", "lacteos": "LÁCTEOS", "frutos de cascara": "FRUTOS DE CÁSCARA",
            "apio": "APIO", "mostaza": "MOSTAZA", "sesamo": "GRANOS DE SÉSAMO", "sulfitos": "DIÓXIDO DE AZUFRE Y SULFITOS",
            "altramuces": "ALTRAMUCES", "moluscos": "MOLUSCOS",
        }
        items = []
        for allergen in ALLERGEN_ORDER:
            src = file_to_data_uri(ICON_MAP.get(allergen))
            icon = f'<img src="{src}">' if src else ""
            items.append(f'<div class="legend-item">{icon}<span>{labels[allergen]}</span></div>')
        footer_html = (
            '<footer class="allergen-footer">'
            '<div class="legal">Informamos de acuerdo con el Reglamento de la UE 1169/2011, que nuestros productos contienen o pueden contener los siguientes alérgenos.</div>'
            f'<div class="legend-grid">{"".join(items)}</div></footer>'
        )
        page_bottom = "58mm"
        footer_css = """
        .allergen-footer{position:fixed;left:0;right:0;bottom:-52mm;height:48mm;border:1.2px solid #4b4038;padding:2.5mm 3mm 2mm;box-sizing:border-box;background:#fff;overflow:visible;}
        .legal{text-align:center;font-size:8.6pt;font-weight:700;margin-bottom:1.8mm;line-height:1.12;}
        .legend-grid{display:flex;flex-wrap:wrap;align-content:flex-start;width:100%;}
        .legend-item{width:14.285714%;height:17mm;text-align:center;font-size:7.8pt;font-weight:700;line-height:1.0;padding:.4mm .6mm;box-sizing:border-box;}
        .legend-item img{display:block;width:9.5mm;height:9.5mm;object-fit:contain;margin:0 auto .7mm;}
        .legend-item span{display:block;overflow-wrap:normal;word-break:normal;}
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
'''


def main() -> None:
    src = APP.read_text(encoding="utf-8")
    src = replace_function(src, "_create_client_word", WORD_BUILDER)
    src = replace_function(src, "add_docx_allergen_legend", WORD_FOOTER)
    src = replace_function(src, "create_client_pdf_html", PDF_BUILDER)
    APP.write_text(src, encoding="utf-8")

    parsed = ast.parse(src)
    assert parsed
    assert "sec.bottom_margin = Cm(1.8)" in src
    assert "grid.autofit = False" in src
    assert "set_grid_widths(grid, [col_cm] * 7)" in src
    assert "display:flex;flex-wrap:wrap" in src
    assert "bottom:-52mm" in src
    print("PASS v12 export polish")


if __name__ == "__main__":
    main()
