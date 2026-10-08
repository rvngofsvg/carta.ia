from io import BytesIO
from pathlib import Path
import unicodedata

from PIL import Image, ImageDraw, ImageFont, ImageOps
from docx.document import Document as _DocumentClass
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt


def _find_root():
    candidates = [Path.cwd(), *Path.cwd().parents]
    for base in candidates:
        if (base / "Public" / "Iconos").exists():
            return base
    return Path.cwd()


_ROOT = _find_root()
_ASSET_PATH = _ROOT / "serval_eider_patch" / "leyenda_alergenos_eider.webp"
_ICON_DIR = _ROOT / "Public" / "Iconos"
_ORDER = [
    "gluten", "crustaceos", "huevos", "pescado", "cacahuetes", "soja", "lacteos",
    "frutos de cascara", "apio", "mostaza", "sesamo", "sulfitos", "altramuces", "moluscos",
]
_ICON_FILES = {
    "gluten": "gluten.png", "crustaceos": "gambas.png", "huevos": "huevo.png",
    "pescado": "pescado.png", "cacahuetes": "cacahuetes.png", "soja": "soja.png",
    "lacteos": "lacteos.png", "frutos de cascara": "frutos_secos.png", "apio": "apio.png",
    "mostaza": "mostaza.png", "sesamo": "sesamo.png", "sulfitos": "sulfitos.png",
    "altramuces": "altramuces.png", "moluscos": "moluscos.png",
}
_LABELS = {
    "gluten": "GLUTEN", "crustaceos": "CRUSTÁCEOS", "huevos": "HUEVOS", "pescado": "PESCADO",
    "cacahuetes": "CACAHUETES", "soja": "SOJA", "lacteos": "LÁCTEOS", "frutos de cascara": "FRUTOS DE\nCÁSCARA",
    "apio": "APIO", "mostaza": "MOSTAZA", "sesamo": "GRANOS DE\nSÉSAMO", "sulfitos": "DIÓXIDO DE\nAZUFRE\nY SULFITOS",
    "altramuces": "ALTRAMUCES", "moluscos": "MOLUSCOS",
}
_NOTICE = (
    "Informamos de acuerdo con el Reglamento de la U.E 1169/2011, "
    "que nuestros productos contienen o pueden contener los siguientes alérgenos."
)
_LEGEND_BYTES = None
_ORIGINAL_SAVE = None


def _font(size):
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
        "Arial Bold.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _fit_font(draw, text, max_width, start=25, minimum=14):
    for size in range(start, minimum - 1, -1):
        font = _font(size)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font
    return _font(minimum)


def _legend_bytes():
    global _LEGEND_BYTES
    if _LEGEND_BYTES is not None:
        return _LEGEND_BYTES

    # Prefer the exact artwork supplied by Eider. It is converted to PNG in memory
    # because python-docx/Word handles PNG more consistently than WebP.
    if _ASSET_PATH.exists():
        try:
            img = Image.open(_ASSET_PATH).convert("RGB")
            out = BytesIO()
            img.save(out, format="PNG", optimize=True)
            _LEGEND_BYTES = out.getvalue()
            return _LEGEND_BYTES
        except Exception:
            pass

    # Safe fallback if the packaged artwork is ever unavailable.
    width, height = 1800, 280
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((5, 5, width - 6, height - 6), outline="#3b1f12", width=5)
    draw.text((40, 17), _NOTICE, fill="black", font=_fit_font(draw, _NOTICE, width - 80))

    label_font = _font(16)
    slot = (width - 54) / len(_ORDER)
    resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
    for index, allergen in enumerate(_ORDER):
        center_x = 27 + slot * (index + 0.5)
        icon_path = _ICON_DIR / _ICON_FILES[allergen]
        if icon_path.exists():
            try:
                icon = Image.open(icon_path).convert("RGBA")
                icon = ImageOps.contain(icon, (88, 88), method=resampling)
                canvas.paste(icon, (int(center_x - icon.width / 2), int(67 + (88 - icon.height) / 2)), icon)
            except Exception:
                pass
        label = _LABELS[allergen]
        box = draw.multiline_textbbox((0, 0), label, font=label_font, spacing=0, align="center")
        draw.multiline_text(
            (int(center_x - (box[2] - box[0]) / 2), 166),
            label, fill="black", font=label_font, spacing=0, align="center",
        )

    out = BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    _LEGEND_BYTES = out.getvalue()
    return _LEGEND_BYTES


