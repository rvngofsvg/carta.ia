import streamlit as st
import google.generativeai as genai
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import transparent, white, black, red
from pypdf import PdfReader, PdfWriter
import io
import PIL.Image
import json
import os

# --- 1. CONFIGURACIÓN ---
# ¡Recuerda poner tu API Key real aquí!
GOOGLE_API_KEY = "AIzaSyA0l07ASmsiBa-g3c7D9wNxZLnEUJ9Bfds"
genai.configure(api_key=GOOGLE_API_KEY)

# --- 2. MAPEO DE ICONOS (Busca en la misma carpeta) ---
ALERGENOS_MAP = {
    "gluten": "gluten.png", 
    "trigo": "gluten.png",
    "harina": "gluten.png",
    "pan": "gluten.png",
    "lácteos": "lacteos.png", 
    "queso": "lacteos.png", 
    "leche": "lacteos.png",
    "nata": "lacteos.png",
    "huevo": "huevo.png",
    "mayonesa": "huevo.png",
    "frutos secos": "frutos_secos.png",
    "nueces": "frutos_secos.png",
    "almendra": "frutos_secos.png",
    "pescado": "pescado.png",
    "atún": "pescado.png",
    "bacalao": "pescado.png",
    "gambas": "gambas.png",
    "crustáceos": "gambas.png",
    "soja": "soja.png",
    "mostaza": "mostaza.png",
    "apio": "apio.png",
    "sulfitos": "sulfitos.png"
}

def leer_y_clasificar_imagen(imagen):
    """Lee la imagen y devuelve JSON estructurado."""
    model = genai.GenerativeModel('gemini-2.5-flash')
    prompt = """
    Analiza esta carta de restaurante.
    Tu tarea es extraer los platos y clasificarlos OBLIGATORIAMENTE en estas 4 categorías:
    1. ENTRANTES (Incluye ensaladas, picoteo, raciones, sartenes)
    2. CARNES (Incluye hamburguesas, pollo, cerdo, ternera)
    3. PESCADOS (Incluye marisco, sepia, calamar)
    4. POSTRES
    
    Para cada plato:
    - Nombre exacto.
    - Precio (solo número).
    - Ingredientes: DEDUCE los ingredientes probables para alérgenos (ej: si es 'Croquetas', pon 'leche, harina, huevo').
    
    Responde SOLO con este JSON:
    {
        "ENTRANTES": [ {"nombre": "X", "precio": "00.00", "ingredientes": "a, b"} ],
        "CARNES": [], "PESCADOS": [], "POSTRES": []
    }
    """
    try:
        response = model.generate_content([prompt, imagen])
        clean_text = response.text.replace("```json", "").replace("```", "")
        return json.loads(clean_text)
    except Exception as e:
        st.error(f"Error IA: {e}")
        return None

def crear_capa_final(datos_clasificados, nombre_restaurante):
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    
    # Configuración de coordenadas (Ajustadas a tu plantilla)
    CONFIG = {
        "HEADER": {"x": 300, "y": 800},
        "ENTRANTES": {"x": 45, "y_start": 725, "max_items": 9},
        "CARNES":    {"x": 45, "y_start": 560, "max_items": 7},
        "PESCADOS":  {"x": 45, "y_start": 405, "max_items": 7},
        "POSTRES":   {"x": 45, "y_start": 250, "max_items": 7}
    }
    
    x_precio = 430
    x_iconos = 470
    line_height = 16.5

    # --- HEADER (Nombre Restaurante) ---
    # 1. Parche blanco para borrar lo de abajo
    can.setFillColor(white)
    can.rect(100, 790, 400, 30, stroke=0, fill=1)
    
    # 2. Texto Editable Invisible
    can.setFont("Helvetica-Bold", 18)
    form = can.acroForm
    form.textfield(
        name="Header", x=150, y=795, width=300, height=25, fontSize=18, 
        value=nombre_restaurante, borderStyle='solid', borderColor=transparent, 
        fillColor=transparent, textColor=black
    )

    # --- BUCLE DE PLATOS ---
    for categoria, platos in datos_clasificados.items():
        if categoria not in CONFIG: continue
        cfg = CONFIG[categoria]
        y = cfg["y_start"]
        
        for i, plato in enumerate(platos):
            if i >= cfg["max_items"]: break
            
            nombre = plato.get("nombre", "")
            precio = str(plato.get("precio", "")).replace("€","").strip()
            ingredientes = plato.get("ingredientes", "").lower()
            
            # 1. PARCHE BLANCO (El "Tipp-Ex" mágico)
            # Tapa el texto "Plato.... 00,00" de la plantilla original
            can.setFillColor(white)
            can.rect(cfg["x"]-5, y-2, 450, 15, stroke=0, fill=1)
            
            # 2. CAMPOS EDITABLES (Nombre y Precio)
            # borderColor=transparent hace que no se vean cajas feas
            form.textfield(name=f"{categoria}_{i}_nm", x=cfg["x"], y=y, width=320, height=13, fontSize=10, value=nombre, borderStyle='solid', borderColor=transparent, fillColor=transparent)
            form.textfield(name=f"{categoria}_{i}_pr", x=x_precio, y=y, width=40, height=13, fontSize=10, value=f"{precio}€", borderStyle='solid', borderColor=transparent, fillColor=transparent)
            
            # 3. ICONOS (Automáticos)
            curr_x_icon = x_iconos
            iconos_usados = set()
            
            # Detectar qué iconos poner
            for clave, nombre_archivo in ALERGENOS_MAP.items():
                if clave in ingredientes:
                    iconos_usados.add(nombre_archivo)
            
            # Dibujarlos
            for nombre_archivo in iconos_usados:
                if os.path.exists(nombre_archivo):
                    try:
                        can.drawImage(nombre_archivo, curr_x_icon, y, width=12, height=12, mask='auto')
                        curr_x_icon += 14
                    except:
                        pass
                else:
                    # Si falta el archivo, pone un punto rojo de aviso
                    can.setFillColor(red)
                    can.circle(curr_x_icon + 6, y + 6, 3, fill=1)
                    curr_x_icon += 10
            
            y -= line_height # Siguiente línea

    can.save()
    packet.seek(0)
    return packet

