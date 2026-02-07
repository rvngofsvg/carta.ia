import streamlit as st
from docx import Document
from docx.shared import Inches
import google.generativeai as genai
import io
import os

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Generador Automático", page_icon="⚡", layout="wide")

st.title("👨‍🍳 Generador de Carta (Auto-Login)")

# --- LÓGICA INTELIGENTE DE LA CLAVE ---
api_key = None

# 1. Buscamos en la Caja Fuerte de Streamlit (Secrets)
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
    st.sidebar.success("✅ Licencia PRO detectada automáticamente.")
else:
    # 2. Si no está en secretos, pedimos manual (Plan B)
    api_key = st.sidebar.text_input("🔑 Introduce tu API Key:", type="password")

# --- MAPA DE IMÁGENES ---
ALERGENOS_MAP = {
    "altramuces": "altramuces.png", "apio": "apio.png", "cacahuetes": "cacahuetes.png",
    "cereales": "cereales.png", "crustaceos": "crustaceos.png", "frutos de cáscara": "frutos_cascara.png",
    "huevos": "huevos.png", "lácteos": "lacteos.png", "moluscos": "moluscos.png",
    "mostaza": "mostaza.png", "pescado": "pescado.png", "sésamo": "sesamo.png",
    "soja": "soja.png", "sulfitos": "sulfitos.png"
}

# --- FUNCIÓN GENERADORA ---
def intentar_generar(prompt, key):
    genai.configure(api_key=key)
    # Tu modelo favorito
    try:
        model = genai.GenerativeModel('gemini-2.5-flash') # El modelo rápido
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return None

# --- INTERFAZ PRINCIPAL ---
if not api_key:
    st.warning("🔒 El sistema está bloqueado. Configura la 'Secret Key' en Streamlit o introdúcela manualmente.")
else:
    st.info("👋 ¡Hola! El sistema está listo y conectado a Gemini 2.5 Flash.")
    
    # Opción manual o archivo
    opcion = st.radio("Método de entrada:", ["Escribir platos", "Subir Word"], horizontal=True)
    
    texto_para_analizar = ""

    if opcion == "Subir Word":
        uploaded_file = st.file_uploader("Arrastra tu Word aquí", type=["docx"])
        if uploaded_file:
            doc = Document(uploaded_file)
            texto_para_analizar = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    else:
        texto_para_analizar = st.text_area("Escribe tus platos aquí:", height=150, placeholder="Ej: Bravas 5€, Calamares 10€...")

    # BOTÓN DE ACCIÓN
    if st.button("🚀 GENERAR CARTA"):
        if not texto_para_analizar:
            st.error("Escribe algo primero.")
        else:
            with st.spinner("⚡ Procesando con Inteligencia Artificial..."):
                
                prompt = f"""
                Analiza: {texto_para_analizar}
                Detecta 14 Alérgenos UE: Altramuces, Apio, Cacahuetes, Cereales, Crustáceos, Frutos de cáscara, Huevos, Lácteos, Moluscos, Mostaza, Pescado, Sésamo, Soja, Sulfitos.
                
                SALIDA OBLIGATORIA:
                Plato | Precio | Alérgenos
                """
                
                resultado_texto = intentar_generar(prompt, api_key)

                if resultado_texto:
                    st.success("✅ ¡Análisis completado!")
                    
                    # VISUALIZACIÓN EN PANTALLA
                    st.markdown("---")
                    cols_header = st.columns([3, 1, 4])
                    cols_header[0].markdown("**PLATO**")
                    cols_header[1].markdown("**PRECIO**")
                    cols_header[2].markdown("**ALÉRGENOS**")
                    
                    doc_final = Document() # Preparamos Word invisible
                    
                    lineas = resultado_texto.split('\n')
                    for linea in lineas:
                        if '|' in linea and "Plato" not in linea:
                            partes = linea.split('|')
                            if len(partes) >= 2:
                                nombre = partes[0].strip()
                                precio = partes[1].strip()
                                alergenos = partes[2].lower() if len(partes) > 2 else ""

                                # Dibujar en web
                                c1, c2, c3 = st.columns([3, 1, 4])
                                c1.write(nombre)
                                c2.write(precio)
                                
                                iconos_encontrados = []
                                for k, v in ALERGENOS_MAP.items():
                                    if k in alergenos or k.split(' ')[0] in alergenos:
                                        iconos_encontrados.append(v)
                                
                                if iconos_encontrados:
                                    c3.image(iconos_encontrados, width=30)
                                else:
                                    c3.write("-")

                                # Guardar en Word
                                p = doc_final.add_paragraph()
                                p.add_run(f"{nombre} ... {precio}  ").bold = True
                                for ico in iconos_encontrados:
                                    try:
                                        p.add_run().add_picture(ico, width=Inches(0.2))
                                        p.add_run(" ")
                                    except: pass
                    
                    # DESCARGA
                    buffer = io.BytesIO()
                    doc_final.save(buffer)
                    st.markdown("---")
                    st.download_button("📥 Descargar Word Final", buffer.getvalue(), "Carta_Lista.docx")

                else:
                    st.error("Error de conexión. Revisa la API Key.")
