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

# --- 1. API KEY ---
GOOGLE_API_KEY = "TU_API_KEY_AQUI"
genai.configure(api_key=GOOGLE_API_KEY)

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
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = """
    Actúa como un camarero experto. Analiza el menú.
    Tu objetivo es llenar estas 4 categorías. Si un plato no encaja, mételo en la más parecida.
    
    1. ENTRANTES (tapas, raciones, ensaladas, sartenes)
    2. CARNES (hamburguesas, pollo, cerdo, ternera)
    3. PESCADOS (marisco, sepia, calamar)
    4. POSTRES
    
    Responde SOLO con este JSON (sin texto extra):
    {
        "ENTRANTES": [ {"nombre": "Ejemplo", "precio": "10.50", "ingredientes": "pan"} ],
        "CARNES": [], 
        "PESCADOS": [], 
        "POSTRES": []
    }
    """
    try:
        response = model.generate_content([prompt, imagen])
        # Limpieza agresiva del texto por si la IA añade explicaciones
        texto_limpio = response.text
        texto_limpio = texto_limpio.replace("```json", "").replace("```", "").strip()
        # Buscamos dónde empieza el JSON '{' y dónde termina '}'
        idx_inicio = texto_limpio.find("{")
        idx_fin = texto_limpio.rfind("}") + 1
        if idx_inicio != -1 and idx_fin != -1:
            texto_limpio = texto_limpio[idx_inicio:idx_fin]
            
        return json.loads(texto_limpio)
    except Exception as e:
        st.error(f"Error interpretando la IA: {e}")
        return None

def crear_capa_dinamica(datos, nombre_restaurante):
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    form = can.acroForm
    
    # --- CONFIGURACIÓN VISUAL ---
    cursor_y = 730 
    margen_izq = 50
    x_precio = 450
    x_iconos = 490
    alto_linea = 20    
    alto_titulo = 35   
    
    # 1. HEADER (Nombre Restaurante)
    can.setFont("Helvetica-Bold", 20)
    can.setFillColor(black)
    can.drawCentredString(297.5, 800, nombre_restaurante)
    
    # Campo invisible encima para editar
    form.textfield(
        name="Header", x=100, y=795, width=400, height=25, 
        value=nombre_restaurante, borderStyle='solid', borderColor=transparent, textColor=transparent
    )

    orden_secciones = ["ENTRANTES", "CARNES", "PESCADOS", "POSTRES"]
    
    for seccion in orden_secciones:
        platos = datos.get(seccion, [])
        if not platos: continue 
        
        if cursor_y < 50: break 
        
        # --- TÍTULO SECCIÓN ---
        can.setStrokeColor(HexColor("#333333"))
        can.line(margen_izq, cursor_y - 5, 500, cursor_y - 5)
        
        # Texto "duro" (se ve siempre)
        can.setFont("Helvetica-Bold", 14)
        can.setFillColor(HexColor("#2C3E50"))
        can.drawString(margen_izq, cursor_y, seccion)
        
        cursor_y -= alto_titulo
        
        # --- PLATOS ---
        for i, plato in enumerate(platos):
            if cursor_y < 50: break
            
            nombre = plato.get("nombre", "Sin nombre")
            precio = str(plato.get("precio", "")).replace("€","").strip()
            ingredientes = plato.get("ingredientes", "").lower()
            
            # 1. DIBUJAR TEXTO FIJO (Tinta negra, para asegurar que se vea)
            can.setFont("Helvetica", 10)
            can.setFillColor(black)
            can.drawString(margen_izq, cursor_y, nombre)
            
            can.setFont("Helvetica-Bold", 10)
            can.drawString(x_precio, cursor_y, f"{precio}€")
            
            # 2. PONER FORMULARIO ENCIMA (Invisible pero clicable)
            # Esto permite editar lo que ya está escrito
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
            
            # 3. ICONOS
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
            
        cursor_y -= 15 # Espacio extra tras la sección

    can.save()
    packet.seek(0)
    return packet

