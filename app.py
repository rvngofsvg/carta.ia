import streamlit as st
import google.generativeai as genai
import os
import json
from docx import Document
from docx.shared import Cm, Pt
from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER, WD_LINE_SPACING
from io import BytesIO
from PIL import Image
from pypdf import PdfReader

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Sistema Integral - Serval TECH", layout="wide")

# --- 1. CONFIGURACIÓN ---
MODELO_A_USAR = "gemini-1.5-flash" 

SANGRIA_CATEGORIA = Cm(0.8)  
SANGRIA_PLATOS = Cm(0.8)     
ESPACIO_PLATOS = Pt(3) 
MARGEN_INFERIOR_FORZADO = Cm(4.5) 

# --- 2. DICCIONARIOS MAESTROS (NORMAL Y EXTREMO) ---
DICCIONARIO_NORMAL = {
    "gluten": ["pan", "trigo", "harina", "pasta", "galleta", "bizcocho", "rebozado", "cerveza", "tempura", "panko", "lasaña", "fideos", "salsa de soja", "brioche", "burger", "bocadillo", "sandwich", "croutons", "picatostes", "seitan", "couscous", "bulgur", "tostada", "regaña", "focaccia", "gyoza", "bao", "mollete"],
    "lacteos": ["queso", "nata", "leche", "yogur", "mantequilla", "bechamel", "mozzarella", "parmesano", "cheddar", "helado", "burrata", "carbonara", "feta", "crema", "lactosa", "mascarpone", "tiramisu", "cheesecake", "stracciatella", "tzatziki", "gorgonzola", "brioche", "chocolate blanco", "creme brulee"],
    "huevos": ["huevo", "tortilla", "mayonesa", "mahonesa", "merengue", "alioli", "bizcocho", "quiche", "brioche", "tarta", "revuelto", "poché", "yema", "clara", "carbonara", "salsa holandesa", "salsa tartara", "rebozado", "empanado", "crema catalana"],
    "crustaceos": ["gamba", "langostino", "cigala", "bogavante", "cangrejo", "buey de mar", "camaron", "carabinero", "txangurro", "quisquilla", "bisque"],
    "moluscos": ["pulpo", "calamar", "sepia", "mejillon", "almeja", "chipiron", "vieira", "ostra", "navaja", "berberecho", "zamburiña", "salsa de ostras"],
    "pescado": ["pescado", "atun", "salmon", "bacalao", "merluza", "anchoa", "sardina", "sushi", "sashimi", "tataki", "ceviche", "ventresca", "bonito", "dorada", "lubina", "salsa perrins", "worcestershire", "kimchi", "dashi", "katsuobushi"],
    "cacahuetes": ["cacahuete", "mani", "satay", "crema de cacahuete"],
    "soja": ["soja", "edamame", "tofu", "miso", "salsa de soja", "teriyaki", "wakame", "yuba", "tamari", "kimchi"],
    "frutos de cascara": ["almendra", "nuez", "avellana", "pistacho", "anacardo", "pesto", "romesco", "brownie", "nutella", "praliné", "macadamia", "ajoblanco", "nogal", "coco"],
    "mostaza": ["mostaza", "dijon", "salsa barbacoa", "vinagreta", "mayonesa"],
    "sesamo": ["sesamo", "ajonjoli", "tahini", "hummus", "pan de hamburguesa", "aceite de sesamo", "bagel", "tataki", "poke"],
    "apio": ["apio", "caldo", "sofrito", "bloody mary", "salsa española"],
    "sulfitos": ["vino", "vinagre", "sulfitos", "cava", "champagne", "mostaza antigua", "martini", "vermut", "cerveza"],
    "altramuces": ["altramuz", "altramuces"]
}

