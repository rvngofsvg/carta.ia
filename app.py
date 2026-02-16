import streamlit as st
import google.generativeai as genai
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import transparent, black, HexColor
from pypdf import PdfReader, PdfWriter
import io
import PIL.Image
import json
import os

# --- 1. TU CONFIGURACIÓN (NO TOCAR) ---
GOOGLE_API_KEY = "AIzaSyA0l07ASmsiBa-g3c7D9wNxZLnEUJ9Bfds"
genai.configure(api_key=GOOGLE_API_KEY)
MODELO_IA = 'gemini-2.5-flash'

# --- 2. ICONOS (Busca en la misma carpeta) ---
ALERGENOS_MAP = {
    "gluten": "gluten.png", "trigo": "gluten.png", "harina": "gluten.png", "pan": "gluten.png",
    "lácteos": "lacteos.png", "queso": "lacteos.png", "leche": "lacteos.png", "nata": "lacteos.png",
    "huevo": "huevo.png", "mayonesa": "huevo.png",
    "frutos secos": "frutos_secos.png", "nueces": "frutos_secos.png",
    "pescado": "pescado.png", "bacalao": "pescado.png", "atún": "pescado.png",
    "gambas": "gambas.png", "crustáceos": "gambas.png",
    "soja": "soja.png",
    "mostaza": "mostaza.png"
}

def leer_y_clasificar_imagen(imagen):
    model = genai.GenerativeModel(MODELO_IA)
    
    prompt = """
    Analiza la carta. Extrae platos y PRECIOS.
    Clasifica OBLIGATORIAMENTE en: ENTRANTES, CARNES, PESCADOS, POSTRES.
    Si una sección no tiene platos, déjala vacía.
    
    Responde SOLO JSON válido:
    {
        "ENTRANTES": [ {"nombre": "X", "precio": "10.00", "ingredientes": "pan"} ],
        "CARNES": [], 
        "PESCADOS": [], 
        "POSTRES": []
    }
    """
    try:
        response = model.generate_content([prompt, imagen])
        texto = response.text.replace("```json", "").replace("```", "").strip()
        
        # Corrección de seguridad para JSON
        inicio = texto.find("{")
        fin = texto.rfind("}") + 1
        if inicio != -1 and fin != -1:
            texto = texto[inicio:fin]
            
        datos = json.loads(texto)
        
        # TRUCO: Convertir todas las claves a MAYÚSCULAS para evitar errores
        datos_normalizados = {}
        for k, v in datos.items():
            datos_normalizados[k.upper()] = v
        return datos_normalizados

    except Exception as e:
        st.error(f"Error IA: {e}")
        return None