# --- INTERFAZ ---
st.set_page_config(layout="wide", page_title="Generador Blindado")
st.title("Generador de Cartas (Versión Depuración)")

plantilla = "Antony PLANTILLA BASE SIN ALERGENOS.pdf"
if not os.path.exists(plantilla):
    st.error(f"❌ ERROR CRÍTICO: No encuentro '{plantilla}'")
    st.stop()

# --- BARRA LATERAL PARA CONTROL ---
with st.sidebar:
    st.header("🛠️ Panel de Control")
    modo = st.radio("Fuente de Datos:", ["🤖 Leer Foto (IA)", "🧪 Datos de Prueba (Manual)"])
    
    if st.button("🔄 Reiniciar Todo"):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.experimental_rerun()

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Entrada de Datos")
    
    if modo == "🤖 Leer Foto (IA)":
        img_file = st.file_uploader("Sube tu carta", type=["jpg", "png"])
        if img_file and st.button("Procesar con IA"):
            with st.spinner("Analizando..."):
                datos = leer_y_clasificar_imagen(PIL.Image.open(img_file))
                if datos:
                    st.session_state["datos_activos"] = datos
                    st.success("¡Datos extraídos!")
                else:
                    st.error("La IA devolvió datos vacíos. Intenta otra foto.")
    
    else: # Modo Prueba
        st.info("Usa esto para verificar que el PDF se genera bien.")
        if st.button("Cargar Datos Falsos"):
            st.session_state["datos_activos"] = {
                "ENTRANTES": [
                    {"nombre": "Croquetas de Jamón", "precio": "12.00", "ingredientes": "leche, harina, jamón"},
                    {"nombre": "Patatas Bravas", "precio": "8.50", "ingredientes": "patata, salsa"}
                ],
                "CARNES": [
                    {"nombre": "Chuletón de Ávila", "precio": "25.00", "ingredientes": "carne de vaca"},
                    {"nombre": "Hamburguesa Completa", "precio": "10.00", "ingredientes": "pan, carne, queso, huevo"}
                ],
                "PESCADOS": [],
                "POSTRES": [
                    {"nombre": "Tarta de Queso", "precio": "5.00", "ingredientes": "queso, leche, huevo, gluten"}
                ]
            }
            st.success("Datos de prueba cargados.")

with col2:
    st.subheader("2. Verificación y PDF")
    
    if "datos_activos" in st.session_state:
        # VISUALIZADOR DE DATOS: Si esto está vacío, el PDF saldrá vacío
        st.write("👀 **Lo que la IA ha encontrado (Edítalo aquí):**")
        datos_editados = st.data_editor(st.session_state["datos_activos"], height=400)
        
        conteo_platos = sum(len(v) for v in datos_editados.values())
        if conteo_platos == 0:
            st.warning("⚠️ ¡Cuidado! No hay platos en la lista. El PDF saldrá vacío.")
        
        nombre_rest = st.text_input("Nombre del Restaurante", "LA CERVECERA LOS PINOS")
        
        if st.button("🖨️ Generar PDF Ahora"):
            try:
                # 1. Crear capa
                capa = crear_capa_dinamica(datos_editados, nombre_rest)
                
                # 2. Mezclar
                reader_base = PdfReader(plantilla)
                page = reader_base.pages[0]
                page.merge_page(PdfReader(capa).pages[0])
                
                writer = PdfWriter()
                writer.add_page(page)
                
                out = io.BytesIO()
                writer.write(out)
                
                st.success("✅ PDF Generado correctamente.")
                st.download_button(
                    label="⬇️ Descargar Carta Final.pdf",
                    data=out.getvalue(),
                    file_name="Carta_Final.pdf",
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"Error al crear el PDF: {e}")
    else:
        st.info("👈 Primero carga datos (Foto o Prueba) en la columna izquierda.")