DICCIONARIO_EXTREMO = {
    "gluten": DICCIONARIO_NORMAL["gluten"] + ["croqueta", "raba", "calamar", "alita", "natxo", "nacho", "morcilla", "chistorra", "torrezno", "cachopo", "codillo", "hamburguesa", "perrito"],
    "lacteos": DICCIONARIO_NORMAL["lacteos"] + ["croqueta", "raba", "calamar", "alita", "natxo", "nacho", "morcilla", "cachopo", "alioli", "ali-oli", "codillo", "hamburguesa", "perrito"],
    "huevos": DICCIONARIO_NORMAL["huevos"] + ["croqueta", "raba", "calamar", "alita", "morcilla", "chistorra", "cachopo", "codillo", "hamburguesa", "perrito", "ali-oli"],
    "crustaceos": DICCIONARIO_NORMAL["crustaceos"] + ["croqueta", "raba", "calamar", "alita"],
    "moluscos": DICCIONARIO_NORMAL["moluscos"] + ["croqueta", "raba", "alita"],
    "pescado": DICCIONARIO_NORMAL["pescado"] + ["croqueta", "raba", "calamar", "alita"],
    "cacahuetes": DICCIONARIO_NORMAL["cacahuetes"],
    "soja": DICCIONARIO_NORMAL["soja"] + ["croqueta", "raba", "calamar", "alita", "morcilla", "chistorra", "torrezno", "codillo", "hamburguesa", "perrito"],
    "frutos de cascara": DICCIONARIO_NORMAL["frutos de cascara"] + ["morcilla"],
    "mostaza": DICCIONARIO_NORMAL["mostaza"] + ["croqueta", "raba", "calamar", "alita", "morcilla", "torrezno", "alioli", "ali-oli", "hamburguesa", "perrito"],
    "sesamo": DICCIONARIO_NORMAL["sesamo"] + ["croqueta", "raba", "calamar", "alita", "morcilla", "hamburguesa", "perrito"],
    "apio": DICCIONARIO_NORMAL["apio"] + ["croqueta", "raba", "calamar", "alita", "morcilla", "alioli", "ali-oli", "codillo"],
    "sulfitos": DICCIONARIO_NORMAL["sulfitos"] + ["morcilla", "carrillera"],
    "altramuces": DICCIONARIO_NORMAL["altramuces"]
}

ALLERGEN_OPTIONS = list(DICCIONARIO_NORMAL.keys())

# --- 3. RUTAS ---
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
try: API_KEY = st.secrets["GEMINI_API_KEY"]
except: API_KEY = os.getenv("GEMINI_API_KEY", "")

if not API_KEY:
    st.error("❌ Falta la GEMINI_API_KEY en los Secrets.")
    st.stop()

genai.configure(api_key=API_KEY)

# --- 5. MAPEO ICONOS ---
if not ICONOS_DIR: ICONOS_DIR = os.path.join(BASE_DIR, "Public", "Iconos")
def get_icon_path(icon_name): return os.path.join(ICONOS_DIR, icon_name)

ICON_MAP = {
    "gluten": get_icon_path("gluten.png"), "crustaceos": get_icon_path("gambas.png"),
    "huevos": get_icon_path("huevo.png"), "pescado": get_icon_path("pescado.png"),
    "cacahuetes": get_icon_path("cacahuetes.png"), "soja": get_icon_path("soja.png"),
    "lacteos": get_icon_path("lacteos.png"), "frutos de cascara": get_icon_path("frutos_secos.png"),
    "apio": get_icon_path("apio.png"), "mostaza": get_icon_path("mostaza.png"),
    "sesamo": get_icon_path("sesamo.png"), "sulfitos": get_icon_path("sulfitos.png"),
    "altramuces": get_icon_path("altramuces.png"), "moluscos": get_icon_path("moluscos.png")
}

# --- 6. LECTURA ---
def extract_text_from_pdf(file):
    try:
        reader = PdfReader(file)
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t: text += t + "\n"
        return text
    except: return None

def extract_text_from_docx(file):
    try:
        doc = Document(file)
        text = "\n".join([p.text for p in doc.paragraphs])
        for table in doc.tables:
            for row in table.rows: text += " | ".join([cell.text for cell in row.cells]) + "\n"
        return text
    except: return None