# --- INTERFAZ DE USUARIO ---
st.set_page_config(layout="wide", page_title="Generador Cartas Pro")
st.title("Generador de Cartas (Versión Final)")

# --- BARRA LATERAL: DIAGNÓSTICO ---
with st.sidebar.expander("🔍 Estado de Archivos", expanded=True):
    st.write("Verificando recursos...")
    
    # 1. Verificar Plantilla
    plantilla_path = "Antony PLANTILLA BASE SIN ALERGENOS.pdf"
    if os.path.exists(plantilla_path):
        st.success(f"✅ Plantilla: {plantilla_path}")
    else:
        st.error(f"❌ FALTA LA PLANTILLA: {plantilla_path}")
        st.stop() # Detiene la app si no hay plantilla

    # 2. Verificar Iconos
    archivos_necesarios = set(ALERGENOS_MAP.values())
    faltan = 0
    for archivo in archivos_necesarios:
        if os.path.exists(archivo):
            pass # Está ok
        else:
            st.warning(f"⚠️ Falta icono: {archivo}")
            faltan += 1
    
    if faltan == 0:
        st.success("✅ Todos los iconos encontrados.")
    else:
        st.info("Sube los iconos .png a la carpeta del proyecto.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Entrada")
    img_file = st.file_uploader("Sube foto del menú (Pizarra/Papel)", type=["jpg","png","jpeg"])
    
    if img_file and st.button("🚀 Procesar Imagen"):
        with st.spinner("La IA está leyendo y clasificando..."):
            img = PIL.Image.open(img_file)
            datos = leer_y_clasificar_imagen(img)
            if datos:
                st.session_state["datos_final"] = datos
                st.success("¡Datos extraídos con éxito!")

with col2:
    st.subheader("2. Resultado y Edición")
    nombre_rest = st.text_input("Nombre del Restaurante", "LA CERVECERA LOS PINOS")
    
    if "datos_final" in st.session_state:
        st.info("Puedes editar los datos aquí antes de generar el PDF:")
        datos_editados = st.data_editor(st.session_state["datos_final"], height=400)
        
        if st.button("💾 Generar PDF Final"):
            try:
                # 1. Crear capa con datos nuevos
                capa = crear_capa_final(datos_editados, nombre_rest)
                
                # 2. Mezclar con plantilla base
                base = PdfReader(plantilla_path)
                page = base.pages[0]
                page.merge_page(PdfReader(capa).pages[0])
                
                writer = PdfWriter()
                writer.add_page(page)
                
                out = io.BytesIO()
                writer.write(out)
                
                st.success("¡PDF Creado! Abre el archivo para editar precios.")
                st.download_button("Descargar Carta (.pdf)", out.getvalue(), "Carta_Final_Editable.pdf", "application/pdf")
            except Exception as e:
                st.error(f"Error generando PDF: {e}")
