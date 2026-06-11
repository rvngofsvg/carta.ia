import streamlit as st
import google.generativeai as genai
import os
import json
import re
from html import escape as html_escape
from datetime import datetime
from docx import Document
from docx.shared import Cm, Pt
from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER, WD_LINE_SPACING
from io import BytesIO
from PIL import Image
from pypdf import PdfReader

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Sistema Integral - Serval TECH", layout="wide")

# --- 1. CONFIGURACIÓN ---
MODELO_A_USAR = "gemini-2.5-flash"

SANGRIA_CATEGORIA = Cm(0.8)
SANGRIA_PLATOS = Cm(0.8)
ESPACIO_PLATOS = Pt(3)
MARGEN_INFERIOR_FORZADO = Cm(4.5)

# --- 2. DICCIONARIOS MAESTROS (NORMAL Y EXTREMO) ---
DICCIONARIO_NORMAL = {
    "gluten": ["pan", "trigo", "harina", "pasta", "galleta", "bizcocho", "rebozado", "cerveza", "tempura", "panko", "lasaña", "fideos", "salsa de soja", "brioche", "burger", "bocadillo", "sandwich", "croutons", "picatostes", "seitan", "couscous", "bulgur", "tostada", "regaña", "focaccia", "gyoza", "bao", "mollete"],
    "lacteos": ["queso", "nata", "leche", "yogur", "mantequilla", "bechamel", "mozzarella", "parmesano", "cheddar", "helado", "burrata", "carbonara", "feta", "crema", "lactosa", "mascarpone", "tiramisu", "cheesecake", "stracciatella", "tzatziki", "gorgonzola", "brioche", "chocolate blanco", "creme brulee"],
    "huevos": ["huevo", "tortilla", "mayonesa", "mahonesa", "merengue", "alioli", "bizcocho", "quiche", "brioche", "tarta", "revuelto", "poché", "yema", "clara", "carbonara", "salsa holandesa", "salsa tartara", "rebozado", "empanado", "crema catalana"],
    "crustaceos": ["gamba", "langostino", "cigala", "bogavante", "cangrejo", "buey de mar", "camaron", "carabinero", "txangurro", "quisquilla", "bisque"],
    "moluscos": ["pulpo", "calamar", "sepia", "mejillon", "almeja", "chipiron", "vieira", "ostra", "navaja", "berberecho", "zamburiña", "salsa de ostras"],
    "pescado": ["pescado", "atun", "salmon", "bacalao", "merluza", "anchoa", "sardina", "sushi", "sashimi", "tataki", "ceviche", "ventresca", "bonito", "dorada", "lubina", "salsa perrins", "worcestershire", "kimchi", "dashi", "katsuobushi"],
    "cacahuetes": ["cacahuete", "mani", "satay", "crema de cacahuete"],
    "soja": ["soja", "edamame", "tofu", "miso", "salsa de soja", "teriyaki", "wakame", "yuba", "tamari", "kimchi"],
    "frutos de cascara": ["almendra", "nuez", "avellana", "pistacho", "anacardo", "pesto", "romesco", "brownie", "nutella", "praliné", "macadamia", "ajoblanco", "nogal", "coco"],
    "mostaza": ["mostaza", "dijon", "salsa barbacoa", "vinagreta", "mayonesa"],
    "sesamo": ["sesamo", "ajonjoli", "tahini", "hummus", "pan de hamburguesa", "aceite de sesamo", "bagel", "tataki", "poke"],
    "apio": ["apio", "caldo", "sofrito", "bloody mary", "salsa española"],
    "sulfitos": ["vino", "vinagre", "sulfitos", "cava", "champagne", "mostaza antigua", "martini", "vermut", "cerveza"],
    "altramuces": ["altramuz", "altramuces"]
}

DICCIONARIO_EXTREMO = {
    "gluten": DICCIONARIO_NORMAL["gluten"] + ["croqueta", "raba", "calamar", "alita", "natxo", "nacho", "morcilla", "chistorra", "torrezno", "cachopo", "codillo", "hamburguesa", "perrito"],
    "lacteos": DICCIONARIO_NORMAL["lacteos"] + ["croqueta", "raba", "calamar", "alita", "natxo", "nacho", "morcilla", "cachopo", "alioli", "ali-oli", "codillo", "hamburguesa", "perrito"],
    "huevos": DICCIONARIO_NORMAL["huevos"] + ["croqueta", "raba", "calamar", "alita", "morcilla", "chistorra", "cachopo", "codillo", "hamburguesa", "perrito", "ali-oli"],
    "crustaceos": DICCIONARIO_NORMAL["crustaceos"] + ["croqueta", "raba", "calamar", "alita"],
    "moluscos": DICCIONARIO_NORMAL["moluscos"] + ["croqueta", "raba", "alita"],
    "pescado": DICCIONARIO_NORMAL["pescado"] + ["croqueta", "raba", "calamar", "alita"],
    "cacahuetes": DICCIONARIO_NORMAL["cacahuetes"],
    "soja": DICCIONARIO_NORMAL["soja"] + ["croqueta", "raba", "calamar", "alita", "morcilla", "chistorra", "torrezno", "codillo", "hamburguesa", "perrito"],
    "frutos de cascara": DICCIONARIO_NORMAL["frutos de cascara"] + ["morcilla"],
    "mostaza": DICCIONARIO_NORMAL["mostaza"] + ["croqueta", "raba", "calamar", "alita", "morcilla", "torrezno", "alioli", "ali-oli", "hamburguesa", "perrito"],
    "sesamo": DICCIONARIO_NORMAL["sesamo"] + ["croqueta", "raba", "calamar", "alita", "morcilla", "hamburguesa", "perrito"],
    "apio": DICCIONARIO_NORMAL["apio"] + ["croqueta", "raba", "calamar", "alita", "morcilla", "alioli", "ali-oli", "codillo"],
    "sulfitos": DICCIONARIO_NORMAL["sulfitos"] + ["morcilla", "carrillera"],
    "altramuces": DICCIONARIO_NORMAL["altramuces"]
}

