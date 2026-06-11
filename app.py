import streamlit as st
import google.generativeai as genai
import os
import json
import re
import base64
import unicodedata
from html import escape as html_escape
from datetime import datetime
from io import BytesIO

from PIL import Image, ImageOps
from pypdf import PdfReader
from docx import Document
from docx.shared import Cm, Pt
from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER, WD_LINE_SPACING
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# ======================================================
# CONFIGURACIÓN GENERAL
# ======================================================
st.set_page_config(page_title="Sistema Integral de Cartas - Serval TECH · v6", layout="wide")

MODELO_A_USAR = "gemini-2.5-flash"

SANGRIA_CATEGORIA = Cm(0.8)
SANGRIA_PLATOS = Cm(0.8)
ESPACIO_PLATOS = Pt(3)
MARGEN_INFERIOR_FORZADO = Cm(4.5)
MAX_IMAGE_SIDE = 2200

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
# No sustituyen la revisión del restaurante: sirven para reforzar a Gemini y evitar omisiones.
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


def apply_allergen_rules_to_dish(dish):
    name = dish.get("name") or ""
    desc = dish.get("description") or ""
    text = normalize_text(f"{name} {desc}")
    current = get_ordered_allergens(dish.get("allergens", []))
    notes = []

    for allergen, keywords in RULES_STRONG.items():
        for keyword in keywords:
            if normalize_text(keyword) in text:
                current = add_allergen(current, allergen)
                break

    for pattern, allergens in COMPOUND_RULES:
        if re.search(pattern, text, flags=re.IGNORECASE):
            for allergen in allergens:
                current = add_allergen(current, allergen)

    for pattern, allergen in NEGATIVE_REMOVALS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            current = [a for a in current if a != allergen]
            if allergen == "gluten":
                notes.append("Marcado como sin gluten: confirmar ficha técnica y manipulación separada.")

    for pattern, note in REVIEW_WARNING_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            if note not in notes:
                notes.append(note)

    # Casos específicos para no inventar: hamburguesa sola no fuerza lácteos/huevo/sésamo.
    # El pan/burger sí aporta gluten; queso aporta lácteos; sésamo solo si aparece.
    dish["allergens"] = get_ordered_allergens(current)
    if notes:
        old = dish.get("review_notes", []) or []
        merged = []
        for n in old + notes:
            if n and n not in merged:
                merged.append(n)
        dish["review_notes"] = merged
    else:
        dish["review_notes"] = dish.get("review_notes", []) or []
    return dish


def apply_allergen_rules(data):
    for category in data.get("categories", []):
        for dish in category.get("dishes", []):
            apply_allergen_rules_to_dish(dish)
    return data

# ======================================================
# API KEY
# ======================================================
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    API_KEY = os.getenv("GEMINI_API_KEY", "")

if not API_KEY:
    st.error("❌ Falta la GEMINI_API_KEY en los Secrets.")
    st.stop()

genai.configure(api_key=API_KEY)

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


def extract_text_from_pdf_scanned_with_gemini(file):
    """Opcional: usa PyMuPDF si está instalado para renderizar PDF escaneado a imágenes."""
    try:
        import fitz  # PyMuPDF
        file.seek(0)
        pdf_bytes = file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        model = genai.GenerativeModel(MODELO_A_USAR)
        chunks = []
        for i, page in enumerate(doc[:6]):  # límite de seguridad
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            img = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
            img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
            response = model.generate_content(
                ["Transcribe literalmente todo el texto visible de esta página de menú. No resumas. No inventes. Devuelve texto plano.", img],
                request_options={"timeout": 120}
            )
            chunks.append(f"\n--- PÁGINA {i+1} ---\n" + response.text)
        file.seek(0)
        return "\n".join(chunks)
    except Exception:
        return None

# ======================================================
# ANÁLISIS IA + REGLAS UNIFICADAS
# ======================================================
def build_ai_prompt():
    allergen_keys = ", ".join(ALLERGEN_ORDER)
    return f"""
Eres un transcriptor profesional de cartas de restaurante y un revisor técnico de alérgenos para hostelería en España/UE.

OBJETIVO:
Extraer la carta literalmente y asignar alérgenos con criterio realista: ni quedarse corto con alérgenos evidentes, ni marcar todo por miedo.

ALÉRGENOS PERMITIDOS:
Usa únicamente estas claves exactas: {allergen_keys}

REGLAS DE TRANSCRIPCIÓN:
- Extrae Nombre, Categorías, Platos, Descripción y Precio exactamente como aparecen.
- No traduzcas. Si la carta es bilingüe, conserva lo que aparezca.
- No inventes platos ni precios.
- Si hay texto suelto, horarios, notas, suplementos o avisos, ponlo en texto_extra.

REGLAS DE ALÉRGENOS:
- Marca alérgenos cuando el nombre, descripción o preparación habitual del plato lo indique claramente.
- Ejemplos:
  - cerveza/caña/tercio/radler: gluten, salvo que indique sin gluten.
  - vinos, cava, vermut, tinto de verano, sidra: sulfitos.
  - café con leche, cortado, cappuccino, queso, nata, bechamel: lacteos.
  - mayonesa, alioli, tortilla, rebozado, empanado, croqueta: huevos si la receta habitual lo implica.
  - croquetas comunes: gluten, lacteos, huevos; añade pescado/crustáceos/moluscos solo si el relleno lo indica.
  - calamares/rabas: moluscos; si dice rebozado/frito/a la romana, añade gluten y huevos.
  - salsa de soja/teriyaki: soja y gluten salvo que indique sin gluten/tamari sin gluten.
  - hummus/tahini/sésamo: sesamo.
  - pesto/romesco/ajoblanco/frutos secos/nueces/pistacho/almendra: frutos de cascara.
  - ensalada/salsa César: huevos, pescado, lacteos, mostaza y posiblemente gluten si hay croutons/pan.
  - caldo/fondo/pastilla de caldo/salsa española: apio si aparece o es preparación típica de base.
- No marques todos los alérgenos solo por ser frito. La contaminación cruzada debe ir como nota de revisión, no como presencia automática de todos los alérgenos.
- Si un producto dice sin gluten, no marques gluten, pero añade nota de revisión.
- Si dice sin lactosa, recuerda que puede seguir siendo alérgeno leche; si hay leche/queso/nata, marca lacteos.

SALIDA JSON PURO, SIN MARKDOWN:
{{
  "restaurant_name": "Nombre detectado o MENÚ",
  "texto_extra": "texto suelto literal",
  "categories": [
    {{
      "name": "Categoría",
      "dishes": [
        {{
          "name": "Plato",
          "description": "Descripción literal",
          "price": "10,50",
          "allergens": ["gluten", "lacteos"],
          "review_notes": ["nota breve si requiere revisar ficha/proveedor o contaminación cruzada"]
        }}
      ]
    }}
  ]
}}
"""


