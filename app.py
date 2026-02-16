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
# Tu clave y modelo se mantienen intactos
GOOGLE_API_KEY = "AIzaSyA0l07ASmsiBa-g3c7D9wNxZLnEUJ9Bfds"
genai.configure(api_key=GOOGLE_API_KEY)
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
    model = genai.GenerativeModel(MODELO_IA)
    
    prompt = """
    Analiza el menú. Extrae platos y PRECIOS (solo números).
    Clasifica en: ENTRANTES, CARNES, PESCADOS, POSTRES.
    
    Responde SOLO JSON válido:
    {
        "ENTRANTES": [ {"nombre": "Plato", "precio": "10.50", "ingredientes": "ingredientes"} ],
        "CARNES": [], "PESCADOS": [], "POSTRES": []
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
        
        # Normalizar claves a mayúsculas
        datos_normalizados = {}
        for k, v in datos.items():
            datos_normalizados[k.upper()] = v
        return datos_normalizados

    except Exception as e:
        st.error(f"Error IA: {e}")
        return None

def crear_capa_contenido(datos, nombre_restaurante):
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    form = can.acroForm
    
    # --- AJUSTES DE DISEÑO ---
    margen_izq = 50       
    x_precio = 370        # Alineado para dejar sitio a los iconos
    x_iconos = 430        # Zona de iconos (Derecha limpia)
    ancho_nombre = 300    
    
    y_inicial = 730       
    y_limite_footer = 120 # Freno antes de chocar con tu pie de página nuevo
    alto_linea = 24       
    alto_titulo = 40      
    
    # --- HEADER DINÁMICO (Nombre Restaurante) ---
    can.setFont("Helvetica-Bold", 22)
    can.setFillColor(black)
    can.drawCentredString(297.5, 790, nombre_restaurante)
    
    # Campo para editar el título si hace falta
    form.textfield(
        name="Header", x=50, y=780, width=500, height=30, 
        value=nombre_restaurante, borderStyle='solid', borderColor=transparent, textColor=transparent
    )

    cursor_y = y_inicial
    orden = ["ENTRANTES", "CARNES", "PESCADOS", "POSTRES"]
    hay_platos = False

    for seccion in orden:
        platos = datos.get(seccion, [])
        
        # Si la sección tiene platos, marcamos que hay contenido
        if platos: hay_platos = True

        # --- TÍTULO DE SECCIÓN ---
        # Verificamos si cabe el título, si no, nueva página
        if cursor_y < y_limite_footer + 40: 
            can.showPage()
            cursor_y = 780
            
        can.setStrokeColor(HexColor("#333333"))
        can.line(margen_izq, cursor_y - 5, 500, cursor_y - 5)
        
        can.setFont("Helvetica-Bold", 14)
        can.setFillColor(HexColor("#2C3E50"))
        can.drawString(margen_izq, cursor_y, seccion)
        
        cursor_y -= alto_titulo
        
        if not platos:
            cursor_y += 10 
            continue

        # --- PLATOS ---
        for i, plato in enumerate(platos):
            # Verificamos si cabe el plato, si no, nueva página
            if cursor_y < y_limite_footer: 
                can.showPage()
                cursor_y = 780 
                # Repetimos título chiquito para guiar
                can.setFont("Helvetica-Oblique", 10)
                can.setFillColor(HexColor("#999999"))
                can.drawString(margen_izq, cursor_y + 10, f"(Cont. {seccion})")
            
            nombre = plato.get("nombre", "Plato")
            precio_raw = str(plato.get("precio", "")).replace("€", "").replace("EUR", "").strip()
            texto_precio = f"{precio_raw} EUR"
            ingredientes = plato.get("ingredientes", "").lower()
            
            # 1. TEXTO NEGRO (Ya no necesitamos borrar fondo blanco porque tu plantilla es limpia)
            can.setFont("Helvetica", 10)
            can.setFillColor(black)
            
            # Recortar nombre visualmente si es muy largo
            nombre_ver = (nombre[:50] + '..') if len(nombre) > 50 else nombre
            can.drawString(margen_izq, cursor_y, nombre_ver)
            
            can.setFont("Helvetica-Bold", 10)
            can.drawString(x_precio, cursor_y, texto_precio)
            
            # 2. CAMPOS EDITABLES (Transparentes y limpios)
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
            
            # 3. ICONOS ALÉRGENOS
            curr_x = x_iconos
            iconos_usados = set()
            for k, v in ALERGENOS_MAP.items():
                if k in ingredientes: iconos_usados.add(v)
            
            for icono in iconos_usados:
                if os.path.exists(icono):
                    try:
                        can.drawImage(icono, curr_x, y=cursor_y-2, width=14, height=14, mask='auto')
                        curr_x += 18 
                    except: pass
            
            cursor_y -= alto_linea 
            
        cursor_y -= 15

    if not hay_platos:
        can.setFont("Helvetica", 12)
        can.setFillColor(red)
        can.drawString(100, 400, "LA IA NO DETECTÓ PLATOS EN ESTA FOTO.")

    can.save()
    packet.seek(0)
    return packet

# --- INTERFAZ WEB ---
st.set_page_config(page_title="Generador Pro", layout="wide")
st.title("Generador de Cartas (Plantilla Limpia)")

# Asegúrate de que este nombre coincida con tu archivo nuevo
plantilla = "Antony PLANTILLA BASE SIN ALERGENOS (1).pdf"

if not os.path.exists(plantilla):
    st.error(f"⚠️ NO ENCUENTRO LA PLANTILLA: {plantilla}")
    st.stop()

col1, col2 = st.columns(2)
with col1:
    img_file = st.file_uploader("1. Sube foto del menú", type=["jpg", "png", "jpeg"])
    # Este nombre es dinámico, cambia según lo que escribas aquí
    nombre_rest = st.text_input("Nombre del Restaurante", "LA CERVECERA LOS PINOS")

with col2:
    st.write("2. Generar PDF")
    if img_file and st.button("🚀 CREAR CARTA"):
        with st.spinner("Procesando..."):
            img = PIL.Image.open(img_file)
            datos = leer_y_clasificar_imagen(img)
            
            if datos:
                try:
                    # 1. Creamos contenido sobre transparente
                    packet = crear_capa_contenido(datos, nombre_rest)
                    lector_capa = PdfReader(packet)
                    
                    # 2. Leemos tu plantilla limpia nueva
                    lector_plantilla = PdfReader(plantilla)
                    pagina_fondo = lector_plantilla.pages[0]

                    escritor = PdfWriter()

                    # 3. Fusión Inteligente (Si salen 2 páginas, pone fondo en las 2)
                    for i in range(len(lector_capa.pages)):
                        escritor.add_blank_page(width=A4[0], height=A4[1])
                        pagina_nueva = escritor.pages[i]
                        pagina_nueva.merge_page(pagina_fondo) # Fondo limpio
                        pagina_nueva.merge_page(lector_capa.pages[i]) # Texto nuevo
                    
                    out = io.BytesIO()
                    escritor.write(out)
                    
                    st.success("✅ ¡PDF Creado Perfecto!")
                    st.download_button("⬇️ DESCARGAR", out.getvalue(), "Carta_Nueva.pdf", "application/pdf")
                except Exception as e:
                    st.error(f"Error técnico: {e}")
            else:
                st.error("Error de lectura de IA.")
