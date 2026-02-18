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

# Lista completa de opciones para el selector
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
    return os.path.join(ICONOS_DIR, icon_name)

ICON_MAP = {
    "gluten": get_icon_path("gluten.png"),
    "crustaceos": get_icon_path("gambas.png"),
    "huevos": get_icon_path("huevo.png"),
    "pescado": get_icon_path("pescado.png"),
    "cacahuetes": get_icon_path("cacahuetes.png"),
    "soja": get_icon_path("soja.png"),
    "lacteos": get_icon_path("lacteos.png"),
    "frutos de cascara": get_icon_path("frutos_secos.png"),
    "apio": get_icon_path("apio.png"),
    "mostaza": get_icon_path("mostaza.png"),
    "sesamo": get_icon_path("sesamo.png"),
    "sulfitos": get_icon_path("sulfitos.png"),
    "altramuces": get_icon_path("altramuces.png"),
    "moluscos": get_icon_path("moluscos.png")
}

# --- 6. FUNCIONES DE LECTURA ---
def extract_text_from_pdf(file):
    try:
        reader = PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except: return None

def extract_text_from_docx(file):
    try:
        doc = Document(file)
        text = "\n".join([p.text for p in doc.paragraphs])
        for table in doc.tables:
            for row in table.rows:
                text += " | ".join([cell.text for cell in row.cells]) + "\n"
        return text
    except: return None

# --- 7. ANÁLISIS ---
def analyze_content(content, content_type="image"):
    model = genai.GenerativeModel(MODELO_A_USAR)
    
    base_prompt = """
    Analiza este menú.
    1. Extrae Nombre del Restaurante, Categorías, Platos y PRECIO.
    2. DETECTA ALÉRGENOS basándote en ingredientes y sentido común gastronómico.
    
    Salida JSON (sin markdown):
    {
        "restaurant_name": "Nombre",
        "categories": [
            {
                "name": "Categoría",
                "dishes": [
                    {
                        "name": "Plato",
                        "description": "Ingredientes",
                        "price": "10.50",
                        "allergens": ["gluten", "lacteos"] 
                    }
                ]
            }
        ]
    }
    """
    
    try:
        with st.spinner(f"🧠 Analizando con IA ({MODELO_A_USAR})..."):
            if content_type == "image":
                response = model.generate_content([base_prompt, content])
            else:
                response = model.generate_content(base_prompt + "\n\nMENÚ:\n" + content)
            
            text = response.text.replace('```json', '').replace('```', '').strip()
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end != -1: text = text[start:end]
            
            data = json.loads(text)

            # Capa de Seguridad (Diccionario)
            for category in data.get("categories", []):
                for dish in category["dishes"]:
                    full_text = (dish.get("name", "") + " " + dish.get("description", "")).lower()
                    current = [a.lower().strip() for a in dish.get("allergens", [])]
                    
                    for allergen, keywords in DICCIONARIO_MAESTRO.items():
                        if any(k in full_text for k in keywords):
                            if allergen not in current: current.append(allergen)
                    
                    dish["allergens"] = current
            
            return data

    except Exception as e:
        st.error(f"Error IA: {e}")
        return None