ALLERGEN_OPTIONS = list(DICCIONARIO_NORMAL.keys())

# --- 2.1. MAPEO VISUAL PARA PLANTILLAS HTML/PDF ---
ALLERGEN_ORDER = [
    "gluten", "crustaceos", "huevos", "pescado", "cacahuetes", "soja", "lacteos",
    "frutos de cascara", "apio", "mostaza", "sesamo", "sulfitos", "altramuces", "moluscos"
]

ALLERGEN_META = {
    "gluten": {"label": "Gluten", "short": "G", "color": "#E4574F"},
    "crustaceos": {"label": "Crustáceos", "short": "C", "color": "#12A6B8"},
    "huevos": {"label": "Huevos", "short": "H", "color": "#F4B942"},
    "pescado": {"label": "Pescado", "short": "P", "color": "#5078D4"},
    "cacahuetes": {"label": "Cacahuetes", "short": "CA", "color": "#B8783A"},
    "soja": {"label": "Soja", "short": "S", "color": "#55B96E"},
    "lacteos": {"label": "Leche / Lácteos", "short": "L", "color": "#F08AAE"},
    "frutos de cascara": {"label": "Frutos de cáscara", "short": "FC", "color": "#D96B9B"},
    "apio": {"label": "Apio", "short": "A", "color": "#79BD52"},
    "mostaza": {"label": "Mostaza", "short": "M", "color": "#E9C844"},
    "sesamo": {"label": "Sésamo", "short": "SE", "color": "#B99057"},
    "sulfitos": {"label": "Sulfitos", "short": "SU", "color": "#9B67D3"},
    "altramuces": {"label": "Altramuces", "short": "AL", "color": "#D9D16E"},
    "moluscos": {"label": "Moluscos", "short": "MO", "color": "#69B8E7"},
}

ALLERGEN_ALIASES = {
    "frutos secos": "frutos de cascara",
    "frutos de cáscara": "frutos de cascara",
    "frutos cascara": "frutos de cascara",
    "lacteos": "lacteos",
    "lácteos": "lacteos",
    "leche": "lacteos",
    "lactosa": "lacteos",
    "huevo": "huevos",
    "crustáceos": "crustaceos",
    "crustaceo": "crustaceos",
    "molusco": "moluscos",
    "sésamo": "sesamo",
    "sesamo": "sesamo",
    "sulfitos": "sulfitos",
    "dioxido de azufre": "sulfitos",
    "dióxido de azufre": "sulfitos",
    "cacahuete": "cacahuetes",
    "mani": "cacahuetes",
    "maní": "cacahuetes",
    "soya": "soja",
    "altramuz": "altramuces",
}

# --- 3. RUTAS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


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
            pass
        if not found:
            return None
    return current


PLANTILLA_PATH = find_path_insensitive(BASE_DIR, ["public", "plantilla", "plantilla_menu.docx"])
ICONOS_DIR = find_path_insensitive(BASE_DIR, ["public", "iconos"])

# --- 4. API KEY ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    API_KEY = os.getenv("GEMINI_API_KEY", "")

if not API_KEY:
    st.error("❌ Falta la GEMINI_API_KEY en los Secrets.")
    st.stop()

genai.configure(api_key=API_KEY)

# --- 5. MAPEO ICONOS WORD ---
if not ICONOS_DIR:
    ICONOS_DIR = os.path.join(BASE_DIR, "Public", "Iconos")


def get_icon_path(icon_name):
    return os.path.join(ICONOS_DIR, icon_name)


ICON_MAP = {
    "gluten": get_icon_path("gluten.png"), "crustaceos": get_icon_path("gambas.png"),
    "huevos": get_icon_path("huevo.png"), "pescado": get_icon_path("pescado.png"),
    "cacahuetes": get_icon_path("cacahuetes.png"), "soja": get_icon_path("soja.png"),
    "lacteos": get_icon_path("lacteos.png"), "frutos de cascara": get_icon_path("frutos_secos.png"),
    "apio": get_icon_path("apio.png"), "mostaza": get_icon_path("mostaza.png"),
    "sesamo": get_icon_path("sesamo.png"), "sulfitos": get_icon_path("sulfitos.png"),
    "altramuces": get_icon_path("altramuces.png"), "moluscos": get_icon_path("moluscos.png")
}

# --- 6. LECTURA ---
def extract_text_from_pdf(file):
    try:
        reader = PdfReader(file)
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        return text
    except Exception:
        return None


def extract_text_from_docx(file):
    try:
        doc = Document(file)
        text = "\n".join([p.text for p in doc.paragraphs])
        for table in doc.tables:
            for row in table.rows:
                text += " | ".join([cell.text for cell in row.cells]) + "\n"
        return text
    except Exception:
        return None