def crear_pdf_directo(datos, nombre_restaurante):
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    form = can.acroForm
    
    # --- CONFIGURACIÓN VISUAL ---
    cursor_y = 750  # Empezamos bien arriba
    margen_izq = 50
    x_precio = 450
    x_iconos = 490
    alto_linea = 20    
    alto_titulo = 40   
    
    # 1. HEADER (Nombre Restaurante)
    can.setFont("Helvetica-Bold", 22)
    can.setFillColor(black)
    can.drawCentredString(297.5, 800, nombre_restaurante)
    
    # Campo invisible editable para el título
    form.textfield(
        name="Header", x=50, y=790, width=500, height=30, 
        value=nombre_restaurante, borderStyle='solid', borderColor=transparent, textColor=transparent
    )

    # Orden estricto de secciones
    orden = ["ENTRANTES", "CARNES", "PESCADOS", "POSTRES"]
    
    hay_contenido = False # Chivato para saber si se escribió algo

    for seccion in orden:
        # Recuperamos los platos (asegurando mayúsculas)
        platos = datos.get(seccion, [])
        
        # --- SIEMPRE IMPRIMIMOS EL TÍTULO DE LA SECCIÓN ---
        # (Aunque esté vacía, así vemos que el PDF funciona)
        if cursor_y < 100: 
            can.showPage() # Nueva página si se acaba el espacio
            cursor_y = 800
            
        can.setStrokeColor(HexColor("#333333"))
        can.line(margen_izq, cursor_y - 5, 500, cursor_y - 5)
        
        can.setFont("Helvetica-Bold", 14)
        can.setFillColor(HexColor("#2C3E50"))
        can.drawString(margen_izq, cursor_y, seccion)
        
        cursor_y -= alto_titulo
        
        if not platos:
            # Si no hay platos, dejamos un hueco pequeño y seguimos
            cursor_y += 10 
            continue

        hay_contenido = True
        
        # --- IMPRIMIR PLATOS ---
        for i, plato in enumerate(platos):
            if cursor_y < 50: 
                can.showPage()
                cursor_y = 800
            
            nombre = plato.get("nombre", "Plato sin nombre")
            precio = str(plato.get("precio", "")).replace("€","").strip()
            ingredientes = plato.get("ingredientes", "").lower()
            
            # Texto visible (Tinta)
            can.setFont("Helvetica", 10)
            can.setFillColor(black)
            can.drawString(margen_izq, cursor_y, nombre)
            
            can.setFont("Helvetica-Bold", 10)
            can.drawString(x_precio, cursor_y, f"{precio}€")
            
            # Campos Editables Invisibles (Superpuestos)
            form.textfield(
                name=f"{seccion}_{i}_nm",
                x=margen_izq, y=cursor_y-2, width=330, height=14,
                value=nombre, borderStyle='solid', borderColor=transparent, textColor=transparent
            )
            form.textfield(
                name=f"{seccion}_{i}_pr",
                x=x_precio, y=cursor_y-2, width=40, height=14,
                value=f"{precio}€", borderStyle='solid', borderColor=transparent, textColor=transparent
            )
            
            # Iconos
            curr_x = x_iconos
            iconos_usados = set()
            for k, v in ALERGENOS_MAP.items():
                if k in ingredientes: iconos_usados.add(v)
            
            for icono in iconos_usados:
                if os.path.exists(icono):
                    try:
                        can.drawImage(icono, curr_x, y=cursor_y-2, width=12, height=12, mask='auto')
                        curr_x += 14
                    except: pass
            
            cursor_y -= alto_linea 
            
        cursor_y -= 15 

    if not hay_contenido:
        # Mensaje de socorro en el PDF si la IA falló
        can.setFont("Helvetica", 12)
        can.setFillColor(red)
        can.drawString(100, 400, "LA IA NO DETECTÓ PLATOS EN LA IMAGEN.")
        can.drawString(100, 380, "Prueba con una foto más clara.")

    can.save()
    packet.seek(0)
    return packet

# --- INTERFAZ SIMPLE (SIN TABLAS) ---
st.set_page_config(page_title="Generador Directo")
st.title("Generador de Cartas (Modo Directo)")

plantilla = "Antony PLANTILLA BASE SIN ALERGENOS.pdf"

if not os.path.exists(plantilla):
    st.error(f"⚠️ FALTA LA PLANTILLA: {plantilla}")
    st.stop()

# Entrada
col1, col2 = st.columns(2)
with col1:
    img_file = st.file_uploader("1. Sube la foto", type=["jpg", "png", "jpeg"])
    nombre_rest = st.text_input("Nombre del Restaurante", "LA CERVECERA LOS PINOS")

with col2:
    st.write("2. Generar")
    if img_file and st.button("🚀 PROCESAR Y DESCARGAR"):
        with st.spinner("Leyendo imagen y generando PDF..."):
            
            # 1. Leer IA
            img = PIL.Image.open(img_file)
            datos = leer_y_clasificar_imagen(img)
            
            if datos:
                # 2. Crear PDF Directamente
                try:
                    capa = crear_pdf_directo(datos, nombre_rest)
                    
                    base = PdfReader(plantilla)
                    page = base.pages[0]
                    page.merge_page(PdfReader(capa).pages[0])
                    
                    writer = PdfWriter()
                    writer.add_page(page)
                    
                    out = io.BytesIO()
                    writer.write(out)
                    
                    st.success("✅ ¡PDF LISTO!")
                    st.download_button(
                        label="⬇️ DESCARGAR CARTA AHORA",
                        data=out.getvalue(),
                        file_name="Carta_Generada.pdf",
                        mime="application/pdf"
                    )
                except Exception as e:
                    st.error(f"Error técnico creando PDF: {e}")
            else:
                st.error("La IA no pudo leer la imagen. Intenta con otra.")
