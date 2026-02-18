import streamlit as st
import google.generativeai as genai
import os
import json
from docx import Document
from docx.shared import Cm
from io import BytesIO
from PIL import Image

# --- 1. RUTAS EXACTAS (Confirmadas por el modo detective) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# RUTA 1: La plantilla (Corregido: plantilla_menu.docx en minúsculas)
PLANTILLA_PATH = os.path.join(BASE_DIR, "Public", "Plantilla", "plantilla_menu.docx")

# RUTA 2: Los iconos (Asumimos Public/Iconos con mayúsculas iniciales)
ICONOS_DIR = os.path.join(BASE_DIR, "Public", "Iconos")

# --- 2. CONFIGURACIÓN API KEY ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    # Fallback para local
    API_KEY = os.getenv("GEMINI_API_KEY", "")

if not API_KEY:
    st.error("❌ Falta la API Key. Configúrala en los Secrets de Streamlit.")
    st.stop()

genai.configure(api_key=API_KEY)

# --- 3. MAPEO DE ICONOS ---
def get_icon_path(icon_name):
    return os.path.join(ICONOS_DIR, icon_name)

# Diccionario de archivos (asegúrate de que los .png se llamen así en la carpeta)
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

# --- 4. FUNCIONES ---

def analyze_image(image):
    """Analiza el menú con Gemini 1.5 Flash"""
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = """
    Analiza esta imagen de menú.
    1. Extrae Nombre del Restaurante.
    2. Extrae Categorías y Platos con PRECIO.
    3. DETECTA ALÉRGENOS basándote en ingredientes (ej: queso=lacteos, pan=gluten, gambas=crustaceos).
    
    Responde SOLO con este JSON (sin markdown):
    {
        "restaurant_name": "Nombre",
        "categories": [
            {
                "name": "Entrantes",
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
        with st.spinner("🧠 Analizando menú e identificando alérgenos..."):
            response = model.generate_content([prompt, image])
            text = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(text)
    except Exception as e:
        st.error(f"Error en la IA: {e}")
        return None

def create_word(data):
    """Genera el Word final"""
    
    # Verificación final de seguridad
    if not os.path.exists(PLANTILLA_PATH):
        st.error(f"❌ ERROR: Sigue sin encontrar la plantilla en: {PLANTILLA_PATH}")
        st.stop()
        
    doc = Document(PLANTILLA_PATH)

    # Título
    try:
        doc.add_heading(data.get("restaurant_name", "MENÚ"), 0)
    except:
        doc.add_paragraph(data.get("restaurant_name", "MENÚ")).bold = True

    # Iterar categorías y platos
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
            
            # Insertar iconos
            for allergen in dish.get("allergens", []):
                key = allergen.lower().strip()
                if "frutos secos" in key: key = "frutos de cascara"
                
                if key in ICON_MAP:
                    icon_path = ICON_MAP[key]
                    if os.path.exists(icon_path):
                        try:
                            # Imagen pequeña 0.5cm
                            run = p_price.add_run()
                            run.add_picture(icon_path, width=Cm(0.5))
                            p_price.add_run("  ") 
                        except:
                            pass # Si falla una imagen, que siga con la siguiente
                    else:
                        print(f"Falta icono: {icon_path}")

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# --- 5. INTERFAZ ---
st.title("Generador de Cartas de Alérgenos ✅")

uploaded_file = st.file_uploader("Sube la foto del menú", type=["jpg", "png", "jpeg"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="Menú subido", width=300)
    
    if st.button("GENERAR WORD"):
        data = analyze_image(image)
        
        if data:
            st.success("¡Análisis completado!")
            # Mostrar datos para verificar
            with st.expander("Ver qué ha detectado la IA"):
                st.write(data)
            
            docx = create_word(data)
            
            st.download_button(
                label="📥 DESCARGAR CARTA LISTA",
                data=docx,
                file_name="Carta_Alergenos.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            
