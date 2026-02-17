import streamlit as st
import google.generativeai as genai
import os
import json
from docx import Document
from docx.shared import Cm
from io import BytesIO
from PIL import Image

# --- CONFIGURACIÓN ---
# AQUÍ PEGA TU API KEY SI NO USAS VARIABLES DE ENTORNO (CUIDADO: NO COMPARTIR)
API_KEY = "TU_API_KEY_AQUI" 

# Configurar Gemini
genai.configure(api_key=API_KEY)

# Mapeo EXACTO de tus iconos (según tu foto)
ICON_MAP = {
    "gluten": "public/iconos/gluten.png",
    "crustaceos": "public/iconos/gambas.png",
    "huevos": "public/iconos/huevo.png",
    "pescado": "public/iconos/pescado.png",
    "cacahuetes": "public/iconos/cacahuetes.png",
    "soja": "public/iconos/soja.png",
    "lacteos": "public/iconos/lacteos.png",
    "frutos de cascara": "public/iconos/frutos_secos.png",
    "apio": "public/iconos/apio.png",
    "mostaza": "public/iconos/mostaza.png",
    "sesamo": "public/iconos/sesamo.png",
    "sulfitos": "public/iconos/sulfitos.png",
    "altramuces": "public/iconos/altramuces.png",
    "moluscos": "public/iconos/moluscos.png"
}

def analyze_image(image):
    """Envía la imagen a Gemini y pide un JSON estructurado"""
    model = genai.GenerativeModel('gemini-1.5-flash') # Usamos Flash por rapidez
    
    prompt = """
    Analiza esta imagen del menú. Extrae los datos en formato JSON puro.
    Estructura requerida:
    {
        "restaurant_name": "Nombre del sitio",
        "categories": [
            {
                "name": "Entrantes",
                "dishes": [
                    {
                        "name": "Nombre plato",
                        "description": "Descripción ingredientes",
                        "price": "10.50",
                        "allergens": ["gluten", "lacteos"] 
                    }
                ]
            }
        ]
    }
    IMPORTANTE:
    1. Mira los ingredientes y DEDUCE los alérgenos probables si no están escritos.
    2. Los alérgenos permitidos son: gluten, crustaceos, huevos, pescado, cacahuetes, soja, lacteos, frutos de cascara, apio, mostaza, sesamo, sulfitos, altramuces, moluscos.
    3. Responde SOLO con el JSON, sin markdown.
    """
    
    try:
        response = model.generate_content([prompt, image])
        # Limpiar respuesta por si pone ```json
        text = response.text.replace('```json', '').replace('```', '')
        return json.loads(text)
    except Exception as e:
        st.error(f"Error al analizar la imagen: {e}")
        return None

def create_word(data):
    """Genera el Word usando la plantilla y poniendo iconos"""
    plantilla_path = "public/plantilla/plantilla_menu.docx"
    
    try:
        doc = Document(plantilla_path)
    except:
        st.error("No se encontró 'public/plantilla/plantilla_menu.docx'. Usando documento en blanco.")
        doc = Document()

    # 1. Título del Bar
    doc.add_heading(data.get("restaurant_name", "Menú"), 0)

    # 2. Recorrer categorías
    for category in data.get("categories", []):
        doc.add_heading(category["name"], level=1)
        
        # 3. Recorrer platos
        for dish in category["dishes"]:
            p = doc.add_paragraph()
            runner = p.add_run(f"{dish['name']} ")
            runner.bold = True
            
            p.add_run(f"\n{dish['description']}")
            
            # 4. Precio e Iconos
            p_price = doc.add_paragraph()
            p_price.add_run(f"{dish['price']}€  ")
            
            # Insertar iconos
            for allergen in dish.get("allergens", []):
                allergen_key = allergen.lower().strip()
                if allergen_key in ICON_MAP:
                    icon_path = ICON_MAP[allergen_key]
                    try:
                        # Insertar imagen pequeña (0.5 cm)
                        p_price.add_run().add_picture(icon_path, width=Cm(0.5))
                        p_price.add_run("  ") # Espacio entre iconos
                    except FileNotFoundError:
                        print(f"Falta icono: {icon_path}")

    # Guardar en memoria
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# --- INTERFAZ STREAMLIT ---
st.title("Generador de Carta de Alérgenos 🍤")

uploaded_file = st.file_uploader("Sube la foto del menú", type=["jpg", "png", "jpeg"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="Menú subido", use_column_width=True)
    
    if st.button("Generar Word con Alérgenos"):
        with st.spinner("Gemini está leyendo el menú y detectando alérgenos..."):
            menu_data = analyze_image(image)
            
            if menu_data:
                st.success("¡Análisis completado!")
                # Generar Word
                docx_file = create_word(menu_data)
                
                # Botón de descarga
                st.download_button(
                    label="📥 Descargar Carta (.docx)",
                    data=docx_file,
                    file_name="carta_alergenos.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
