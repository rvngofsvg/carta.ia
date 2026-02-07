import streamlit as st
from docx import Document
from docx.shared import Inches
import google.generativeai as genai
import io

st.set_page_config(page_title="Generador Alérgenos 14", page_icon="⚖️")

st.title("🛡️ Generador de Carta (14 Alérgenos)")
st.sidebar.header("Configuración")
api_key = st.sidebar.text_input("Introduce API Key de Gemini", type="password")

# Diccionario de alérgenos (Asegúrate que coinciden con tus archivos .png)
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

def get_gemini_model():
    """Intenta encontrar un modelo que funcione"""
    modelos_a_probar = ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-1.0-pro', 'gemini-pro']
    for nombre_modelo in modelos_a_probar:
        try:
            model = genai.GenerativeModel(nombre_modelo)
            return model, nombre_modelo
        except:
            continue
    return None, None

if not api_key:
    st.info("Esperando API Key para activar la IA...")
else:
    genai.configure(api_key=api_key)
    
    # Probamos qué modelo está disponible
    model, nombre_usado = get_gemini_model()
    
    if model is None:
        st.error("Error: No se pudo conectar con ningún modelo de Gemini. Verifica tu API Key.")
    else:
        # st.success(f"Conectado usando el modelo: {nombre_usado}") # Descomenta si quieres ver cuál usa

        uploaded_file = st.file_uploader("Sube el Word con los platos", type=["docx"])

        if uploaded_file and st.button("🪄 Generar Carta Maquetada"):
            with st.spinner('Analizando ingredientes y consultando alérgenos...'):
                try:
                    # 1. Leer texto del cliente
                    doc_cliente = Document(uploaded_file)
                    texto_menu = "\n".join([p.text for p in doc_cliente.paragraphs if p.text.strip()])

                    # 2. IA analiza alérgenos
                    prompt = f"""
                    Analiza estos platos y detecta CUALQUIERA de los 14 alérgenos legales:
                    Altramuces, Apio, Cacahuetes, Cereales (gluten), Crustáceos, Frutos de cáscara, Huevos, Lácteos, Moluscos, Mostaza, Pescado, Sésamo, Soja, Sulfitos.
                    
                    Formato de respuesta estrictamente:
                    Nombre del Plato | Precio | Alérgenos (separados por comas)
                    
                    Menú a analizar:
                    {texto_menu}
                    """
                    
                    response = model.generate_content(prompt)
                    
                    # 3. Crear el Word final
                    doc_final = Document("PLANTILLA BASE CARTA.docx")
                    doc_final.add_paragraph("\n--- NUEVA CARTA GENERADA ---")

                    if response.text:
                        lineas = response.text.split('\n')
                        for linea in lineas:
                            if '|' in linea:
                                datos = linea.split('|')
                                if len(datos) >= 3:
                                    nombre = datos[0].strip()
                                    precio = datos[1].strip()
                                    alergenos_detectados = datos[2].lower()

                                    p = doc_final.add_paragraph()
                                    run_nombre = p.add_run(f"{nombre} ")
                                    run_nombre.bold = True
                                    p.add_run(f".... {precio}   ")

                                    # Insertar iconos
                                    for nombre_alergeno, archivo_png in ALERGENOS_MAP.items():
                                        # Ajuste para detectar singulares y plurales básicos
                                        keyword = nombre_alergeno.split(' ')[0] # Toma la primera palabra clave
                                        if keyword in alergenos_detectados or nombre_alergeno in alergenos_detectados:
                                            try:
                                                p.add_run().add_picture(archivo_png, width=Inches(0.18))
                                                p.add_run("  ") 
                                            except:
                                                st.warning(f"Falta imagen: {archivo_png}")

                        # 4. Preparar descarga
                        target_stream = io.BytesIO()
                        doc_final.save(target_stream)
                        
                        st.success("✅ ¡Carta lista!")
                        st.download_button(
                            label="📥 Descargar Word Final",
                            data=target_stream.getvalue(),
                            file_name="Carta_Final_Alergenos.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
                except Exception as e:
                    st.error(f"Ocurrió un error técnico: {e}")
