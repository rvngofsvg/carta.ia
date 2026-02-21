import streamlit as st
import google.generativeai as genai
import os
import json
from docx import Document
from docx.shared import Cm, Pt
from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER, WD_LINE_SPACING
from io import BytesIO
from PIL import Image
from pypdf import PdfReader

# --- 1. CONFIGURACIÓN ---
MODELO_A_USAR = "gemini-2.5-flash" 
SANGRIA_GENERAL = Cm(0.8) # Sangría unificada para todo el bloque

# --- 2. DICCIONARIO MAESTRO ---
DICCIONARIO_MAESTRO = {
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
ALLERGEN_OPTIONS = list(DICCIONARIO_MAESTRO.keys())

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
        if not found: return None
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

# --- 5. MAPEO ICONOS ---
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
            if t: text += t + "\n"
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
def analyze_content(content, content_type="image"):
    model = genai.GenerativeModel(MODELO_A_USAR)
    
    base_prompt = """
    Eres un Transcriptor Profesional y un Nutricionista.
    
    REGLA 1 (TRANSCRIPCIÓN LITERAL):
    - Extrae el Nombre, la Descripción y el Precio EXACTAMENTE como aparecen.
    - NO RESUMAS NADA.
    - NO AÑADAS TEXTO INVENTADO ("puede contener trazas...").
    - Si el texto está en Inglés, tradúcelo al Español literalmente.
    
    REGLA 2 (ALÉRGENOS):
    - Usa tu conocimiento para listar los alérgenos ocultos.
    
    Salida JSON (sin markdown):
    {
        "restaurant_name": "Nombre",
        "categories": [
            {
                "name": "Categoría",
                "dishes": [
                    {
                        "name": "Plato",
                        "description": "Texto literal sin inventar ni omitir nada",
                        "price": "10.50",
                        "allergens": ["gluten", "lacteos"] 
                    }
                ]
            }
        ]
    }
    """
    try:
        with st.spinner(f"🧠 Transcribiendo y Analizando ({MODELO_A_USAR})..."):
            if content_type == "image": 
                response = model.generate_content([base_prompt, content])
            else:
                if not content: content = ""
                response = model.generate_content(base_prompt + "\n\nMENÚ:\n" + str(content))
            
            text = response.text.replace('```json', '').replace('```', '').strip()
            s = text.find('{')
            e = text.rfind('}') + 1
            if s != -1 and e != -1: 
                text = text[s:e]
            data = json.loads(text)

            for category in data.get("categories", []):
                for dish in category["dishes"]:
                    d_name = dish.get("name") or ""
                    d_desc = dish.get("description") or ""
                    full_text = (d_name + " " + d_desc).lower()
                    current = [a.lower().strip() for a in dish.get("allergens", [])]
                    for allergen, keywords in DICCIONARIO_MAESTRO.items():
                        if any(k in full_text for k in keywords):
                            if allergen not in current: 
                                current.append(allergen)
                    dish["allergens"] = current
            return data
    except Exception as e: 
        st.error(f"Error IA: {e}")
        return None

# --- FUNCION AUXILIAR PARA COMPACTAR Y SANGRAR ---
def format_paragraph(paragraph):
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    paragraph.paragraph_format.left_indent = SANGRIA_GENERAL

# --- 8. GENERADOR 1: CARTA CON ALÉRGENOS ---
def create_word(data):
    if not PLANTILLA_PATH or not os.path.exists(PLANTILLA_PATH):
        st.error(f"❌ Falta plantilla: {PLANTILLA_PATH}")
        st.stop()
        
    doc = Document(PLANTILLA_PATH)
    
    rest_name = data.get("restaurant_name", "MENÚ")
    try: 
        p_title = doc.add_heading(rest_name, 0)
        p_title.paragraph_format.left_indent = SANGRIA_GENERAL
    except Exception: 
        p_title = doc.add_paragraph(rest_name)
        p_title.bold = True
        p_title.paragraph_format.left_indent = SANGRIA_GENERAL

    for category in data.get("categories", []):
        p_cat = doc.add_heading(category["name"], level=1)
        p_cat.paragraph_format.space_after = Pt(2) 
        p_cat.paragraph_format.left_indent = SANGRIA_GENERAL
        
        for dish in category["dishes"]:
            p = doc.add_paragraph()
            format_paragraph(p) 
            
            tab_stops = p.paragraph_format.tab_stops
            tab_stops.add_tab_stop
        
