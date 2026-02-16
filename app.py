import streamlit as st
import google.generativeai as genai
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import transparent, black
from pypdf import PdfReader, PdfWriter
import io
import PIL.Image
import json
import os

# --- 1. CONFIGURACIÓN ---
# ¡Asegúrate de que tu API Key es la correcta!
GOOGLE_API_KEY = "AIzaSyA0l07ASmsiBa-g3c7D9wNxZLnEUJ9Bfds"
genai.configure(api_key=GOOGLE_API_KEY)

# Mapeo de iconos
ALERGENOS_MAP = {
    "gluten": "icons/gluten.png", "trigo": "icons/gluten.png", "pan": "icons/gluten.png",
    "lácteos": "icons/lacteos.png", "queso": "icons/lacteos.png", "leche": "icons/lacteos.png", "nata": "icons/lacteos.png",
    "huevo": "icons/huevo.png", "mayonesa": "icons/huevo.png",
    "frutos secos": "icons/frutos_secos.png", "nueces": "icons/frutos_secos.png",
    "pescado": "icons/pescado.png", "bacalao": "icons/pescado.png", "atún": "icons/pescado.png",
    "crustáceos": "icons/gambas.png", "gambas": "icons/gambas.png"
}

# --- 2. INTELIGENCIA ARTIFICIAL (CLASIFICADOR) ---
def leer_y_clasificar_imagen(imagen):
    model = genai.GenerativeModel('gemini-2.5-flash')
    prompt = """
    Analiza esta imagen de menú. Extrae los platos y precios.
    TU MISIÓN PRINCIPAL es clasificar cada plato en una de estas 4 categorías EXACTAS:
    1. ENTRANTES (Incluye ensaladas, picoteo, tablas, raciones)
    2. CARNES (Incluye hamburguesas, pollo, chuleton, sartenes con carne)
    3. PESCADOS (Incluye bacalao, sepia, calamares)
    4. POSTRES
    
    Devuelve SOLO un objeto JSON válido con esta estructura exacta:
    {
        "ENTRANTES": [ {"nombre": "Plato", "precio": "00.00", "ingredientes": "ingr1"} ],
        "CARNES": [ {"nombre": "Plato", "precio": "00.00", "ingredientes": "ingr1"} ],
        "PESCADOS": [ {"nombre": "Plato", "precio": "00.00", "ingredientes": "ingr1"} ],
        "POSTRES": [ {"nombre": "Plato", "precio": "00.00", "ingredientes": "ingr1"} ]
    }
    """
    try:
        response = model.generate_content([prompt, imagen])
        texto_limpio = response.text.replace("```json", "").replace("```", "")
        return json.loads(texto_limpio)
    except Exception as e:
        st.error(f"Error leyendo la IA: {e}")
        return None