# --- 8. GENERACIÓN WORD (ALINEACIÓN PERFECTA) ---
def create_word(data):
    if not PLANTILLA_PATH or not os.path.exists(PLANTILLA_PATH):
        st.error(f"❌ Falta plantilla en: {PLANTILLA_PATH}")
        st.stop()
        
    doc = Document(PLANTILLA_PATH)
    
    # Título
    try: doc.add_heading(data.get("restaurant_name", "MENÚ"), 0)
    except: doc.add_paragraph(data.get("restaurant_name", "MENÚ")).bold = True

    for category in data.get("categories", []):
        doc.add_heading(category["name"], level=1)
        for dish in category["dishes"]:
            p = doc.add_paragraph()
            
            # --- SISTEMA DE DOBLE TABULACIÓN PARA ALINEAR ---
            # Tab 1: Precio (Alineado a la derecha, con puntos) -> Posición 15 cm
            # Tab 2: Iconos (Alineado a la izquierda, sin puntos) -> Posición 15.5 cm
            
            tab_stops = p.paragraph_format.tab_stops
            # Tabulador para el precio (con puntos)
            tab_stops.add_tab_stop(Cm(14.5), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            # Tabulador para los iconos (fijo para que empiecen siempre igual)
            tab_stops.add_tab_stop(Cm(15.0), WD_TAB_ALIGNMENT.LEFT, WD_TAB_LEADER.SPACES)
            
            # 1. Nombre
            p.add_run(dish['name']).bold = True
            
            # 2. Salto al Precio
            p.add_run(f"\t{dish['price']}€")
            
            # 3. Salto a la Columna de Iconos
            p.add_run("\t") 
            
            # 4. Insertar Iconos
            for allergen in dish.get("allergens", []):
                key = allergen.lower().strip()
                if "frutos secos" in key: key = "frutos de cascara"
                
                if key in ICON_MAP:
                    icon_path = ICON_MAP[key]
                    if os.path.exists(icon_path):
                        try:
                            run = p.add_run()
                            run.add_picture(icon_path, width=Cm(0.4))
                        except: pass
            
            # Descripción
            if dish.get('description'):
                p_desc = doc.add_paragraph()
                p_desc.add_run(dish['description']).italic = True
                p.paragraph_format.space_after = Pt(2)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# --- 9. INTERFAZ (CON EDITOR MANUAL) ---
st.title("Generador de Cartas: Edición Pro ✏️")

if "menu_data" not in st.session_state:
    st.session_state.menu_data = None

uploaded_file = st.file_uploader("Sube Menú", type=["jpg", "png", "pdf", "docx"])

if uploaded_file:
    # Botón de análisis inicial
    if st.button("1. ANALIZAR MENÚ CON IA"):
        file_type = uploaded_file.name.split('.')[-1].lower()
        data = None
        if file_type in ['jpg', 'png', 'jpeg']:
            data = analyze_content(Image.open(uploaded_file), "image")
        elif file_type == 'pdf':
            text = extract_text_from_pdf(uploaded_file)
            if text: data = analyze_content(text, "text")
        elif file_type == 'docx':
            text = extract_text_from_docx(uploaded_file)
            if text: data = analyze_content(text, "text")
        
        if data:
            st.session_state.menu_data = data
            st.rerun()

# --- EDITOR EN PANTALLA ---
if st.session_state.menu_data:
    st.markdown("---")
    st.subheader("🔍 Revisa y Edita los Alérgenos")
    st.info("La IA no sabe si la comida es congelada o casera. Aquí puedes corregirlo manualmente.")
    
    data = st.session_state.menu_data
    
    # Nombre Restaurante Editable
    data["restaurant_name"] = st.text_input("Nombre Restaurante", data.get("restaurant_name", ""))
    
    # Iterar categorías y platos para crear el formulario
    for cat_idx, category in enumerate(data.get("categories", [])):
        with st.expander(f"📂 {category['name']}", expanded=True):
            # Editar nombre categoría
            category["name"] = st.text_input(f"Categoría {cat_idx+1}", category["name"], key=f"cat_{cat_idx}")
            
            for dish_idx, dish in enumerate(category["dishes"]):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    # Editar Nombre y Precio
                    dish["name"] = st.text_input("Plato", dish["name"], key=f"name_{cat_idx}_{dish_idx}")
                    dish["description"] = st.text_area("Descripción", dish.get("description", ""), key=f"desc_{cat_idx}_{dish_idx}", height=68)
                
                with col2:
                    dish["price"] = st.text_input("Precio", dish["price"], key=f"price_{cat_idx}_{dish_idx}")
                    # SELECTOR MÚLTIPLE DE ALÉRGENOS
                    # Aquí es donde ocurre la magia: El usuario marca lo que quiera
                    current_allergens = [a.lower() for a in dish.get("allergens", [])]
                    # Limpiamos para que coincida con las opciones
                    valid_defaults = [a for a in current_allergens if a in ALLERGEN_OPTIONS]
                    
                    selected = st.multiselect(
                        "Alérgenos",
                        options=ALLERGEN_OPTIONS,
                        default=valid_defaults,
                        key=f"all_{cat_idx}_{dish_idx}"
                    )
                    dish["allergens"] = selected
                    
                st.markdown("---")

    # Botón final
    st.markdown("### ¿Todo listo?")
    if st.button("⬇️ 2. DESCARGAR WORD DEFINITIVO"):
        docx = create_word(st.session_state.menu_data)
        st.download_button(
            label="DESCARGAR CARTA.DOCX",
            data=docx,
            file_name="Carta_Revisada.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
