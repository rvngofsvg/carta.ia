from io import BytesIO
from pathlib import Path
import sys
import unicodedata

from docx.document import Document as _DocumentClass
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from docx.text.run import Run as _RunClass


LEGAL_TEXT = (
    "Informamos de acuerdo con el Reglamento de la UE 1169/2011, "
    "que nuestros productos contienen o pueden contener los siguientes alérgenos."
)

LEGEND_ITEMS = (
    ("GLUTEN", "gluten.png"),
    ("CRUSTÁCEOS", "gambas.png"),
    ("HUEVOS", "huevo.png"),
    ("PESCADO", "pescado.png"),
    ("CACAHUETES", "cacahuetes.png"),
    ("SOJA", "soja.png"),
    ("LÁCTEOS", "lacteos.png"),
    ("FRUTOS DE\nCÁSCARA", "frutos_secos.png"),
    ("APIO", "apio.png"),
    ("MOSTAZA", "mostaza.png"),
    ("GRANOS DE\nSÉSAMO", "sesamo.png"),
    ("DIÓXIDO DE AZUFRE\nY SULFITOS", "sulfitos.png"),
    ("ALTRAMUCES", "altramuces.png"),
    ("MOLUSCOS", "moluscos.png"),
)

_ALLERGEN_ICON_FILENAMES = {filename.lower() for _, filename in LEGEND_ITEMS}
INLINE_ICON_MIN_CM = 0.75


def _find_root():
    for base in (Path.cwd(), *Path.cwd().parents):
        if (base / "Public" / "Iconos").exists():
            return base
    return Path.cwd()


def _find_legend_path():
    root = _find_root()
    filename = "leyenda_alergenos_eider.png"
    candidates = (
        Path(sys.prefix) / "serval_eider_legend" / filename,
        Path(__file__).resolve().parent / "serval_eider_legend" / filename,
        root / "serval_eider_patch" / filename,
    )
    for path in candidates:
        if path.is_file():
            return path
    return candidates[-1]


def _find_icon_dir():
    """Localiza primero los iconos empaquetados y solo después el árbol del proyecto."""
    root = _find_root()
    candidates = (
        Path(sys.prefix) / "serval_eider_icons",
        Path(__file__).resolve().parent / "serval_eider_icons",
        root / "serval_eider_patch" / "icons",
        root / "Public" / "Iconos",
        Path(__file__).resolve().parent.parent / "Public" / "Iconos",
    )
    for path in candidates:
        if path.is_dir() and all((path / filename).is_file() for _, filename in LEGEND_ITEMS):
            return path
    return None


_LEGEND_PATH = _find_legend_path()
_ICON_DIR = _find_icon_dir()
_LEGEND_BYTES = None
_ORIGINAL_SAVE = None
_ORIGINAL_RUN_ADD_PICTURE = None


def _legend_bytes():
    """Fallback visual original de Eider; la salida normal usa la leyenda Word nativa."""
    global _LEGEND_BYTES
    if _LEGEND_BYTES is not None:
        return _LEGEND_BYTES

    if not _LEGEND_PATH.is_file():
        raise FileNotFoundError(f"No se encontró la leyenda de alérgenos de Eider: {_LEGEND_PATH}")

    raw = _LEGEND_PATH.read_bytes()
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("La leyenda de alérgenos de Eider no es un PNG válido")
    _LEGEND_BYTES = raw
    return _LEGEND_BYTES


def _normalize(text):
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().split())


def _remove_element(element):
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def _looks_like_allergen_legend_table(table):
    terms = {
        "GLUTEN", "CRUSTACEOS", "HUEVOS", "PESCADO", "CACAHUETES", "SOJA", "LACTEOS",
        "FRUTOS DE CASCARA", "APIO", "MOSTAZA", "SESAMO", "SULFITOS", "ALTRAMUCES", "MOLUSCOS",
    }
    joined = _normalize(" ".join(cell.text for row in table.rows for cell in row.cells))
    return len(table.rows) <= 4 and sum(term in joined for term in terms) >= 7


def _document_requests_allergen_footer(doc):
    """Evita modificar Word limpios o cartas finales sin alérgenos."""
    for paragraph in doc.paragraphs:
        text = _normalize(paragraph.text)
        if (
            "GUIA DE ALERGENOS" in text
            or "INFORMACION ORIENTATIVA BASADA EN CARTA" in text
            or "DEBE VALIDARSE CON INGREDIENTES REALES" in text
        ):
            return True
    return any(_looks_like_allergen_legend_table(table) for table in doc.tables)