# --- 7. ANÁLISIS ---
def analyze_content(content, content_type="image", modo="Normal"):
    model = genai.GenerativeModel(MODELO_A_USAR)
    
    if modo == "Extremo":
        diccionario_activo = DICCIONARIO_EXTREMO
        regla_2 = """
        REGLA 2 (CONTAMINACIÓN CRUZADA Y ALÉRGENOS AL MÁXIMO): 
        - Asume SIEMPRE el peor escenario para proteger al cliente de demandas.
        - Si es un frito de bar (croquetas, rabas, calamares, alitas, torreznos, cachopo), asume freidora compartida y producto industrial. Añade trazas de pescado, moluscos, crustaceos, soja, lacteos, mostaza, apio, sesamo y gluten.
        """
    else:
        diccionario_activo = DICCIONARIO_NORMAL
        regla_2 = """
        REGLA 2 (ALÉRGENOS - MODO ESTÁNDAR): 
        - Usa tu conocimiento para listar los alérgenos propios de la receta tradicional.
        """

    base_prompt = f"""
    Eres un Transcriptor Profesional y un Nutricionista.
    
    REGLA 1 (TRANSCRIPCIÓN LITERAL E IDIOMA ORIGINAL):
    - Extrae Nombre, Descripción y Precio EXACTAMENTE como aparecen en la imagen. NO RESUMAS NADA.
    - PROHIBIDO TRADUCIR. Mantén el idioma original de la carta (ej. si dice "Smash Burger", "Bacon", "Pulled Pork", cópialo exactamente así).
    - ANÁLISIS MENTAL DE ALÉRGENOS: Aunque escribas el plato en su idioma original, debes usar tu conocimiento para identificar los alérgenos de esas palabras extranjeras. Por ejemplo: si lees "Cheese" o "Peanut", mantén esa palabra intacta, pero incluye 'lacteos' o 'cacahuetes' en la lista de alérgenos.
    
    ⚠️ REGLA 3 CRÍTICA (TODO EL TEXTO RESTANTE):
    - Extrae literalmente cualquier otro texto, párrafo o frase que aparezca en la imagen y que no sean platos ni categorías.
    - Copia todo este texto tal cual está escrito y ponlo en el campo "texto_extra". No lo clasifiques, solo cópialo.
    
    {regla_2}
    
    Salida JSON (sin markdown):
    {{
        "restaurant_name": "Nombre",
        "texto_extra": "Copia aquí literalmente todo el texto sobrante de la imagen",
        "categories": [
            {{
                "name": "Categoría",
                "dishes": [
                    {{
                        "name": "Plato",
                        "description": "Texto literal en idioma original",
                        "price": "10.50",
                        "allergens": ["gluten", "lacteos"] 
                    }}
                ]
            }}
        ]
    }}
    """
    try:
        with st.spinner(f"🧠 Analizando ({MODELO_A_USAR})..."):
            if content_type == "image": response = model.generate_content([base_prompt, content])
            else: response = model.generate_content(base_prompt + "\n\nMENÚ:\n" + str(content))
            
            text = response.text.replace('```json', '').replace('```', '').strip()
            s, e = text.find('{'), text.rfind('}') + 1
            if s != -1 and e != -1: text = text[s:e]
            data = json.loads(text)

            for category in data.get("categories", []):
                for dish in category["dishes"]:
                    d_name = dish.get("name") or ""
                    d_desc = dish.get("description") or ""
                    full_text = (d_name + " " + d_desc).lower()
                    current = [a.lower().strip() for a in dish.get("allergens", [])]
                    for allergen, keywords in diccionario_activo.items():
                        if any(k in full_text for k in keywords):
                            if allergen not in current: current.append(allergen)
                    dish["allergens"] = current
            return data
    except Exception as e: st.error(f"Error IA: {e}"); return None

# --- FUNCIONES AUXILIARES ---
def release_paragraph_constraints(paragraph, indent, is_dish=False):
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = ESPACIO_PLATOS if is_dish else Pt(0)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    paragraph.paragraph_format.left_indent = indent

