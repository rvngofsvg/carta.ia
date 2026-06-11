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

# ======================================================
# CONFIGURACIÓN GENERAL
# ======================================================
st.set_page_config(page_title="Sistema Integral de Cartas - Serval TECH", layout="wide")

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


def allergen_legend_html(compact=False):
    items = []
    for allergen in ALLERGEN_ORDER:
        items.append(
            f'<div class="legend-item">{icon_img_html(allergen, cls="legend-icon")}<span>{html_escape(ALLERGEN_LABELS[allergen])}</span></div>'
        )
    cls = "legend compact" if compact else "legend"
    return f'<div class="{cls}">{"".join(items)}</div>'


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
<footer class="footer">{extra_html}{allergen_legend_html(compact=True)}<div class="notice">{notice}</div></footer>
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
<footer class="footer">{extra_html}{allergen_legend_html()}<div class="notice">{notice}</div></footer>
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
<footer class="footer"><div class="legend-mini"><strong>Leyenda:</strong> {' · '.join([ALLERGEN_SHORT[a] + ' ' + ALLERGEN_LABELS[a] for a in ALLERGEN_ORDER])}</div><div class="notice">{notice}</div></footer>
</div></body></html>"""


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
    st.subheader("🎨 Plantillas visuales con iconos reales")

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
        "Pizarra negra restaurante",
        "Premium café/bistró",
        "Matriz técnica"
    ])

    if template == "Pizarra negra restaurante":
        html_code = create_blackboard_html(data, logo_src=logo_src, qr_src=qr_src)
        base_name = "Carta_Pizarra_" + slugify_filename(data.get("restaurant_name", "menu"))
    elif template == "Premium café/bistró":
        html_code = create_modern_html(data, logo_src=logo_src, qr_src=qr_src)
        base_name = "Carta_Premium_" + slugify_filename(data.get("restaurant_name", "menu"))
    else:
        html_code = create_matrix_html(data, logo_src=logo_src, qr_src=qr_src)
        base_name = "Matriz_Alergenos_" + slugify_filename(data.get("restaurant_name", "menu"))

    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Descargar HTML imprimible", html_code.encode("utf-8"), file_name=f"{base_name}.html", mime="text/html")
    with c2:
        pdf_bytes = html_to_pdf_bytes(html_code)
        if pdf_bytes:
            st.download_button("⬇️ Descargar PDF visual", pdf_bytes, file_name=f"{base_name}.pdf", mime="application/pdf")
        else:
            st.info("PDF directo no activo. Abre el HTML y usa Imprimir → Guardar como PDF, o instala WeasyPrint.")

    with st.expander("👀 Vista previa", expanded=True):
        st.components.v1.html(html_code, height=760, scrolling=True)

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
