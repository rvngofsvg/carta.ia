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
MODELO_A_USAR = "gemini-2.5-flash" # O "gemini-1.5-flash" si prefieres

# --- 2. EL SUPER DICCIONARIO DE SEGURIDAD (La red de seguridad) ---
# Si Python detecta estas palabras, marca el icono OBLIGATORIAMENTE.
# Incluye términos culinarios técnicos y salsas complejas.

DICCIONARIO_MAESTRO = {
    "gluten": [
        "pan", "trigo", "harina", "pasta", "galleta", "bizcocho", "rebozado", "cerveza", 
        "espelta", "centeno", "cebada", "crostini", "tostada", "brioche", "burger", "bocadillo", 
        "sandwich", "tempura", "panko", "gyoza", "focaccia", "pizza", "couscous", "bulgur", 
        "seitan", "bechamel", "velouté", "croqueta", "empanada", "lasaña", "canelones", "fideos",
        "udon", "ramen", "salsa de soja", "teriyaki", "hojaldre", "crumble", "croutons", "picatostes"
    ],
    "lacteos": [
        "queso", "nata", "leche", "yogur", "crema", "mantequilla", "bechamel", "burrata", 
        "mozzarella", "parmesano", "cheddar", "lactosa", "helado", "roquefort", "gorgonzola", 
        "feta", "mascarpone", "ricotta", "brie", "camembert", "manchego", "cabra", "oveja",
        "tzatziki", "ghee", "paneer", "dulce de leche", "tiramisu", "cheesecake", "stracciatella",
        "parmentier", "carbonara", "mousse", "chantilly"
    ],
    "huevos": [
        "huevo", "tortilla", "mayonesa", "mahonesa", "merengue", "yema", "clara", "alioli", 
        "holandesa", "carbonara", "bizcocho", "quiche", "revuelto", "poché", "frito", "coulant",
        "brioche", "tiramisu", "crep", "pancake", "tarta", "flan", "natillas"
    ],
    "crustaceos": [
        "gamba", "langostino", "cigala", "bogavante", "cangrejo", "buey de mar", "camaron", 
        "nécora", "carabinero", "quisquilla", "percebe", "bisque", "paella marinera", "txangurro"
    ],
    "moluscos": [
        "pulpo", "calamar", "sepia", "mejillon", "almeja", "chipiron", "vieira", "ostra", 
        "navaja", "berberecho", "coquina", "zamburiña", "rabas", "choquitos", "oreja de mar"
    ],
    "pescado": [
        "pescado", "atun", "salmon", "bacalao", "merluza", "anchoa", "boqueron", "sardina", 
        "lubina", "dorada", "rodaballo", "rape", "lenguado", "tataki", "sashimi", "ceviche", 
        "dashi", "salsa perrins", "worcestershire", "surimi", "gulas", "caviar", "huevas"
    ],
    "cacahuetes": [
        "cacahuete", "mani", "satay", "crema de cacahuete", "mantequilla de mani"
    ],
    "soja": [
        "soja", "edamame", "tofu", "miso", "salsa de soja", "tamari", "teriyaki", "tempeh", 
        "yuba", "lecitina de soja", "wakame" # A veces la ensalada wakame lleva sésamo y soja
    ],
    "frutos de cascara": [
        "almendra", "nuez", "nueces", "avellana", "pistacho", "anacardo", "piñon", "praliné", 
        "macadamia", "pecana", "mazapan", "turron", "pesto", "romesco", "ajoblanco", "baklava", 
        "nocilla", "nutella", "brownie" # A menudo lleva nueces
    ],
    "mostaza": [
        "mostaza", "dijon", "antigua", "vinagreta de mostaza", "salsa barbacoa" # A veces lleva mostaza
    ],
    "sesamo": [
        "sesamo", "ajonjoli", "tahini", "hummus", "halva", "tataki", "poké", "aceite de sesamo", 
        "pan de hamburguesa" # A veces lleva sésamo
    ],
    "apio": [
        "apio", "caldo de verduras", "mirepoix", "sofrito", "bloody mary", "waldorf"
    ],
    "sulfitos": [
        "vino", "vinagre", "sulfitos", "reducción", "cava", "champagne", "cerveza", "sidra", 
        "mostaza" # A veces lleva vinagre con sulfitos
    ],
    "altramuces": ["altramuz", "altramuces", "harina de altramuz"],
}

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