# --- 7. ANÁLISIS ---
def analyze_content(content, content_type="image", modo="Normal"):
    model = genai.GenerativeModel(MODELO_A_USAR)

    if modo == "Extremo":
        diccionario_activo = DICCIONARIO_EXTREMO
        regla_2 = """
        REGLA 2 (CONTAMINACIÓN CRUZADA Y ALÉRGENOS AL MÁXIMO):
        - Asume SIEMPRE el peor escenario para proteger al cliente de demandas.
        - Si es un frito de bar (croquetas, rabas, calamares, alitas, torreznos, cachopo), asume freidora compartida y producto industrial. Añade trazas de pescado, moluscos, crustaceos, soja, lacteos, mostaza, apio, sesamo y gluten.
        """
    else:
        diccionario_activo = DICCIONARIO_NORMAL
        regla_2 = """
        REGLA 2 (ALÉRGENOS - MODO ESTÁNDAR):
        - Usa tu conocimiento para listar los alérgenos propios de la receta tradicional.
        """

    base_prompt = f"""
    Eres un Transcriptor Profesional y un Nutricionista.

    REGLA 1 (TRANSCRIPCIÓN LITERAL E IDIOMA ORIGINAL):
    - Extrae Nombre, Descripción y Precio EXACTAMENTE como aparecen en la imagen. NO RESUMAS NADA.
    - PROHIBIDO TRADUCIR. Mantén el idioma original de la carta (ej. si dice "Smash Burger", "Bacon", "Pulled Pork", cópialo exactamente así).
    - ANÁLISIS MENTAL DE ALÉRGENOS: Aunque escribas el plato en su idioma original, debes usar tu conocimiento para identificar los alérgenos de esas palabras extranjeras. Por ejemplo: si lees "Cheese" o "Peanut", mantén esa palabra intacta, pero incluye 'lacteos' o 'cacahuetes' en la lista de alérgenos.

    ⚠️ REGLA 3 CRÍTICA (TODO EL TEXTO RESTANTE):
    - Extrae literalmente cualquier otro texto, párrafo o frase que aparezca en la imagen y que no sean platos ni categorías.
    - Copia todo este texto tal cual está escrito y ponlo en el campo "texto_extra". No lo clasifiques, solo cópialo.

    {regla_2}

    Salida JSON (sin markdown):
    {{
        "restaurant_name": "Nombre",
        "texto_extra": "Copia aquí literalmente todo el texto sobrante de la imagen",
        "categories": [
            {{
                "name": "Categoría",
                "dishes": [
                    {{
                        "name": "Plato",
                        "description": "Texto literal en idioma original",
                        "price": "10.50",
                        "allergens": ["gluten", "lacteos"]
                    }}
                ]
            }}
        ]
    }}
    """
    try:
        with st.spinner(f"🧠 Analizando ({MODELO_A_USAR})..."):
            if content_type == "image":
                response = model.generate_content([base_prompt, content])
            else:
                response = model.generate_content(base_prompt + "\n\nMENÚ:\n" + str(content))

            text = response.text.replace('```json', '').replace('```', '').strip()
            s, e = text.find('{'), text.rfind('}') + 1
            if s != -1 and e != -1:
                text = text[s:e]
            data = json.loads(text)

            for category in data.get("categories", []):
                for dish in category.get("dishes", []):
                    d_name = dish.get("name") or ""
                    d_desc = dish.get("description") or ""
                    full_text = (d_name + " " + d_desc).lower()
                    current = [normalize_allergen_key(a) for a in dish.get("allergens", [])]
                    current = [a for a in current if a]
                    for allergen, keywords in diccionario_activo.items():
                        if any(k in full_text for k in keywords):
                            if allergen not in current:
                                current.append(allergen)
                    dish["allergens"] = get_ordered_allergens(current)
            data["_modo_seguridad"] = modo
            data["_generated_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            return data
    except Exception as e:
        st.error(f"Error IA: {e}")
        return None


# --- FUNCIONES AUXILIARES WORD ---
def release_paragraph_constraints(paragraph, indent, is_dish=False):
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = ESPACIO_PLATOS if is_dish else Pt(0)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    paragraph.paragraph_format.left_indent = indent


def new_doc_from_template():
    if PLANTILLA_PATH and os.path.exists(PLANTILLA_PATH):
        return Document(PLANTILLA_PATH)
    return Document()


# --- 8. GENERADORES DE WORD ---
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
        p_title.bold = True
        release_paragraph_constraints(p_title, SANGRIA_CATEGORIA)

    for category in data.get("categories", []):
        p_cat = doc.add_heading(category.get("name", "Categoría"), level=1)
        release_paragraph_constraints(p_cat, SANGRIA_CATEGORIA)
        p_cat.paragraph_format.space_before = Pt(6)
        for dish in category.get("dishes", []):
            p = doc.add_paragraph()
            release_paragraph_constraints(p, SANGRIA_PLATOS, is_dish=True)
            p.paragraph_format.tab_stops.add_tab_stop(Cm(13.5), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            p.add_run(dish.get('name', 'Plato')).bold = True
            p.add_run(f"\t{dish.get('price', '')}€\t")

            run_icons = p.add_run()
            for allergen in dish.get("allergens", []):
                key = normalize_allergen_key(allergen)
                if key in ICON_MAP and os.path.exists(ICON_MAP[key]):
                    try:
                        run_icons.add_picture(ICON_MAP[key], width=Cm(0.38))
                    except Exception:
                        pass

            if dish.get('description'):
                p_desc = doc.add_paragraph()
                release_paragraph_constraints(p_desc, SANGRIA_PLATOS, is_dish=True)
                p_desc.add_run(dish['description']).italic = True

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
    try:
        p_title = doc.add_heading(rest_name, 0)
        release_paragraph_constraints(p_title, SANGRIA_CATEGORIA)
    except Exception:
        p_title = doc.add_paragraph(rest_name)
        p_title.bold = True
        release_paragraph_constraints(p_title, SANGRIA_CATEGORIA)

    for category in data.get("categories", []):
        p_cat = doc.add_heading(category.get("name", "Categoría"), level=1)
        release_paragraph_constraints(p_cat, SANGRIA_CATEGORIA)
        p_cat.paragraph_format.space_before = Pt(6)
        for dish in category.get("dishes", []):
            p = doc.add_paragraph()
            release_paragraph_constraints(p, SANGRIA_PLATOS, is_dish=True)
            p.paragraph_format.tab_stops.add_tab_stop(Cm(15.0), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            p.add_run(dish.get('name', 'Plato')).bold = True
            p.add_run(f"\t{dish.get('price', '')}€")
            if dish.get('description'):
                p_desc = doc.add_paragraph()
                release_paragraph_constraints(p_desc, SANGRIA_PLATOS, is_dish=True)
                p_desc.add_run(dish['description']).italic = True

    if data.get("texto_extra"):
        doc.add_paragraph()
        p_extra = doc.add_paragraph()
        release_paragraph_constraints(p_extra, SANGRIA_CATEGORIA)
        p_extra.add_run(data["texto_extra"]).italic = True

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


# ======================================================
# 9. NUEVO: MOTOR DE PLANTILLAS VISUALES HTML/PDF
# ======================================================
def normalize_allergen_key(key):
    if not key:
        return ""
    k = str(key).strip().lower()
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"
    }
    k_no_accents = k
    for a, b in replacements.items():
        k_no_accents = k_no_accents.replace(a, b)

    if k in ALLERGEN_ALIASES:
        return ALLERGEN_ALIASES[k]
    if k_no_accents in ALLERGEN_ALIASES:
        return ALLERGEN_ALIASES[k_no_accents]
    if k_no_accents in ALLERGEN_META:
        return k_no_accents
    if k in ALLERGEN_META:
        return k
    return k_no_accents


def get_ordered_allergens(allergens):
    normalized = []
    for a in allergens or []:
        key = normalize_allergen_key(a)
        if key in ALLERGEN_META and key not in normalized:
            normalized.append(key)
    ordered = [a for a in ALLERGEN_ORDER if a in normalized]
    extras = [a for a in normalized if a not in ordered]
    return ordered + extras


def format_price(price):
    p = str(price or "").strip()
    if not p:
        return ""
    p = p.replace("€", "").strip()
    return f"{p}€"


def slugify_filename(text):
    text = str(text or "carta").strip().lower()
    text = re.sub(r"[^a-z0-9áéíóúüñ]+", "_", text, flags=re.IGNORECASE)
    text = text.strip("_") or "carta"
    return text[:60]


def allergen_dots_html(allergens, small=False):
    dots = []
    for key in get_ordered_allergens(allergens):
        meta = ALLERGEN_META.get(key)
        if not meta:
            continue
        cls = "a-dot small" if small else "a-dot"
        dots.append(
            f'<span class="{cls}" style="background:{meta["color"]}" title="{html_escape(meta["label"])}">{html_escape(meta["short"])}</span>'
        )
    return "".join(dots)


def allergen_legend_html(compact=False):
    cls = "legend compact" if compact else "legend"
    items = []
    for key in ALLERGEN_ORDER:
        meta = ALLERGEN_META[key]
        items.append(
            f'<div class="legend-item"><span class="a-dot legend-dot" style="background:{meta["color"]}">{html_escape(meta["short"])}</span><span>{html_escape(meta["label"])}</span></div>'
        )
    return f'<div class="{cls}">{"".join(items)}</div>'


def build_html_notice(data):
    modo = html_escape(data.get("_modo_seguridad", "Normal"))
    generated = html_escape(data.get("_generated_at", datetime.now().strftime("%d/%m/%Y %H:%M")))
    return (
        f"Información generada en modo {modo}. Última generación: {generated}. "
        "Documento de apoyo: confirmar siempre con fichas técnicas, etiquetas de producto, proveedores y protocolo real de cocina. "
        "Comunique cualquier alergia o intolerancia al personal antes de realizar el pedido."
    )


def flattened_dishes(data):
    rows = []
    for cat in data.get("categories", []):
        cat_name = cat.get("name", "Categoría")
        for dish in cat.get("dishes", []):
            rows.append({
                "category": cat_name,
                "name": dish.get("name", ""),
                "description": dish.get("description", ""),
                "price": dish.get("price", ""),
                "allergens": get_ordered_allergens(dish.get("allergens", [])),
            })
    return rows


def html_to_pdf_bytes(html_code):
    """Convierte HTML a PDF si WeasyPrint está instalado. Si no, devuelve None."""
    try:
        from weasyprint import HTML
        return HTML(string=html_code, base_url=BASE_DIR).write_pdf()
    except Exception:
        return None


def create_blackboard_html(data):
    restaurant_name = html_escape(data.get("restaurant_name", "MENÚ"))
    texto_extra = html_escape(data.get("texto_extra", ""))
    notice = html_escape(build_html_notice(data))

    category_blocks = []
    for cat in data.get("categories", []):
        dishes_html = []
        for dish in cat.get("dishes", []):
            desc = html_escape(dish.get("description", ""))
            desc_html = f'<div class="dish-desc">{desc}</div>' if desc else ""
            dots = allergen_dots_html(dish.get("allergens", []), small=True)
            price = html_escape(format_price(dish.get("price", "")))
            price_html = f'<span class="price">{price}</span>' if price else '<span class="price"></span>'
            dishes_html.append(f"""
                <div class="dish-row">
                    <div class="dish-main">
                        <div class="dish-title-line"><span class="dish-name">{html_escape(dish.get('name', 'Plato'))}</span>{dots}</div>
                        {desc_html}
                    </div>
                    {price_html}
                </div>
            """)
        category_blocks.append(f"""
            <section class="category-block">
                <h2>{html_escape(cat.get('name', 'Categoría'))}</h2>
                <div class="dish-list">{''.join(dishes_html)}</div>
            </section>
        """)

    extra_html = f'<div class="extra-text">{texto_extra}</div>' if texto_extra else ""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Carta Pizarra - {restaurant_name}</title>
<style>
@page {{ size: A3 portrait; margin: 0; }}
* {{ box-sizing: border-box; }}
body {{
    margin: 0;
    background: #111;
    color: #f8f4e8;
    font-family: Arial, Helvetica, sans-serif;
}}
.page {{
    width: 297mm;
    min-height: 420mm;
    padding: 15mm 15mm 12mm;
    background:
        radial-gradient(circle at 20% 0%, rgba(255,255,255,0.055), transparent 30%),
        radial-gradient(circle at 80% 20%, rgba(210,178,89,0.08), transparent 28%),
        linear-gradient(180deg, #202020 0%, #111 100%);
    border: 6mm solid #c69b5a;
}}
.header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10mm;
    margin-bottom: 8mm;
    border-bottom: 1px solid rgba(239, 217, 154, 0.35);
    padding-bottom: 5mm;
}}
.brand-box {{
    border: 1px solid rgba(255,255,255,0.35);
    padding: 4mm 6mm;
    min-width: 42mm;
    text-align: center;
    color: #ddd;
    font-size: 12px;
    letter-spacing: 1px;
}}
.title {{ text-align: center; flex: 1; }}
.title .eyebrow {{ color: #cdb66a; text-transform: uppercase; font-size: 14px; letter-spacing: 4px; }}
.title h1 {{
    margin: 0;
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 42px;
    line-height: 1;
    color: #fff;
    text-shadow: 0 2px 0 #000;
}}
.title .subtitle {{ color: #dad2b5; font-size: 14px; margin-top: 3mm; }}
.columns {{
    column-count: 2;
    column-gap: 14mm;
}}
.category-block {{
    break-inside: avoid;
    margin-bottom: 8mm;
}}
.category-block h2 {{
    font-family: Georgia, 'Times New Roman', serif;
    margin: 0 0 3mm;
    color: #fff;
    font-size: 26px;
    font-style: italic;
    text-align: center;
    text-shadow: 0 2px 0 #000;
}}
.dish-row {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 4mm;
    padding: 1.1mm 0;
    border-bottom: 1px dotted rgba(255,255,255,0.11);
}}
.dish-main {{ flex: 1; min-width: 0; }}
.dish-title-line {{ display: flex; flex-wrap: wrap; align-items: center; gap: 1.3mm; }}
.dish-name {{
    color: #d5c36c;
    font-weight: 800;
    font-size: 11px;
    letter-spacing: .3px;
    text-transform: uppercase;
}}
.dish-desc {{ color: #e7e1cf; font-size: 9.2px; line-height: 1.25; margin-top: .6mm; }}
.price {{
    color: #fff;
    font-weight: 700;
    font-size: 10px;
    min-width: 14mm;
    text-align: right;
    padding-top: .4mm;
}}
.a-dot {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 13px;
    height: 13px;
    border-radius: 50%;
    color: #fff;
    font-size: 5.5px;
    font-weight: 800;
    line-height: 1;
    box-shadow: 0 0 0 1px rgba(255,255,255,.35) inset;
}}
.a-dot.small {{ width: 10px; height: 10px; font-size: 4.8px; }}
.footer {{
    margin-top: 9mm;
    padding-top: 5mm;
    border-top: 1px solid rgba(239, 217, 154, 0.35);
}}
.legend {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 2mm 4mm; }}
.legend-item {{ display: flex; align-items: center; gap: 1.4mm; font-size: 8px; color: #efe8d0; }}
.legend-dot {{ width: 14px; height: 14px; font-size: 5px; }}
.extra-text {{
    margin: 5mm 0;
    padding: 4mm;
    border: 1px solid rgba(213,195,108,0.55);
    color: #efe8d0;
    font-size: 10px;
    text-align: center;
}}
.notice {{ color: #cfc6a7; font-size: 8px; line-height: 1.35; text-align: center; margin-top: 4mm; }}
</style>
</head>
<body>
<div class="page">
    <header class="header">
        <div class="brand-box">LOGO<br>RESTAURANTE</div>
        <div class="title">
            <div class="eyebrow">Carta visual</div>
            <h1>{restaurant_name}</h1>
            <div class="subtitle">Menú con alérgenos</div>
        </div>
        <div class="brand-box">QR<br>MENÚ</div>
    </header>
    <main class="columns">
        {''.join(category_blocks)}
    </main>
    <footer class="footer">
        {extra_html}
        {allergen_legend_html(compact=True)}
        <div class="notice">{notice}</div>
    </footer>
</div>
</body>
</html>"""


def create_modern_html(data):
    restaurant_name = html_escape(data.get("restaurant_name", "MENÚ"))
    texto_extra = html_escape(data.get("texto_extra", ""))
    notice = html_escape(build_html_notice(data))

    category_blocks = []
    for cat in data.get("categories", []):
        dishes_html = []
        for dish in cat.get("dishes", []):
            desc = html_escape(dish.get("description", ""))
            desc_html = f'<p>{desc}</p>' if desc else ""
            dots = allergen_dots_html(dish.get("allergens", []), small=False)
            price = html_escape(format_price(dish.get("price", "")))
            dishes_html.append(f"""
                <article class="modern-dish">
                    <div class="modern-line">
                        <h3>{html_escape(dish.get('name', 'Plato'))}</h3>
                        <strong>{price}</strong>
                    </div>
                    {desc_html}
                    <div class="dot-line">{dots}</div>
                </article>
            """)
        category_blocks.append(f"""
            <section class="modern-category">
                <h2>{html_escape(cat.get('name', 'Categoría'))}</h2>
                {''.join(dishes_html)}
            </section>
        """)

    extra_html = f'<div class="modern-extra"><strong>Notas:</strong> {texto_extra}</div>' if texto_extra else ""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Carta Moderna - {restaurant_name}</title>
<style>
@page {{ size: A4 portrait; margin: 10mm; }}
* {{ box-sizing: border-box; }}
body {{
    margin: 0;
    background: #f7f1e6;
    color: #1c1b1a;
    font-family: Arial, Helvetica, sans-serif;
}}
.page {{
    min-height: 277mm;
    background: linear-gradient(135deg, #fffaf0 0%, #f3eadc 100%);
    border: 1px solid #dec9a0;
    padding: 12mm;
}}
.header {{
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 8mm;
    align-items: end;
    margin-bottom: 9mm;
}}
.header h1 {{
    margin: 0;
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 34px;
    color: #2a2119;
}}
.header .label {{
    color: #9a6a31;
    text-transform: uppercase;
    letter-spacing: 3px;
    font-size: 11px;
    font-weight: 800;
}}
.qr-box {{
    width: 28mm;
    height: 28mm;
    border: 1px dashed #a38355;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    color: #7d684e;
    font-size: 10px;
}}
.layout {{
    column-count: 2;
    column-gap: 8mm;
}}
.modern-category {{
    break-inside: avoid;
    background: rgba(255,255,255,0.72);
    border: 1px solid #e4d5bd;
    border-radius: 13px;
    padding: 5mm;
    margin-bottom: 6mm;
    box-shadow: 0 6px 16px rgba(60,44,24,0.06);
}}
.modern-category h2 {{
    margin: 0 0 4mm;
    padding-bottom: 2mm;
    border-bottom: 1px solid #ddc9aa;
    color: #7b4c20;
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 22px;
}}
.modern-dish {{ padding: 2.2mm 0; border-bottom: 1px solid rgba(123,76,32,0.12); }}
.modern-dish:last-child {{ border-bottom: none; }}
.modern-line {{ display: flex; justify-content: space-between; gap: 5mm; align-items: baseline; }}
.modern-line h3 {{ margin: 0; font-size: 13px; text-transform: uppercase; letter-spacing: .25px; }}
.modern-line strong {{ font-size: 12px; color: #7b4c20; white-space: nowrap; }}
.modern-dish p {{ margin: 1mm 0 1.5mm; color: #5f554c; font-size: 10px; line-height: 1.35; }}
.dot-line {{ display: flex; flex-wrap: wrap; gap: 1.5mm; min-height: 4mm; }}
.a-dot {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 15px;
    height: 15px;
    border-radius: 50%;
    color: #fff;
    font-size: 6px;
    font-weight: 900;
    box-shadow: 0 0 0 1px rgba(255,255,255,.45) inset;
}}
.footer {{
    margin-top: 8mm;
    padding-top: 5mm;
    border-top: 1px solid #d8c2a2;
}}
.legend {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 2mm 5mm; }}
.legend-item {{ display: flex; align-items: center; gap: 2mm; font-size: 8.5px; color: #47382a; }}
.legend-dot {{ width: 14px; height: 14px; font-size: 5px; }}
.modern-extra {{
    margin-bottom: 5mm;
    background: #fff7e8;
    border: 1px solid #dcc299;
    border-radius: 8px;
    padding: 3mm;
    font-size: 10px;
    color: #554437;
}}
.notice {{ margin-top: 4mm; color: #66564a; font-size: 8px; line-height: 1.35; }}
</style>
</head>
<body>
<div class="page">
    <header class="header">
        <div>
            <div class="label">Carta premium · alérgenos</div>
            <h1>{restaurant_name}</h1>
        </div>
        <div class="qr-box">QR<br>MENÚ</div>
    </header>
    <main class="layout">{''.join(category_blocks)}</main>
    <footer class="footer">
        {extra_html}
        {allergen_legend_html(compact=False)}
        <div class="notice">{notice}</div>
    </footer>
</div>
</body>
</html>"""


def create_matrix_html(data):
    restaurant_name = html_escape(data.get("restaurant_name", "MENÚ"))
    rows = flattened_dishes(data)
    notice = html_escape(build_html_notice(data))

    header_cells = []
    for key in ALLERGEN_ORDER:
        meta = ALLERGEN_META[key]
        header_cells.append(f'<th><span class="matrix-dot" style="background:{meta["color"]}">{html_escape(meta["short"])}</span><small>{html_escape(meta["label"])}</small></th>')

    body_rows = []
    for r in rows:
        allergs = set(r["allergens"])
        allergen_cells = []
        for key in ALLERGEN_ORDER:
            allergen_cells.append('<td class="mark">●</td>' if key in allergs else '<td></td>')
        body_rows.append(f"""
            <tr>
                <td class="cat">{html_escape(r['category'])}</td>
                <td class="prod"><strong>{html_escape(r['name'])}</strong><br><span>{html_escape(r['description'])}</span></td>
                <td class="price-cell">{html_escape(format_price(r['price']))}</td>
                {''.join(allergen_cells)}
            </tr>
        """)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Matriz Alérgenos - {restaurant_name}</title>
<style>
@page {{ size: A3 landscape; margin: 8mm; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; color: #111; background: #fff; }}
.page {{ padding: 4mm; }}
.header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 10mm;
    border-bottom: 2px solid #111;
    padding-bottom: 3mm;
    margin-bottom: 4mm;
}}
.header h1 {{ margin: 0; font-size: 24px; }}
.header p {{ margin: 1mm 0 0; font-size: 10px; color: #555; }}
.badge {{ border: 1px solid #111; padding: 2mm 4mm; font-size: 10px; font-weight: 800; text-transform: uppercase; }}
table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
th, td {{ border: 1px solid #cfcfcf; padding: 1.6mm; vertical-align: middle; }}
th {{ background: #f2f2f2; font-size: 7.5px; text-align: center; }}
th:nth-child(1) {{ width: 33mm; }}
th:nth-child(2) {{ width: 95mm; }}
th:nth-child(3) {{ width: 18mm; }}
td {{ font-size: 8px; }}
.cat {{ font-weight: 800; color: #333; background: #fafafa; }}
.prod strong {{ font-size: 8.6px; }}
.prod span {{ color: #555; line-height: 1.25; }}
.price-cell {{ text-align: right; font-weight: 800; }}
.mark {{ text-align: center; font-size: 11px; font-weight: 900; }}
.matrix-dot {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    color: #fff;
    font-size: 6px;
    font-weight: 900;
    margin-bottom: 1mm;
}}
th small {{ display: block; font-size: 6.4px; line-height: 1.05; }}
.footer {{ margin-top: 3mm; display: grid; grid-template-columns: 1fr 1fr; gap: 6mm; }}
.legend-mini {{ font-size: 8px; line-height: 1.35; color: #333; }}
.notice {{ font-size: 8px; line-height: 1.35; color: #444; text-align: right; }}
</style>
</head>
<body>
<div class="page">
    <header class="header">
        <div>
            <h1>{restaurant_name} · Matriz de alérgenos</h1>
            <p>Formato técnico para consulta rápida por producto. Marcado ● = alérgeno presente o posible presencia según revisión.</p>
        </div>
        <div class="badge">Serval TECH · Carta Pro</div>
    </header>
    <table>
        <thead>
            <tr><th>Categoría</th><th>Producto / descripción</th><th>Precio</th>{''.join(header_cells)}</tr>
        </thead>
        <tbody>{''.join(body_rows)}</tbody>
    </table>
    <footer class="footer">
        <div class="legend-mini">
            <strong>Leyenda:</strong> G Gluten · C Crustáceos · H Huevos · P Pescado · CA Cacahuetes · S Soja · L Lácteos · FC Frutos de cáscara · A Apio · M Mostaza · SE Sésamo · SU Sulfitos · AL Altramuces · MO Moluscos.
        </div>
        <div class="notice">{notice}</div>
    </footer>
</div>
</body>
</html>"""


def render_visual_template_downloads(data):
    st.subheader("🎨 Plantillas visuales nuevas")
    st.caption("Descarga HTML listo para imprimir a PDF. Si instalas WeasyPrint, también descarga PDF directo desde la app.")

    template = st.selectbox(
        "Elige una plantilla visual",
        [
            "Pizarra negra tipo restaurante",
            "Carta premium moderna",
            "Matriz técnica de alérgenos"
        ]
    )

    if template == "Pizarra negra tipo restaurante":
        html_code = create_blackboard_html(data)
        base_name = "Carta_Pizarra_" + slugify_filename(data.get("restaurant_name", "menu"))
    elif template == "Carta premium moderna":
        html_code = create_modern_html(data)
        base_name = "Carta_Premium_" + slugify_filename(data.get("restaurant_name", "menu"))
    else:
        html_code = create_matrix_html(data)
        base_name = "Matriz_Alergenos_" + slugify_filename(data.get("restaurant_name", "menu"))

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "⬇️ Descargar HTML imprimible",
            html_code.encode("utf-8"),
            file_name=f"{base_name}.html",
            mime="text/html"
        )
    with c2:
        pdf_bytes = html_to_pdf_bytes(html_code)
        if pdf_bytes:
            st.download_button(
                "⬇️ Descargar PDF visual",
                pdf_bytes,
                file_name=f"{base_name}.pdf",
                mime="application/pdf"
            )
        else:
            st.info("PDF directo no activo. Añade `weasyprint` al requirements.txt o abre el HTML y usa Imprimir → Guardar como PDF.")

    with st.expander("👀 Vista previa HTML", expanded=False):
        st.components.v1.html(html_code, height=720, scrolling=True)


# ==========================================
# MENÚ LATERAL Y NAVEGACIÓN
# ==========================================
st.sidebar.title("Menú Principal 🚀")
app_mode = st.sidebar.radio("Navegación", ["📝 Generador de Cartas", "📡 Radar de Clientes", "📄 Extractor de Texto Universal"])

# ==========================================
# MÓDULO 1: GENERADOR DE CARTAS
# ==========================================
if app_mode == "📝 Generador de Cartas":
    st.title("Sistema Integral de Cartas 🥘")
    modo_seguridad = st.radio("Perfil de cocina:", ["🟢 Normal", "🔴 Extremo"])
    modo_param = "Extremo" if "Extremo" in modo_seguridad else "Normal"

    if "menu_data" not in st.session_state:
        st.session_state.menu_data = None
    uploaded_file = st.file_uploader("Sube el Menú", type=["jpg", "png", "jpeg", "pdf", "docx"])

    if uploaded_file and st.button("1. ANALIZAR MENÚ"):
        ft = uploaded_file.name.split('.')[-1].lower()
        data = None
        if ft in ['jpg', 'png', 'jpeg']:
            data = analyze_content(Image.open(uploaded_file), "image", modo_param)
        elif ft == 'pdf':
            data = analyze_content(extract_text_from_pdf(uploaded_file), "text", modo_param)
        elif ft == 'docx':
            data = analyze_content(extract_text_from_docx(uploaded_file), "text", modo_param)
        if data:
            st.session_state.menu_data = data
            st.rerun()

    if st.session_state.menu_data:
        st.markdown("---")
        tab1, tab2, tab3 = st.tabs(["🍤 Con Alérgenos Word", "📄 Texto Limpio Word", "🎨 Plantillas Visuales"])
        data = st.session_state.menu_data

        with tab1:
            data["restaurant_name"] = st.text_input("Restaurante", data.get("restaurant_name", ""))
            data["texto_extra"] = st.text_area("📝 Texto suelto detectado", data.get("texto_extra", ""), height=100)
            for c_idx, cat in enumerate(data.get("categories", [])):
                with st.expander(f"📂 {cat.get('name', 'Categoría')}", expanded=True):
                    cat["name"] = st.text_input("Categoría", cat.get("name", ""), key=f"c_{c_idx}")
                    for d_idx, dish in enumerate(cat.get("dishes", [])):
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            dish["name"] = st.text_input("Plato", dish.get("name", ""), key=f"n_{c_idx}_{d_idx}")
                            dish["description"] = st.text_area("Desc", dish.get("description", ""), key=f"d_{c_idx}_{d_idx}", height=68)
                        with c2:
                            dish["price"] = st.text_input("Precio", dish.get("price", ""), key=f"p_{c_idx}_{d_idx}")
                            default_allergens = [normalize_allergen_key(x) for x in dish.get("allergens", [])]
                            default_allergens = [x for x in default_allergens if x in ALLERGEN_OPTIONS]
                            sel = st.multiselect("Alérgenos", ALLERGEN_OPTIONS, default=default_allergens, key=f"a_{c_idx}_{d_idx}")
                            dish["allergens"] = get_ordered_allergens(sel)
            st.download_button("⬇️ DESCARGAR CARTA COMPLETA", create_word(data), "Carta_Alérgenos.docx")

        with tab2:
            st.download_button("⬇️ DESCARGAR TEXTO LIMPIO", create_clean_word(data), "Carta_Limpia.docx")

        with tab3:
            render_visual_template_downloads(data)

# ==========================================
# MÓDULO 2: RADAR DE CLIENTES
# ==========================================
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

# ==========================================
# MÓDULO 3: EXTRACTOR DE TEXTO UNIVERSAL (Soporta JPG, PNG, PDF, TXT)
# ==========================================
elif app_mode == "📄 Extractor de Texto Universal":
    st.title("Extractor de Texto Plano 📄➡️📝")
    st.caption("Sube cualquier archivo (Imagen, PDF nativo/escaneado, Documento o TXT) para volcar todo su texto de forma literal a un Word limpio.")

    if "universal_bytes" not in st.session_state:
        st.session_state.universal_bytes = None

    up_any = st.file_uploader("Sube tu archivo (Imagen, PDF, TXT, DOCX)", type=["pdf", "jpg", "jpeg", "png", "txt", "docx"])

    if up_any:
        if st.button("🔄 Extraer Todo el Texto"):
            with st.spinner("Leyendo y procesando el archivo con Gemini..."):
                ext = up_any.name.split('.')[-1].lower()
                texto_extraido = ""

                if ext == "txt":
                    texto_extraido = up_any.getvalue().decode("utf-8")

                elif ext == "docx":
                    texto_extraido = extract_text_from_docx(up_any)

                elif ext == "pdf":
                    texto_nativo = extract_text_from_pdf(up_any)
                    if texto_nativo and len(texto_nativo.strip()) > 50:
                        texto_extraido = texto_nativo
                    else:
                        model = genai.GenerativeModel(MODELO_A_USAR)
                        response = model.generate_content(
                            f"Transcribe literalmente todo el texto que encuentres en este documento adjunto, palabra por palabra, sin añadir resúmenes ni explicaciones:\n\n{texto_nativo}"
                        )
                        texto_extraido = response.text

                elif ext in ["jpg", "jpeg", "png"]:
                    model = genai.GenerativeModel(MODELO_A_USAR)
                    imagen = Image.open(up_any)
                    response = model.generate_content([
                        "Transcribe literalmente de arriba a abajo todo el texto que veas en esta imagen, de forma exacta, palabra por palabra. No inventes nada ni estructures en JSON, solo texto plano legible.",
                        imagen
                    ])
                    texto_extraido = response.text

                if texto_extraido:
                    doc_out = new_doc_from_template()
                    for section in doc_out.sections:
                        section.bottom_margin = MARGEN_INFERIOR_FORZADO

                    p_t = doc_out.add_paragraph()
                    p_t.add_run(f"Texto Extraído de: {up_any.name}").bold = True
                    p_t.paragraph_format.space_after = Pt(12)

                    for linea in texto_extraido.split('\n'):
                        if linea.strip():
                            p_linea = doc_out.add_paragraph()
                            release_paragraph_constraints(p_linea, SANGRIA_CATEGORIA)
                            p_linea.add_run(linea)

                    buffer_universal = BytesIO()
                    doc_out.save(buffer_universal)
                    buffer_universal.seek(0)
                    st.session_state.universal_bytes = buffer_universal.getvalue()
                    st.success("✅ ¡Texto extraído correctamente!")
                else:
                    st.error("No se pudo extraer texto del archivo.")

        if st.session_state.universal_bytes:
            nombre_descarga = f"Texto_Extraido_{up_any.name.split('.')[0]}.docx"
            st.download_button("⬇️ Descargar Word con Texto Literal", st.session_state.universal_bytes, nombre_descarga)
