import streamlit as st
import google.generativeai as genai
import os
import json
from docx import Document
from docx.shared import Cm, Pt
from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
from io import BytesIO
from PIL import Image
from pypdf import PdfReader

# --- 1. CONFIGURACIÓN DEL MODELO ---
# Tal como pediste. Si te funciona, ¡adelante!
MODELO_A_USAR = "gemini-2.5-flash"

# --- 2. RUTAS INTELIGENTES ---
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
        except: pass
        if not found: return None
    return current

PLANTILLA_PATH = find_path_insensitive(BASE_DIR, ["public", "plantilla", "plantilla_menu.docx"])
ICONOS_DIR = find_path_insensitive(BASE_DIR, ["public", "iconos"])

# --- 3. API KEY ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = os.getenv("GEMINI_API_KEY", "")

if not API_KEY:
    st.error("❌ ERROR: Falta la GEMINI_API_KEY en los Secrets.")
    st.stop()

genai.configure(api_key=API_KEY)

# --- 4. MAPEO DE ICONOS ---
if not ICONOS_DIR: 
    ICONOS_DIR = os.path.join(BASE_DIR, "Public", "Iconos")

def get_icon_path(icon_name):
    return os.path.join(ICONOS_DIR, icon_name)

ICON_MAP = {
    "gluten": get_icon_path("gluten.png"),
    "crustaceos": get_icon_path("gambas.png"),
    "huevos": get_icon_path("huevo.png"),
    "pescado": get_icon_path("pescado.png"),
    "cacahuetes": get_icon_path("cacahuetes.png"),
    "soja": get_icon_path("soja.png"),
    "lacteos": get_icon_path("lacteos.png"),
    "frutos de cascara": get_icon_path("frutos_secos.png"),
    "apio": get_icon_path("apio.png"),
    "mostaza": get_icon_path("mostaza.png"),
    "sesamo": get_icon_path("sesamo.png"),
    "sulfitos": get_icon_path("sulfitos.png"),
    "altramuces": get_icon_path("altramuces.png"),
    "moluscos": get_icon_path("moluscos.png")
}

# --- 5. LECTURA DE ARCHIVOS ---

def extract_text_from_pdf(file):
    try:
        reader = PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except: return None

def extract_text_from_docx(file):
    try:
        doc = Document(file)
        text = "\n".join([p.text for p in doc.paragraphs])
        for table in doc.tables:
            for row in table.rows:
                text += " | ".join([cell.text for cell in row.cells]) + "\n"
        return text
    except: return None

# --- 6. ANÁLISIS IA ---

def analyze_content(content, content_type="image"):
    model = genai.GenerativeModel(MODELO_A_USAR)
    
    base_prompt = """
    Analiza este menú.
    1. Extrae Nombre Restaurante.
    2. Extrae Categorías, Platos y PRECIO EXACTO.
    3. DETECTA ALÉRGENOS por ingredientes.
    
    Output JSON (sin markdown):
    {
        "restaurant_name": "Nombre",
        "categories": [
            {
                "name": "Categoría",
                "dishes": [
                    {
                        "name": "Plato",
                        "description": "Ingredientes",
                        "price": "10.50",
                        "allergens": ["gluten", "lacteos"] 
                    }
                ]
            }
        ]
    }
    """
    
    try:
        with st.spinner(f"🧠 Analizando con {MODELO_A_USAR}... (Esto puede tardar unos segundos)"):
            if content_type == "image":
                response = model.generate_content([base_prompt, content])
            else:
                response = model.generate_content(base_prompt + "\n\nMENÚ:\n" + content)
            
            # Limpieza agresiva del JSON
            text = response.text.replace('```json', '').replace('```', '').strip()
            # A veces la IA pone texto antes del JSON, buscamos la primera llave
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end != -1:
                text = text[start:end]
                
            return json.loads(text)
    except Exception as e:
        st.error(f"Error IA: {e}")
        return None

# --- 7. GENERACIÓN WORD (Iconos Juntos) ---

def create_word(data):
    if not PLANTILLA_PATH or not os.path.exists(PLANTILLA_PATH):
        st.error(f"❌ Falta plantilla en: {PLANTILLA_PATH}")
        st.stop()
        
    doc = Document(PLANTILLA_PATH)

    # Título
    try: doc.add_heading(data.get("restaurant_name", "MENÚ"), 0)
    except: doc.add_paragraph(data.get("restaurant_name", "MENÚ")).bold = True

    for category in data.get("categories", []):
        doc.add_heading(category["name"], level=1)
        
        for dish in category["dishes"]:
            # LÍNEA 1: Nombre ............ Precio[Iconos]
            p = doc.add_paragraph()
            
            # Tabulador a la derecha (16cm) con puntos
            tab_stops = p.paragraph_format.tab_stops
            tab_stops.add_tab_stop(Cm(16), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            
            # Nombre
            p.add_run(dish['name']).bold = True
            
            # Salto + Precio
            p.add_run(f"\t{dish['price']}€  ")
            
            # ICONOS (Ajuste solicitado: Más juntos y pegados)
            for allergen in dish.get("allergens", []):
                key = allergen.lower().strip()
                if "frutos secos" in key: key = "frutos de cascara"
                
                if key in ICON_MAP:
                    icon_path = ICON_MAP[key]
                    if os.path.exists(icon_path):
                        try:
                            run = p.add_run()
                            # Reducido a 0.4cm para que quepan más
                            run.add_picture(icon_path, width=Cm(0.4))
                            # HE QUITADO EL ESPACIO p.add_run(" ") PARA QUE VAYAN PEGADOS
                        except: pass
            
            # Descripción
            if dish.get('description'):
                p_desc = doc.add_paragraph()
                p_desc.add_run(dish['description']).italic = True
                p.paragraph_format.space_after = Pt(2)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# --- 8. INTERFAZ ---
st.title(f"Generador de Cartas Pro ({MODELO_A_USAR}) 🚀")

uploaded_file = st.file_uploader("Sube Menú (Foto/PDF/Word)", type=["jpg", "png", "pdf", "docx"])

if uploaded_file is not None:
    file_type = uploaded_file.name.split('.')[-1].lower()
    
    if st.button("GENERAR CARTA"):
        data = None
        if file_type in ['jpg', 'png', 'jpeg']:
            data = analyze_content(Image.open(uploaded_file), "image")
        elif file_type == 'pdf':
            text = extract_text_from_pdf(uploaded_file)
            if text: data = analyze_content(text, "text")
        elif file_type == 'docx':
            text = extract_text_from_docx(uploaded_file)
            if text: data = analyze_content(text, "text")

        if data:
            st.success("✅ ¡Listo!")
            docx = create_word(data)
            st.download_button("📥 DESCARGAR", docx, "Carta_Alergenos.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            
