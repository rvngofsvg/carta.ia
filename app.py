import streamlit as st
import google.generativeai as genai
import os
import json
from docx import Document
from docx.shared import Cm
from io import BytesIO
from PIL import Image
from pypdf import PdfReader

# --- 1. CONFIGURACIÓN DE MODELO ---
# AQUÍ ES DONDE ELIGES LA VERSIÓN DE LA IA
# Opciones válidas: "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"
MODELO_A_USAR = "gemini-3.0-pro" 

# --- 2. RUTAS INTELIGENTES ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Función para buscar carpetas ignorando mayúsculas/minúsculas (Linux friendly)
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

# Buscamos la plantilla y los iconos automáticamente
PLANTILLA_PATH = find_path_insensitive(BASE_DIR, ["public", "plantilla", "plantilla_menu.docx"])
ICONOS_DIR = find_path_insensitive(BASE_DIR, ["public", "iconos"])

# --- 3. API KEY ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = os.getenv("GEMINI_API_KEY", "")

if not API_KEY:
    st.error("❌ Falta la API Key. Configúrala en los Secrets de Streamlit.")
    st.stop()

genai.configure(api_key=API_KEY)

# --- 4. MAPEO DE ICONOS ---
# Si no encuentra carpeta iconos, usa una ruta por defecto para no romper
if not ICONOS_DIR: ICONOS_DIR = os.path.join(BASE_DIR, "Public", "Iconos")

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

# --- 5. FUNCIONES DE LECTURA (PDF/WORD) ---

def extract_text_from_pdf(file):
    """Extrae texto de PDF"""
    try:
        reader = PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        st.error(f"Error leyendo PDF: {e}")
        return None

def extract_text_from_docx(file):
    """Extrae texto de Word"""
    try:
        doc = Document(file)
        text = "\n".join([p.text for p in doc.paragraphs])
        for table in doc.tables:
            for row in table.rows:
                text += " | ".join([cell.text for cell in row.cells]) + "\n"
        return text
    except Exception as e:
        st.error(f"Error leyendo Word: {e}")
        return None

def analyze_content(content, content_type="image"):
    """
    Analiza Imagen o Texto usando el modelo seleccionado
    """
    # Usamos la variable MODELO_A_USAR definida arriba
    model = genai.GenerativeModel(MODELO_A_USAR)
    
    base_prompt = """
    Analiza este menú. 
    1. Extrae Nombre Restaurante.
    2. Extrae Categorías, Platos y PRECIOS.
    3. DETECTA ALÉRGENOS (gluten, lacteos, crustaceos, etc.) según ingredientes.
    
    Salida JSON (sin markdown):
    {
        "restaurant_name": "Nombre",
        "categories": [
            {
                "name": "Categoría",
                "dishes": [
                    {
                        "name": "Plato",
                        "description": "Ingredientes",
                        "price": "10.00",
                        "allergens": ["gluten", "lacteos"] 
                    }
                ]
            }
        ]
    }
    """
    
    try:
        with st.spinner(f"🤖 Analizando con {MODELO_A_USAR}..."):
            if content_type == "image":
                response = model.generate_content([base_prompt, content])
            else:
                # Para texto (PDF/Word)
                response = model.generate_content(base_prompt + "\n\nMENÚ:\n" + content)
                
            text = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(text)
    except Exception as e:
        st.error(f"Error en la IA ({MODELO_A_USAR}): {e}")
        return None

def create_word(data):
    """Genera el Word Final"""
    if not PLANTILLA_PATH or not os.path.exists(PLANTILLA_PATH):
        st.error("❌ No encuentro la plantilla (plantilla_menu.docx) en Public/Plantilla")
        st.stop()
        
    doc = Document(PLANTILLA_PATH)

    # Título
    try:
        doc.add_heading(data.get("restaurant_name", "MENÚ"), 0)
    except:
        doc.add_paragraph(data.get("restaurant_name", "MENÚ")).bold = True

    # Platos
    for category in data.get("categories", []):
        doc.add_heading(category["name"], level=1)
        for dish in category["dishes"]:
            p = doc.add_paragraph()
            p.add_run(dish['name']).bold = True
            if dish.get('description'):
                p.add_run(f"\n{dish['description']}")
            
            # Precio + Iconos
            p_price = doc.add_paragraph()
            p_price.add_run(f"{dish['price']}€  ")
            
            for allergen in dish.get("allergens", []):
                key = allergen.lower().strip()
                if "frutos secos" in key: key = "frutos de cascara"
                
                if key in ICON_MAP:
                    icon_path = ICON_MAP[key]
                    if os.path.exists(icon_path):
                        try:
                            run = p_price.add_run()
                            run.add_picture(icon_path, width=Cm(0.5))
                            p_price.add_run("  ") 
                        except: pass

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# --- 6. INTERFAZ ---
st.title(f"Generador de Cartas ({MODELO_A_USAR}) 🚀")

uploaded_file = st.file_uploader("Sube menú (Foto, PDF o Word)", type=["jpg", "png", "jpeg", "pdf", "docx"])

if uploaded_file is not None:
    file_type = uploaded_file.name.split('.')[-1].lower()
    data = None
    
    if file_type in ['jpg', 'png', 'jpeg']:
        image = Image.open(uploaded_file)
        st.image(image, width=300)
        data = analyze_content(image, "image")
        
    elif file_type == 'pdf':
        text = extract_text_from_pdf(uploaded_file)
        if text: data = analyze_content(text, "text")
            
    elif file_type == 'docx':
        text = extract_text_from_docx(uploaded_file)
        if text: data = analyze_content(text, "text")

    if data:
        st.success("¡Análisis completado!")
        with st.expander("Ver datos detectados"):
            st.write(data)
        
        docx = create_word(data)
        st.download_button("📥 DESCARGAR CARTA", docx, "Carta_Alergenos.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
