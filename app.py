import streamlit as st
import google.generativeai as genai

st.title("🔍 Diagnóstico FINAL")

# Pide la clave
api_key = st.text_input("Pega tu NUEVA API Key aquí:", type="password")

if api_key:
    try:
        genai.configure(api_key=api_key)
        st.write("📡 Conectando con Google...")
        
        # LISTAMOS LOS MODELOS REALES QUE VE TU CLAVE
        modelos = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                modelos.append(m.name)
        
        if modelos:
            st.success("✅ ¡CONEXIÓN PERFECTA!")
            st.write("Tu clave permite usar estos modelos:")
            st.code(modelos)
        else:
            st.error("La clave conecta, pero no ve modelos. ¿Es un proyecto nuevo?")
            
    except Exception as e:
        st.error(f"❌ Error: {e}")