def _remove_old_body_legend(doc):
    """Elimina la leyenda antigua del body antes de crear el pie real."""
    for paragraph in list(doc.paragraphs):
        text = _normalize(paragraph.text)
        if (
            "GUIA DE ALERGENOS" in text
            or "INFORMACION ORIENTATIVA BASADA EN CARTA" in text
            or "DEBE VALIDARSE CON INGREDIENTES REALES" in text
        ):
            _remove_element(paragraph._element)

    for table in list(doc.tables):
        if _looks_like_allergen_legend_table(table):
            _remove_element(table._element)


def _clear(container):
    for child in list(container._element):
        container._element.remove(child)


def _set_cell_width(cell, width_cm):
    width = Cm(width_cm)
    cell.width = width
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_w = tc_pr.find(qn("w:tcW"))
    if tc_w is None:
        tc_w = OxmlElement("w:tcW")
        tc_pr.append(tc_w)
    tc_w.set(qn("w:w"), str(int(width.twips)))
    tc_w.set(qn("w:type"), "dxa")


def _set_table_grid_widths(table, widths_cm):
    grid_cols = table._tbl.tblGrid.findall(qn("w:gridCol"))
    for idx, width_cm in enumerate(widths_cm):
        if idx < len(grid_cols):
            grid_cols[idx].set(qn("w:w"), str(int(Cm(width_cm).twips)))


def _set_cell_margins(cell, twips=0):
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for name in ("top", "start", "bottom", "end"):
        node = tc_mar.find(qn(f"w:{name}"))
        if node is None:
            node = OxmlElement(f"w:{name}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(twips))
        node.set(qn("w:type"), "dxa")


def _set_cell_border(cell, size=10, color="3F332B"):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "start", "bottom", "end"):
        node = borders.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            borders.append(node)
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), str(size))
        node.set(qn("w:space"), "0")
        node.set(qn("w:color"), color)


def _remove_table_borders(table):
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


def _compact_paragraph(paragraph):
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1


def _add_fallback_picture(paragraph, width_cm):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _compact_paragraph(paragraph)
    paragraph.add_run().add_picture(BytesIO(_legend_bytes()), width=Cm(width_cm))


def _fill_native_legend(cell, width_cm, icon_cm, label_pt, legal_pt):
    """Leyenda en 2 filas de 7 para que iconos y etiquetas sean realmente legibles."""
    if _ICON_DIR is None:
        raise FileNotFoundError("No se encontraron los 14 iconos empaquetados de alérgenos")

    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    _set_cell_margins(cell, 45)
    _set_cell_border(cell)

    legal = cell.paragraphs[0]
    legal.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _compact_paragraph(legal)
    legal.paragraph_format.space_after = Pt(2)
    legal_run = legal.add_run(LEGAL_TEXT)
    legal_run.font.size = Pt(legal_pt)
    legal_run.bold = True

    grid = cell.add_table(rows=2, cols=7)
    grid.alignment = WD_TABLE_ALIGNMENT.CENTER
    grid.autofit = False
    _remove_table_borders(grid)
    col_cm = width_cm / 7.0
    _set_table_grid_widths(grid, [col_cm] * 7)

    for idx, (label, filename) in enumerate(LEGEND_ITEMS):
        row = idx // 7
        col = idx % 7
        item_cell = grid.cell(row, col)
        item_cell.text = ""
        item_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        _set_cell_width(item_cell, col_cm)
        _set_cell_margins(item_cell, 16)

        icon_p = item_cell.paragraphs[0]
        icon_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _compact_paragraph(icon_p)
        icon_p.add_run().add_picture(str(_ICON_DIR / filename), width=Cm(icon_cm))

        label_p = item_cell.add_paragraph()
        label_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _compact_paragraph(label_p)
        label_p.paragraph_format.space_before = Pt(1)
        label_run = label_p.add_run(label)
        label_run.font.size = Pt(label_pt)
        label_run.bold = True


def _footer_variants(section):
    return section.footer, section.first_page_footer, section.even_page_footer


