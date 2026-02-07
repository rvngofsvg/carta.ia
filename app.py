import streamlit as st
from docx import Document
from docx.shared import Inches
import google.generativeai as genai
import io

# Configuración de la página
st.set_page_config(page_title="Generador Alérgenos PRO", page_icon="🍽️")

st.title("👨‍🍳 Generador de Carta Automático")
st.markdown("---")

# --- BARRA LATERAL (CLAVE) ---
st.sidebar.header("🔐 Configuración")
api_key = st.sidebar.text_input("Pega tu API Key aquí:", type="password")

# --- LISTA DE TUS IMÁGENES ---
ALERGENOS_MAP = {
    "altramuces": "altramuces.png",
    "apio": "apio.png",
    "cacahuetes": "cacahuetes.png",
    "cereales": "cereales.png",
    "crustaceos": "crustaceos.png",
    "frutos de cáscara": "frutos_cascara.png",
    "huevos": "huevos.png",
    "lácteos": "lacteos.png",
    "moluscos": "moluscos.png",
    "mostaza": "mostaza.png",
    "pescado": "pescado.png",
    "sésamo": "sesamo.png",
    "soja": "soja.png",
    "sulfitos": "sulfitos.png"
}

if not api_key:
    st.info("👈 Por favor, pega tu llave maestra en la barra lateral.")
else:
    try:
        genai.configure(api_key=api_key)
        
        # USAREMOS LA VERSIÓN 1.5 FLASH (ESTA ES LA SEGURA EN ESPAÑA)
        model = genai.GenerativeModel('gemini-1.5-flash')

        # --- SUBIDA DE ARCHIVO ---
        uploaded_file = st.file_uploader("Sube tu archivo Word (.docx)", type=["docx"])

        if uploaded_file is not None:
            if st.button("🚀 GENERAR CARTA AHORA"):
                with st.spinner('⏳ La IA está leyendo tus platos...'):
                    
                    # 1. Leer el Word
                    doc_cliente = Document(uploaded_file)
                    texto_menu = "\n".join([p.text for p in doc_cliente.paragraphs if p.text.strip()])

                    # 2. Prompt
                    prompt = f"""
                    Actúa como un experto en seguridad alimentaria. Analiza estos platos y detecta los 14 alérgenos legales UE:
                    (Altramuces, Apio, Cacahuetes, Cereales, Crustáceos, Frutos de cáscara, Huevos, Lácteos, Moluscos, Mostaza, Pescado, Sésamo, Soja, Sulfitos).

                    Reglas:
                    1. Sé preciso. "Queso" = Lácteos. "Pan" = Cereales.
                    2. Formato de salida OBLIGATORIO (usa | para separar):
                    Nombre del Plato | Precio | Alérgenos detectados
                    
                    MENÚ:
                    {texto_menu}
                    """
                    
                    # 3. Generar
                    response = model.generate_content(prompt)
                    
                    # 4. Crear Word
                    try:
                        doc_final = Document("PLANTILLA BASE CARTA.docx")
                        doc_final.add_paragraph("\n")
                    except:
                        doc_final = Document()

                    if response.text:
                        lineas = response.text.split('\n')
                        for linea in lineas:
                            if '|' in linea and "Nombre del Plato" not in linea:
                                partes = linea.split('|')
                                if len(partes) >= 2:
                                    nombre = partes[0].strip()
                                    precio = partes[1].strip()
                                    alerg = partes[2].lower() if len(partes) > 2 else ""

                                    p = doc_final.add_paragraph()
                                    runner = p.add_run(f"{nombre} ................. {precio}   ")
                                    runner.bold = True
                                    
                                    for clave, archivo in ALERGENOS_MAP.items():
                                        clave_simple = clave.split(' ')[0]
                                        if clave in alerg or clave_simple in alerg:
                                            try:
                                                p.add_run().add_picture(archivo, width=Inches(0.2))
                                                p.add_run("  ")
                                            except:
                                                pass

                        # 5. Descargar
                        buffer = io.BytesIO()
                        doc_final.save(buffer)
                        buffer.seek(0)
                        
                        st.success("✅ ¡CARTA LISTA!")
                        st.download_button(
                            label="📥 Descargar Word Final",
                            data=buffer,
                            file_name="Carta_Con_Alergenos.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )

    except Exception as e:
        st.error(f"❌ Ocurrió un error: {e}")