def _normalize(text):
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().split())


def _remove_element(element):
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def _remove_old_body_legend(doc):
    for paragraph in list(doc.paragraphs):
        text = _normalize(paragraph.text)
        if (
            "GUIA DE ALERGENOS" in text
            or "INFORMACION ORIENTATIVA BASADA EN CARTA" in text
            or "DEBE VALIDARSE CON INGREDIENTES REALES" in text
        ):
            _remove_element(paragraph._element)

    terms = {
        "GLUTEN", "CRUSTACEOS", "HUEVOS", "PESCADO", "CACAHUETES", "SOJA", "LACTEOS",
        "FRUTOS DE CASCARA", "APIO", "MOSTAZA", "SESAMO", "SULFITOS", "ALTRAMUCES", "MOLUSCOS",
    }
    for table in list(doc.tables):
        joined = _normalize(" ".join(cell.text for row in table.rows for cell in row.cells))
        if len(table.rows) <= 3 and sum(1 for term in terms if term in joined) >= 7:
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
        if idx >= len(grid_cols):
            break
        grid_cols[idx].set(qn("w:w"), str(int(Cm(width_cm).twips)))


def _set_cell_margins(cell, top=0, start=0, bottom=0, end=0):
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for name, value in {"top": top, "start": start, "bottom": bottom, "end": end}.items():
        node = tc_mar.find(qn(f"w:{name}"))
        if node is None:
            node = OxmlElement(f"w:{name}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def _add_picture(paragraph, width_cm):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1
    paragraph.add_run().add_picture(BytesIO(_legend_bytes()), width=Cm(width_cm))


def _footer_variants(section):
    # Fill all variants so the legend stays in the real footer even if a template
    # uses a different first page or odd/even footers.
    return (section.footer, section.first_page_footer, section.even_page_footer)


def _single_footer(section, usable_cm):
    if section.bottom_margin < Cm(3.15):
        section.bottom_margin = Cm(3.15)
    section.footer_distance = Cm(0.18)
    for footer in _footer_variants(section):
        footer.is_linked_to_previous = False
        _clear(footer)
        _add_picture(footer.add_paragraph(), min(18.0, usable_cm))


def _book_footer(section, usable_cm):
    if section.bottom_margin < Cm(2.55):
        section.bottom_margin = Cm(2.55)
    section.footer_distance = Cm(0.12)
    gutter_cm = 0.8
    side_cm = max(6.0, (usable_cm - gutter_cm) / 2.0)
    for footer in _footer_variants(section):
        footer.is_linked_to_previous = False
        _clear(footer)
        table = footer.add_table(rows=1, cols=3, width=Cm(usable_cm))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        widths = (side_cm, gutter_cm, side_cm)
        _set_table_grid_widths(table, widths)
        for idx, width in enumerate(widths):
            cell = table.cell(0, idx)
            _set_cell_width(cell, width)
            _set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        for idx in (0, 2):
            cell = table.cell(0, idx)
            cell.text = ""
            _add_picture(cell.paragraphs[0], max(5.5, side_cm - 0.35))
        table.cell(0, 1).text = ""


def _prepare(doc):
    _remove_old_body_legend(doc)
    for section in doc.sections:
        usable_cm = max(1.0, (section.page_width - section.left_margin - section.right_margin) / 360000.0)
        if section.page_width > section.page_height:
            _book_footer(section, usable_cm)
        else:
            _single_footer(section, usable_cm)


def _install():
    global _ORIGINAL_SAVE
    if getattr(_DocumentClass.save, "_eider_legend_patch", False):
        return
    _ORIGINAL_SAVE = _DocumentClass.save

    def save_with_eider_legend(self, path_or_stream):
        try:
            _prepare(self)
        except Exception:
            pass
        return _ORIGINAL_SAVE(self, path_or_stream)

    save_with_eider_legend._eider_legend_patch = True
    _DocumentClass.save = save_with_eider_legend


_install()
