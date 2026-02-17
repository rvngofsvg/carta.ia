import streamlit as st
import google.generativeai as genai
import os
import json
from docx import Document
from docx.shared import Cm
from io import BytesIO
from PIL import Image

# --- 1. CONFIGURACIÓN DE RUTAS EXACTAS (Respetando Mayúsculas) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Rutas corregidas según tu indicación: Public/Plantilla y Public/Iconos
PLANTILLA_PATH = os.path.join(BASE_DIR, "Public", "Plantilla", "Plantilla_menu.docx")
ICONOS_DIR = os.path.join(BASE_DIR, "Public", "Iconos")

# --- 2. CONFIGURACIÓN API KEY ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyAXjWqTko_sdWsGD-amErjoOyxbS82iReI")

genai.configure(api_key=API_KEY)

# --- 3. MAPEO DE ICONOS ---
def get_icon_path(icon_name):
    # Busca el archivo dentro de Public/Iconos
    return os.path.join(ICONOS_DIR, icon_name)

# Asegúrate de que los nombres de archivo .png sean correctos (minúsculas o mayúsculas tal cual los tengas)
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
    """Envía la imagen a Gemini (Modelo Flash)"""
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = """
    Analiza este menú de restaurante.
    Tu tarea es:
    1. Extraer el nombre del restaurante y los platos con sus precios.
    2. DETECTAR ALÉRGENOS en cada plato basándote en sus ingredientes (ej: queso=lacteos, gambas=crustaceos).
    
    Salida OBLIGATORIA en JSON puro (sin markdown):
    {
        "restaurant_name": "Nombre Restaurante",
        "categories": [
            {
                "name": "Entrantes",
                "dishes": [
                    {
                        "name": "Nombre Plato",
                        "description": "Ingredientes...",
                        "price": "10.00",
                        "allergens": ["gluten", "lacteos"] 
                    }
                ]
            }
        ]
    }
    """
    
    try:
        with st.spinner("Analizando menú con IA..."):
            response = model.generate_content([prompt, image])
            text = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(text)
    except Exception as e:
        st.error(f"Error analizando la imagen: {e}")
        return None

def create_word(data):
    """Genera el Word"""
    
    # Verificación de seguridad para la plantilla
    if not os.path.exists(PLANTILLA_PATH):
        st.error(f"⚠️ ERROR: No se encuentra la plantilla en: {PLANTILLA_PATH}")
        st.stop() # Detiene la ejecución si no hay plantilla
    
    doc = Document(PLANTILLA_PATH)

    # Título (intenta ponerlo bonito)
    restaurant_name = data.get("restaurant_name", "MENÚ")
    try:
        doc.add_heading(restaurant_name, 0)
    except:
        doc.add_paragraph(restaurant_name).bold = True

    # Recorrer datos
    for category in data.get("categories", []):
        doc.add_heading(category["name"], level=1)
        
        for dish in category["dishes"]:
            p = doc.add_paragraph()
            p.add_run(dish['name']).bold = True
            if dish.get('description'):
                p.add_run(f"\n{dish['description']}")
            
            # Línea de Precio + Iconos
            p_price = doc.add_paragraph()
            p_price.add_run(f"{dish['price']}€  ")
            
            # Insertar iconos
            for allergen in dish.get("allergens", []):
                # Normalizar clave (quitar espacios extra)
                key = allergen.lower().strip()
                if "frutos secos" in key: key = "frutos de cascara" # Corrección común
                
                if key in ICON_MAP:
                    icon_file = ICON_MAP[key]
                    if os.path.exists(icon_file):
                        try:
                            # Insertar imagen 0.5cm
                            run = p_price.add_run()
                            run.add_picture(icon_file, width=Cm(0.5))
                            p_price.add_run("  ") 
                        except Exception as e:
                            print(f"Error insertando imagen: {e}")
                    else:
                        print(f"Falta el archivo: {icon_file}")

    # Guardar en memoria
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# --- 5. INTERFAZ WEB ---
st.title("Generador de Cartas (Corregido)")

uploaded_file = st.file_uploader("Sube tu menú (Foto)", type=["jpg", "png", "jpeg"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="Imagen cargada", width=300)
    
    if st.button("GENERAR CARTA"):
        data = analyze_image(image)
        
        if data:
            # Muestra los datos para verificar qué detectó la IA
            with st.expander("Ver qué alérgenos detectó la IA"):
                st.write(data)
            
            docx = create_word(data)
            
            st.success("¡Carta generada!")
            st.download_button(
                label="DESCARGAR WORD",
                data=docx,
                file_name="Carta_Alergenos.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