def _single_footer(section, usable_cm):
    if section.bottom_margin < Cm(6.1):
        section.bottom_margin = Cm(6.1)
    section.footer_distance = Cm(0.15)

    for footer in _footer_variants(section):
        footer.is_linked_to_previous = False
        _clear(footer)
        width_cm = min(18.2, usable_cm)
        wrapper = footer.add_table(rows=1, cols=1, width=Cm(width_cm))
        wrapper.alignment = WD_TABLE_ALIGNMENT.CENTER
        wrapper.autofit = False
        _set_table_grid_widths(wrapper, [width_cm])
        _set_cell_width(wrapper.cell(0, 0), width_cm)
        try:
            _fill_native_legend(
                wrapper.cell(0, 0),
                width_cm=width_cm,
                icon_cm=1.35,
                label_pt=10.2,
                legal_pt=9.6,
            )
        except Exception:
            _clear(footer)
            _add_fallback_picture(footer.add_paragraph(), width_cm)


def _book_footer(section, usable_cm):
    if section.bottom_margin < Cm(5.4):
        section.bottom_margin = Cm(5.4)
    section.footer_distance = Cm(0.12)
    gutter_cm = 0.8
    side_cm = max(6.0, (usable_cm - gutter_cm) / 2.0)
    widths = (side_cm, gutter_cm, side_cm)

    for footer in _footer_variants(section):
        footer.is_linked_to_previous = False
        _clear(footer)
        table = footer.add_table(rows=1, cols=3, width=Cm(usable_cm))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        _remove_table_borders(table)
        _set_table_grid_widths(table, widths)

        for idx, width in enumerate(widths):
            cell = table.cell(0, idx)
            _set_cell_width(cell, width)
            _set_cell_margins(cell, 0)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

        try:
            for idx in (0, 2):
                _fill_native_legend(
                    table.cell(0, idx),
                    width_cm=side_cm,
                    icon_cm=1.00,
                    label_pt=8.3,
                    legal_pt=8.0,
                )
        except Exception:
            for idx in (0, 2):
                table.cell(0, idx).text = ""
                _add_fallback_picture(table.cell(0, idx).paragraphs[0], max(5.5, side_cm - 0.35))
        table.cell(0, 1).text = ""


def _prepare(doc):
    # Solo las cartas que ya incluyen la guía de alérgenos solicitan este footer.
    if not _document_requests_allergen_footer(doc):
        return

    _remove_old_body_legend(doc)
    for section in doc.sections:
        usable_cm = max(
            1.0,
            (section.page_width - section.left_margin - section.right_margin) / 360000.0,
        )
        if section.page_width > section.page_height:
            _book_footer(section, usable_cm)
        else:
            _single_footer(section, usable_cm)


def _install_inline_icon_minimum():
    """Corrige todos los iconos inline minúsculos del generador sin tocar iconos grandes de leyenda."""
    global _ORIGINAL_RUN_ADD_PICTURE
    if getattr(_RunClass.add_picture, "_serval_allergen_icon_patch", False):
        return

    _ORIGINAL_RUN_ADD_PICTURE = _RunClass.add_picture

    def add_picture_with_minimum(self, image_path_or_stream, width=None, height=None):
        adjusted_width = width
        try:
            if width is not None and isinstance(image_path_or_stream, (str, Path)):
                filename = Path(image_path_or_stream).name.lower()
                if filename in _ALLERGEN_ICON_FILENAMES and int(width) < int(Cm(INLINE_ICON_MIN_CM)):
                    adjusted_width = Cm(INLINE_ICON_MIN_CM)
        except Exception:
            adjusted_width = width
        return _ORIGINAL_RUN_ADD_PICTURE(self, image_path_or_stream, width=adjusted_width, height=height)

    add_picture_with_minimum._serval_allergen_icon_patch = True
    _RunClass.add_picture = add_picture_with_minimum


def _install_document_footer_patch():
    global _ORIGINAL_SAVE
    if getattr(_DocumentClass.save, "_eider_legend_patch", False):
        return
    _ORIGINAL_SAVE = _DocumentClass.save

    def save_with_eider_legend(self, path_or_stream):
        _prepare(self)
        return _ORIGINAL_SAVE(self, path_or_stream)

    save_with_eider_legend._eider_legend_patch = True
    _DocumentClass.save = save_with_eider_legend


def _install():
    # El footer lo crea app.py directamente; aquí solo mantenemos el mínimo visual de iconos inline.
    _install_inline_icon_minimum()


_install()
