import streamlit as st
import os
import json
import re
import base64
import zipfile
import unicodedata
from collections import Counter
from html import escape as html_escape
from datetime import datetime
from io import BytesIO

from PIL import Image, ImageOps
from pypdf import PdfReader
from docx import Document
from docx.shared import Cm, Pt
from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER, WD_LINE_SPACING
from docx.enum.section import WD_SECTION, WD_ORIENT
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from ai_design import render_ai_design_mode
from qwen_core import (
    QWEN_FLASH, QWEN_MAX, QWEN_OMNI, ensure_configured,
    menu_json_from_text, menu_json_from_image, transcribe_menu_page,
    allergen_reasoning_json, translate_json, audio_menu_json,
)

# ======================================================
# CONFIGURACIÓN GENERAL
# ======================================================
st.set_page_config(page_title="Carta IA · Serval TECH", layout="wide")

MODELO_A_USAR = QWEN_FLASH
MODELO_ALERGENOS = QWEN_MAX

SANGRIA_CATEGORIA = Cm(0.8)
SANGRIA_PLATOS = Cm(0.8)
ESPACIO_PLATOS = Pt(3)
MARGEN_INFERIOR_FORZADO = Cm(4.5)
MAX_IMAGE_SIDE = 1800
CLEAN_WORD_DISH_FONT_SIZE = 12
CLEAN_WORD_PRICE_FONT_SIZE = 12
CLEAN_WORD_DESCRIPTION_FONT_SIZE = 10.5

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ======================================================
# ALÉRGENOS OFICIALES UE - 14 GRUPOS
# ======================================================
ALLERGEN_ORDER = [
    "gluten", "crustaceos", "huevos", "pescado", "cacahuetes", "soja", "lacteos",
    "frutos de cascara", "apio", "mostaza", "sesamo", "sulfitos", "altramuces", "moluscos"
]

ALLERGEN_LABELS = {
    "gluten": "Gluten",
    "crustaceos": "Crustáceos",
    "huevos": "Huevos",
    "pescado": "Pescado",
    "cacahuetes": "Cacahuetes",
    "soja": "Soja",
    "lacteos": "Leche / Lácteos",
    "frutos de cascara": "Frutos de cáscara",
    "apio": "Apio",
    "mostaza": "Mostaza",
    "sesamo": "Sésamo",
    "sulfitos": "Sulfitos",
    "altramuces": "Altramuces",
    "moluscos": "Moluscos",
}

ALLERGEN_SHORT = {
    "gluten": "GLU", "crustaceos": "CRU", "huevos": "HUE", "pescado": "PES",
    "cacahuetes": "CAC", "soja": "SOJ", "lacteos": "LAC", "frutos de cascara": "FRC",
    "apio": "API", "mostaza": "MOS", "sesamo": "SES", "sulfitos": "SUL",
    "altramuces": "ALT", "moluscos": "MOL"
}

ALLERGEN_ALIASES = {
    "gluten": "gluten", "cereales": "gluten", "cereales con gluten": "gluten", "trigo": "gluten", "cebada": "gluten", "centeno": "gluten", "avena": "gluten", "espelta": "gluten",
    "crustaceos": "crustaceos", "crustáceos": "crustaceos", "crustaceo": "crustaceos", "crustáceo": "crustaceos", "gambas": "crustaceos", "gamba": "crustaceos",
    "huevos": "huevos", "huevo": "huevos",
    "pescado": "pescado", "pescados": "pescado",
    "cacahuetes": "cacahuetes", "cacahuete": "cacahuetes", "mani": "cacahuetes", "maní": "cacahuetes",
    "soja": "soja", "soya": "soja",
    "lacteos": "lacteos", "lácteos": "lacteos", "leche": "lacteos", "lactosa": "lacteos", "productos lacteos": "lacteos", "productos lácteos": "lacteos",
    "frutos de cascara": "frutos de cascara", "frutos de cáscara": "frutos de cascara", "frutos secos": "frutos de cascara", "frutos secos de cáscara": "frutos de cascara",
    "apio": "apio",
    "mostaza": "mostaza",
    "sesamo": "sesamo", "sésamo": "sesamo", "ajonjoli": "sesamo", "ajonjolí": "sesamo",
    "sulfitos": "sulfitos", "sulfito": "sulfitos", "dioxido de azufre": "sulfitos", "dióxido de azufre": "sulfitos", "so2": "sulfitos",
    "altramuces": "altramuces", "altramuz": "altramuces",
    "moluscos": "moluscos", "molusco": "moluscos",
}

# Nombres esperados según tu primera versión. Se busca de forma insensible a mayúsculas/minúsculas.
ICON_FILENAMES = {
    "gluten": "gluten.png",
    "crustaceos": "gambas.png",
    "huevos": "huevo.png",
    "pescado": "pescado.png",
    "cacahuetes": "cacahuetes.png",
    "soja": "soja.png",
    "lacteos": "lacteos.png",
    "frutos de cascara": "frutos_secos.png",
    "apio": "apio.png",
    "mostaza": "mostaza.png",
    "sesamo": "sesamo.png",
    "sulfitos": "sulfitos.png",
    "altramuces": "altramuces.png",
    "moluscos": "moluscos.png",
}

# ======================================================
# MOTOR DE REGLAS DE ALÉRGENOS - UNIFICADO
# ======================================================
# Reglas fuertes: se aplican cuando el nombre/descripcion contiene términos bastante inequívocos.
# No sustituyen la revisión del restaurante: sirven para reforzar a la IA y evitar omisiones.
RULES_STRONG = {
    "gluten": [
        "pan", "trigo", "harina", "pasta", "galleta", "bizcocho", "rebozado", "empanado", "tempura", "panko", "lasaña", "fideos",
        "salsa de soja", "soja sauce", "brioche", "burger", "hamburguesa con pan", "bocadillo", "sandwich", "sándwich", "croutons", "picatostes",
        "seitan", "couscous", "cuscus", "cuscús", "bulgur", "tostada", "regaña", "focaccia", "gyoza", "bao", "mollete", "masa", "pizza", "tortilla de trigo",
        "croqueta", "canelon", "canelón", "crepe", "crep", "gofre", "waffle", "tarta", "brownie", "muffin", "donut", "churro", "porra", "calzone"
    ],
    "lacteos": [
        "queso", "nata", "leche", "yogur", "yoghurt", "mantequilla", "bechamel", "mozzarella", "parmesano", "cheddar", "helado", "burrata", "carbonara",
        "feta", "crema de leche", "lactosa", "mascarpone", "tiramisu", "tiramisú", "cheesecake", "stracciatella", "tzatziki", "gorgonzola", "chocolate blanco",
        "creme brulee", "crème brûlée", "capuccino", "cappuccino", "café con leche", "cafe con leche", "cortado", "manchado", "cola-cao", "colacao", "batido", "milkshake",
        "salsa de queso", "crema ruavieja", "licor de crema", "croqueta", "croquetas", "gratinado", "alioli de leche"
    ],
    "huevos": [
        "huevo", "tortilla", "mayonesa", "mahonesa", "merengue", "alioli", "ali-oli", "bizcocho", "quiche", "brioche", "tarta", "revuelto", "poché",
        "yema", "clara", "carbonara", "salsa holandesa", "salsa tartara", "salsa tártara", "rebozado", "empanado", "crema catalana", "croqueta", "croquetas", "gofre", "waffle"
    ],
    "crustaceos": [
        "gamba", "gambas", "langostino", "langostinos", "cigala", "cigalas", "bogavante", "cangrejo", "buey de mar", "camaron", "camarón", "carabinero", "txangurro", "quisquilla", "bisque", "marisco"
    ],
    "moluscos": [
        "pulpo", "calamar", "calamares", "raba", "rabas", "sepia", "mejillon", "mejillón", "mejillones", "almeja", "almejas", "chipiron", "chipirón", "vieira", "vieiras", "ostra", "ostras", "navaja", "navajas", "berberecho", "berberechos", "zamburiña", "zamburiñas", "salsa de ostras"
    ],
    "pescado": [
        "pescado", "atun", "atún", "salmon", "salmón", "bacalao", "merluza", "anchoa", "anchoas", "boquerón", "boquerones", "sardina", "sardinas", "sushi", "sashimi", "tataki", "ceviche", "ventresca", "bonito", "dorada", "lubina", "salsa perrins", "worcestershire", "dashi", "katsuobushi", "cesar", "césar"
    ],
    "cacahuetes": ["cacahuete", "cacahuetes", "mani", "maní", "satay", "crema de cacahuete", "peanut"],
    "soja": ["soja", "soya", "edamame", "tofu", "miso", "salsa de soja", "teriyaki", "tamari", "yuba", "wakame", "kimchi", "texturizada"],
    "frutos de cascara": [
        "almendra", "almendras", "nuez", "nueces", "avellana", "avellanas", "pistacho", "pistachos", "anacardo", "anacardos", "pesto", "romesco", "nutella", "praliné", "praline", "macadamia", "ajoblanco", "nogal", "piñones", "pinones"
    ],
    "mostaza": ["mostaza", "dijon", "honey mustard", "salsa cesar", "salsa césar", "vinagreta de mostaza"],
    "sesamo": ["sesamo", "sésamo", "ajonjoli", "ajonjolí", "tahini", "hummus", "aceite de sesamo", "aceite de sésamo", "bagel", "pan con sésamo", "pan de sésamo"],
    "apio": ["apio", "caldo de verduras", "caldo de carne", "caldo de pollo", "fondo oscuro", "fondo de carne", "sofrito", "bloody mary", "salsa española", "demiglace", "pastilla de caldo"],
    "sulfitos": ["vino", "vinagre", "sulfitos", "sulfito", "cava", "champagne", "mostaza antigua", "martini", "vermut", "vermouth", "tinto de verano", "sidra", "licor", "limoncello", "pacharan", "pacharán", "fruta deshidratada", "orejones"],
    "altramuces": ["altramuz", "altramuces", "lupin", "lupino"]
}

# Reglas compuestas de hostelería común.
COMPOUND_RULES = [
    (r"\bcroquet", ["gluten", "lacteos", "huevos"]),
    (r"\brabas?\b|\bcalamares?\s+(a la romana|fritos?|rebozados?)", ["moluscos", "gluten", "huevos"]),
    (r"\bensalada\s+c[eé]sar\b|\bsalsa\s+c[eé]sar\b", ["gluten", "huevos", "pescado", "lacteos", "mostaza"]),
    (r"\bcarbonara\b", ["huevos", "lacteos"]),
    (r"\bhummus\b", ["sesamo"]),
    (r"\bromesco\b", ["frutos de cascara", "gluten"]),
    (r"\bpesto\b", ["frutos de cascara", "lacteos"]),
    (r"\bbao\b|\bgyoza\b", ["gluten", "soja"]),
    (r"\bsalsa\s+teriyaki\b", ["soja", "gluten"]),
    (r"\bsalsa\s+de\s+soja\b", ["soja", "gluten"]),
    (r"\bcerveza\b|\bca[nñ]a\b|\bdoble\s+\d+\s*cl\b|\btercio\b|\bradler\b", ["gluten"]),
    (r"\bmahou\b|\balhambra\b|\bheineken\b|\bcruzcampo\b|\baguila\b|\b[aá]guila\b|\bpaulaner\b|\bcorona\b|\bamstel\b", ["gluten"]),
    (r"\bvino\b|\bcava\b|\bvermut\b|\bvermouth\b|\btinto\s+de\s+verano\b|\bsidra\b", ["sulfitos"]),
    (r"\bcaf[eé]\s+con\s+leche\b|\bcaf[eé]\s+cortado\b|\bcapp?uccino\b|\bmanchado\b|\bt[eé]\s+con\s+leche\b", ["lacteos"]),
]

NEGATIVE_REMOVALS = [
    (r"\bsin\s+gluten\b|\bgluten\s*free\b", "gluten"),
]

