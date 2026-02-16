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
# ¡PON TU API KEY AQUÍ!
GOOGLE_API_KEY = "AIzaSyA0l07ASmsiBa-g3c7D9wNxZLnEUJ9Bfds"
genai.configure(api_key=GOOGLE_API_KEY)

# Mapeo de iconos (Asegúrate de tener la carpeta 'icons' con estas imágenes)
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
    """Lee la carta y fuerza a la IA a organizar los platos en LAS 4 CATEGORÍAS de la plantilla."""
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    # Este prompt es la clave: obliga a la IA a reordenar el menú original
    prompt = """
    Analiza esta imagen de menú. Extrae los platos y precios.
    TU MISIÓN PRINCIPAL es clasificar cada plato en una de estas 4 categorías EXACTAS:
    1. ENTRANTES (Incluye ensaladas, picoteo, tablas, raciones)
    2. CARNES (Incluye hamburguesas, pollo, chuleton, sartenes con carne)
    3. PESCADOS (Incluye bacalao, sepia, calamares)
    4. POSTRES
    
    Devuelve SOLO un objeto JSON válido con esta estructura exacta, sin texto extra:
    {
        "ENTRANTES": [ {"nombre": "Plato", "precio": "00.00", "ingredientes": "ingr1, ingr2"} ],
        "CARNES": [ {"nombre": "Plato", "precio": "00.00", "ingredientes": "ingr1, ingr2"} ],
        "PESCADOS": [ {"nombre": "Plato", "precio": "00.00", "ingredientes": "ingr1, ingr2"} ],
        "POSTRES": [ {"nombre": "Plato", "precio": "00.00", "ingredientes": "ingr1, ingr2"} ]
    }
    """
    try:
        response = model.generate_content([prompt, imagen])
        # Limpiamos por si la IA mete ```json al principio
        texto_limpio = response.text.replace("```json", "").replace("```", "")
        return json.loads(texto_limpio)
    except Exception as e:
        st.error(f"Error leyendo la IA: {e}")
        return None

# --- 3. GENERADOR DE PDF ---
def crear_capa_pdf(datos_clasificados, nombre_restaurante):
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    
    # --- COORDENADAS DE TU PLANTILLA (Ajustadas a ojo para A4) ---
    # Si ves que el texto sale muy arriba o abajo, cambia el valor 'y_inicio'
    COORDENADAS = {
        "HEADER": {"x": 300, "y": 800}, # Donde va el nombre del Restaurante
        "ENTRANTES": {"x": 50, "y_inicio": 730}, # Debajo del título Entrantes
        "CARNES":    {"x": 50, "y_inicio": 560}, # Debajo del título Carnes
        "PESCADOS":  {"x": 50, "y_inicio": 390}, # Debajo del título Pescados
        "POSTRES":   {"x": 50, "y_inicio": 230}  # Debajo del título Postres
    }
    
    # 1. Escribir Nombre del Restaurante (Editable)
    can.setFont("Helvetica-Bold", 18)
    can.drawCentredString(COORDENADAS["HEADER"]["x"], COORDENADAS["HEADER"]["y"], nombre_restaurante)
    # Hacemos que sea editable
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
        if categoria not in COORDINADAS: continue
        
        y_actual = COORDINADAS[categoria]["y_inicio"]
        x_nombre = COORDINADAS[categoria]["x"]
        
        for i, plato in enumerate(platos):
            # Limitar a 6-7 platos por sección para que no se monten
            if i > 7: break 
            
            nombre = plato.get("nombre", "")
            precio = str(plato.get("precio", "")).replace("€","")
            ingredientes = plato.get("ingredientes", "").lower()
            
            # --- NOMBRE DEL PLATO (Editable) ---
            can.setFont("Helvetica", 10)
            form.textfield(
                name=f"{categoria}_{i}_nombre",
                x=x_nombre, y=y_actual-2, width=300, height=14,
                fontSize=10, value=nombre,
                borderStyle='inset', borderColor=transparent, fillColor=transparent
            )
            
            # --- PRECIO (Editable) ---
            form.textfield(
                name=f"{categoria}_{i}_precio",
                x=x_precio_base, y=y_actual-2, width=40, height=14,
                fontSize=10, value=f"{precio}€",
                borderStyle='inset', borderColor=transparent, fillColor=transparent
            )
            
            # --- ICONOS ALÉRGENOS (Automático) ---
            x_icono = x_iconos_base
            for clave, ruta in ALERGENOS_MAP.items():
                if clave in ingredientes:
                    try:
                        can.drawImage(ruta, x_icono, y_actual-4, width=12, height=12, mask='auto')
                        x_icono += 15
                    except:
                        pass # Si falta el icono no pasa nada
            
            y_actual -= 20 # Espacio entre platos
            
    can.save()
    packet.seek(0)
    return packet

# --- 4. INTERFAZ WEB (STREAMLIT) ---
st.set_page_config(page_title="Gestor de Cartas IA", layout="wide")
st.title("👨‍🍳 Editor de Cartas Inteligente")

# Carga de plantilla automática
if not os.path.exists("Antony PLANTILLA BASE SIN ALERGENOS.pdf"):
    st.error("⚠️ No encuentro el archivo 'Antony PLANTILLA BASE SIN ALERGENOS.pdf'. Súbelo a la carpeta.")
    st.stop()

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Digitalizar Carta")
    imagen_subida = st.file_uploader("Sube la foto del menú (JPG/PNG)", type=["jpg", "png", "jpeg"])
    
    if "datos_menu" not in st.session_state:
        st.session_state["datos_menu"] = None

    if imagen_subida and st.button("✨ Leer y Clasificar con IA"):
        with st.spinner("Leyendo y organizando platos..."):
            img = PIL.Image.open(imagen_subida)
            datos = leer_y_clasificar_imagen(img)
            if datos:
                st.session_state["datos_menu"] = datos
                st.success("¡Carta clasificada correctamente!")

with col2:
    st.subheader("2. Personalización")
    nombre_rest = st.text_input("Nombre del Restaurante (Editable en PDF)", "LA CERVECERA LOS PINOS")
    
    # Editor visual básico (JSON)
    if st.session_state["datos_menu"]:
        st.write("Edita los datos aquí si la IA se equivocó:")
        datos_editados = st.data_editor(st.session_state["datos_menu"])
        
        if st.button("🖨️ Generar PDF Final"):
            try:
                # Crear capa de texto
                capa = crear_capa_pdf(datos_editados, nombre_rest)
                
                # Fusionar con tu plantilla
                plantilla = PdfReader("Antony PLANTILLA BASE SIN ALERGENOS.pdf")
                pagina = plantilla.pages[0] # Usamos la primera página
                
                capa_reader = PdfReader(capa)
                pagina.merge_page(capa_reader.pages[0])
                
                writer = PdfWriter()
                writer.add_page(pagina)
                
                output = io.BytesIO()
                writer.write(output)
                
                st.success("PDF Generado. Los campos 'Plato' y 'Precio' son editables.")
                st.download_button(
                    label="Descargar Carta Lista (.pdf)",
                    data=output.getvalue(),
                    file_name="Carta_Clasificada.pdf",
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"Error generando PDF: {e}")
