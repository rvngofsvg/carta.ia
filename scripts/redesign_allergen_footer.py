from pathlib import Path
import re

APP = Path('app.py')
text = APP.read_text(encoding='utf-8')

new_func = r'''def add_docx_allergen_legend(doc, data, theme):
    """Leyenda 2x7 limpia: un único marco exterior y retícula interior invisible."""
    legal_text = (
        "Informamos de acuerdo con el Reglamento de la UE 1169/2011, que nuestros productos "
        "contienen o pueden contener los siguientes alérgenos."
    )
    legend_labels = {
        "gluten": "GLUTEN",
        "crustaceos": "CRUSTÁCEOS",
        "huevos": "HUEVOS",
        "pescado": "PESCADO",
        "cacahuetes": "CACAHUETES",
        "soja": "SOJA",
        "lacteos": "LÁCTEOS",
        "frutos de cascara": "FRUTOS DE\nCÁSCARA",
        "apio": "APIO",
        "mostaza": "MOSTAZA",
        "sesamo": "GRANOS DE\nSÉSAMO",
        "sulfitos": "DIÓXIDO DE AZUFRE\nY SULFITOS",
        "altramuces": "ALTRAMUCES",
        "moluscos": "MOLUSCOS",
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

    def set_cell_margins_local(cell, top=0, start=0, bottom=0, end=0):
        tc_pr = cell._tc.get_or_add_tcPr()
        tc_mar = tc_pr.find(qn("w:tcMar"))
        if tc_mar is None:
            tc_mar = OxmlElement("w:tcMar")
            tc_pr.append(tc_mar)
        for edge, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
            node = tc_mar.find(qn(f"w:{edge}"))
            if node is None:
                node = OxmlElement(f"w:{edge}")
                tc_mar.append(node)
            node.set(qn("w:w"), str(int(value)))
            node.set(qn("w:type"), "dxa")

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

    def nil_table_borders(table):
        tbl_pr = table._tbl.tblPr
        borders = tbl_pr.first_child_found_in("w:tblBorders")
        if borders is None:
            borders = OxmlElement("w:tblBorders")
            tbl_pr.append(borders)
        for edge in ("top", "start", "bottom", "end", "insideH", "insideV"):
            node = borders.find(qn(f"w:{edge}"))
            if node is None:
                node = OxmlElement(f"w:{edge}")
                borders.append(node)
            node.set(qn("w:val"), "nil")

    def nil_cell_borders(cell):
        tc_pr = cell._tc.get_or_add_tcPr()
        borders = tc_pr.find(qn("w:tcBorders"))
        if borders is None:
            borders = OxmlElement("w:tcBorders")
            tc_pr.append(borders)
        for edge in ("top", "start", "bottom", "end", "insideH", "insideV"):
            node = borders.find(qn(f"w:{edge}"))
            if node is None:
                node = OxmlElement(f"w:{edge}")
                borders.append(node)
            node.set(qn("w:val"), "nil")

    border_color = theme.get("muted", "6B7280")

    for section in doc.sections:
        if section.bottom_margin < Cm(3.8):
            section.bottom_margin = Cm(3.8)
        section.footer_distance = Cm(0.12)
        usable_cm = max(12.0, (section.page_width - section.left_margin - section.right_margin) / 360000.0)

        for footer in (section.footer, section.first_page_footer, section.even_page_footer):
            footer.is_linked_to_previous = False
            clear(footer)

            wrapper = footer.add_table(rows=1, cols=1, width=Cm(usable_cm))
            wrapper.alignment = WD_TABLE_ALIGNMENT.CENTER
            wrapper.autofit = False
            set_grid_widths(wrapper, [usable_cm])
            set_outer_border(wrapper, border_color)

            cell = wrapper.cell(0, 0)
            set_cell_width(cell, usable_cm)
            set_cell_margins_local(cell, top=16, start=42, bottom=12, end=42)
            cell.text = ""

            legal = cell.paragraphs[0]
            legal.alignment = 1
            compact(legal)
            legal.paragraph_format.space_after = Pt(1.2)
            lr = legal.add_run(legal_text)
            lr.font.size = Pt(8.4)
            lr.bold = True
            set_run_color(lr, theme.get("text", "111111"))

            col_weights = [1.00, 1.12, 0.92, 0.98, 1.12, 1.02, 1.00]
            weight_total = sum(col_weights)
            col_widths = [usable_cm * weight / weight_total for weight in col_weights]
            grid = cell.add_table(rows=2, cols=7)
            grid.alignment = WD_TABLE_ALIGNMENT.CENTER
            grid.autofit = False
            set_grid_widths(grid, col_widths)
            nil_table_borders(grid)

            trailing = cell.paragraphs[-1]
            compact(trailing)
            trailing.paragraph_format.line_spacing = Pt(1)
            if not trailing.runs:
                trailing.add_run("")
            for run in trailing.runs:
                run.font.size = Pt(1)

            for idx, allergen in enumerate(ALLERGEN_ORDER):
                r, c = divmod(idx, 7)
                item = grid.cell(r, c)
                nil_cell_borders(item)
                set_cell_width(item, col_widths[c])
                set_cell_margins_local(item, top=0, start=14, bottom=0, end=14)
                item.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

                tc_pr = item._tc.get_or_add_tcPr()
                no_wrap = tc_pr.find(qn("w:noWrap"))
                if no_wrap is None:
                    no_wrap = OxmlElement("w:noWrap")
                    tc_pr.append(no_wrap)

                item.text = ""
                p = item.paragraphs[0]
                p.alignment = 1
                compact(p)
                icon_path = ICON_MAP.get(allergen)
                if icon_path and os.path.exists(icon_path):
                    try:
                        p.add_run().add_picture(icon_path, width=Cm(0.92))
                    except Exception:
                        pass

                lp = item.add_paragraph()
                lp.alignment = 1
                compact(lp)
                lp.paragraph_format.line_spacing = Pt(7.7)
                label = lp.add_run(legend_labels.get(allergen, ALLERGEN_LABELS.get(allergen, allergen)))
                label.font.size = Pt(7.4)
                label.bold = True
                set_run_color(label, theme.get("text", "111111"))

            nil_table_borders(grid)

'''