REVIEW_WARNING_PATTERNS = [
    (r"\bfrit[oa]s?\b|\bfritura\b|\bfreidora\b", "Frito/freidora: revisar protocolo real de contaminación cruzada."),
    (r"\bsin\s+lactosa\b", "Sin lactosa no equivale necesariamente a sin leche: revisar si contiene proteína láctea."),
    (r"\bsalsa\b|\bmayonesa\b|\balioli\b|\bcaldo\b|\bfondo\b", "Salsa/caldo: revisar ficha técnica del proveedor."),
    (r"\bproducto\s+industrial\b|\bcaser[oa]\b", "Confirmar receta real y fichas de proveedor."),
]

# ======================================================
# UTILIDADES DE RUTA, IMAGEN E ICONOS
# ======================================================
def strip_accents(text):
    text = str(text or "")
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def normalize_text(text):
    t = strip_accents(str(text or "").lower())
    t = re.sub(r"\s+", " ", t).strip()
    return t


def find_path_insensitive(base, components):
    current = base
    for part in components:
        found = False
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.name.lower() == part.lower():
                        current = entry.path
                        found = True
                        break
        except Exception:
            return None
        if not found:
            return None
    return current


def find_file_insensitive(folder, filename):
    if not folder or not os.path.isdir(folder):
        return None
    target = filename.lower()
    try:
        for entry in os.scandir(folder):
            if entry.is_file() and entry.name.lower() == target:
                return entry.path
    except Exception:
        return None
    direct = os.path.join(folder, filename)
    return direct if os.path.exists(direct) else None


PLANTILLA_PATH = find_path_insensitive(BASE_DIR, ["public", "plantilla", "plantilla_menu.docx"])
ICONOS_DIR = find_path_insensitive(BASE_DIR, ["public", "iconos"])
if not ICONOS_DIR:
    ICONOS_DIR = find_path_insensitive(BASE_DIR, ["Public", "Iconos"])


def build_icon_map():
    icon_map = {}
    for allergen, filename in ICON_FILENAMES.items():
        icon_map[allergen] = find_file_insensitive(ICONOS_DIR, filename) if ICONOS_DIR else None
    return icon_map


ICON_MAP = build_icon_map()


def file_to_data_uri(path):
    if not path or not os.path.exists(path):
        return None
    ext = os.path.splitext(path)[1].lower()
    mime = "image/png"
    if ext in [".jpg", ".jpeg"]:
        mime = "image/jpeg"
    elif ext == ".webp":
        mime = "image/webp"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def uploaded_image_to_data_uri(uploaded_file, max_side=1200):
    if not uploaded_file:
        return None
    try:
        uploaded_file.seek(0)
        img = Image.open(uploaded_file)
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        if img.mode == "RGBA":
            img.save(buffer, format="PNG", optimize=True)
            mime = "image/png"
        else:
            img.save(buffer, format="JPEG", quality=90, optimize=True)
            mime = "image/jpeg"
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        uploaded_file.seek(0)
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None


def generate_qr_data_uri(url):
    url = str(url or "").strip()
    if not url:
        return None
    try:
        import qrcode
        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return None


def prepare_image_for_ai(uploaded_file):
    uploaded_file.seek(0)
    img = Image.open(uploaded_file)
    img = ImageOps.exif_transpose(img)
    original_info = {
        "format": img.format,
        "mode": img.mode,
        "size": img.size,
        "bytes": getattr(uploaded_file, "size", None),
    }
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
    clean = BytesIO()
    img.save(clean, format="JPEG", quality=92, optimize=True)
    clean.seek(0)
    final_img = Image.open(clean).copy()
    uploaded_file.seek(0)
    return final_img, original_info


def normalize_allergen_key(key):
    if not key:
        return ""
    raw = str(key).strip().lower()
    raw_no = normalize_text(raw)
    if raw in ALLERGEN_ALIASES:
        return ALLERGEN_ALIASES[raw]
    if raw_no in ALLERGEN_ALIASES:
        return ALLERGEN_ALIASES[raw_no]
    if raw_no in ALLERGEN_ORDER:
        return raw_no
    return raw_no


def get_ordered_allergens(allergens):
    seen = []
    for a in allergens or []:
        k = normalize_allergen_key(a)
        if k in ALLERGEN_ORDER and k not in seen:
            seen.append(k)
    return [a for a in ALLERGEN_ORDER if a in seen]


def add_allergen(current, key):
    key = normalize_allergen_key(key)
    if key in ALLERGEN_ORDER and key not in current:
        current.append(key)
    return current





# ======================================================
# QWEN / ALIBABA MODEL STUDIO
# ======================================================
# La clave permanece exclusivamente en Streamlit Secrets. No se muestra al cliente.
try:
    ensure_configured()
except RuntimeError as exc:
    st.error(f"❌ {exc}")
    st.stop()


# ======================================================
# LECTURA DE ARCHIVOS
# ======================================================
def extract_text_from_pdf(file):
    try:
        file.seek(0)
        reader = PdfReader(file)
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        file.seek(0)
        return text
    except Exception:
        return None


def extract_text_from_docx(file):
    try:
        file.seek(0)
        doc = Document(file)
        text = "\n".join([p.text for p in doc.paragraphs])
        for table in doc.tables:
            for row in table.rows:
                text += " | ".join([cell.text for cell in row.cells]) + "\n"
        file.seek(0)
        return text
    except Exception:
        return None


def extract_text_from_pdf_scanned_with_qwen(file):
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

        chunks = []
        failed_pages = []
        progress = st.progress(0, text=f"Procesando PDF escaneado · 0/{total_pages} páginas")

        for i in range(total_pages):
            try:
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                img = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
                img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
                page_text = (transcribe_menu_page(img) or "").strip()
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

# ======================================================
# ANÁLISIS IA + REGLAS UNIFICADAS
# ======================================================


def parse_json_response(text):
    text = (text or "").replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]
    return json.loads(text)



# ======================================================
# WORD
# ======================================================
def release_paragraph_constraints(paragraph, indent, is_dish=False):
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = ESPACIO_PLATOS if is_dish else Pt(0)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    paragraph.paragraph_format.left_indent = indent


def new_doc_from_template():
    if PLANTILLA_PATH and os.path.exists(PLANTILLA_PATH):
        return Document(PLANTILLA_PATH)
    return Document()


def format_price(price):
    p = str(price or "").strip()
    if not p:
        return ""
    if "€" in p:
        return p
    return f"{p}€"


def clean_text_value(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(x).strip() for x in value if str(x).strip())
    return str(value).strip()


def unique_text_blocks(*values):
    blocks = []
    seen = set()
    for value in values:
        txt = clean_text_value(value)
        if not txt:
            continue
        for part in re.split(r"\n{2,}|\r\n|\n", txt):
            part = part.strip()
            if not part:
                continue
            key = normalize_text(part)
            if key and key not in seen:
                seen.add(key)
                blocks.append(part)
    return blocks


def dish_display_name(dish):
    """Nombre visible del plato, conservando numeración original cuando la IA la haya separado."""
    name = str(dish.get("name") or "Plato").strip()
    number = str(dish.get("number") or dish.get("numero") or dish.get("n") or "").strip()
    if not number:
        return name
    number_clean = number.strip()
    # Evita duplicar si la IA ya dejó el número dentro del nombre.
    name_norm = normalize_text(name)
    number_norm = normalize_text(number_clean).rstrip(".)-ºª")
    if name_norm.startswith(number_norm + " ") or name_norm.startswith(number_norm + ".") or name_norm.startswith(number_norm + ")"):
        return name
    if re.search(r"[\.)]$", number_clean):
        return f"{number_clean} {name}".strip()
    return f"{number_clean}. {name}".strip()


def add_text_block_to_doc(doc, text, indent=None, font_size=10.5, italic=True, color=None):
    text = clean_text_value(text)
    if not text:
        return
    for line in unique_text_blocks(text):
        p = doc.add_paragraph()
        if indent is not None:
            release_paragraph_constraints(p, indent)
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(line)
        r.font.size = Pt(font_size)
        r.italic = italic
        if color:
            try:
                set_run_color(r, color)
            except Exception:
                pass




