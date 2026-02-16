import streamlit as st
import google.generativeai as genai
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import transparent, black, red, HexColor
from pypdf import PdfReader, PdfWriter
import io
import PIL.Image
import json
import os

# --- 1. CONFIGURACIÓN ---
# Tu API Key se mantiene
GOOGLE_API_KEY = "AIzaSyA0l07ASmsiBa-g3c7D9wNxZLnEUJ9Bfds"
genai.configure(api_key=GOOGLE_API_KEY)

# ✅ TUS REQUISITO 1: MODELO EXACTO QUE PEDISTE
MODELO_IA = 'gemini-2.5-flash'

# --- 2. ICONOS ---
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
    # Usamos el modelo específico que pediste
    model = genai.GenerativeModel(MODELO_IA)
    
    prompt = """
    Analiza la carta. Extrae platos y PRECIOS (solo números).
    Clasifica OBLIGATORIAMENTE en: ENTRANTES, CARNES, PESCADOS, POSTRES.
    
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
        
        inicio = texto.find("{")
        fin = texto.rfind("}") + 1
        if inicio != -1 and fin != -1:
            texto = texto[inicio:fin]
            
        datos = json.loads(texto)
        
        datos_normalizados = {}
        for k, v in datos.items():
            datos_normalizados[k.upper()] = v
        return datos_normalizados

    except Exception as e:
        st.error(f"Error IA ({MODELO_IA}): {e}")
        return None

def crear_capa_contenido(datos, nombre_restaurante):
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    form = can.acroForm
    
    # --- ✅ TUS REQUISITO 2: ESPACIO PARA ALÉRGENOS ---
    # He movido el precio a la izquierda (370) para dejar mucho sitio a la derecha
    margen_izq = 50       
    ancho_nombre = 300    # Reduzco un poco el nombre para que no choque
    x_precio = 370        # PRECIO MÁS A LA IZQUIERDA
    x_iconos = 430        # AQUÍ EMPIEZAN LOS ICONOS (Tenéis 130px de espacio libre hasta el borde)
    
    y_inicial = 730       
    y_limite_footer = 120 # Respeta el pie de página
    alto_linea = 24       # Un poco más de aire entre líneas
    alto_titulo = 40      
    
    # --- HEADER ---
    can.setFont("Helvetica-Bold", 22)
    can.setFillColor(black)
    can.drawCentredString(297.5, 790, nombre_restaurante)
    
    form.textfield(
        name="Header", x=50, y=780, width=500, height=30, 
        value=nombre_restaurante, borderStyle='solid', borderColor=transparent, textColor=transparent
    )

    cursor_y = y_inicial
    orden = ["ENTRANTES", "CARNES", "PESCADOS", "POSTRES"]
    
    # Pre-cálculo para saber si hay contenido
    hay_platos = any(datos.get(k) for k in orden)

    for seccion in orden:
        platos = datos.get(seccion, [])
        
        # Salto de página inteligente si no cabe el título
        if cursor_y < y_limite_footer + 40: 
            can.showPage()
            cursor_y = 780
            
        # Línea y Título
        can.setStrokeColor(HexColor("#333333"))
        can.line(margen_izq, cursor_y - 5, 500, cursor_y - 5)
        
        can.setFont("Helvetica-Bold", 14)
        can.setFillColor(HexColor("#2C3E50"))
        can.drawString(margen_izq, cursor_y, seccion)
        
        cursor_y -= alto_titulo
        
        if not platos:
            cursor_y += 10 
            continue

        for i, plato in enumerate(platos):
            # Salto de página inteligente si no cabe el plato
            if cursor_y < y_limite_footer: 
                can.showPage()
                cursor_y = 780 
                # Repetimos título chiquito
                can.setFont("Helvetica-Oblique", 10)
                can.setFillColor(HexColor("#999999"))
                can.drawString(margen_izq, cursor_y + 10, f"(Cont. {seccion})")
            
            nombre = plato.get("nombre", "Plato")
            precio_raw = str(plato.get("precio", "")).replace("€", "").replace("EUR", "").strip()
            texto_precio = f"{precio_raw} EUR"
            ingredientes = plato.get("ingredientes", "").lower()
            
            # --- 1. TEXTO VISIBLE (NEGRO) ---
            can.setFont("Helvetica", 10)
            can.setFillColor(black)
            # Recortamos nombre visualmente si es eterno
            nombre_ver = (nombre[:50] + '..') if len(nombre) > 50 else nombre
            can.drawString(margen_izq, cursor_y, nombre_ver)
            
            can.setFont("Helvetica-Bold", 10)
            can.drawString(x_precio, cursor_y, texto_precio)
            
            # --- 2. FORMULARIO TRANSPARENTE (PARA EDITAR) ---
            # borderColor=transparent -> Sin borde azul
            form.textfield(
                name=f"{seccion}_{i}_nm",
                x=margen_izq, y=cursor_y-4, width=ancho_nombre, height=16,
                value=nombre, borderStyle='solid', borderColor=transparent, fillColor=transparent, textColor=transparent
            )
            form.textfield(
                name=f"{seccion}_{i}_pr",
                x=x_precio, y=cursor_y-4, width=50, height=16,
                value=texto_precio, borderStyle='solid', borderColor=transparent, fillColor=transparent, textColor=transparent
            )
            
            # --- 3. ICONOS (ALINEADOS A LA DERECHA) ---
            curr_x = x_iconos
            iconos_usados = set()
            for k, v in ALERGENOS_MAP.items():
                if k in ingredientes: iconos_usados.add(v)
            
            for icono in iconos_usados:
                if os.path.exists(icono):
                    try:
                        can.drawImage(icono, curr_x, y=cursor_y-2, width=14, height=14, mask='auto')
                        curr_x += 18 # Separación entre iconos
                    except: pass
            
            cursor_y -= alto_linea 
            
        cursor_y -= 15

    if not hay_platos:
        can.setFont("Helvetica", 12)
        can.setFillColor(red)
        can.drawString(100, 400, "ERROR: LA IA NO ENCONTRÓ PLATOS EN LA FOTO.")

    can.save()
    packet.seek(0)
    return packet

# --- INTERFAZ ---
st.set_page_config(page_title="Generador Final", layout="wide")
st.title(f"Generador de Cartas (IA: {MODELO_IA})")

plantilla = "Antony PLANTILLA BASE SIN ALERGENOS.pdf"

if not os.path.exists(plantilla):
    st.error(f"⚠️ FALTA LA PLANTILLA: {plantilla}")
    st.stop()

col1, col2 = st.columns(2)
with col1:
    img_file = st.file_uploader("1. Sube la foto", type=["jpg", "png", "jpeg"])
    nombre_rest = st.text_input("Nombre del Restaurante", "LA CERVECERA LOS PINOS")

with col2:
    st.write("2. Generar")
    if img_file and st.button("🚀 PROCESAR"):
        with st.spinner(f"Analizando con {MODELO_IA}..."):
            img = PIL.Image.open(img_file)
            datos = leer_y_clasificar_imagen(img)
            
            if datos:
                try:
                    packet_contenido = crear_capa_contenido(datos, nombre_rest)
                    lector_contenido = PdfReader(packet_contenido)
                    lector_plantilla = PdfReader(plantilla)
                    pagina_fondo = lector_plantilla.pages[0]

                    escritor = PdfWriter()

                    # Fusión inteligente de páginas (Fondo en todas)
                    for i in range(len(lector_contenido.pages)):
                        escritor.add_blank_page(width=A4[0], height=A4[1])
                        pagina_nueva = escritor.pages[i]
                        pagina_nueva.merge_page(pagina_fondo) # Fondo
                        pagina_nueva.merge_page(lector_contenido.pages[i]) # Texto
                    
                    out = io.BytesIO()
                    escritor.write(out)
                    
                    st.success(f"✅ ¡PDF Creado con {len(lector_contenido.pages)} páginas!")
                    st.download_button("⬇️ DESCARGAR CARTA", out.getvalue(), "Carta_Final.pdf", "application/pdf")
                except Exception as e:
                    st.error(f"Error técnico: {e}")
            else:
                st.error("La IA no devolvió datos.")