def parse_json_response(text):
    text = (text or "").replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]
    return json.loads(text)


def analyze_content(content, content_type="image"):
    model = genai.GenerativeModel(MODELO_A_USAR)
    prompt = build_ai_prompt()
    try:
        with st.spinner(f"🧠 Analizando menú con {MODELO_A_USAR} + reglas Serval TECH..."):
            if content_type == "image":
                response = model.generate_content([prompt, content], request_options={"timeout": 120})
            else:
                response = model.generate_content(prompt + "\n\nMENÚ:\n" + str(content), request_options={"timeout": 120})

            data = parse_json_response(response.text)
            data = apply_allergen_rules(data)
            data["_generated_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            data["_system_mode"] = "Revisión unificada IA + reglas Serval TECH"
            return data
    except Exception as e:
        st.error(f"Error IA/análisis: {e}")
        return None

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


def create_word(data):
    doc = new_doc_from_template()
    for section in doc.sections:
        section.bottom_margin = MARGEN_INFERIOR_FORZADO

    rest_name = data.get("restaurant_name", "MENÚ")
    try:
        p_title = doc.add_heading(rest_name, 0)
        release_paragraph_constraints(p_title, SANGRIA_CATEGORIA)
    except Exception:
        p_title = doc.add_paragraph(rest_name)
        p_title.add_run(rest_name).bold = True
        release_paragraph_constraints(p_title, SANGRIA_CATEGORIA)

    for category in data.get("categories", []):
        p_cat = doc.add_heading(category.get("name", "Categoría"), level=1)
        release_paragraph_constraints(p_cat, SANGRIA_CATEGORIA)
        p_cat.paragraph_format.space_before = Pt(6)
        for dish in category.get("dishes", []):
            p = doc.add_paragraph()
            release_paragraph_constraints(p, SANGRIA_PLATOS, is_dish=True)
            p.paragraph_format.tab_stops.add_tab_stop(Cm(13.5), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            p.add_run(dish.get("name", "Plato")).bold = True
            p.add_run(f"\t{format_price(dish.get('price', ''))}\t")
            run_icons = p.add_run()
            for allergen in get_ordered_allergens(dish.get("allergens", [])):
                path = ICON_MAP.get(allergen)
                if path and os.path.exists(path):
                    try:
                        run_icons.add_picture(path, width=Cm(0.38))
                    except Exception:
                        pass
            if dish.get("description"):
                p_desc = doc.add_paragraph()
                release_paragraph_constraints(p_desc, SANGRIA_PLATOS, is_dish=True)
                p_desc.add_run(dish["description"]).italic = True

    if data.get("texto_extra"):
        doc.add_paragraph()
        p_extra = doc.add_paragraph()
        release_paragraph_constraints(p_extra, SANGRIA_CATEGORIA)
        p_extra.add_run(data["texto_extra"]).italic = True

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def create_clean_word(data):
    doc = new_doc_from_template()
    for section in doc.sections:
        section.bottom_margin = MARGEN_INFERIOR_FORZADO

    rest_name = data.get("restaurant_name", "MENÚ")
    p_title = doc.add_heading(rest_name, 0)
    release_paragraph_constraints(p_title, SANGRIA_CATEGORIA)

    for category in data.get("categories", []):
        p_cat = doc.add_heading(category.get("name", "Categoría"), level=1)
        release_paragraph_constraints(p_cat, SANGRIA_CATEGORIA)
        p_cat.paragraph_format.space_before = Pt(6)
        for dish in category.get("dishes", []):
            p = doc.add_paragraph()
            release_paragraph_constraints(p, SANGRIA_PLATOS, is_dish=True)
            p.paragraph_format.tab_stops.add_tab_stop(Cm(15.0), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            p.add_run(dish.get("name", "Plato")).bold = True
            p.add_run(f"\t{format_price(dish.get('price', ''))}")
            if dish.get("description"):
                p_desc = doc.add_paragraph()
                release_paragraph_constraints(p_desc, SANGRIA_PLATOS, is_dish=True)
                p_desc.add_run(dish["description"]).italic = True

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
                    <div class="dish-title-line"><span class="dish-name">{html_escape(dish.get('name', 'Plato'))}</span><span class="icons-line">{icons}</span></div>
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
                <div class="modern-line"><h3>{html_escape(dish.get('name','Plato'))}</h3><strong>{price}</strong></div>
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
                <td class="prod"><strong>{html_escape(dish.get('name',''))}</strong><br><span>{html_escape(dish.get('description',''))}</span></td>
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
                    <div class="mesa-title"><span>{html_escape(dish.get('name', 'Plato'))}</span><span class="mesa-icons">{icons}</span></div>
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
                    <div class="compact-title"><span>{html_escape(dish.get('name','Plato'))}</span><span class="compact-icons">{icons}</span></div>
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
                <div class="clean-line"><h3>{html_escape(dish.get('name','Plato'))}</h3><strong>{price}</strong></div>
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
                <div class="table-product"><strong>{html_escape(dish.get('name','Plato'))}</strong>{desc_html}</div>
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
            r = p.add_run(dish.get('name', 'Plato'))
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

def html_to_pdf_bytes(html_code):
    try:
        from weasyprint import HTML
        return HTML(string=html_code, base_url=BASE_DIR).write_pdf()
    except Exception:
        return None

# ======================================================
# UI AUXILIAR
# ======================================================
def show_asset_diagnostics():
    missing = [ALLERGEN_LABELS[a] for a in ALLERGEN_ORDER if not ICON_MAP.get(a) or not os.path.exists(ICON_MAP.get(a))]
    with st.sidebar.expander("🧪 Diagnóstico archivos", expanded=False):
        st.write("**BASE_DIR:**", BASE_DIR)
        st.write("**Plantilla Word:**", "✅" if PLANTILLA_PATH and os.path.exists(PLANTILLA_PATH) else "❌ No encontrada")
        st.write("**Carpeta iconos:**", ICONOS_DIR or "❌ No encontrada")
        if missing:
            st.error("Faltan iconos: " + ", ".join(missing))
        else:
            st.success("Todos los iconos de alérgenos están detectados.")


def render_editor(data):
    data["restaurant_name"] = st.text_input("Nombre del restaurante", data.get("restaurant_name", ""))
    data["texto_extra"] = st.text_area("📝 Texto suelto detectado", data.get("texto_extra", ""), height=90)

    st.info("La app usa revisión unificada: IA + reglas de hostelería + edición manual final. Revisa especialmente salsas, fritos, caldos y productos industriales.")
    for c_idx, cat in enumerate(data.get("categories", [])):
        with st.expander(f"📂 {cat.get('name', 'Categoría')}", expanded=True):
            cat["name"] = st.text_input("Categoría", cat.get("name", ""), key=f"cat_{c_idx}")
            for d_idx, dish in enumerate(cat.get("dishes", [])):
                st.markdown(f"**Plato {d_idx + 1}**")
                col1, col2 = st.columns([3, 1.35])
                with col1:
                    dish["name"] = st.text_input("Plato", dish.get("name", ""), key=f"name_{c_idx}_{d_idx}")
                    dish["description"] = st.text_area("Descripción", dish.get("description", ""), key=f"desc_{c_idx}_{d_idx}", height=64)
                with col2:
                    dish["price"] = st.text_input("Precio", dish.get("price", ""), key=f"price_{c_idx}_{d_idx}")
                    defaults = get_ordered_allergens(dish.get("allergens", []))
                    dish["allergens"] = st.multiselect(
                        "Alérgenos",
                        ALLERGEN_ORDER,
                        default=defaults,
                        format_func=lambda x: ALLERGEN_LABELS.get(x, x),
                        key=f"all_{c_idx}_{d_idx}"
                    )
                if dish.get("review_notes"):
                    st.warning(" · ".join(dish.get("review_notes", [])))
                st.divider()
    return data


def render_visual_downloads(data):
    st.subheader("🎨 Plantillas premium en dos columnas")
    st.caption(
        "La clienta prefiere el estilo premium y trabajar en dos columnas. Por eso esta versión sustituye las plantillas más distintas "
        "por una familia visual premium: todas mantienen dos columnas, iconos reales y una guía inferior más grande."
    )

    colA, colB, colC = st.columns([1.15, 1.15, 1])
    with colA:
        logo_file = st.file_uploader("Subir logo del restaurante", type=["png", "jpg", "jpeg", "webp"], key="logo_visual")
    with colB:
        qr_file = st.file_uploader("Subir QR del menú", type=["png", "jpg", "jpeg", "webp"], key="qr_visual")
    with colC:
        qr_url = st.text_input("O generar QR desde URL", placeholder="https://...")

    logo_src = uploaded_image_to_data_uri(logo_file, max_side=900) if logo_file else None
    qr_src = uploaded_image_to_data_uri(qr_file, max_side=700) if qr_file else generate_qr_data_uri(qr_url)

    template = st.selectbox("Elige plantilla final", [
        "Premium café/bistró · 2 columnas",
        "Premium claro · 2 columnas",
        "Premium compacto · 2 columnas",
        "Premium técnico · 2 columnas",
        "Premium mesa QR · 2 columnas"
    ])

    if template == "Premium café/bistró · 2 columnas":
        html_code = create_modern_html(data, logo_src=logo_src, qr_src=qr_src)
        base_name = "Carta_Premium_Bistro_" + slugify_filename(data.get("restaurant_name", "menu"))
    elif template == "Premium claro · 2 columnas":
        html_code = create_premium_clean_html(data, logo_src=logo_src, qr_src=qr_src)
        base_name = "Carta_Premium_Claro_" + slugify_filename(data.get("restaurant_name", "menu"))
    elif template == "Premium compacto · 2 columnas":
        html_code = create_premium_compact_html(data, logo_src=logo_src, qr_src=qr_src)
        base_name = "Carta_Premium_Compacta_" + slugify_filename(data.get("restaurant_name", "menu"))
    elif template == "Premium técnico · 2 columnas":
        html_code = create_premium_table_html(data, logo_src=logo_src, qr_src=qr_src)
        base_name = "Carta_Premium_Tecnica_" + slugify_filename(data.get("restaurant_name", "menu"))
    else:
        html_code = create_qr_mesa_html(data, logo_src=logo_src, qr_src=qr_src)
        base_name = "Carta_Premium_Mesa_QR_" + slugify_filename(data.get("restaurant_name", "menu"))

    st.markdown("#### Descargas")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button(
            "⬇️ HTML imprimible",
            html_code.encode("utf-8"),
            file_name=f"{base_name}.html",
            mime="text/html"
        )
    with c2:
        pdf_bytes = html_to_pdf_bytes(html_code)
        if pdf_bytes:
            st.download_button("⬇️ PDF visual", pdf_bytes, file_name=f"{base_name}.pdf", mime="application/pdf")
        else:
            st.info("PDF directo no activo. Abre el HTML y usa Imprimir → Guardar como PDF, o instala WeasyPrint.")
    with c3:
        st.download_button(
            "⬇️ Word editable",
            create_premium_editable_word(data),
            file_name=f"{base_name}_editable.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    st.info(
        "Para edición manual real, descarga el Word editable. El HTML/PDF mantiene mejor el diseño visual; el DOCX permite cambiar textos, precios, categorías e iconos desde Word o Google Docs."
    )

    with st.expander("👀 Vista previa", expanded=True):
        st.components.v1.html(html_code, height=840, scrolling=True)



# ======================================================
# V6 - FAMILIA PREMIUM CON SKINS VISUALES DISTINTAS
# ======================================================
PREMIUM_V6_THEMES = {
    "cafe": {
        "name": "Premium Café Editorial",
        "label": "Carta premium café · alérgenos",
        "body_bg": "#eadbc5",
        "page_bg": "linear-gradient(145deg,#fff9ed 0%,#f1dfc4 100%)",
        "page_border": "#2a2119",
        "inner_border": "#c49a59",
        "panel_bg": "rgba(255,255,255,.76)",
        "panel_bg_alt": "#fff7e8",
        "panel_border": "#dcc299",
        "text": "#211a14",
        "muted": "#5d5146",
        "accent": "#86531f",
        "accent_2": "#c49a59",
        "title": "#2a2119",
        "header_bg": "transparent",
        "shadow": "0 8px 18px rgba(47,32,15,.08)",
        "decor": "radial-gradient(circle at 92% 6%, rgba(196,154,89,.16), transparent 20%), radial-gradient(circle at 8% 94%, rgba(123,76,32,.08), transparent 22%)",
        "guide_theme": "light",
    },
    "noir": {
        "name": "Premium Noir",
        "label": "Carta premium noir · alérgenos",
        "body_bg": "#090807",
        "page_bg": "linear-gradient(145deg,#171411 0%,#0d0b0a 55%,#050505 100%)",
        "page_border": "#d2aa5c",
        "inner_border": "rgba(255,255,255,.16)",
        "panel_bg": "rgba(255,255,255,.055)",
        "panel_bg_alt": "rgba(210,170,92,.08)",
        "panel_border": "rgba(210,170,92,.42)",
        "text": "#f7efd9",
        "muted": "#cdbf9d",
        "accent": "#d2aa5c",
        "accent_2": "#8e6b32",
        "title": "#fff8e6",
        "header_bg": "rgba(0,0,0,.16)",
        "shadow": "0 10px 22px rgba(0,0,0,.28)",
        "decor": "radial-gradient(circle at 15% 10%, rgba(255,255,255,.08), transparent 23%), radial-gradient(circle at 80% 8%, rgba(210,170,92,.18), transparent 20%), repeating-linear-gradient(0deg, rgba(255,255,255,.018), rgba(255,255,255,.018) 1px, transparent 1px, transparent 4px)",
        "guide_theme": "dark",
    },
    "oliva": {
        "name": "Premium Oliva Natural",
        "label": "Carta premium oliva · alérgenos",
        "body_bg": "#dfe5d5",
        "page_bg": "linear-gradient(145deg,#fbfbef 0%,#e4ead7 100%)",
        "page_border": "#3f4a33",
        "inner_border": "#9aac7c",
        "panel_bg": "rgba(255,255,250,.78)",
        "panel_bg_alt": "#f3f5e9",
        "panel_border": "#c8d2b3",
        "text": "#202416",
        "muted": "#58604a",
        "accent": "#566b35",
        "accent_2": "#9aac7c",
        "title": "#2b351f",
        "header_bg": "rgba(86,107,53,.06)",
        "shadow": "0 8px 18px rgba(63,74,51,.10)",
        "decor": "radial-gradient(circle at 90% 8%, rgba(86,107,53,.13), transparent 21%), radial-gradient(circle at 4% 86%, rgba(154,172,124,.18), transparent 24%)",
        "guide_theme": "light",
    },
    "burdeos": {
        "name": "Premium Burdeos Gastrobar",
        "label": "Carta premium burdeos · alérgenos",
        "body_bg": "#2b0f15",
        "page_bg": "linear-gradient(150deg,#fff7ec 0%,#f4dccb 64%,#ead0bd 100%)",
        "page_border": "#5a1824",
        "inner_border": "#b98455",
        "panel_bg": "rgba(255,250,244,.84)",
        "panel_bg_alt": "#fff1e4",
        "panel_border": "#d9b896",
        "text": "#261516",
        "muted": "#654d45",
        "accent": "#7b1e2e",
        "accent_2": "#b98455",
        "title": "#4b121d",
        "header_bg": "linear-gradient(90deg, rgba(123,30,46,.12), transparent)",
        "shadow": "0 8px 20px rgba(75,18,29,.12)",
        "decor": "radial-gradient(circle at 88% 10%, rgba(123,30,46,.12), transparent 22%), radial-gradient(circle at 9% 88%, rgba(185,132,85,.16), transparent 24%)",
        "guide_theme": "light",
    },
    "azul": {
        "name": "Premium Azul Noche",
        "label": "Carta premium azul noche · alérgenos",
        "body_bg": "#071521",
        "page_bg": "linear-gradient(145deg,#0f2a3a 0%,#0a1a26 58%,#06101a 100%)",
        "page_border": "#d8c08a",
        "inner_border": "rgba(216,192,138,.44)",
        "panel_bg": "rgba(255,255,255,.075)",
        "panel_bg_alt": "rgba(216,192,138,.08)",
        "panel_border": "rgba(216,192,138,.38)",
        "text": "#f3efe2",
        "muted": "#c4d0d5",
        "accent": "#d8c08a",
        "accent_2": "#7fb0c8",
        "title": "#fff7dd",
        "header_bg": "rgba(255,255,255,.035)",
        "shadow": "0 10px 22px rgba(0,0,0,.30)",
        "decor": "radial-gradient(circle at 86% 8%, rgba(127,176,200,.20), transparent 22%), radial-gradient(circle at 10% 92%, rgba(216,192,138,.14), transparent 26%)",
        "guide_theme": "dark",
    },
}


def premium_v6_theme(theme_key="cafe", custom=None):
    theme = dict(PREMIUM_V6_THEMES.get(theme_key, PREMIUM_V6_THEMES["cafe"]))
    if custom:
        theme.update({k: v for k, v in custom.items() if v})
        theme["name"] = custom.get("name", "Premium Personalizado")
        theme["label"] = custom.get("label", "Carta premium personalizada · alérgenos")
        theme.setdefault("guide_theme", "light")
    return theme


def allergen_guide_panel_v6(theme, notice=""):
    dark = theme.get("guide_theme") == "dark"
    bg = "linear-gradient(135deg, rgba(0,0,0,.22), rgba(255,255,255,.045))" if dark else f"linear-gradient(135deg,{theme['panel_bg_alt']},rgba(255,255,255,.72))"
    title_color = theme["accent"]
    text_color = theme["text"]
    muted = theme["muted"]
    border = theme["panel_border"]
    item_bg = "rgba(255,255,255,.06)" if dark else "rgba(255,255,255,.68)"
    icon_filter = "drop-shadow(0 1px 2px rgba(0,0,0,.65))" if dark else "drop-shadow(0 1px 1px rgba(80,50,20,.18))"
    items = []
    for allergen in ALLERGEN_ORDER:
        icon = icon_img_html_inline(allergen, f"width:8mm; height:8mm; object-fit:contain; filter:{icon_filter};")
        items.append(
            f'<div class="guide-item">{icon}<span>{html_escape(ALLERGEN_LABELS[allergen])}</span></div>'
        )
    return f'''
    <section class="v6-guide">
        <h3>Guía de alérgenos</h3>
        <div class="v6-guide-grid">{"".join(items)}</div>
        <div class="v6-notice">{notice}</div>
    </section>
    <style>
    .v6-guide {{ margin-top:5.5mm; padding:4.8mm; border:1px solid {border}; border-radius:12px; background:{bg}; box-shadow:{theme['shadow']}; }}
    .v6-guide h3 {{ margin:0 0 3.4mm; text-align:center; color:{title_color}; font-family:Georgia,'Times New Roman',serif; font-size:15px; letter-spacing:2.2px; text-transform:uppercase; }}
    .v6-guide-grid {{ display:grid; grid-template-columns:repeat(7,1fr); gap:2mm 2.4mm; align-items:start; }}
    .guide-item {{ min-height:15mm; padding:1.5mm .8mm; display:flex; flex-direction:column; align-items:center; justify-content:flex-start; gap:1mm; color:{text_color}; text-align:center; font-size:7.1px; line-height:1.08; border:1px solid {border}; border-radius:8px; background:{item_bg}; }}
    .v6-notice {{ margin-top:3.1mm; color:{muted}; font-size:6.9px; line-height:1.3; text-align:center; }}
    </style>
    '''


def _premium_v6_header(data, theme, logo_src=None, qr_src=None, label=None, qr_large=False):
    label = label or theme.get("label", "Carta premium · alérgenos")
    brand = brand_html(data, logo_src)
    qr = qr_html(qr_src)
    if qr_large and not qr:
        qr = '<div class="qr-wrap qr-empty"><div class="qr-placeholder">QR</div><span>Añade QR o URL</span></div>'
    return f'''
    <header class="header">
        <div class="head-main"><div class="label">{html_escape(label)}</div><div class="brandline">{brand}</div></div>
        {qr}
    </header>
    '''


def _build_cards_sections(data, variant="cards"):
    sections = []
    for cat in data.get("categories", []):
        dishes = []
        for dish in cat.get("dishes", []):
            desc = html_escape(dish.get("description", ""))
            desc_html = f'<p class="dish-desc">{desc}</p>' if desc else ""
            icons = allergen_icons_html(dish.get("allergens", []), small=(variant != "cards"))
            price = html_escape(format_price(dish.get("price", "")))
            dishes.append(f'''
            <article class="dish {variant}">
                <div class="dish-line"><h3>{html_escape(dish.get('name','Plato'))}</h3><strong>{price}</strong></div>
                {desc_html}
                <div class="icon-line">{icons}</div>
            </article>
            ''')
        sections.append(f'''
        <section class="category {variant}">
            <h2>{html_escape(cat.get('name','Categoría'))}</h2>
            {''.join(dishes)}
        </section>
        ''')
    return "".join(sections)


def _build_table_sections(data):
    blocks = []
    for cat in data.get("categories", []):
        rows = []
        for dish in cat.get("dishes", []):
            desc = html_escape(dish.get("description", ""))
            desc_html = f'<div class="table-desc">{desc}</div>' if desc else ""
            icons = allergen_icons_html(dish.get("allergens", []), small=True)
            price = html_escape(format_price(dish.get("price", "")))
            rows.append(f'''
            <div class="table-row">
                <div class="table-product"><strong>{html_escape(dish.get('name','Plato'))}</strong>{desc_html}</div>
                <div class="table-icons">{icons}</div>
                <div class="table-price">{price}</div>
            </div>
            ''')
        blocks.append(f'''
        <section class="table-category">
            <h2>{html_escape(cat.get('name','Categoría'))}</h2>
            {''.join(rows)}
        </section>
        ''')
    return "".join(blocks)


def create_premium_v6_html(data, logo_src=None, qr_src=None, theme_key="cafe", variant="cards", custom_theme=None):
    theme = premium_v6_theme(theme_key, custom=custom_theme)
    notice = html_escape(build_notice(data))
    extra = html_escape(data.get("texto_extra", ""))
    extra_html = f'<div class="extra-box"><strong>Notas de carta:</strong> {extra}</div>' if extra else ""

    if variant == "table":
        content = _build_table_sections(data)
        label = theme.get("label", "Carta premium técnica · alérgenos")
    else:
        content = _build_cards_sections(data, variant=variant)
        label = theme.get("label", "Carta premium · alérgenos")

    intro = ""
    qr_large = False
    if variant == "mesa":
        qr_large = True
        intro = f'''
        <section class="intro-box">
            <div><strong>Consulta rápida en mesa o barra.</strong><br>Los iconos junto a cada producto indican alérgenos detectados o de revisión recomendada.</div>
            <div class="intro-badge">2 columnas · QR</div>
        </section>
        '''

    page_classes = f"page variant-{variant} theme-{theme_key}"
    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>{html_escape(theme['name'])} - {html_escape(data.get('restaurant_name','Menú'))}</title>
<style>
@page {{ size:A4 portrait; margin:8mm; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:{theme['body_bg']}; color:{theme['text']}; font-family:'Trebuchet MS', Verdana, Arial, sans-serif; }}
.page {{ min-height:281mm; padding:9.5mm; position:relative; overflow:hidden; background:{theme['decor']}, {theme['page_bg']}; border:1.25mm solid {theme['page_border']}; box-shadow:inset 0 0 0 .55mm {theme['inner_border']}; }}
.header {{ position:relative; z-index:1; display:grid; grid-template-columns:1fr auto; gap:8mm; align-items:center; margin-bottom:7mm; padding:4mm 0 5mm; border-bottom:1px solid {theme['accent_2']}; background:{theme['header_bg']}; }}
.head-main {{ min-width:0; }}
.label {{ color:{theme['accent']}; text-transform:uppercase; letter-spacing:3px; font-size:9px; font-weight:900; margin-bottom:1.8mm; }}
.brandline {{ display:flex; align-items:center; gap:5mm; min-width:0; }}
.brand-wrap {{ display:flex; align-items:center; gap:4mm; }}
.restaurant-logo {{ max-width:34mm; max-height:22mm; object-fit:contain; }}
.brand-name.mini {{ color:{theme['muted']}; font-size:8.8px; text-transform:uppercase; letter-spacing:1px; font-weight:900; }}
.brand-wordmark {{ font-family:Georgia,'Times New Roman',serif; font-size:28px; line-height:1; color:{theme['title']}; font-weight:900; letter-spacing:.5px; text-transform:uppercase; }}
.qr-wrap {{ width:30mm; text-align:center; color:{theme['muted']}; font-size:7.3px; text-transform:uppercase; letter-spacing:.55px; }}
.qr-img {{ width:27mm; height:27mm; object-fit:contain; background:#fff; padding:1.1mm; border:1px solid {theme['accent_2']}; border-radius:4px; }}
.qr-placeholder {{ width:27mm; height:27mm; display:flex; align-items:center; justify-content:center; border:1px dashed {theme['accent_2']}; color:{theme['accent']}; font-size:14px; font-weight:900; margin:0 auto 1mm; background:rgba(255,255,255,.35); }}
.intro-box {{ position:relative; z-index:1; margin:0 0 5mm; display:grid; grid-template-columns:1fr auto; gap:4mm; align-items:center; padding:3mm 4mm; border:1px solid {theme['panel_border']}; border-left:4px solid {theme['accent']}; border-radius:10px; background:{theme['panel_bg_alt']}; color:{theme['muted']}; font-size:9px; line-height:1.32; }}
.intro-badge {{ color:{theme['accent']}; font-weight:900; text-transform:uppercase; letter-spacing:.8px; white-space:nowrap; }}
.layout {{ position:relative; z-index:1; column-count:2; column-gap:7mm; }}
.category {{ break-inside:avoid; margin-bottom:5mm; padding:4mm; border:1px solid {theme['panel_border']}; border-radius:10px; background:{theme['panel_bg']}; box-shadow:{theme['shadow']}; }}
.category h2 {{ margin:0 0 3mm; padding-bottom:2mm; color:{theme['accent']}; border-bottom:1px solid {theme['accent_2']}; font-family:Georgia,'Times New Roman',serif; font-size:20px; line-height:1; }}
.dish {{ padding:1.9mm 0; border-bottom:1px solid {theme['panel_border']}; }}
.dish:last-child {{ border-bottom:none; }}
.dish-line {{ display:flex; justify-content:space-between; gap:4mm; align-items:baseline; }}
.dish-line h3 {{ margin:0; color:{theme['text']}; font-size:11.4px; text-transform:uppercase; letter-spacing:.18px; }}
.dish-line strong {{ color:{theme['accent']}; font-size:11.2px; white-space:nowrap; }}
.dish-desc {{ margin:1mm 0 1.1mm; color:{theme['muted']}; font-size:8.8px; line-height:1.28; }}
.icon-line {{ display:flex; flex-wrap:wrap; gap:1mm; min-height:4mm; align-items:center; }}
.allergen-icon {{ width:4.9mm; height:4.9mm; object-fit:contain; }}
.allergen-icon.small {{ width:4mm; height:4mm; object-fit:contain; vertical-align:middle; }}
.missing-icon {{ display:inline-flex; align-items:center; justify-content:center; width:4.5mm; height:4.5mm; border:1px solid {theme['accent']}; color:{theme['accent']}; font-size:4.4px; font-weight:900; border-radius:50%; }}
.extra-box {{ position:relative; z-index:1; margin-bottom:3mm; padding:2.7mm 3mm; border:1px solid {theme['panel_border']}; border-radius:9px; background:{theme['panel_bg_alt']}; color:{theme['muted']}; font-size:8.2px; text-align:center; }}
.footer {{ position:relative; z-index:1; margin-top:5.5mm; }}
.category.compact {{ padding:3.5mm; border-radius:7px; }}
.category.compact h2 {{ font-size:18px; margin-bottom:2.5mm; }}
.dish.compact {{ padding:1.3mm 0; }}
.dish.compact .dish-line h3 {{ font-size:9.4px; }}
.dish.compact .dish-line strong {{ font-size:9.5px; }}
.dish.compact .icon-line {{ margin-top:.6mm; }}
.dish.compact .dish-desc {{ font-size:7.6px; }}
.category.soft {{ border-radius:16px; padding:4.5mm; }}
.category.soft h2 {{ border-bottom:none; padding-bottom:0; }}
.category.soft h2:after {{ content:""; display:block; width:26mm; height:1px; background:{theme['accent_2']}; margin:2mm 0 0; }}
.category.mesa {{ border-radius:11px; padding:3.8mm; }}
.dish.mesa {{ padding:1.55mm 0; }}
.dish.mesa .dish-line h3 {{ font-size:9.6px; }}
.dish.mesa .dish-line strong {{ font-size:9.5px; }}
.dish.mesa .dish-desc {{ font-size:7.8px; }}
.table-category {{ break-inside:avoid; margin-bottom:4.7mm; border:1px solid {theme['panel_border']}; border-radius:10px; overflow:hidden; background:{theme['panel_bg']}; box-shadow:{theme['shadow']}; }}
.table-category h2 {{ margin:0; padding:2.6mm 3.2mm; color:{theme['panel_bg_alt']}; background:{theme['accent']}; font-family:Georgia,'Times New Roman',serif; font-size:17px; line-height:1; }}
.table-row {{ display:grid; grid-template-columns:1fr auto 13mm; gap:2.2mm; align-items:center; padding:1.75mm 2.8mm; border-bottom:1px solid {theme['panel_border']}; }}
.table-row:last-child {{ border-bottom:none; }}
.table-product strong {{ display:block; color:{theme['text']}; font-size:9.2px; text-transform:uppercase; letter-spacing:.12px; }}
.table-desc {{ color:{theme['muted']}; font-size:7.5px; line-height:1.2; margin-top:.5mm; }}
.table-icons {{ display:flex; flex-wrap:wrap; gap:.7mm; justify-content:flex-end; min-width:12mm; }}
.table-price {{ text-align:right; color:{theme['accent']}; font-size:9px; font-weight:900; }}
</style>
</head>
<body>
<div class="{page_classes}">
{_premium_v6_header(data, theme, logo_src, qr_src, label=label, qr_large=qr_large)}
{intro}
<main class="layout">{content}</main>
<footer class="footer">{extra_html}{allergen_guide_panel_v6(theme, notice)}</footer>
</div>
</body>
</html>'''


def render_visual_downloads(data):
    st.subheader("🎨 Plantillas premium en dos columnas · v6")
    st.caption(
        "Todas mantienen 2 columnas, iconos reales junto a los platos y la leyenda abajo. "
        "La diferencia está en color, fondo, contraste y estructura visual."
    )

    colA, colB, colC = st.columns([1.15, 1.15, 1])
    with colA:
        logo_file = st.file_uploader("Subir logo del restaurante", type=["png", "jpg", "jpeg", "webp"], key="logo_visual_v6")
    with colB:
        qr_file = st.file_uploader("Subir QR del menú", type=["png", "jpg", "jpeg", "webp"], key="qr_visual_v6")
    with colC:
        qr_url = st.text_input("O generar QR desde URL", placeholder="https://...", key="qr_url_v6")

    logo_src = uploaded_image_to_data_uri(logo_file, max_side=900) if logo_file else None
    qr_src = uploaded_image_to_data_uri(qr_file, max_side=700) if qr_file else generate_qr_data_uri(qr_url)

    template = st.selectbox("Elige plantilla final", [
        "Premium Café Editorial · 2 columnas",
        "Premium Noir · 2 columnas",
        "Premium Oliva Natural · 2 columnas",
        "Premium Burdeos Gastrobar · 2 columnas",
        "Premium Azul Noche Mesa QR · 2 columnas",
        "Premium Personalizable · 2 columnas"
    ], key="template_v6")

    mapping = {
        "Premium Café Editorial · 2 columnas": ("cafe", "cards", "Carta_Premium_Cafe_Editorial_"),
        "Premium Noir · 2 columnas": ("noir", "cards", "Carta_Premium_Noir_"),
        "Premium Oliva Natural · 2 columnas": ("oliva", "soft", "Carta_Premium_Oliva_"),
        "Premium Burdeos Gastrobar · 2 columnas": ("burdeos", "compact", "Carta_Premium_Burdeos_"),
        "Premium Azul Noche Mesa QR · 2 columnas": ("azul", "mesa", "Carta_Premium_Azul_Noche_"),
    }

    custom_theme = None
    if template == "Premium Personalizable · 2 columnas":
        st.markdown("#### Personalización visual")
        c1, c2, c3 = st.columns(3)
        with c1:
            body_bg = st.color_picker("Fondo exterior", "#eadbc5", key="v6_body_bg")
            page_color = st.color_picker("Fondo carta", "#fff9ed", key="v6_page_color")
            panel_bg = st.color_picker("Fondo bloques", "#ffffff", key="v6_panel_bg")
        with c2:
            text = st.color_picker("Texto", "#211a14", key="v6_text")
            muted = st.color_picker("Texto secundario", "#5d5146", key="v6_muted")
            accent = st.color_picker("Color principal", "#86531f", key="v6_accent")
        with c3:
            accent_2 = st.color_picker("Líneas/detalles", "#c49a59", key="v6_accent2")
            border = st.color_picker("Borde carta", "#2a2119", key="v6_border")
            variant = st.radio("Estructura", ["cards", "soft", "compact", "mesa", "table"], format_func=lambda x: {"cards":"Editorial", "soft":"Suave", "compact":"Compacta", "mesa":"Mesa QR", "table":"Técnica"}[x], horizontal=True, key="v6_variant")
        custom_theme = {
            "name": "Premium Personalizado",
            "label": "Carta premium personalizada · alérgenos",
            "body_bg": body_bg,
            "page_bg": f"linear-gradient(145deg,{page_color} 0%,{page_color} 100%)",
            "page_border": border,
            "inner_border": accent_2,
            "panel_bg": f"{panel_bg}d9",
            "panel_bg_alt": panel_bg,
            "panel_border": accent_2,
            "text": text,
            "muted": muted,
            "accent": accent,
            "accent_2": accent_2,
            "title": text,
            "header_bg": "transparent",
            "shadow": "0 8px 18px rgba(0,0,0,.08)",
            "decor": "radial-gradient(circle at 90% 8%, rgba(0,0,0,.035), transparent 20%)",
            "guide_theme": "light",
        }
        theme_key = "cafe"
        prefix = "Carta_Premium_Personalizada_"
    else:
        theme_key, variant, prefix = mapping[template]

    html_code = create_premium_v6_html(
        data,
        logo_src=logo_src,
        qr_src=qr_src,
        theme_key=theme_key,
        variant=variant,
        custom_theme=custom_theme,
    )
    base_name = prefix + slugify_filename(data.get("restaurant_name", "menu"))

    st.markdown("#### Descargas")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button(
            "⬇️ HTML imprimible",
            html_code.encode("utf-8"),
            file_name=f"{base_name}.html",
            mime="text/html"
        )
    with c2:
        pdf_bytes = html_to_pdf_bytes(html_code)
        if pdf_bytes:
            st.download_button("⬇️ PDF visual", pdf_bytes, file_name=f"{base_name}.pdf", mime="application/pdf")
        else:
            st.info("PDF directo no activo. Abre el HTML y usa Imprimir → Guardar como PDF, o instala WeasyPrint.")
    with c3:
        st.download_button(
            "⬇️ Word editable",
            create_premium_editable_word(data),
            file_name=f"{base_name}_editable.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    st.info(
        "La modificación manual real se hace con el Word editable. El HTML/PDF mantiene mejor el diseño visual; "
        "la opción Personalizable permite cambiar colores y estructura sin tocar código."
    )

    with st.expander("👀 Vista previa", expanded=True):
        st.components.v1.html(html_code, height=840, scrolling=True)

# ======================================================
# APP
# ======================================================
st.sidebar.title("Menú Principal 🚀")
show_asset_diagnostics()
app_mode = st.sidebar.radio("Navegación", ["📝 Generador de Cartas", "📡 Radar de Clientes", "📄 Extractor de Texto Universal"])

if app_mode == "📝 Generador de Cartas":
    st.title("Sistema Integral de Cartas 🥘")
    st.caption("Revisión unificada de alérgenos: IA + reglas de hostelería + edición manual + salida con iconos reales.")

    if "menu_data" not in st.session_state:
        st.session_state.menu_data = None
    if "last_image_info" not in st.session_state:
        st.session_state.last_image_info = None

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
                scanned_text = extract_text_from_pdf_scanned_with_gemini(uploaded_file)
                if scanned_text:
                    data = analyze_content(scanned_text, "text")
                else:
                    st.error("El PDF parece escaneado y no se pudo procesar. Convierte la página a imagen JPG/PNG o instala PyMuPDF en requirements.txt.")
        elif ft == "docx":
            data = analyze_content(extract_text_from_docx(uploaded_file), "text")
        if data:
            st.session_state.menu_data = data
            st.success("✅ Menú analizado. Revisa los alérgenos antes de descargar.")
            st.rerun()

    if st.session_state.menu_data:
        st.markdown("---")
        tab1, tab2, tab3, tab4 = st.tabs(["✅ Revisar carta", "🍤 Word con iconos", "📄 Word limpio", "🎨 Plantillas visuales"])
        data = st.session_state.menu_data

        with tab1:
            st.session_state.menu_data = render_editor(data)

        with tab2:
            st.download_button("⬇️ DESCARGAR CARTA WORD CON ALÉRGENOS", create_word(data), "Carta_Alergenos.docx")

        with tab3:
            st.download_button("⬇️ DESCARGAR TEXTO LIMPIO WORD", create_clean_word(data), "Carta_Limpia.docx")

        with tab4:
            render_visual_downloads(data)

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
                    texto_extraido = extract_text_from_pdf_scanned_with_gemini(up_any) or ""
            elif ext in ["jpg", "jpeg", "png"]:
                model = genai.GenerativeModel(MODELO_A_USAR)
                img, _ = prepare_image_for_ai(up_any)
                response = model.generate_content([
                    "Transcribe literalmente de arriba a abajo todo el texto que veas en esta imagen. No inventes. Devuelve solo texto plano.",
                    img
                ], request_options={"timeout": 120})
                texto_extraido = response.text

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