# MUY IMPORTANTE: solo sustituir la función de la leyenda. La siguiente función
# en la fuente estable es create_editable_word_clean_template. No atravesar otros
# helpers ni generadores del proyecto.
pattern = re.compile(
    r"def add_docx_allergen_legend\(doc, data, theme\):.*?(?=\ndef create_editable_word_clean_template\()",
    re.S,
)
text, n = pattern.subn(lambda _m: new_func, text, count=1)
if n != 1:
    raise SystemExit(f'No se pudo reemplazar únicamente add_docx_allergen_legend: {n}')

# Iconos inline Word: discretos y siempre después del precio.
text = text.replace(
    'def _add_allergen_icons_to_run(paragraph, allergens, width_cm=0.75):',
    'def _add_allergen_icons_to_run(paragraph, allergens, width_cm=0.46):',
)
text = text.replace(
    '_add_allergen_icons_to_run(p, dish.get("allergens", []), width_cm=0.75)',
    '_add_allergen_icons_to_run(p, dish.get("allergens", []), width_cm=0.46)',
)

# PDF principal: mismo lenguaje visual que Word, compacto y sin aspecto de tabla.
repls = {
    'margin: 15mm 15mm 58mm 15mm;': 'margin: 15mm 15mm 42mm 15mm;',
    'height: 48mm;': 'height: 33mm;',
    'border: 1.2px solid #4b4038;': 'border: 1px solid #7a746e;',
    'padding: 2.5mm 3mm 2mm;': 'padding: 1.4mm 2.5mm 1.0mm;',
    'font-size: 8.6pt;': 'font-size: 8.2pt;',
    'margin: 0 0 1.5mm;': 'margin: 0 0 0.8mm;',
    'height: 17mm;': 'height: 11.2mm;',
    'font-size: 7.6pt;': 'font-size: 7.2pt;',
    'width: 9.2mm;': 'width: 7.4mm;',
    'height: 9.2mm;': 'height: 7.4mm;',
    'margin: 0 auto 0.6mm;': 'margin: 0 auto 0.25mm;',
    '.dish-icon{{width:7.5mm;height:7.5mm;object-fit:contain;}}': '.dish-icon{{width:4.6mm;height:4.6mm;object-fit:contain;}}',
}
for old, new in repls.items():
    text = text.replace(old, new)

# Guardarraíl: si desaparece una función estructural, abortar antes de escribir.
required_functions = [
    'def create_editable_word_clean_template(',
    'def show_asset_diagnostics(',
    'def _add_allergen_icons_to_run(',
    'def _create_client_word(',
    'def create_client_pdf_html(',
    'def analyze_content(',
]
missing = [name for name in required_functions if name not in text]
if missing:
    raise SystemExit('El parche intentó eliminar funciones estructurales: ' + ', '.join(missing))

APP.write_text(text, encoding='utf-8')
print('Allergen footer redesign applied surgically')