# --- 7. ANÁLISIS BLINDADO (IA + DICCIONARIO) ---
def analyze_content(content, content_type="image"):
    model = genai.GenerativeModel(MODELO_A_USAR)
    
    # PROMPT AVANZADO: Instrucciones de "Chef Ejecutivo de Seguridad"
    base_prompt = """
    Analiza este menú actuando como un AUDITOR DE SEGURIDAD ALIMENTARIA muy estricto.
    
    TAREA:
    1. Extrae Nombre del Restaurante, Categorías, Platos y PRECIOS EXACTOS.
    2. DETECCIÓN DE ALÉRGENOS (CRÍTICO):
       - No te limites a los ingredientes obvios. Piensa en la elaboración.
       - Si ves "Tempura", "Rebozado", "Empanado" -> Marca GLUTEN.
       - Si ves "Salsa Tartara" o "Mayonesa" -> Marca HUEVOS.
       - Si ves "Pesto" -> Marca FRUTOS DE CASCARA y LACTEOS.
       - Si ves "Teriyaki" o "Salsa de Soja" -> Marca SOJA y GLUTEN.
       - Si ves "Brioche" -> Marca GLUTEN, HUEVOS y LACTEOS.
       - Si ves "Surimi" -> Marca PESCADO y GLUTEN.
       - Ante la más mínima duda de contaminación cruzada o ingrediente oculto, MARCALO.
    
    FORMATO JSON EXACTO (sin markdown):
    {
        "restaurant_name": "Nombre",
        "categories": [
            {
                "name": "Categoría",
                "dishes": [
                    {
                        "name": "Nombre del Plato",
                        "description": "Descripción completa",
                        "price": "10.50",
                        "allergens": ["gluten", "lacteos", "huevos"] 
                    }
                ]
            }
        ]
    }
    """
    
    try:
        with st.spinner(f"🕵️‍♀️ Analizando menú con protocolo de seguridad máxima..."):
            if content_type == "image":
                response = model.generate_content([base_prompt, content])
            else:
                response = model.generate_content(base_prompt + "\n\nMENÚ:\n" + content)
            
            text = response.text.replace('```json', '').replace('```', '').strip()
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end != -1: text = text[start:end]
            
            data = json.loads(text)

            # --- CAPA DE SEGURIDAD 2: EL SUPER DICCIONARIO ---
            # Python revisa lo que la IA pudo haber pasado por alto
            for category in data.get("categories", []):
                for dish in category["dishes"]:
                    # Analizamos TODO el texto del plato (nombre + descripción)
                    full_text = (dish.get("name", "") + " " + dish.get("description", "")).lower()
                    
                    # Lista actual detectada por la IA
                    current_allergens = [a.lower().strip() for a in dish.get("allergens", [])]
                    
                    # Chequeo contra el DICCIONARIO MAESTRO
                    for allergen, keywords in DICCIONARIO_MAESTRO.items():
                        # Si alguna palabra clave compleja aparece...
                        if any(keyword in full_text for keyword in keywords):
                            if allergen not in current_allergens:
                                current_allergens.append(allergen)
                                # (Opcional) Debug
                                # print(f"🛡️ SEGURIDAD ACTIVA: Se detectó '{allergen}' en '{dish['name']}'")
                    
                    dish["allergens"] = current_allergens
            
            return data

    except Exception as e:
        st.error(f"Error en análisis: {e}")
        return None

# --- 8. GENERACIÓN WORD (PROFESIONAL) ---
def create_word(data):
    if not PLANTILLA_PATH or not os.path.exists(PLANTILLA_PATH):
        st.error(f"❌ Falta plantilla en: {PLANTILLA_PATH}")
        st.stop()
        
    doc = Document(PLANTILLA_PATH)
    try: doc.add_heading(data.get("restaurant_name", "MENÚ"), 0)
    except: doc.add_paragraph(data.get("restaurant_name", "MENÚ")).bold = True

    for category in data.get("categories", []):
        doc.add_heading(category["name"], level=1)
        for dish in category["dishes"]:
            p = doc.add_paragraph()
            
            # Formato: Nombre ......... Precio [Iconos]
            tab_stops = p.paragraph_format.tab_stops
            tab_stops.add_tab_stop(Cm(16), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            
            p.add_run(dish['name']).bold = True
            p.add_run(f"\t{dish['price']}€  ")
            
            # Iconos juntos (sin espacios extra)
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
            
            if dish.get('description'):
                p_desc = doc.add_paragraph()
                p_desc.add_run(dish['description']).italic = True
                p.paragraph_format.space_after = Pt(2)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# --- 9. INTERFAZ ---
st.title(f"Generador de Cartas 3.0 🍤")

uploaded_file = st.file_uploader("Sube Menú (Foto/PDF/Word)", type=["jpg", "png", "pdf", "docx"])

if uploaded_file is not None:
    file_type = uploaded_file.name.split('.')[-1].lower()
    
    if st.button("GENERAR CARTA"):
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
            st.success("✅ Análisis completado con doble verificación.")
            with st.expander("Ver detalle de detección"):
                st.write(data)
            
            docx = create_word(data)
            st.download_button("📥 DESCARGAR CARTA SEGURA", docx, "Carta_Alergenos.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            