def create_clean_word(data):
    """Word limpio clásico: una columna, editable, sin iconos junto a platos.
    Conserva numeración de platos si existe, texto auxiliar de la carta y cuerpo a 12 pt.
    """
    doc = new_doc_from_template()
    for section in doc.sections:
        section.bottom_margin = MARGEN_INFERIOR_FORZADO

    rest_name = data.get("restaurant_name", "MENÚ")
    p_title = doc.add_heading(rest_name, 0)
    release_paragraph_constraints(p_title, SANGRIA_CATEGORIA)

    # Texto auxiliar general detectado en la carta: teléfonos, horarios, dirección, avisos, etc.
    for block in unique_text_blocks(data.get("texto_extra"), data.get("header_text"), data.get("footer_text"), data.get("notes")):
        add_text_block_to_doc(doc, block, SANGRIA_CATEGORIA, font_size=10.5, italic=True)

    for category in data.get("categories", []):
        p_cat = doc.add_heading(category.get("name", "Categoría"), level=1)
        release_paragraph_constraints(p_cat, SANGRIA_CATEGORIA)
        p_cat.paragraph_format.space_before = Pt(6)

        for block in unique_text_blocks(category.get("category_text"), category.get("texto_extra"), category.get("notes")):
            add_text_block_to_doc(doc, block, SANGRIA_PLATOS, font_size=10.5, italic=True)

        for dish in category.get("dishes", []):
            p = doc.add_paragraph()
            release_paragraph_constraints(p, SANGRIA_PLATOS, is_dish=True)
            p.paragraph_format.tab_stops.add_tab_stop(Cm(15.0), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            rn = p.add_run(dish_display_name(dish))
            rn.bold = True
            rn.font.size = Pt(CLEAN_WORD_DISH_FONT_SIZE)
            rp = p.add_run(f"\t{format_price(dish.get('price', ''))}")
            rp.font.size = Pt(CLEAN_WORD_PRICE_FONT_SIZE)
            if dish.get("description"):
                p_desc = doc.add_paragraph()
                release_paragraph_constraints(p_desc, SANGRIA_PLATOS, is_dish=True)
                rd = p_desc.add_run(dish["description"])
                rd.italic = True
                rd.font.size = Pt(CLEAN_WORD_DESCRIPTION_FONT_SIZE)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


# ======================================================
# HTML/PDF VISUAL CON ICONOS REALES
# ======================================================
def slugify_filename(text):
    text = strip_accents(str(text or "carta")).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_") or "carta"
    return text[:60]


def icon_img_html(allergen, cls="allergen-icon"):
    path = ICON_MAP.get(allergen)
    src = file_to_data_uri(path)
    label = ALLERGEN_LABELS.get(allergen, allergen)
    if src:
        return f'<img class="{cls}" src="{src}" alt="{html_escape(label)}" title="{html_escape(label)}">'
    # fallback visible si falta PNG: no son puntos de colores, es aviso textual mínimo.
    return f'<span class="missing-icon" title="Falta icono: {html_escape(label)}">{html_escape(ALLERGEN_SHORT.get(allergen, allergen[:3].upper()))}</span>'


def allergen_icons_html(allergens, small=True):
    cls = "allergen-icon small" if small else "allergen-icon"
    return "".join(icon_img_html(a, cls=cls) for a in get_ordered_allergens(allergens))


def icon_img_html_inline(allergen, style=""):
    path = ICON_MAP.get(allergen)
    src = file_to_data_uri(path)
    label = ALLERGEN_LABELS.get(allergen, allergen)
    if src:
        return f'<img src="{src}" alt="{html_escape(label)}" title="{html_escape(label)}" style="{style}">'
    short = ALLERGEN_SHORT.get(allergen, allergen[:3].upper())
    return f'<span title="Falta icono: {html_escape(label)}" style="{style}; display:inline-flex; align-items:center; justify-content:center; border:1px solid currentColor; border-radius:50%; font-size:7px; font-weight:900;">{html_escape(short)}</span>'


def allergen_legend_html(compact=False):
    items = []
    for allergen in ALLERGEN_ORDER:
        items.append(
            f'<div class="legend-item">{icon_img_html(allergen, cls="legend-icon")}<span>{html_escape(ALLERGEN_LABELS[allergen])}</span></div>'
        )
    cls = "legend compact" if compact else "legend"
    return f'<div class="{cls}">{"".join(items)}</div>'


def allergen_guide_panel_html(theme="dark", notice="", compact=False):
    # Bloque premium de cierre visual: iconos reales grandes + aviso legal compacto.
    if theme == "dark":
        section_style = "margin-top:5mm; padding:5mm 5mm 4mm; border:1px solid rgba(220,184,94,.55); background:linear-gradient(135deg, rgba(0,0,0,.24), rgba(255,255,255,.035)); box-shadow:inset 0 0 18px rgba(0,0,0,.22);"
        title_style = "margin:0 0 3.5mm; text-align:center; color:#f4d684; font-family:Georgia,'Times New Roman',serif; font-size:15px; letter-spacing:2.6px; text-transform:uppercase;"
        item_style = "display:flex; flex-direction:column; align-items:center; justify-content:flex-start; gap:1mm; min-height:16mm; padding:1.8mm 1mm; color:#f8efd2; text-align:center; font-size:7.2px; line-height:1.1; border:1px solid rgba(255,255,255,.07); background:rgba(0,0,0,.12);"
        icon_style = "width:8.5mm; height:8.5mm; object-fit:contain; filter:drop-shadow(0 1px 2px rgba(0,0,0,.65));"
        notice_style = "margin-top:3.6mm; color:#cabf9e; font-size:7px; line-height:1.32; text-align:center;"
    elif theme == "technical":
        section_style = "margin-top:3mm; padding:3mm; border:1px solid #cfcfcf; background:#f8f8f8;"
        title_style = "margin:0 0 2mm; text-align:left; color:#111; font-family:Arial,Helvetica,sans-serif; font-size:10px; letter-spacing:.8px; text-transform:uppercase;"
        item_style = "display:flex; align-items:center; gap:1mm; min-height:8mm; color:#111; font-size:6.8px; line-height:1.05;"
        icon_style = "width:5.5mm; height:5.5mm; object-fit:contain;"
        notice_style = "margin-top:2mm; color:#444; font-size:6.8px; line-height:1.25; text-align:right;"
    else:
        section_style = "margin-top:5mm; padding:4.5mm; border:1px solid #d8c2a2; border-radius:12px; background:linear-gradient(135deg,#fffaf0,#f4ead9); box-shadow:0 8px 18px rgba(70,44,18,.06);"
        title_style = "margin:0 0 3.2mm; text-align:center; color:#7b4c20; font-family:Georgia,'Times New Roman',serif; font-size:15px; letter-spacing:2px; text-transform:uppercase;"
        item_style = "display:flex; flex-direction:column; align-items:center; justify-content:flex-start; gap:1mm; min-height:15mm; padding:1.6mm .8mm; color:#3e3025; text-align:center; font-size:7.2px; line-height:1.08; border:1px solid rgba(123,76,32,.11); border-radius:8px; background:rgba(255,255,255,.58);"
        icon_style = "width:8mm; height:8mm; object-fit:contain; filter:drop-shadow(0 1px 1px rgba(80,50,20,.18));"
        notice_style = "margin-top:3.2mm; color:#6a5848; font-size:7px; line-height:1.32; text-align:center;"

    grid_cols = "repeat(7, 1fr)"
    items = []
    for allergen in ALLERGEN_ORDER:
        items.append(
            f'<div style="{item_style}">{icon_img_html_inline(allergen, icon_style)}<span>{html_escape(ALLERGEN_LABELS[allergen])}</span></div>'
        )
    return (
        f'<section class="allergen-guide-panel" style="{section_style}">'
        f'<h3 style="{title_style}">Guía de alérgenos</h3>'
        f'<div style="display:grid; grid-template-columns:{grid_cols}; gap:2mm 2.4mm; align-items:start;">{"".join(items)}</div>'
        f'<div style="{notice_style}">{notice}</div>'
        f'</section>'
    )


def brand_html(data, logo_src=None, mode="dark"):
    rest_name = html_escape(data.get("restaurant_name", "MENÚ"))
    if logo_src:
        return f'<div class="brand-wrap"><img class="restaurant-logo" src="{logo_src}" alt="Logo restaurante"><div class="brand-name mini">{rest_name}</div></div>'
    return f'<div class="brand-wordmark">{rest_name}</div>'


def qr_html(qr_src=None, dark=False):
    if qr_src:
        return f'<div class="qr-wrap"><img class="qr-img" src="{qr_src}" alt="QR menú"><span>Escanea el menú</span></div>'
    return ""


def build_notice(data):
    generated = data.get("_generated_at", datetime.now().strftime("%d/%m/%Y %H:%M"))
    return (
        f"Generado el {generated}. Información orientativa basada en carta, receta habitual y reglas de revisión. "
        "Debe validarse con ingredientes reales, fichas técnicas de proveedor y protocolo de cocina. "
        "Si tiene alergia o intolerancia, consulte siempre al personal antes de pedir."
    )


def create_blackboard_html(data, logo_src=None, qr_src=None):
    notice = html_escape(build_notice(data))
    category_blocks = []
    for cat in data.get("categories", []):
        dishes = []
        for dish in cat.get("dishes", []):
            desc = html_escape(dish.get("description", ""))
            desc_html = f'<div class="dish-desc">{desc}</div>' if desc else ""
            icons = allergen_icons_html(dish.get("allergens", []), small=True)
            price = html_escape(format_price(dish.get("price", "")))
            dishes.append(f"""
            <div class="dish-row">
                <div class="dish-main">
                    <div class="dish-title-line"><span class="dish-name">{html_escape(dish_display_name(dish))}</span><span class="icons-line">{icons}</span></div>
                    {desc_html}
                </div>
                <div class="price">{price}</div>
            </div>
            """)
        category_blocks.append(f"""
        <section class="category-block">
            <h2>{html_escape(cat.get('name', 'Categoría'))}</h2>
            <div class="dish-list">{''.join(dishes)}</div>
        </section>
        """)

    extra = html_escape(data.get("texto_extra", ""))
    extra_html = f'<div class="extra-text">{extra}</div>' if extra else ""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Carta Pizarra - {html_escape(data.get('restaurant_name', 'Menú'))}</title>
<style>
@page {{ size: A3 portrait; margin: 0; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:#0c0b09; color:#f7f0dc; font-family:'Trebuchet MS', Verdana, sans-serif; }}
.page {{ width:297mm; min-height:420mm; padding:13mm 13mm 11mm; position:relative; overflow:hidden; background:
    radial-gradient(circle at 15% 12%, rgba(255,255,255,.09), transparent 21%),
    radial-gradient(circle at 84% 9%, rgba(214,174,86,.13), transparent 22%),
    repeating-linear-gradient(0deg, rgba(255,255,255,.015), rgba(255,255,255,.015) 1px, transparent 1px, transparent 4px),
    linear-gradient(145deg, #20201d 0%, #11100e 48%, #080807 100%);
    border:6mm double #c9a85f; box-shadow: inset 0 0 0 1.2mm rgba(255,255,255,.08); }}
.page:before {{ content:""; position:absolute; inset:8mm; border:1px solid rgba(238,213,139,.25); pointer-events:none; }}
.header {{ position:relative; z-index:2; display:grid; grid-template-columns:54mm 1fr 42mm; align-items:center; gap:8mm; padding-bottom:6mm; margin-bottom:7mm; border-bottom:1px solid rgba(238,213,139,.42); }}
.brand-wrap {{ text-align:center; }}
.restaurant-logo {{ max-width:48mm; max-height:30mm; object-fit:contain; filter: drop-shadow(0 2px 4px #000); }}
.brand-name.mini {{ margin-top:1mm; font-size:8px; color:#d8ca9e; letter-spacing:1px; text-transform:uppercase; }}
.brand-wordmark {{ border:1px solid rgba(238,213,139,.48); padding:4mm 3mm; text-align:center; font-family:Georgia,serif; font-size:18px; color:#f5df9a; text-transform:uppercase; letter-spacing:1.2px; }}
.title {{ text-align:center; }}
.eyebrow {{ color:#d5b25a; text-transform:uppercase; font-size:11px; letter-spacing:4px; font-weight:900; }}
h1 {{ margin:1mm 0 0; font-family:Georgia,'Times New Roman',serif; font-size:48px; line-height:.92; color:#fff8df; text-shadow:0 3px 0 #000, 0 0 18px rgba(213,178,90,.18); }}
.subtitle {{ margin-top:3mm; color:#e3d7b5; font-size:12px; letter-spacing:1px; }}
.qr-wrap {{ justify-self:end; width:34mm; text-align:center; color:#e3d7b5; font-size:8px; text-transform:uppercase; letter-spacing:.6px; }}
.qr-img {{ width:30mm; height:30mm; object-fit:contain; background:#fff; padding:1.5mm; border-radius:2mm; }}
.columns {{ position:relative; z-index:2; column-count:2; column-gap:13mm; }}
.category-block {{ break-inside:avoid; margin-bottom:7mm; padding:3mm 3.5mm 2.5mm; border:1px solid rgba(239,217,154,.18); background:rgba(0,0,0,.11); }}
.category-block h2 {{ margin:0 0 3mm; text-align:center; font-family:Georgia,'Times New Roman',serif; font-style:italic; color:#fff9e8; font-size:25px; line-height:1; text-shadow:0 2px 0 #000; }}
.category-block h2:after {{ content:""; display:block; width:28mm; height:1px; background:#d5b25a; margin:2.2mm auto 0; }}
.dish-row {{ display:flex; gap:3mm; align-items:flex-start; border-bottom:1px dotted rgba(255,255,255,.14); padding:1.15mm 0; }}
.dish-main {{ flex:1; min-width:0; }}
.dish-title-line {{ display:flex; gap:1.8mm; align-items:center; flex-wrap:wrap; }}
.dish-name {{ color:#e2c263; font-size:10.5px; text-transform:uppercase; letter-spacing:.28px; font-weight:900; }}
.dish-desc {{ margin-top:.65mm; color:#e6dcc4; font-size:8.6px; line-height:1.25; }}
.price {{ color:#fff; font-size:10px; font-weight:900; min-width:15mm; text-align:right; }}
.icons-line {{ display:inline-flex; gap:.8mm; align-items:center; }}
.allergen-icon.small {{ width:4.3mm; height:4.3mm; object-fit:contain; vertical-align:middle; filter: drop-shadow(0 1px 1px rgba(0,0,0,.55)); }}
.legend-icon {{ width:5.2mm; height:5.2mm; object-fit:contain; }}
.missing-icon {{ display:inline-flex; align-items:center; justify-content:center; width:4.3mm; height:4.3mm; border:1px solid #e6c66d; color:#e6c66d; font-size:5px; font-weight:900; border-radius:50%; }}
.footer {{ position:relative; z-index:2; margin-top:8mm; padding-top:5mm; border-top:1px solid rgba(238,213,139,.42); }}
.extra-text {{ margin-bottom:4mm; padding:3mm; border:1px solid rgba(213,178,90,.5); color:#efe2bf; text-align:center; font-size:9px; }}
.legend {{ display:flex; flex-wrap:wrap; justify-content:center; gap:2.2mm 4.5mm; }}
.legend-item {{ display:flex; align-items:center; gap:1.2mm; font-size:7.6px; color:#f1e8ce; white-space:nowrap; }}
.notice {{ color:#cfc3a2; font-size:7.5px; line-height:1.35; text-align:center; margin-top:4mm; }}
</style>
</head>
<body><div class="page">
<header class="header">
    {brand_html(data, logo_src)}
    <div class="title"><div class="eyebrow">Carta de alérgenos</div><h1>{html_escape(data.get('restaurant_name','MENÚ'))}</h1><div class="subtitle">Información para consulta del cliente</div></div>
    {qr_html(qr_src)}
</header>
<main class="columns">{''.join(category_blocks)}</main>
<footer class="footer">{extra_html}{allergen_guide_panel_html(theme="dark", notice=notice)}</footer>
</div></body></html>"""


def create_modern_html(data, logo_src=None, qr_src=None):
    notice = html_escape(build_notice(data))
    blocks = []
    for cat in data.get("categories", []):
        dishes = []
        for dish in cat.get("dishes", []):
            desc = html_escape(dish.get("description", ""))
            desc_html = f'<p>{desc}</p>' if desc else ""
            icons = allergen_icons_html(dish.get("allergens", []), small=False)
            price = html_escape(format_price(dish.get("price", "")))
            dishes.append(f"""
            <article class="modern-dish">
                <div class="modern-line"><h3>{html_escape(dish_display_name(dish))}</h3><strong>{price}</strong></div>
                {desc_html}
                <div class="icon-line">{icons}</div>
            </article>
            """)
        blocks.append(f"""
        <section class="modern-category">
            <h2>{html_escape(cat.get('name','Categoría'))}</h2>
            {''.join(dishes)}
        </section>
        """)
    extra = html_escape(data.get("texto_extra", ""))
    extra_html = f'<div class="modern-extra"><strong>Notas de carta:</strong> {extra}</div>' if extra else ""
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><title>Carta Premium - {html_escape(data.get('restaurant_name','Menú'))}</title>
<style>
@page {{ size:A4 portrait; margin:8mm; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#efe5d2; color:#211a14; font-family:'Trebuchet MS', Verdana, sans-serif; }}
.page {{ min-height:281mm; padding:10mm; background:linear-gradient(140deg,#fffaf0 0%,#f3e2c7 100%); border:1.4mm solid #2a2119; box-shadow: inset 0 0 0 .6mm #c49a59; }}
.header {{ display:grid; grid-template-columns:1fr auto; gap:8mm; align-items:center; margin-bottom:8mm; padding-bottom:5mm; border-bottom:1px solid #c49a59; }}
.brandline {{ display:flex; align-items:center; gap:5mm; }}
.restaurant-logo {{ max-width:34mm; max-height:22mm; object-fit:contain; }}
.brand-wordmark {{ font-family:Georgia,'Times New Roman',serif; font-size:26px; color:#2a2119; font-weight:900; letter-spacing:.5px; }}
.label {{ color:#98652c; font-size:9px; text-transform:uppercase; letter-spacing:3px; font-weight:900; margin-bottom:2mm; }}
h1 {{ margin:0; font-family:Georgia,'Times New Roman',serif; font-size:36px; line-height:1; color:#2a2119; }}
.qr-wrap {{ width:29mm; text-align:center; color:#6c563e; font-size:7.5px; text-transform:uppercase; letter-spacing:.6px; }}
.qr-img {{ width:27mm; height:27mm; object-fit:contain; background:#fff; padding:1.2mm; border:1px solid #c49a59; }}
.layout {{ column-count:2; column-gap:7mm; }}
.modern-category {{ break-inside:avoid; background:rgba(255,255,255,.74); border:1px solid #dcc299; border-radius:8px; padding:4.2mm; margin-bottom:5mm; box-shadow:0 8px 18px rgba(47,32,15,.08); }}
.modern-category h2 {{ margin:0 0 3mm; padding-bottom:2mm; border-bottom:1px solid #d7bb8d; color:#86531f; font-family:Georgia,'Times New Roman',serif; font-size:21px; }}
.modern-dish {{ padding:2mm 0; border-bottom:1px solid rgba(134,83,31,.13); }}
.modern-dish:last-child {{ border-bottom:none; }}
.modern-line {{ display:flex; justify-content:space-between; gap:4mm; align-items:baseline; }}
.modern-line h3 {{ margin:0; font-size:12px; text-transform:uppercase; letter-spacing:.2px; }}
.modern-line strong {{ color:#86531f; font-size:11.5px; white-space:nowrap; }}
.modern-dish p {{ margin:1mm 0 1.2mm; color:#5d5146; font-size:9.5px; line-height:1.3; }}
.icon-line {{ display:flex; flex-wrap:wrap; gap:1.1mm; min-height:4.5mm; align-items:center; }}
.allergen-icon {{ width:5.1mm; height:5.1mm; object-fit:contain; }}
.legend-icon {{ width:5mm; height:5mm; object-fit:contain; }}
.missing-icon {{ display:inline-flex; align-items:center; justify-content:center; width:5.1mm; height:5.1mm; border:1px solid #86531f; color:#86531f; font-size:5px; font-weight:900; border-radius:50%; }}
.footer {{ margin-top:7mm; padding-top:4mm; border-top:1px solid #c49a59; }}
.modern-extra {{ margin-bottom:4mm; padding:3mm; border:1px solid #dcc299; background:#fff7e8; font-size:9px; color:#493b2d; }}
.legend {{ display:grid; grid-template-columns:repeat(2, 1fr); gap:1.7mm 5mm; }}
.legend-item {{ display:flex; align-items:center; gap:1.8mm; font-size:8.2px; color:#47382a; }}
.notice {{ margin-top:4mm; color:#66564a; font-size:7.8px; line-height:1.35; }}
</style></head>
<body><div class="page">
<header class="header">
    <div><div class="label">Carta premium · alérgenos</div><div class="brandline">{brand_html(data, logo_src)}</div></div>
    {qr_html(qr_src)}
</header>
<main class="layout">{''.join(blocks)}</main>
<footer class="footer">{extra_html}{allergen_guide_panel_html(theme="light", notice=notice)}</footer>
</div></body></html>"""


def create_matrix_html(data, logo_src=None, qr_src=None):
    header_cells = []
    for allergen in ALLERGEN_ORDER:
        header_cells.append(f'<th>{icon_img_html(allergen, "matrix-icon")}<small>{html_escape(ALLERGEN_LABELS[allergen])}</small></th>')
    rows = []
    for cat in data.get("categories", []):
        for dish in cat.get("dishes", []):
            allergens = set(get_ordered_allergens(dish.get("allergens", [])))
            cells = []
            for allergen in ALLERGEN_ORDER:
                cells.append(f'<td class="mark">{icon_img_html(allergen, "matrix-mark") if allergen in allergens else ""}</td>')
            rows.append(f"""
            <tr>
                <td class="cat">{html_escape(cat.get('name',''))}</td>
                <td class="prod"><strong>{html_escape(dish_display_name(dish))}</strong><br><span>{html_escape(dish.get('description',''))}</span></td>
                <td class="price-cell">{html_escape(format_price(dish.get('price','')))}</td>
                {''.join(cells)}
            </tr>
            """)
    notice = html_escape(build_notice(data))
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><title>Matriz Alérgenos - {html_escape(data.get('restaurant_name','Menú'))}</title>
<style>
@page {{ size:A3 landscape; margin:7mm; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Arial, Helvetica, sans-serif; color:#111; background:#fff; }}
.page {{ padding:3mm; }}
.header {{ display:flex; justify-content:space-between; align-items:center; gap:8mm; border-bottom:2px solid #111; padding-bottom:3mm; margin-bottom:4mm; }}
.header-left {{ display:flex; align-items:center; gap:5mm; }}
.restaurant-logo {{ max-width:32mm; max-height:18mm; object-fit:contain; }}
.brand-wordmark {{ font-size:20px; font-weight:900; text-transform:uppercase; }}
h1 {{ margin:0; font-size:22px; }}
p {{ margin:1mm 0 0; font-size:9px; color:#555; }}
.badge {{ border:1px solid #111; padding:2mm 3mm; font-size:9px; font-weight:900; text-transform:uppercase; }}
table {{ width:100%; border-collapse:collapse; table-layout:fixed; }}
th, td {{ border:1px solid #cfcfcf; padding:1.2mm; vertical-align:middle; }}
th {{ background:#f3f3f3; font-size:6.9px; text-align:center; }}
th:nth-child(1) {{ width:32mm; }} th:nth-child(2) {{ width:86mm; }} th:nth-child(3) {{ width:18mm; }}
td {{ font-size:7.4px; }}
.cat {{ font-weight:800; background:#fafafa; }}
.prod strong {{ font-size:7.8px; }} .prod span {{ color:#555; line-height:1.2; }}
.price-cell {{ text-align:right; font-weight:800; }}
.matrix-icon {{ width:5mm; height:5mm; object-fit:contain; display:block; margin:0 auto .6mm; }}
.matrix-mark {{ width:4.6mm; height:4.6mm; object-fit:contain; display:block; margin:auto; }}
th small {{ display:block; font-size:5.8px; line-height:1.05; }}
.mark {{ text-align:center; }}
.footer {{ margin-top:3mm; display:grid; grid-template-columns:1fr 1fr; gap:6mm; }}
.legend-mini {{ font-size:7.6px; line-height:1.35; color:#333; }}
.notice {{ font-size:7.6px; line-height:1.35; color:#444; text-align:right; }}
</style></head><body><div class="page">
<header class="header">
    <div><div class="header-left">{brand_html(data, logo_src)}</div><h1>{html_escape(data.get('restaurant_name','MENÚ'))} · Matriz de alérgenos</h1><p>Marcado con icono = alérgeno presente según revisión IA + reglas. Validar con fichas técnicas.</p></div>
    <div class="badge">Serval TECH · Carta Pro</div>
</header>
<table><thead><tr><th>Categoría</th><th>Producto / descripción</th><th>Precio</th>{''.join(header_cells)}</tr></thead><tbody>{''.join(rows)}</tbody></table>
<footer class="footer">{allergen_guide_panel_html(theme="technical", notice=notice, compact=True)}</footer>
</div></body></html>"""


def create_qr_mesa_html(data, logo_src=None, qr_src=None):
    # Plantilla compacta para mesa/barra: A4, QR visible, lectura rápida e iconos reales.
    notice = html_escape(build_notice(data))
    restaurant_name = html_escape(data.get("restaurant_name", "MENÚ"))

    if logo_src:
        brand_block = f'<img class="restaurant-logo" src="{logo_src}" alt="Logo restaurante"><div class="brand-name">{restaurant_name}</div>'
    else:
        brand_block = f'<div class="brand-wordmark">{restaurant_name}</div>'

    if qr_src:
        qr_block = f'<div class="qr-card"><img class="qr-img" src="{qr_src}" alt="QR menú"><div>Escanea la carta digital</div></div>'
    else:
        qr_block = '<div class="qr-card empty"><div class="qr-placeholder">QR</div><div>Añade un QR o URL desde la app</div></div>'

    category_blocks = []
    for cat in data.get("categories", []):
        dishes = []
        for dish in cat.get("dishes", []):
            desc = html_escape(dish.get("description", ""))
            desc_html = f'<div class="desc">{desc}</div>' if desc else ""
            icons = allergen_icons_html(dish.get("allergens", []), small=True)
            price = html_escape(format_price(dish.get("price", "")))
            dishes.append(f"""
            <div class="mesa-row">
                <div class="mesa-info">
                    <div class="mesa-title"><span>{html_escape(dish_display_name(dish))}</span><span class="mesa-icons">{icons}</span></div>
                    {desc_html}
                </div>
                <div class="mesa-price">{price}</div>
            </div>
            """)
        category_blocks.append(f"""
        <section class="mesa-category">
            <h2>{html_escape(cat.get('name','Categoría'))}</h2>
            {''.join(dishes)}
        </section>
        """)

    extra = html_escape(data.get("texto_extra", ""))
    extra_html = f'<div class="mesa-extra">{extra}</div>' if extra else ""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Mesa QR Alérgenos - {restaurant_name}</title>
<style>
@page {{ size:A4 portrait; margin:0; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#efe6d7; color:#211915; font-family:'Trebuchet MS', Arial, sans-serif; }}
.page {{ width:210mm; min-height:297mm; padding:10mm; background:linear-gradient(160deg,#fffaf0 0%,#f2e5cf 100%); position:relative; overflow:hidden; }}
.page:before {{ content:""; position:absolute; inset:6mm; border:1px solid rgba(132,86,38,.18); pointer-events:none; }}
.header {{ position:relative; z-index:1; display:grid; grid-template-columns:1fr 38mm; gap:8mm; align-items:center; padding-bottom:5mm; border-bottom:2px solid #7b4c20; margin-bottom:5mm; }}
.brand {{ display:flex; align-items:center; gap:5mm; min-width:0; }}
.restaurant-logo {{ max-width:34mm; max-height:24mm; object-fit:contain; }}
.brand-name {{ font-size:12px; color:#7b4c20; text-transform:uppercase; letter-spacing:1.4px; font-weight:900; }}
.brand-wordmark {{ font-family:Georgia,'Times New Roman',serif; font-size:29px; color:#3a271b; line-height:1; text-transform:uppercase; letter-spacing:.8px; }}
.header-text .label {{ color:#9b6b35; text-transform:uppercase; letter-spacing:2.5px; font-size:10px; font-weight:900; }}
.header-text h1 {{ margin:1.5mm 0 0; font-family:Georgia,'Times New Roman',serif; font-size:30px; color:#241811; line-height:1; }}
.qr-card {{ width:36mm; min-height:40mm; padding:2.2mm; border:1px solid #b28a58; background:#fff; border-radius:7px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; font-size:7.5px; color:#6d543b; text-transform:uppercase; gap:1.5mm; }}
.qr-img {{ width:28mm; height:28mm; object-fit:contain; }}
.qr-placeholder {{ width:25mm; height:25mm; display:flex; align-items:center; justify-content:center; border:1px dashed #a38355; color:#a38355; font-size:14px; font-weight:900; }}
.intro {{ position:relative; z-index:1; margin:0 0 5mm; display:grid; grid-template-columns:1fr auto; gap:5mm; align-items:center; }}
.intro-main {{ padding:3mm 4mm; border-left:4px solid #7b4c20; background:rgba(255,255,255,.5); font-size:10px; line-height:1.35; color:#574333; }}
.intro-badge {{ padding:2.5mm 3.2mm; border:1px solid #7b4c20; color:#7b4c20; font-size:9px; font-weight:900; text-transform:uppercase; letter-spacing:1px; }}
.menu-grid {{ position:relative; z-index:1; column-count:2; column-gap:7mm; }}
.mesa-category {{ break-inside:avoid; margin-bottom:5mm; background:rgba(255,255,255,.72); border:1px solid #e0ceb2; border-radius:11px; padding:4mm; box-shadow:0 6px 16px rgba(80,55,28,.06); }}
.mesa-category h2 {{ margin:0 0 3mm; color:#7b4c20; font-family:Georgia,'Times New Roman',serif; font-size:17px; border-bottom:1px solid #d9c3a3; padding-bottom:1.8mm; }}
.mesa-row {{ display:flex; gap:3mm; align-items:flex-start; padding:1.7mm 0; border-bottom:1px dotted rgba(123,76,32,.22); }}
.mesa-row:last-child {{ border-bottom:none; }}
.mesa-info {{ flex:1; min-width:0; }}
.mesa-title {{ display:flex; gap:1.5mm; align-items:center; flex-wrap:wrap; font-size:9.4px; font-weight:900; text-transform:uppercase; letter-spacing:.18px; color:#2d221a; }}
.desc {{ margin-top:.7mm; color:#66564a; font-size:7.8px; line-height:1.25; }}
.mesa-price {{ min-width:13mm; text-align:right; color:#7b4c20; font-size:9.2px; font-weight:900; }}
.mesa-icons {{ display:inline-flex; gap:.8mm; align-items:center; }}
.allergen-icon.small {{ width:4.1mm; height:4.1mm; object-fit:contain; vertical-align:middle; }}
.missing-icon {{ display:inline-flex; align-items:center; justify-content:center; width:4.1mm; height:4.1mm; border:1px solid #7b4c20; color:#7b4c20; font-size:4.6px; font-weight:900; border-radius:50%; }}
.footer {{ position:relative; z-index:1; margin-top:6mm; }}
.mesa-extra {{ margin-bottom:3mm; padding:3mm; border:1px solid #d8c2a2; border-radius:8px; background:#fff7e8; color:#5d4635; font-size:8.5px; text-align:center; }}
</style>
</head>
<body><div class="page">
<header class="header">
    <div class="brand">{brand_block}<div class="header-text"><div class="label">Mesa QR · Alérgenos</div><h1>Consulta rápida</h1></div></div>
    {qr_block}
</header>
<section class="intro">
    <div class="intro-main">Carta compacta para consulta en mesa o barra. Los iconos junto a cada producto indican alérgenos presentes o de revisión recomendada.</div>
    <div class="intro-badge">Iconos reales</div>
</section>
<main class="menu-grid">{''.join(category_blocks)}</main>
<footer class="footer">{extra_html}{allergen_guide_panel_html(theme="light", notice=notice)}</footer>
</div></body></html>"""



def _premium_brand_header(data, logo_src=None, qr_src=None, label="Carta premium · alérgenos"):
    return f"""
    <header class="header">
        <div><div class="label">{html_escape(label)}</div>{brand_html(data, logo_src)}</div>
        {qr_html(qr_src)}
    </header>
    """


def create_premium_compact_html(data, logo_src=None, qr_src=None):
    # Plantilla premium similar a la favorita, más compacta para cartas largas. Siempre dos columnas.
    notice = html_escape(build_notice(data))
    blocks = []
    for cat in data.get("categories", []):
        rows = []
        for dish in cat.get("dishes", []):
            desc = html_escape(dish.get("description", ""))
            desc_html = f'<div class="compact-desc">{desc}</div>' if desc else ""
            icons = allergen_icons_html(dish.get("allergens", []), small=True)
            price = html_escape(format_price(dish.get("price", "")))
            rows.append(f"""
            <div class="compact-row">
                <div class="compact-main">
                    <div class="compact-title"><span>{html_escape(dish_display_name(dish))}</span><span class="compact-icons">{icons}</span></div>
                    {desc_html}
                </div>
                <div class="compact-price">{price}</div>
            </div>
            """)
        blocks.append(f"""
        <section class="compact-category">
            <h2>{html_escape(cat.get('name','Categoría'))}</h2>
            {''.join(rows)}
        </section>
        """)
    extra = html_escape(data.get("texto_extra", ""))
    extra_html = f'<div class="premium-note">{extra}</div>' if extra else ""
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><title>Premium Compacta - {html_escape(data.get('restaurant_name','Menú'))}</title>
<style>
@page {{ size:A4 portrait; margin:8mm; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#efe4d1; color:#1f1711; font-family:'Trebuchet MS', Arial, sans-serif; }}
.page {{ min-height:281mm; padding:9mm; background:linear-gradient(150deg,#fffdf6 0%,#f3e4cb 100%); border:1.2mm solid #2a2119; box-shadow:inset 0 0 0 .55mm #c49a59; }}
.header {{ display:grid; grid-template-columns:1fr auto; gap:7mm; align-items:center; margin-bottom:6mm; padding-bottom:4mm; border-bottom:1px solid #c49a59; }}
.label {{ color:#9b6b35; text-transform:uppercase; letter-spacing:2.8px; font-size:9px; font-weight:900; margin-bottom:1.6mm; }}
.brand-wrap {{ display:flex; align-items:center; gap:4mm; }}
.restaurant-logo {{ max-width:31mm; max-height:20mm; object-fit:contain; }}
.brand-name.mini {{ font-size:9px; color:#7b4c20; text-transform:uppercase; font-weight:900; letter-spacing:1px; }}
.brand-wordmark {{ font-family:Georgia,'Times New Roman',serif; font-size:28px; color:#2a2119; font-weight:900; letter-spacing:.4px; text-transform:uppercase; }}
.qr-wrap {{ width:28mm; text-align:center; color:#6c563e; font-size:7px; text-transform:uppercase; letter-spacing:.5px; }}
.qr-img {{ width:26mm; height:26mm; object-fit:contain; background:#fff; padding:1.1mm; border:1px solid #c49a59; }}
.layout {{ column-count:2; column-gap:6.5mm; }}
.compact-category {{ break-inside:avoid; background:rgba(255,255,255,.76); border:1px solid #dcc299; border-radius:7px; padding:3.6mm; margin-bottom:4.2mm; box-shadow:0 5px 13px rgba(47,32,15,.06); }}
.compact-category h2 {{ margin:0 0 2.6mm; padding-bottom:1.8mm; border-bottom:1px solid #d7bb8d; color:#86531f; font-family:Georgia,'Times New Roman',serif; font-size:18px; line-height:1; }}
.compact-row {{ display:flex; gap:3mm; align-items:flex-start; padding:1.35mm 0; border-bottom:1px dotted rgba(134,83,31,.18); }}
.compact-row:last-child {{ border-bottom:none; }}
.compact-main {{ flex:1; min-width:0; }}
.compact-title {{ display:flex; align-items:center; flex-wrap:wrap; gap:1.2mm; color:#2d2118; font-size:9.6px; text-transform:uppercase; letter-spacing:.18px; font-weight:900; }}
.compact-price {{ min-width:12mm; text-align:right; color:#86531f; font-size:9.5px; font-weight:900; }}
.compact-desc {{ margin-top:.6mm; color:#625448; font-size:7.8px; line-height:1.23; }}
.compact-icons {{ display:inline-flex; align-items:center; gap:.7mm; }}
.allergen-icon.small {{ width:3.9mm; height:3.9mm; object-fit:contain; vertical-align:middle; }}
.missing-icon {{ display:inline-flex; align-items:center; justify-content:center; width:3.9mm; height:3.9mm; border:1px solid #86531f; color:#86531f; font-size:4.5px; font-weight:900; border-radius:50%; }}
.footer {{ margin-top:5mm; }}
.premium-note {{ margin-bottom:3mm; padding:2.5mm; border:1px solid #dcc299; background:#fff7e8; color:#493b2d; font-size:8px; text-align:center; }}
</style></head>
<body><div class="page">
{_premium_brand_header(data, logo_src, qr_src, 'Carta premium compacta · alérgenos')}
<main class="layout">{''.join(blocks)}</main>
<footer class="footer">{extra_html}{allergen_guide_panel_html(theme="light", notice=notice)}</footer>
</div></body></html>"""


def create_premium_clean_html(data, logo_src=None, qr_src=None):
    # Plantilla premium clara/editorial, muy similar al template favorito pero con otra personalidad.
    notice = html_escape(build_notice(data))
    sections = []
    for cat in data.get("categories", []):
        dishes = []
        for dish in cat.get("dishes", []):
            desc = html_escape(dish.get("description", ""))
            desc_html = f'<p>{desc}</p>' if desc else ""
            icons = allergen_icons_html(dish.get("allergens", []), small=False)
            price = html_escape(format_price(dish.get("price", "")))
            dishes.append(f"""
            <article class="clean-dish">
                <div class="clean-line"><h3>{html_escape(dish_display_name(dish))}</h3><strong>{price}</strong></div>
                {desc_html}
                <div class="clean-icons">{icons}</div>
            </article>
            """)
        sections.append(f"""
        <section class="clean-category">
            <h2>{html_escape(cat.get('name','Categoría'))}</h2>
            {''.join(dishes)}
        </section>
        """)
    extra = html_escape(data.get("texto_extra", ""))
    extra_html = f'<div class="clean-extra"><strong>Notas:</strong> {extra}</div>' if extra else ""
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><title>Premium Claro - {html_escape(data.get('restaurant_name','Menú'))}</title>
<style>
@page {{ size:A4 portrait; margin:8mm; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#eadfcf; color:#201814; font-family:'Trebuchet MS', Arial, sans-serif; }}
.page {{ min-height:281mm; padding:10mm; background:#fffaf2; border:1.1mm solid #b88b51; box-shadow:inset 0 0 0 .6mm rgba(42,33,25,.15); }}
.header {{ display:grid; grid-template-columns:1fr auto; gap:8mm; align-items:center; margin-bottom:8mm; padding-bottom:5mm; border-bottom:1px solid #d5ba91; }}
.label {{ color:#9b6b35; text-transform:uppercase; letter-spacing:3px; font-size:9px; font-weight:900; margin-bottom:2mm; }}
.brand-wrap {{ display:flex; align-items:center; gap:4mm; }}
.restaurant-logo {{ max-width:34mm; max-height:22mm; object-fit:contain; }}
.brand-name.mini {{ font-size:9px; color:#7b4c20; text-transform:uppercase; letter-spacing:1px; font-weight:900; }}
.brand-wordmark {{ font-family:Georgia,'Times New Roman',serif; font-size:29px; color:#2a2119; font-weight:900; text-transform:uppercase; letter-spacing:.45px; }}
.qr-wrap {{ width:30mm; text-align:center; color:#7b6044; font-size:7.5px; text-transform:uppercase; letter-spacing:.6px; }}
.qr-img {{ width:28mm; height:28mm; object-fit:contain; background:#fff; padding:1.2mm; border:1px solid #c49a59; }}
.layout {{ column-count:2; column-gap:7.5mm; }}
.clean-category {{ break-inside:avoid; margin-bottom:5.2mm; padding:4.4mm; border:1px solid #e0ceb2; border-radius:12px; background:linear-gradient(180deg,#ffffff 0%,#fff8ec 100%); box-shadow:0 8px 20px rgba(70,45,20,.06); }}
.clean-category h2 {{ margin:0 0 3.2mm; padding-bottom:2mm; color:#784a1d; border-bottom:1px solid #dfc7a1; font-family:Georgia,'Times New Roman',serif; font-size:20px; line-height:1; }}
.clean-dish {{ padding:2mm 0; border-bottom:1px solid rgba(120,74,29,.12); }}
.clean-dish:last-child {{ border-bottom:none; }}
.clean-line {{ display:flex; justify-content:space-between; gap:4mm; align-items:baseline; }}
.clean-line h3 {{ margin:0; font-size:11.5px; color:#221b15; text-transform:uppercase; letter-spacing:.18px; }}
.clean-line strong {{ color:#784a1d; font-size:11.2px; white-space:nowrap; }}
.clean-dish p {{ margin:1mm 0 1.1mm; color:#625347; font-size:9px; line-height:1.28; }}
.clean-icons {{ display:flex; flex-wrap:wrap; gap:1mm; min-height:4.3mm; align-items:center; }}
.allergen-icon {{ width:4.8mm; height:4.8mm; object-fit:contain; }}
.missing-icon {{ display:inline-flex; align-items:center; justify-content:center; width:4.8mm; height:4.8mm; border:1px solid #784a1d; color:#784a1d; font-size:4.8px; font-weight:900; border-radius:50%; }}
.footer {{ margin-top:6mm; }}
.clean-extra {{ margin-bottom:3mm; padding:2.8mm; border:1px solid #e0ceb2; background:#fff4e0; color:#493b2d; font-size:8.4px; text-align:center; }}
</style></head>
<body><div class="page">
{_premium_brand_header(data, logo_src, qr_src, 'Carta premium clara · alérgenos')}
<main class="layout">{''.join(sections)}</main>
<footer class="footer">{extra_html}{allergen_guide_panel_html(theme="light", notice=notice)}</footer>
</div></body></html>"""


def create_premium_table_html(data, logo_src=None, qr_src=None):
    # Plantilla premium técnica, pero con estética similar al premium. Siempre dos columnas.
    notice = html_escape(build_notice(data))
    blocks = []
    for cat in data.get("categories", []):
        rows = []
        for dish in cat.get("dishes", []):
            desc = html_escape(dish.get("description", ""))
            desc_html = f'<div class="table-desc">{desc}</div>' if desc else ""
            icons = allergen_icons_html(dish.get("allergens", []), small=True)
            price = html_escape(format_price(dish.get("price", "")))
            rows.append(f"""
            <div class="table-row">
                <div class="table-product"><strong>{html_escape(dish_display_name(dish))}</strong>{desc_html}</div>
                <div class="table-icons">{icons}</div>
                <div class="table-price">{price}</div>
            </div>
            """)
        blocks.append(f"""
        <section class="table-category">
            <h2>{html_escape(cat.get('name','Categoría'))}</h2>
            {''.join(rows)}
        </section>
        """)
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><title>Premium Técnico - {html_escape(data.get('restaurant_name','Menú'))}</title>
<style>
@page {{ size:A4 portrait; margin:8mm; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#eee1cf; color:#1f1813; font-family:'Trebuchet MS', Arial, sans-serif; }}
.page {{ min-height:281mm; padding:9mm; background:linear-gradient(145deg,#fffaf1 0%,#f2e2c8 100%); border:1.2mm solid #2a2119; box-shadow:inset 0 0 0 .55mm #c49a59; }}
.header {{ display:grid; grid-template-columns:1fr auto; gap:8mm; align-items:center; margin-bottom:7mm; padding-bottom:4mm; border-bottom:1px solid #c49a59; }}
.label {{ color:#9b6b35; text-transform:uppercase; letter-spacing:2.8px; font-size:9px; font-weight:900; margin-bottom:1.8mm; }}
.brand-wrap {{ display:flex; align-items:center; gap:4mm; }}
.restaurant-logo {{ max-width:33mm; max-height:21mm; object-fit:contain; }}
.brand-name.mini {{ font-size:9px; color:#7b4c20; text-transform:uppercase; letter-spacing:1px; font-weight:900; }}
.brand-wordmark {{ font-family:Georgia,'Times New Roman',serif; font-size:27px; color:#2a2119; font-weight:900; text-transform:uppercase; letter-spacing:.45px; }}
.qr-wrap {{ width:29mm; text-align:center; color:#6c563e; font-size:7px; text-transform:uppercase; letter-spacing:.6px; }}
.qr-img {{ width:27mm; height:27mm; object-fit:contain; background:#fff; padding:1.1mm; border:1px solid #c49a59; }}
.layout {{ column-count:2; column-gap:6.5mm; }}
.table-category {{ break-inside:avoid; margin-bottom:4.8mm; border:1px solid #dcc299; border-radius:10px; overflow:hidden; background:#fffdfa; box-shadow:0 6px 16px rgba(70,45,20,.06); }}
.table-category h2 {{ margin:0; padding:2.6mm 3.2mm; color:#fffaf0; background:#7b4c20; font-family:Georgia,'Times New Roman',serif; font-size:17px; line-height:1; }}
.table-row {{ display:grid; grid-template-columns:1fr auto 13mm; gap:2.2mm; align-items:center; padding:1.8mm 2.8mm; border-bottom:1px solid #ead9bd; }}
.table-row:last-child {{ border-bottom:none; }}
.table-product strong {{ display:block; color:#241b14; font-size:9.4px; text-transform:uppercase; letter-spacing:.15px; }}
.table-desc {{ color:#66564a; font-size:7.6px; line-height:1.2; margin-top:.5mm; }}
.table-icons {{ display:flex; flex-wrap:wrap; gap:.7mm; justify-content:flex-end; min-width:12mm; }}
.table-price {{ text-align:right; color:#7b4c20; font-size:9px; font-weight:900; }}
.allergen-icon.small {{ width:3.9mm; height:3.9mm; object-fit:contain; }}
.missing-icon {{ display:inline-flex; align-items:center; justify-content:center; width:3.9mm; height:3.9mm; border:1px solid #7b4c20; color:#7b4c20; font-size:4.4px; font-weight:900; border-radius:50%; }}
.footer {{ margin-top:5mm; }}
</style></head>
<body><div class="page">
{_premium_brand_header(data, logo_src, qr_src, 'Carta premium técnica · alérgenos')}
<main class="layout">{''.join(blocks)}</main>
<footer class="footer">{allergen_guide_panel_html(theme="light", notice=notice)}</footer>
</div></body></html>"""


def set_docx_two_columns(section):
    sectPr = section._sectPr
    cols = sectPr.xpath('./w:cols')
    cols_el = cols[0] if cols else OxmlElement('w:cols')
    if not cols:
        sectPr.append(cols_el)
    cols_el.set(qn('w:num'), '2')
    cols_el.set(qn('w:space'), '720')


def set_docx_margins(section):
    section.top_margin = Cm(1.4)
    section.bottom_margin = Cm(1.4)
    section.left_margin = Cm(1.3)
    section.right_margin = Cm(1.3)


def create_premium_editable_word(data):
    # DOCX editable en Word/Google Docs. Diseño premium en dos columnas, pensado para cambios manuales.
    doc = Document()
    section = doc.sections[0]
    set_docx_margins(section)

    styles = doc.styles
    styles['Normal'].font.name = 'Arial'
    styles['Normal'].font.size = Pt(8.5)

    try:
        title_style = styles.add_style('Serval Premium Title', WD_STYLE_TYPE.PARAGRAPH)
    except Exception:
        title_style = styles['Serval Premium Title']
    title_style.font.name = 'Georgia'
    title_style.font.size = Pt(22)
    title_style.font.bold = True

    try:
        cat_style = styles.add_style('Serval Premium Category', WD_STYLE_TYPE.PARAGRAPH)
    except Exception:
        cat_style = styles['Serval Premium Category']
    cat_style.font.name = 'Georgia'
    cat_style.font.size = Pt(13)
    cat_style.font.bold = True

    p = doc.add_paragraph(style='Serval Premium Title')
    p.alignment = 1
    p.add_run(data.get('restaurant_name', 'MENÚ'))
    sub = doc.add_paragraph()
    sub.alignment = 1
    run = sub.add_run('Carta premium de alérgenos · Documento editable')
    run.bold = True
    run.font.size = Pt(8.5)

    doc.add_paragraph()
    set_docx_two_columns(section)

    for cat in data.get('categories', []):
        p_cat = doc.add_paragraph(style='Serval Premium Category')
        p_cat.paragraph_format.space_before = Pt(6)
        p_cat.paragraph_format.space_after = Pt(3)
        p_cat.add_run(cat.get('name', 'Categoría'))
        for dish in cat.get('dishes', []):
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.tab_stops.add_tab_stop(Cm(7.6), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            r = p.add_run(dish_display_name(dish))
            r.bold = True
            r.font.size = Pt(8.4)
            p.add_run('\t' + format_price(dish.get('price', '')) + '  ')
            icon_run = p.add_run()
            for allergen in get_ordered_allergens(dish.get('allergens', [])):
                icon_path = ICON_MAP.get(allergen)
                if icon_path and os.path.exists(icon_path):
                    try:
                        icon_run.add_picture(icon_path, width=Cm(0.34))
                    except Exception:
                        p.add_run(f'[{ALLERGEN_SHORT.get(allergen, allergen[:3]).upper()}]')
            if dish.get('description'):
                p_desc = doc.add_paragraph()
                p_desc.paragraph_format.space_after = Pt(2)
                d = p_desc.add_run(dish.get('description', ''))
                d.italic = True
                d.font.size = Pt(7.4)

    footer_section = doc.add_section(WD_SECTION.CONTINUOUS)
    set_docx_margins(footer_section)
    doc.add_paragraph()
    legend_title = doc.add_paragraph()
    legend_title.alignment = 1
    legend_title.add_run('GUÍA DE ALÉRGENOS').bold = True

    table = doc.add_table(rows=2, cols=7)
    table.autofit = True
    for idx, allergen in enumerate(ALLERGEN_ORDER):
        row = 0 if idx < 7 else 1
        col = idx if idx < 7 else idx - 7
        cell = table.cell(row, col)
        par = cell.paragraphs[0]
        par.alignment = 1
        icon_path = ICON_MAP.get(allergen)
        if icon_path and os.path.exists(icon_path):
            try:
                par.add_run().add_picture(icon_path, width=Cm(0.55))
                par.add_run('\n')
            except Exception:
                pass
        txt = par.add_run(ALLERGEN_LABELS.get(allergen, allergen))
        txt.font.size = Pt(6.5)

    notice = doc.add_paragraph()
    notice.alignment = 1
    nr = notice.add_run(build_notice(data))
    nr.font.size = Pt(6.5)
    nr.italic = True

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def set_docx_one_column(section):
    sectPr = section._sectPr
    cols = sectPr.xpath('./w:cols')
    cols_el = cols[0] if cols else OxmlElement('w:cols')
    if not cols:
        sectPr.append(cols_el)
    cols_el.set(qn('w:num'), '1')


def set_cell_shading(cell, fill):
    if not fill:
        return
    fill = fill.replace('#', '')
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn('w:shd'))
    if shd is None:
        shd = OxmlElement('w:shd')
        tcPr.append(shd)
    shd.set(qn('w:fill'), fill)


def set_run_color(run, color):
    if color:
        run.font.color.rgb = None
        try:
            from docx.shared import RGBColor
            c = color.replace('#', '')
            run.font.color.rgb = RGBColor(int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
        except Exception:
            pass


EDITABLE_WORD_THEMES = {
    'neutral': {'name':'Neutra', 'header':'1F2937', 'cat':'374151', 'text':'111827', 'muted':'6B7280', 'bg':'FFFFFF', 'light':'F9FAFB'},
    'cafe': {'name':'Café editorial', 'header':'8A5A2B', 'cat':'7B4C20', 'text':'211A14', 'muted':'6A5848', 'bg':'FFF4E2', 'light':'FFF9ED'},
    'noir': {'name':'Noir elegante', 'header':'111111', 'cat':'C8A45D', 'text':'111111', 'muted':'555555', 'bg':'F7F1E6', 'light':'FFFFFF'},
    'oliva': {'name':'Oliva natural', 'header':'556B3E', 'cat':'4F6F3A', 'text':'1E261A', 'muted':'59644F', 'bg':'F3F5E8', 'light':'FFFFFF'},
    'burdeos': {'name':'Burdeos gastrobar', 'header':'6D1F2C', 'cat':'7B1E2E', 'text':'261516', 'muted':'654D45', 'bg':'FFF1E8', 'light':'FFFFFF'},
    'azul': {'name':'Azul noche', 'header':'123047', 'cat':'1E4C66', 'text':'14222D', 'muted':'566B75', 'bg':'EDF6FA', 'light':'FFFFFF'},
    'arena': {'name':'Mediterráneo arena', 'header':'B68143', 'cat':'9A642B', 'text':'2A2119', 'muted':'695A4C', 'bg':'FFF7E8', 'light':'FFFFFF'},
    'minimal': {'name':'Minimal blanco', 'header':'222222', 'cat':'222222', 'text':'111111', 'muted':'666666', 'bg':'FFFFFF', 'light':'FFFFFF'},
    'terracota': {'name':'Terracota cálida', 'header':'A64B2A', 'cat':'A64B2A', 'text':'2A1710', 'muted':'735142', 'bg':'FFF0E8', 'light':'FFFFFF'},
    'rosa': {'name':'Rosa pastel', 'header':'B76E79', 'cat':'9B4F5B', 'text':'2A181C', 'muted':'725963', 'bg':'FFF1F3', 'light':'FFFFFF'},
    'botanico': {'name':'Botánico claro', 'header':'2F6B4F', 'cat':'2F6B4F', 'text':'1A241E', 'muted':'52645A', 'bg':'EEF8F1', 'light':'FFFFFF'},
    'gris': {'name':'Gris urbano', 'header':'3B3F45', 'cat':'2F343B', 'text':'181A1E', 'muted':'5C626A', 'bg':'F3F4F6', 'light':'FFFFFF'},
    'dorado': {'name':'Dorado clásico', 'header':'8A6A2F', 'cat':'8A6A2F', 'text':'211A14', 'muted':'6A5848', 'bg':'FBF4E5', 'light':'FFFFFF'},
}


def add_docx_heading_block(doc, data, theme, subtitle='Plantilla editable sin iconos por plato'):
    table = doc.add_table(rows=1, cols=1)
    table.autofit = True
    cell = table.cell(0, 0)
    set_cell_shading(cell, theme['header'])
    p = cell.paragraphs[0]
    p.alignment = 1
    r = p.add_run(data.get('restaurant_name', 'MENÚ').upper())
    r.bold = True
    r.font.size = Pt(22)
    set_run_color(r, 'FFFFFF')
    p2 = cell.add_paragraph()
    p2.alignment = 1
    r2 = p2.add_run(subtitle)
    r2.bold = True
    r2.font.size = Pt(8)
    set_run_color(r2, 'FFFFFF')
    doc.add_paragraph()


def add_docx_allergen_legend(doc, data, theme):
    """Leyenda 2x7 limpia: marco exterior único, sin cuadrícula interna visible."""
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

    def _nil_cell_borders(cell):
        tc_pr = cell._tc.get_or_add_tcPr()
        borders = tc_pr.find(qn("w:tcBorders"))
        if borders is None:
            borders = OxmlElement("w:tcBorders")
            tc_pr.append(borders)
        for edge in ("top", "left", "bottom", "right", "start", "end", "insideH", "insideV"):
            tag = qn(f"w:{edge}")
            node = borders.find(tag)
            if node is None:
                node = OxmlElement(f"w:{edge}")
                borders.append(node)
            node.set(qn("w:val"), "nil")

    def _nil_table_borders(table):
        tbl_pr = table._tbl.tblPr
        borders = tbl_pr.find(qn("w:tblBorders"))
        if borders is None:
            borders = OxmlElement("w:tblBorders")
            tbl_pr.append(borders)
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            tag = qn(f"w:{edge}")
            node = borders.find(tag)
            if node is None:
                node = OxmlElement(f"w:{edge}")
                borders.append(node)
            node.set(qn("w:val"), "nil")

    border_color = theme.get("muted", "6B7280")
    outer_border = {"val": "single", "sz": "10", "space": "0", "color": border_color}

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
            cell = wrapper.cell(0, 0)
            set_cell_width(cell, usable_cm)
            set_cell_margins(cell, top=18, start=42, bottom=16, end=42)
            set_table_cell_border(
                cell,
                top=outer_border,
                bottom=outer_border,
                start=outer_border,
                end=outer_border,
            )

            legal = cell.paragraphs[0]
            legal.alignment = 1
            compact(legal)
            legal.paragraph_format.space_before = Pt(0)
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
            _nil_table_borders(grid)

            trailing = cell.paragraphs[-1]
            compact(trailing)
            trailing.paragraph_format.space_before = Pt(0)
            trailing.paragraph_format.space_after = Pt(0)
            trailing.paragraph_format.line_spacing = Pt(1)
            if not trailing.runs:
                trailing.add_run("")
            for run in trailing.runs:
                run.font.size = Pt(1)

            for idx, allergen in enumerate(ALLERGEN_ORDER):
                r, c = divmod(idx, 7)
                item = grid.cell(r, c)
                _nil_cell_borders(item)
                set_cell_width(item, col_widths[c])
                set_cell_margins(item, top=0, start=16, bottom=0, end=16)
                set_cell_vertical_padding(item, top_twips=1, bottom_twips=1)
                item.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                item.text = ""

                p = item.paragraphs[0]
                p.alignment = 1
                compact(p)
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)
                icon_path = ICON_MAP.get(allergen)
                if icon_path and os.path.exists(icon_path):
                    try:
                        p.add_run().add_picture(icon_path, width=Cm(0.92))
                    except Exception:
                        pass

                lp = item.add_paragraph()
                lp.alignment = 1
                compact(lp)
                lp.paragraph_format.space_before = Pt(0)
                lp.paragraph_format.space_after = Pt(0)
                lp.paragraph_format.line_spacing = Pt(7.7)
                label = lp.add_run(legend_labels.get(allergen, ALLERGEN_LABELS.get(allergen, allergen)))
                label.font.size = Pt(7.4)
                label.bold = True
                set_run_color(label, theme.get("text", "111111"))

            # Nada de líneas internas: solo el marco exterior del bloque.
            _nil_table_borders(grid)


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
                f'<span class="dots"></span>'
                f'<span class="price">{html_escape(format_price(dish.get("price", "")))}</span>'
                f'<span class="dish-icons">{icons}</span></div>{desc_html}</div>'
            )
        cat_note = html_escape(str(category.get("category_text") or ""))
        note_html = f'<div class="cat-note">{cat_note}</div>' if cat_note else ""
        category_html.append(
            f'<section class="category"><h2>{html_escape(str(category.get("name") or "Categoría"))}</h2>{note_html}{"".join(dishes_html)}</section>'
        )

    page_css = """
    @page {
        size: A4;
        margin: 15mm 15mm 16mm 15mm;
    }
    """
    footer_html = ""
    footer_css = ""

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
            icon = f'<img src="{src}" alt="{html_escape(labels[allergen])}">' if src else ""
            items.append(f'<div class="legend-item">{icon}<span>{labels[allergen]}</span></div>')

        footer_html = (
            '<footer class="allergen-footer">'
            '<div class="legal">Informamos de acuerdo con el Reglamento de la UE 1169/2011, que nuestros productos contienen o pueden contener los siguientes alérgenos.</div>'
            f'<div class="legend-grid">{"".join(items)}</div>'
            '</footer>'
        )
        page_css = """
        @page {
            size: A4;
            margin: 15mm 15mm 42mm 15mm;
            @bottom-center {
                content: element(allergenFooter);
                vertical-align: bottom;
            }
        }
        """
        footer_css = """
        .allergen-footer {
            position: running(allergenFooter);
            width: 180mm;
            height: 33mm;
            border: 1px solid #7a746e;
            padding: 1.4mm 2.5mm 1.0mm;
            box-sizing: border-box;
            background: #fff;
            overflow: hidden;
        }
        .legal {
            text-align: center;
            font-size: 8.2pt;
            font-weight: 700;
            margin: 0 0 0.8mm;
            line-height: 1.12;
        }
        .legend-grid {
            display: flex;
            flex-wrap: wrap;
            align-content: flex-start;
            width: 100%;
        }
        .legend-item {
            width: 14.285714%;
            height: 11.2mm;
            text-align: center;
            font-size: 7.2pt;
            font-weight: 700;
            line-height: 1.04;
            padding: 0.3mm 0.5mm;
            box-sizing: border-box;
            hyphens: none;
            word-break: normal;
            overflow-wrap: normal;
        }
        .legend-item img {
            display: block;
            width: 7.4mm;
            height: 7.4mm;
            object-fit: contain;
            margin: 0 auto 0.25mm;
        }
        .legend-item span {
            display: block;
            white-space: normal;
            hyphens: none;
            word-break: normal;
            overflow-wrap: normal;
        }
        """

    extra = html_escape(str(data.get("texto_extra") or ""))
    extra_html = f'<div class="extra">{extra}</div>' if extra else ""

    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
    {page_css}
    *{{box-sizing:border-box}}
    body{{font-family:Arial,Helvetica,sans-serif;color:{text};margin:0;background:#fff;font-size:10.5pt;}}
    h1{{font-size:24pt;text-align:center;color:{header};margin:0 0 8mm;letter-spacing:.3px;}}
    h2{{font-size:14pt;color:{cat};border-bottom:1px solid {cat};padding-bottom:1.5mm;margin:6mm 0 2.5mm;}}
    .cat-note,.extra{{color:{muted};font-size:9pt;margin:1.5mm 0 3mm;}}
    .dish{{margin:0 0 2.2mm;break-inside:avoid;}}
    .dish-main{{display:flex;align-items:center;gap:1.6mm;font-size:11pt;}}
    .dish-name{{font-weight:700;}}
    .dish-icons{{display:inline-flex;gap:.8mm;align-items:center;flex-shrink:0;}}
    .dish-icon{{width:4.6mm;height:4.6mm;object-fit:contain;}}
    .dots{{flex:1;border-bottom:1px dotted {muted};height:0;min-width:8mm;}}
    .price{{font-weight:700;white-space:nowrap;}}
    .desc{{font-size:9.2pt;color:{muted};font-style:italic;margin-top:.5mm;}}
    .extra{{padding:2.5mm;background:{light};border:1px solid #ddd;margin-top:6mm;}}
    {footer_css}
    </style></head><body>{footer_html}<h1>{rest}</h1>{''.join(category_html)}{extra_html}</body></html>"""


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
        st.caption("Alérgenos calculados automáticamente y editables en Revisar.")
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


def menu_signature(data):
    stable = {
        "restaurant_name": data.get("restaurant_name", ""),
        "texto_extra": data.get("texto_extra", ""),
        "categories": [],
    }
    for category in data.get("categories", []):
        c = {"name": category.get("name", ""), "category_text": category.get("category_text", ""), "dishes": []}
        for dish in category.get("dishes", []):
            c["dishes"].append({
                "number": dish.get("number", ""),
                "name": dish.get("name", ""),
                "description": dish.get("description", ""),
                "price": dish.get("price", ""),
                "allergens": get_ordered_allergens(dish.get("allergens", [])),
            })
        stable["categories"].append(c)
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def invalidate_translation():
    st.session_state.pop("translated_menu_data", None)
    st.session_state.pop("translated_language", None)
    st.session_state.pop("translated_source_signature", None)


TRANSLATION_SCHEMA = {
    "type": "object",
    "properties": {
        "texto_extra": {"type": "string"},
        "categories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "category_text": {"type": "string"},
                    "dishes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                            },
                            "required": ["id", "name", "description"],
                        },
                    },
                },
                "required": ["id", "name", "category_text", "dishes"],
            },
        },
    },
    "required": ["texto_extra", "categories"],
}


def _translation_payload(data):
    payload = {"texto_extra": data.get("texto_extra", ""), "categories": []}
    for ci, category in enumerate(data.get("categories", [])):
        cat_id = f"cat_{ci}"
        c = {
            "id": cat_id,
            "name": category.get("name", ""),
            "category_text": category.get("category_text", ""),
            "dishes": [],
        }
        for di, dish in enumerate(category.get("dishes", [])):
            c["dishes"].append({
                "id": f"{cat_id}_dish_{di}",
                "name": dish.get("name", ""),
                "description": dish.get("description", ""),
            })
        payload["categories"].append(c)
    return payload


def translate_menu_data(data, target_language):
    payload = _translation_payload(data)
    prompt = f"""
Traduce al idioma {target_language} los textos gastronómicos del JSON adjunto.
Devuelve SOLO JSON válido con exactamente los mismos IDs.
NO añadas, borres, unas ni reordenes categorías o platos.
NO traduzcas nombres comerciales del restaurante: el nombre del restaurante no se envía y se conservará aparte.
Traduce únicamente texto_extra, name/category_text de categorías y name/description de platos.
No inventes contenido.

JSON:
{json.dumps(payload, ensure_ascii=False)}
"""
    translated_payload = translate_json(prompt)

    src_cat_ids = [c["id"] for c in payload["categories"]]
    dst_cat_ids = [c.get("id") for c in translated_payload.get("categories", [])]
    if src_cat_ids != dst_cat_ids:
        raise ValueError("La traducción alteró las categorías. No se ha generado el documento para evitar mezclar datos.")

    result = copy.deepcopy(data)
    result["texto_extra"] = translated_payload.get("texto_extra", data.get("texto_extra", ""))
    by_cat_id = {c.get("id"): c for c in translated_payload.get("categories", [])}

    for ci, category in enumerate(result.get("categories", [])):
        cat_id = f"cat_{ci}"
        translated_cat = by_cat_id.get(cat_id)
        if not translated_cat:
            raise ValueError(f"Falta la categoría {cat_id} en la traducción.")
        category["name"] = translated_cat.get("name", category.get("name", ""))
        category["category_text"] = translated_cat.get("category_text", category.get("category_text", ""))
        dst_dishes = {d.get("id"): d for d in translated_cat.get("dishes", [])}
        expected_dish_ids = [f"{cat_id}_dish_{di}" for di, _ in enumerate(category.get("dishes", []))]
        if set(dst_dishes.keys()) != set(expected_dish_ids):
            raise ValueError(f"La traducción alteró los platos de {cat_id}. Se ha bloqueado la salida.")
        for di, dish in enumerate(category.get("dishes", [])):
            translated_dish = dst_dishes[f"{cat_id}_dish_{di}"]
            dish["name"] = translated_dish.get("name", dish.get("name", ""))
            dish["description"] = translated_dish.get("description", dish.get("description", ""))

    result["restaurant_name"] = data.get("restaurant_name", "MENÚ")
    result["_translated_language"] = target_language
    return result


def render_voice_menu_capture():
    with st.expander("🎙️ Dictar menú por voz", expanded=True):
        st.caption("Habla de forma natural. La app ignora muletillas y correcciones, estructura el menú y después lo deja editable para revisar.")
        recorded = st.audio_input("Grabar menú", sample_rate=16000, key="v11_1_voice_record") if hasattr(st, "audio_input") else None
        if recorded is None and not hasattr(st, "audio_input"):
            st.info("La versión instalada de Streamlit no permite grabación directa; puedes subir un audio.")
        uploaded_audio = st.file_uploader(
            "O subir audio ya grabado",
            type=["wav", "mp3", "aac", "ogg", "flac"],
            key="v11_1_voice_upload",
        )
        audio_source = recorded or uploaded_audio
        if audio_source:
            st.audio(audio_source)
            if st.button("✨ CONVERTIR AUDIO EN MENÚ", type="primary", key="v11_1_process_voice"):
                try:
                    with st.spinner("Transcribiendo y estructurando el menú..."):
                        data = analyze_audio_menu(audio_source)
                    if data:
                        st.session_state.menu_data = data
                        invalidate_translation()
                        st.session_state["_last_menu_signature"] = menu_signature(data)
                        st.success("✅ Audio convertido. Revisa platos, precios y alérgenos antes de descargar.")
                        st.rerun()
                    else:
                        st.error("No se pudo obtener un menú válido del audio.")
                except Exception as exc:
                    st.error(f"No se pudo procesar el audio: {exc}")
        st.caption("La IA ayuda a estructurar y detectar; la validación final de alérgenos corresponde a la receta y fichas reales del establecimiento.")


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


# ======================================================
# APP
# ======================================================
st.sidebar.title("Menú Principal 🚀")
show_asset_diagnostics()
app_mode = st.sidebar.radio("Navegación", ["📝 Generador de Cartas", "📡 Radar de Clientes", "📄 Extractor de Texto Universal"])

if app_mode == "📝 Generador de Cartas":
    st.title("Sistema Integral de Cartas 🥘")
    st.caption("Crea, revisa y descarga tu carta de forma sencilla.")

    if "menu_data" not in st.session_state:
        st.session_state.menu_data = None
    if "last_image_info" not in st.session_state:
        st.session_state.last_image_info = None

    render_voice_menu_capture()

    st.markdown("#### O subir una carta existente")
    uploaded_file = st.file_uploader("Sube el menú", type=["jpg", "png", "jpeg", "pdf", "docx"])

    if uploaded_file:
        ft = uploaded_file.name.split(".")[-1].lower()
        if ft in ["jpg", "png", "jpeg"]:
            try:
                preview_img, info = prepare_image_for_ai(uploaded_file)
                st.session_state.last_image_info = info
                with st.expander("👀 Previsualización de imagen preparada", expanded=False):
                    st.image(preview_img, caption=f"Imagen normalizada para análisis · Original: {info.get('size')} · modo {info.get('mode')}")
            except Exception as e:
                st.error(f"No se pudo preparar la imagen: {e}")

    if uploaded_file and st.button("1. ANALIZAR MENÚ", type="primary"):
        ft = uploaded_file.name.split(".")[-1].lower()
        data = None
        if ft in ["jpg", "png", "jpeg"]:
            try:
                img, info = prepare_image_for_ai(uploaded_file)
                data = analyze_content(img, "image")
            except Exception as e:
                st.error(f"Error preparando imagen: {e}")
        elif ft == "pdf":
            native = extract_text_from_pdf(uploaded_file)
            if native and len(native.strip()) > 80:
                data = analyze_content(native, "text")
            else:
                scanned_text = extract_text_from_pdf_scanned_with_qwen(uploaded_file)
                if scanned_text:
                    data = analyze_content(scanned_text, "text")
                else:
                    st.error("El PDF parece escaneado y no se pudo procesar. Convierte la página a imagen JPG/PNG o instala PyMuPDF en requirements.txt.")
        elif ft == "docx":
            data = analyze_content(extract_text_from_docx(uploaded_file), "text")
        if data:
            st.session_state.menu_data = data
            invalidate_translation()
            st.session_state["_last_menu_signature"] = menu_signature(data)
            st.success("✅ Carta preparada. Revisa lo que quieras cambiar y después pulsa Descargar.")
            st.rerun()

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
                render_ai_design_mode(st.session_state.menu_data, ICON_MAP)
                st.divider()
                render_editable_clean_templates(st.session_state.menu_data)
                st.markdown("---")
                render_visual_downloads(st.session_state.menu_data)
            with st.expander("📖 Formato horizontal / modo libro", expanded=False):
                render_landscape_book_word(st.session_state.menu_data)
            with st.expander("🧪 Revisión técnica de alérgenos (opcional)", expanded=False):
                render_allergen_validation(st.session_state.menu_data)

elif app_mode == "📡 Radar de Clientes":
    st.title("Radar de Redes y Mapas 📡")
    import urllib.parse
    c1, c2 = st.columns(2)
    with c1:
        r_nombre = st.text_input("Nombre local")
    with c2:
        r_prov = st.text_input("Provincia")
    if st.button("🚀 Buscar"):
        if r_nombre and r_prov:
            q = urllib.parse.quote_plus(f"{r_nombre} {r_prov}")
            st.markdown(f"### 📍 [Google Maps](https://www.google.com/maps/search/?api=1&query={q})")
            st.markdown(f"### 📸 [Instagram](https://www.google.com/search?q=site%3Ainstagram.com+{q})")
            st.markdown(f"### 📘 [Facebook](https://www.google.com/search?q=site%3Afacebook.com+{q})")
            st.markdown(f"### 🦉 [TripAdvisor](https://www.google.com/search?q=site%3Atripadvisor.es+{q})")
            st.markdown(f"### 🌐 [Búsqueda General Carta](https://www.google.com/search?q={q}+carta+menu)")

elif app_mode == "📄 Extractor de Texto Universal":
    st.title("Extractor de Texto Plano 📄➡️📝")
    st.caption("Sube imagen, PDF, TXT o DOCX para volcar todo su texto literal a Word.")

    if "universal_bytes" not in st.session_state:
        st.session_state.universal_bytes = None

    up_any = st.file_uploader("Sube tu archivo", type=["pdf", "jpg", "jpeg", "png", "txt", "docx"], key="universal_upload")

    if up_any and st.button("🔄 Extraer Todo el Texto"):
        with st.spinner("Leyendo y procesando el archivo..."):
            ext = up_any.name.split(".")[-1].lower()
            texto_extraido = ""
            if ext == "txt":
                texto_extraido = up_any.getvalue().decode("utf-8", errors="ignore")
            elif ext == "docx":
                texto_extraido = extract_text_from_docx(up_any) or ""
            elif ext == "pdf":
                texto_nativo = extract_text_from_pdf(up_any)
                if texto_nativo and len(texto_nativo.strip()) > 50:
                    texto_extraido = texto_nativo
                else:
                    texto_extraido = extract_text_from_pdf_scanned_with_qwen(up_any) or ""
            elif ext in ["jpg", "jpeg", "png"]:
                img, _ = prepare_image_for_ai(up_any)
                texto_extraido = transcribe_menu_page(img) or ""

            if texto_extraido:
                doc_out = new_doc_from_template()
                for section in doc_out.sections:
                    section.bottom_margin = MARGEN_INFERIOR_FORZADO
                p_t = doc_out.add_paragraph()
                p_t.add_run(f"Texto Extraído de: {up_any.name}").bold = True
                p_t.paragraph_format.space_after = Pt(12)
                for line in texto_extraido.split("\n"):
                    if line.strip():
                        p_line = doc_out.add_paragraph()
                        release_paragraph_constraints(p_line, SANGRIA_CATEGORIA)
                        p_line.add_run(line)
                buffer = BytesIO()
                doc_out.save(buffer)
                buffer.seek(0)
                st.session_state.universal_bytes = buffer.getvalue()
                st.success("✅ Texto extraído correctamente.")
            else:
                st.error("No se pudo extraer texto del archivo.")

    if st.session_state.universal_bytes and up_any:
        name = f"Texto_Extraido_{slugify_filename(up_any.name.rsplit('.',1)[0])}.docx"
        st.download_button("⬇️ Descargar Word con Texto Literal", st.session_state.universal_bytes, name)