# --- 8. GENERADORES DE WORD ---
def create_word(data):
    doc = Document(PLANTILLA_PATH)
    for section in doc.sections: section.bottom_margin = MARGEN_INFERIOR_FORZADO
    
    rest_name = data.get("restaurant_name", "MENÚ")
    try: p_title = doc.add_heading(rest_name, 0); release_paragraph_constraints(p_title, SANGRIA_CATEGORIA)
    except: p_title = doc.add_paragraph(rest_name); p_title.bold = True; release_paragraph_constraints(p_title, SANGRIA_CATEGORIA)

    for category in data.get("categories", []):
        p_cat = doc.add_heading(category["name"], level=1); release_paragraph_constraints(p_cat, SANGRIA_CATEGORIA)
        p_cat.paragraph_format.space_before = Pt(6) 
        for dish in category["dishes"]:
            p = doc.add_paragraph(); release_paragraph_constraints(p, SANGRIA_PLATOS, is_dish=True)
            p.paragraph_format.tab_stops.add_tab_stop(Cm(14.5), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            p.add_run(dish.get('name', 'Plato')).bold = True
            p.add_run(f"\t{dish.get('price', '')}€\t")
            
            run_icons = p.add_run()
            for allergen in dish.get("allergens", []):
                key = allergen.lower().strip()
                if "frutos secos" in key: key = "frutos de cascara"
                if key in ICON_MAP and os.path.exists(ICON_MAP[key]):
                    try: run_icons.add_picture(ICON_MAP[key], width=Cm(0.38))
                    except: pass
            
            if dish.get('description'):
                p_desc = doc.add_paragraph(); release_paragraph_constraints(p_desc, SANGRIA_PLATOS, is_dish=True)
                p_desc.add_run(dish['description']).italic = True

    if data.get("texto_extra"):
        doc.add_paragraph()
        p_extra = doc.add_paragraph(); release_paragraph_constraints(p_extra, SANGRIA_CATEGORIA)
        p_extra.add_run(data["texto_extra"]).italic = True

    buffer = BytesIO(); doc.save(buffer); buffer.seek(0); return buffer

def create_clean_word(data):
    doc = Document(PLANTILLA_PATH)
    for section in doc.sections: section.bottom_margin = MARGEN_INFERIOR_FORZADO
    
    rest_name = data.get("restaurant_name", "MENÚ")
    try: p_title = doc.add_heading(rest_name, 0); release_paragraph_constraints(p_title, SANGRIA_CATEGORIA)
    except: p_title = doc.add_paragraph(rest_name); p_title.bold = True; release_paragraph_constraints(p_title, SANGRIA_CATEGORIA)

    for category in data.get("categories", []):
        p_cat = doc.add_heading(category["name"], level=1); release_paragraph_constraints(p_cat, SANGRIA_CATEGORIA)
        p_cat.paragraph_format.space_before = Pt(6)
        for dish in category["dishes"]:
            p = doc.add_paragraph(); release_paragraph_constraints(p, SANGRIA_PLATOS, is_dish=True)
            p.paragraph_format.tab_stops.add_tab_stop(Cm(16.0), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            p.add_run(dish.get('name', 'Plato')).bold = True
            p.add_run(f"\t{dish.get('price', '')}€")
            if dish.get('description'):
                p_desc = doc.add_paragraph(); release_paragraph_constraints(p_desc, SANGRIA_PLATOS, is_dish=True)
                p_desc.add_run(dish['description']).italic = True
                
    if data.get("texto_extra"):
        doc.add_paragraph()
        p_extra = doc.add_paragraph(); release_paragraph_constraints(p_extra, SANGRIA_CATEGORIA)
        p_extra.add_run(data["texto_extra"]).italic = True

    buffer = BytesIO(); doc.save(buffer); buffer.seek(0); return buffer

# ==========================================
# MENÚ LATERAL Y NAVEGACIÓN
# ==========================================
st.sidebar.title("Menú Principal 🚀")
app_mode = st.sidebar.radio("Navegación", ["📝 Generador de Cartas", "📡 Radar de Clientes", "📄 Convertidor PDF a Word"])

# ==========================================
# MÓDULO 1: GENERADOR DE CARTAS
# ==========================================
if app_mode == "📝 Generador de Cartas":
    st.title("Sistema Integral de Cartas 🥘")
    modo_seguridad = st.radio("Perfil de cocina:", ["🟢 Normal", "🔴 Extremo"])
    modo_param = "Extremo" if "Extremo" in modo_seguridad else "Normal"

    if "menu_data" not in st.session_state: st.session_state.menu_data = None
    uploaded_file = st.file_uploader("Sube el Menú", type=["jpg", "png", "pdf", "docx"])

    if uploaded_file and st.button("1. ANALIZAR MENÚ"):
        ft = uploaded_file.name.split('.')[-1].lower()
        data = None
        if ft in ['jpg','png','jpeg']: data = analyze_content(Image.open(uploaded_file), "image", modo_param)
        elif ft == 'pdf': data = analyze_content(extract_text_from_pdf(uploaded_file), "text", modo_param)
        elif ft == 'docx': data = analyze_content(extract_text_from_docx(uploaded_file), "text", modo_param)
        if data: st.session_state.menu_data = data; st.rerun()

    if st.session_state.menu_data:
        st.markdown("---")
        tab1, tab2 = st.tabs(["🍤 Con Alérgenos", "📄 Texto Limpio"])
        data = st.session_state.menu_data
        
        with tab1:
            data["restaurant_name"] = st.text_input("Restaurante", data.get("restaurant_name", ""))
            data["texto_extra"] = st.text_area("📝 Texto suelto detectado", data.get("texto_extra", ""), height=100)
            for c_idx, cat in enumerate(data.get("categories", [])):
                with st.expander(f"📂 {cat['name']}", expanded=True):
                    cat["name"] = st.text_input(f"Categoría", cat["name"], key=f"c_{c_idx}")
                    for d_idx, dish in enumerate(cat["dishes"]):
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            dish["name"] = st.text_input("Plato", dish.get("name",""), key=f"n_{c_idx}_{d_idx}")
                            dish["description"] = st.text_area("Desc", dish.get("description",""), key=f"d_{c_idx}_{d_idx}", height=68)
                        with c2:
                            dish["price"] = st.text_input("Precio", dish.get("price",""), key=f"p_{c_idx}_{d_idx}")
                            sel = st.multiselect("Alérgenos", ALLERGEN_OPTIONS, default=[x for x in dish.get("allergens", []) if x in ALLERGEN_OPTIONS], key=f"a_{c_idx}_{d_idx}")
                            dish["allergens"] = sel
            st.download_button("⬇️ DESCARGAR CARTA COMPLETA", create_word(data), "Carta_Alérgenos.docx")

        with tab2:
            st.download_button("⬇️ DESCARGAR TEXTO LIMPIO", create_clean_word(data), "Carta_Limpia.docx")

# ==========================================
# MÓDULO 2: RADAR DE CLIENTES
# ==========================================
elif app_mode == "📡 Radar de Clientes":
    st.title("Radar de Redes y Mapas 📡")
    import urllib.parse
    c1, c2 = st.columns(2)
    with c1: r_nombre = st.text_input("Nombre local")
    with c2: r_prov = st.text_input("Provincia")
    if st.button("🚀 Buscar"):
        if r_nombre and r_prov:
            q = urllib.parse.quote_plus(f"{r_nombre} {r_prov}")
            st.markdown(f"### 📍 [Google Maps](https://www.google.com/maps/search/?api=1&query={q})")
            st.markdown(f"### 📸 [Instagram](https://www.google.com/search?q=site%3Ainstagram.com+{q})")
            st.markdown(f"### 📘 [Facebook](https://www.google.com/search?q=site%3Afacebook.com+{q})")
            st.markdown(f"### 🦉 [TripAdvisor](https://www.google.com/search?q=site%3Atripadvisor.es+{q})")
            st.markdown(f"### 🌐 [Búsqueda General Carta](https://www.google.com/search?q={q}+carta+menu)")

# ==========================================
# MÓDULO 3: CONVERTIDOR PDF A WORD
# ==========================================
elif app_mode == "📄 Convertidor PDF a Word":
    st.title("Convertidor Directo 📄➡️📝")
    import tempfile
    from pdf2docx import Converter
    if "w_bytes" not in st.session_state: st.session_state.w_bytes = None
    up_pdf = st.file_uploader("Sube PDF", type=["pdf"])
    if up_pdf:
        if st.button("🔄 Convertir"):
            with st.spinner("Convirtiendo..."):
                t_in = os.path.join(tempfile.gettempdir(), "in.pdf")
                t_out = os.path.join(tempfile.gettempdir(), "out.docx")
                with open(t_in, "wb") as f: f.write(up_pdf.getvalue())
                cv = Converter(t_in); cv.convert(t_out); cv.close()
                with open(t_out, "rb") as f: st.session_state.w_bytes = f.read()
        if st.session_state.w_bytes:
            st.download_button("⬇️ Descargar Word", st.session_state.w_bytes, f"{up_pdf.name.split('.')[0]}.docx")
            
