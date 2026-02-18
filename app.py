import streamlit as st
import google.generativeai as genai
import os
import json
from docx import Document
from docx.shared import Cm, Pt
from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER # Importante para los puntos .....
from io import BytesIO
from PIL import Image
from pypdf import PdfReader

# --- 1. CONFIGURACIÓN DEL MODELO ---
# Puedes cambiar a "gemini-1.5-flash" si la 2.0 te da problemas
MODELO_A_USAR = "gemini-2.5-flash"

# --- 2. RUTAS INTELIGENTES (Mayúsculas/Minúsculas) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def find_path_insensitive(base, components):
    """Busca una ruta ignorando si es mayúscula o minúscula"""
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

# Buscamos las carpetas automáticamente
PLANTILLA_PATH = find_path_insensitive(BASE_DIR, ["public", "plantilla", "plantilla_menu.docx"])
ICONOS_DIR = find_path_insensitive(BASE_DIR, ["public", "iconos"])

# --- 3. API KEY (SECRETS) ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = os.getenv("GEMINI_API_KEY", "")

if not API_KEY:
    st.error("❌ ERROR CRÍTICO: Falta la API Key en los Secrets de Streamlit.")
    st.stop()

genai.configure(api_key=API_KEY)

# --- 4. MAPEO DE ICONOS ---
# Si no encuentra la carpeta, usa una ruta por defecto para no romper
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

# --- 5. FUNCIONES DE LECTURA (TEXTO) ---

def extract_text_from_pdf(file):
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

# --- 6. ANÁLISIS CON IA (GEMINI) ---

def analyze_content(content, content_type="image"):
    model = genai.GenerativeModel(MODELO_A_USAR)
    
    base_prompt = """
    Analiza este menú de restaurante.
    
    TAREAS:
    1. Extrae el Nombre del Restaurante.
    2. Extrae las Categorías (Entrantes, Principales...) y sus Platos.
    3. Extrae el PRECIO exacto de cada plato.
    4. DETECTA ALÉRGENOS basándote en los ingredientes (ej: queso=lacteos, pan=gluten).
    
    FORMATO DE SALIDA (JSON PURO):
    {
        "restaurant_name": "Nombre del Sitio",
        "categories": [
            {
                "name": "Nombre Categoría",
                "dishes": [
                    {
                        "name": "Nombre del Plato",
                        "description": "Descripción corta de ingredientes",
                        "price": "12.50",
                        "allergens": ["gluten", "lacteos"] 
                    }
                ]
            }
        ]
    }
    """
    
    try:
        with st.spinner(f"🧠 Analizando con {MODELO_A_USAR}..."):
            if content_type == "image":
                response = model.generate_content([base_prompt, content])
            else:
                response = model.generate_content(base_prompt + "\n\nMENÚ:\n" + content)
                
            text = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(text)
    except Exception as e:
        st.error(f"Error en la IA: {e}")
        return None

# --- 7. GENERACIÓN DEL WORD (CON PUNTOS SUSPENSIVOS) ---

def create_word(data):
    if not PLANTILLA_PATH or not os.path.exists(PLANTILLA_PATH):
        st.error(f"❌ No encuentro la plantilla en: {PLANTILLA_PATH}")
        st.stop()
        
    doc = Document(PLANTILLA_PATH)

    # Título
    try:
        doc.add_heading(data.get("restaurant_name", "MENÚ"), 0)
    except:
        doc.add_paragraph(data.get("restaurant_name", "MENÚ")).bold = True

    # Iterar categorías
    for category in data.get("categories", []):
        doc.add_heading(category["name"], level=1)
        
        for dish in category["dishes"]:
            # --- LÍNEA PRINCIPAL: Plato ............ Precio [Iconos] ---
            p = doc.add_paragraph()
            
            # 1. Configurar tabulador derecho con relleno de puntos
            # Cm(16) es el ancho estándar para llegar al final de la línea en A4
            tab_stops = p.paragraph_format.tab_stops
            tab_stops.add_tab_stop(Cm(16), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            
            # 2. Nombre del plato (Negrita)
            run_name = p.add_run(dish['name'])
            run_name.bold = True
            
            # 3. Salto con puntos + Precio
            p.add_run(f"\t{dish['price']}€  ")
            
            # 4. Iconos (Al lado del precio)
            for allergen in dish.get("allergens", []):
                key = allergen.lower().strip()
                if "frutos secos" in key: key = "frutos de cascara"
                
                if key in ICON_MAP:
                    icon_path = ICON_MAP[key]
                    if os.path.exists(icon_path):
                        try:
                            run = p.add_run()
                            run.add_picture(icon_path, width=Cm(0.5))
                            p.add_run(" ") 
                        except: pass
            
            # --- LÍNEA DESCRIPCIÓN (Debajo) ---
            if dish.get('description'):
                p_desc = doc.add_paragraph()
                p_desc.add_run(dish['description']).italic = True
                # Reducir espacio entre plato y descripción
                p.paragraph_format.space_after = Pt(2) 

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# --- 8. INTERFAZ FINAL ---
st.title(f"Generador de Cartas Inteligente 🍤")
st.markdown("Sube tu menú en **Foto, PDF o Word** y descarga la carta lista con iconos.")

uploaded_file = st.file_uploader("Sube el archivo aquí", type=["jpg", "png", "jpeg", "pdf", "docx"])

if uploaded_file is not None:
    file_type = uploaded_file.name.split('.')[-1].lower()
    st.info(f"Archivo detectado: {file_type.upper()}")
    
    if st.button("GENERAR CARTA AHORA"):
        data = None
        
        # Lógica de lectura
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

        # Generar resultado
        if data:
            st.success("✅ ¡Análisis completado!")
            with st.expander("Ver datos detectados (Click aquí)"):
                st.write(data)
            
            docx = create_word(data)
            
            st.download_button(
                label="📥 DESCARGAR CARTA (.docx)",
                data=docx,
                file_name="Carta_Alergenos.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
            
