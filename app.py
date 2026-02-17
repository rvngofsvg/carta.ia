import streamlit as st
import os

st.title("🕵️ MODO DETECTIVE: ¿Dónde están mis archivos?")

# 1. Dónde estamos parados
base_dir = os.path.dirname(os.path.abspath(__file__))
st.write(f"📍 **Carpeta donde está app.py:** `{base_dir}`")

# 2. Listado TOTAL de archivos
st.write("---")
st.subheader("🌲 Árbol de archivos en el servidor:")

archivos_encontrados = []

# Recorre todas las carpetas desde donde estamos
for root, dirs, files in os.walk(base_dir):
    level = root.replace(base_dir, '').count(os.sep)
    indent = ' ' * 4 * (level)
    folder_name = os.path.basename(root)
    
    # Imprime carpeta
    st.text(f"{indent}📁 {folder_name}/")
    
    subindent = ' ' * 4 * (level + 1)
    for f in files:
        # Imprime archivo
        st.text(f"{subindent}📄 {f}")
        archivos_encontrados.append(f)
        
        # Si encuentra algo que parece la plantilla, avisa
        if "plantilla" in f.lower() and "docx" in f.lower():
            st.success(f"✅ ¡LA ENCONTRÉ! La ruta real es:\n{os.path.join(root, f)}")

st.write("---")

# 3. Diagnóstico final
if not any("plantilla" in f.lower() for f in archivos_encontrados):
    st.error("❌ CONCLUSIÓN: El archivo .docx NO ha subido al servidor. Revisa tu GitHub.")
else:
    st.info("Copia la ruta que aparece en verde arriba, esa es la que tienes que poner en el código final.")