# --- 3. GENERADOR DE PDF ---
def crear_capa_pdf(datos_clasificados, nombre_restaurante):
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    
    # --- COORDENADAS CORREGIDAS ---
    COORDENADAS = {
        "HEADER": {"x": 300, "y": 800}, 
        "ENTRANTES": {"x": 50, "y_inicio": 730}, 
        "CARNES":    {"x": 50, "y_inicio": 560}, 
        "PESCADOS":  {"x": 50, "y_inicio": 390}, 
        "POSTRES":   {"x": 50, "y_inicio": 230}  
    }
    
    # 1. Header (Nombre del Restaurante)
    can.setFont("Helvetica-Bold", 18)
    # Variable HEADER corregida:
    can.drawCentredString(COORDENADAS["HEADER"]["x"], COORDENADAS["HEADER"]["y"], nombre_restaurante)
    
    form = can.acroForm
    form.textfield(
        name="Header_Restaurante",
        tooltip="Nombre del Restaurante",
        x=150, y=COORDENADAS["HEADER"]["y"]-5, width=300, height=25,
        fontSize=18, value=nombre_restaurante,
        borderStyle='underlined', borderColor=transparent, fillColor=transparent,
        textColor=black, forceBorder=False
    )

    # 2. Rellenar las categorías
    x_precio_base = 450
    x_iconos_base = 490
    
    for categoria, platos in datos_clasificados.items():
        # AQUÍ ESTABA EL ERROR: Ahora usamos 'COORDENADAS' (sin la I extra)
        if categoria not in COORDENADAS: continue
        
        y_actual = COORDENADAS[categoria]["y_inicio"]
        x_nombre = COORDENADAS[categoria]["x"]
        
        for i, plato in enumerate(platos):
            if i > 7: break 
            
            nombre = plato.get("nombre", "")
            precio = str(plato.get("precio", "")).replace("€","")
            ingredientes = plato.get("ingredientes", "").lower()
            
            # Nombre del plato
            can.setFont("Helvetica", 10)
            form.textfield(
                name=f"{categoria}_{i}_nombre",
                x=x_nombre, y=y_actual-2, width=300, height=14,
                fontSize=10, value=nombre,
                borderStyle='inset', borderColor=transparent, fillColor=transparent
            )
            
            # Precio
            form.textfield(
                name=f"{categoria}_{i}_precio",
                x=x_precio_base, y=y_actual-2, width=40, height=14,
                fontSize=10, value=f"{precio}€",
                borderStyle='inset', borderColor=transparent, fillColor=transparent
            )
            
            # Iconos
            x_icono = x_iconos_base
            for clave, ruta in ALERGENOS_MAP.items():
                if clave in ingredientes:
                    try:
                        can.drawImage(ruta, x_icono, y_actual-4, width=12, height=12, mask='auto')
                        x_icono += 15
                    except:
                        pass
            
            y_actual -= 20 
            
    can.save()
    packet.seek(0)
    return packet

# --- 4. INTERFAZ WEB ---
st.set_page_config(page_title="Gestor de Cartas IA", layout="wide")
st.title("👨‍🍳 Editor de Cartas Inteligente")

# Verificación de plantilla
nombre_plantilla = "Antony PLANTILLA BASE SIN ALERGENOS.pdf"
if not os.path.exists(nombre_plantilla):
    st.error(f"⚠️ No encuentro el archivo '{nombre_plantilla}'.")
    st.stop()

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Digitalizar Carta")
    imagen_subida = st.file_uploader("Sube la foto del menú", type=["jpg", "png", "jpeg"])
    
    if "datos_menu" not in st.session_state:
        st.session_state["datos_menu"] = None

    if imagen_subida and st.button("✨ Leer y Clasificar"):
        with st.spinner("Leyendo..."):
            img = PIL.Image.open(imagen_subida)
            datos = leer_y_clasificar_imagen(img)
            if datos:
                st.session_state["datos_menu"] = datos
                st.success("¡Clasificado!")

with col2:
    st.subheader("2. Resultado")
    nombre_rest = st.text_input("Restaurante:", "LA CERVECERA LOS PINOS")
    
    if st.session_state["datos_menu"]:
        st.write("Datos extraídos:")
        datos_editados = st.data_editor(st.session_state["datos_menu"])
        
        if st.button("🖨️ Generar PDF"):
            try:
                capa = crear_capa_pdf(datos_editados, nombre_rest)
                
                plantilla = PdfReader(nombre_plantilla)
                pagina = plantilla.pages[0]
                
                capa_reader = PdfReader(capa)
                pagina.merge_page(capa_reader.pages[0])
                
                writer = PdfWriter()
                writer.add_page(pagina)
                
                output = io.BytesIO()
                writer.write(output)
                
                st.success("¡PDF Listo!")
                st.download_button("Descargar PDF", data=output.getvalue(), file_name="Carta_Final.pdf", mime="application/pdf")
            except Exception as e:
                st.error(f"Error: {e}")
