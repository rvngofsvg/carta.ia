import streamlit as st
import google.generativeai as genai
import os
import json
from docx import Document
from docx.shared import Cm, Pt
from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
from io import BytesIO
from PIL import Image
from pypdf import PdfReader

# --- 1. CONFIGURACIÓN ---
MODELO_A_USAR = "gemini-2.5-flash" 

# --- 2. DICCIONARIO DE SEGURIDAD (BASE) ---
DICCIONARIO_MAESTRO = {
    "gluten": ["pan", "trigo", "harina", "pasta", "galleta", "bizcocho", "rebozado", "cerveza", "tempura", "panko", "lasaña", "fideos", "salsa de soja"],
    "lacteos": ["queso", "nata", "leche", "yogur", "mantequilla", "bechamel", "mozzarella", "parmesano", "cheddar", "helado", "burrata", "carbonara"],
    "huevos": ["huevo", "tortilla", "mayonesa", "merengue", "alioli", "bizcocho", "quiche", "brioche", "tarta"],
    "crustaceos": ["gamba", "langostino", "cigala", "bogavante", "cangrejo", "buey de mar", "camaron"],
    "moluscos": ["pulpo", "calamar", "sepia", "mejillon", "almeja", "chipiron", "vieira", "ostra"],
    "pescado": ["pescado", "atun", "salmon", "bacalao", "merluza", "anchoa", "sardina", "sushi", "sashimi"],
    "cacahuetes": ["cacahuete", "mani", "satay"],
    "soja": ["soja", "edamame", "tofu", "miso", "salsa de soja", "teriyaki", "wakame"],
    "frutos de cascara": ["almendra", "nuez", "avellana", "pistacho", "anacardo", "pesto", "romesco", "brownie", "nutella"],
    "mostaza": ["mostaza", "dijon", "salsa barbacoa"],
    "sesamo": ["sesamo", "ajonjoli", "tahini", "hummus", "pan de hamburguesa"],
    "apio": ["apio", "caldo"],
    "sulfitos": ["vino", "vinagre", "sulfitos"],
    "altramuces": ["altramuz", "altramuces"]
}

ALLERGEN_OPTIONS = list(DICCIONARIO_MAESTRO.keys())

# --- 3. RUTAS INTELIGENTES ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def find_path_insensitive(base, components):
    current = base
    for part in components:
        found = False
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.name.lower() == part.lower():
                        current = entry.path
                        found = True
                        break
        except: pass
        if not found: return None
    return current

PLANTILLA_PATH = find_path_insensitive(BASE_DIR, ["public", "plantilla", "plantilla_menu.docx"])
ICONOS_DIR = find_path_insensitive(BASE_DIR, ["public", "iconos"])

# --- 4. API KEY ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = os.getenv("GEMINI_API_KEY", "")

if not API_KEY:
    st.error("❌ Falta la GEMINI_API_KEY en los Secrets.")
    st.stop()

genai.configure(api_key=API_KEY)

# --- 5. MAPEO DE ICONOS ---
if not ICONOS_DIR: 
    ICONOS_DIR = os.path.join(BASE_DIR, "Public", "Iconos")

def get_icon_path(icon_name):
    return os
