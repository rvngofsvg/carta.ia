import streamlit as st
from docx import Document
from docx.shared import Inches
import google.generativeai as genai
import io

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Generador Visual", page_icon="👁️", layout="wide")

st.title("👨‍🍳 Visualizador de Carta con IA")
st.markdown("### 1. Sube tu menú -> 2. La IA detecta alérgenos -> 3. Copia o Descarga")

# --- BARRA LATERAL ---
st.sidebar.header("🔑 Llave de Acceso")
api_key = st.sidebar.text_input("Pega tu API Key aquí:", type="password")

# --- MAPA DE IMÁGENES (Asegúrate que están en GitHub) ---
ALERGENOS_MAP = {
    "altramuces": "altramuces.png", "apio": "apio.png", "cacahuetes": "cacahuetes.png",
    "cereales": "cereales.png", "crustaceos": "crustaceos.png", "frutos de cáscara": "frutos_cascara.png",
    "huevos": "huevos.png", "lácteos": "lacteos.png", "moluscos": "moluscos.png",
    "mostaza": "mostaza.png", "pescado": "pescado.png", "sésamo": "sesamo.png",
    "soja": "soja.png", "sulfitos": "sulfitos.png"
}

# --- FUNCIÓN INTELIGENTE PARA EVITAR ERRORES ---
def intentar_generar(prompt, key):
    genai.configure(api_key=key)
    # Lista de modelos a probar en orden de preferencia
    modelos = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro', 'gemini-1.0-pro']
    
    for modelo in modelos:
        try:
            model = genai.GenerativeModel(modelo)
            response = model.generate_content(prompt)
            return response.text, modelo # Si funciona, devuelve el texto y el modelo usado
        except Exception as e:
            continue # Si falla, prueba el siguiente
    return None, None

# --- INTERFAZ ---
if not api_key:
    st.warning("⚠️ Pega tu API Key a la izquierda para empezar.")
else:
    # Área de texto manual (OPCIÓN NUEVA: NO HACE FALTA SUBIR WORD SI NO QUIERES)
    opcion = st.radio("¿Cómo quieres introducir los platos?", ["Escribir texto manual", "Subir archivo Word"])
    
    texto_para_analizar = ""

    if opcion == "Subir archivo Word":
        uploaded_file = st.file_uploader("Sube tu Word", type=["docx"])
        if uploaded_file:
            doc = Document(uploaded_file)
            texto_para_analizar = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    else:
        texto_para_analizar = st.text_area("Escribe aquí tus platos (Ej: Calamares 10€, Ensalada de queso 8€)", height=150)

    if st.button("✨ ANALIZAR CARTA AHORA"):
        if not texto_para_analizar:
            st.error("Por favor, sube un archivo o escribe algunos platos.")
        else:
            with st.spinner("🧠 La IA está buscando el mejor modelo y analizando alérgenos..."):
                
                prompt = f"""
                Eres un experto en alérgenos. Analiza: {texto_para_analizar}
                Detecta: Altramuces, Apio, Cacahuetes, Cereales, Crustáceos, Frutos de cáscara, Huevos, Lácteos, Moluscos, Mostaza, Pescado, Sésamo, Soja, Sulfitos.
                
                IMPORTANTE: Devuelve SOLO una lista con este formato exacto:
                Plato | Precio | Alérgenos
                """
                
                resultado_texto, modelo_usado = intentar_generar(prompt, api_key)

                if resultado_texto:
                    st.success(f"✅ ¡Éxito! Usando el modelo: {modelo_usado}")
                    
                    # --- MOSTRAR RESULTADO VISUALMENTE (TABLA BONITA) ---
                    st.markdown("---")
                    st.subheader("👀 Vista Previa del Resultado")
                    
                    # Preparamos el Word en memoria por si acaso lo quiere
                    doc_final = Document()
                    doc_final.add_heading("CARTA DE ALÉRGENOS", 0)

                    cols_header = st.columns([3, 1, 4])
                    cols_header[0].markdown("**PLATO**")
                    cols_header[1].markdown("**PRECIO**")
                    cols_header[2].markdown("**ICONOS DETECTADOS**")
                    
                    lineas = resultado_texto.split('\n')
                    for linea in lineas:
                        if '|' in linea and "Plato" not in linea:
                            partes = linea.split('|')
                            if len(partes) >= 2:
                                nombre = partes[0].strip()
                                precio = partes[1].strip()
                                alergenos = partes[2].lower() if len(partes) > 2 else ""

                                # 1. DIBUJAR EN PANTALLA
                                c1, c2, c3 = st.columns([3, 1, 4])
                                c1.write(nombre)
                                c2.write(precio)
                                
                                # Lógica de iconos en pantalla
                                iconos_encontrados = []
                                for k, v in ALERGENOS_MAP.items():
                                    clave_corta = k.split(' ')[0]
                                    if k in alergenos or clave_corta in alergenos:
                                        iconos_encontrados.append(v)
                                
                                # Mostrar imágenes en la columna 3
                                if iconos_encontrados:
                                    c3.image(iconos_encontrados, width=30) # Iconos pequeños en fila
                                else:
                                    c3.write("-")

                                # 2. GUARDAR EN WORD (Invisible)
                                p = doc_final.add_paragraph()
                                p.add_run(f"{nombre} ... {precio}  ").bold = True
                                for ico in iconos_encontrados:
                                    try:
                                        p.add_run().add_picture(ico, width=Inches(0.2))
                                        p.add_run(" ")
                                    except:
                                        pass
                    
                    st.markdown("---")
                    
                    # --- OPCIÓN DE DESCARGA (PLAN B) ---
                    buffer = io.BytesIO()
                    doc_final.save(buffer)
                    buffer.seek(0)
                    
                    col_dl1, col_dl2 = st.columns(2)
                    with col_dl1:
                        st.download_button("📥 Descargar Word con Iconos", buffer, "Carta_Lista.docx")
                    with col_dl2:
                        st.info("💡 Si prefieres, copia el texto de arriba y pégalo en tu PC, aunque los iconos no se copiarán automáticos.")

                else:
                    st.error("❌ Google está saturado ahora mismo o la clave falló. Intenta en 1 min.")
