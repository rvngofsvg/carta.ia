from pathlib import Path
import re

path = Path("app.py")
s = path.read_text(encoding="utf-8")
original = s

# 1) Imports and model constants.
s = s.replace("from google import genai\nfrom google.genai import types as genai_types\n", "")
s = s.replace(
    "from ai_design import render_ai_design_mode\n",
    "from ai_design import render_ai_design_mode\n"
    "from qwen_core import (\n"
    "    QWEN_FLASH, QWEN_MAX, QWEN_OMNI, ensure_configured,\n"
    "    menu_json_from_text, menu_json_from_image, transcribe_menu_page,\n"
    "    allergen_reasoning_json, translate_json, audio_menu_json,\n"
    ")\n",
)
s = s.replace('MODELO_A_USAR = "gemini-3.8-flash"\nMODELO_ALERGENOS = "gemini-3.1-pro-preview"',
              'MODELO_A_USAR = QWEN_FLASH\nMODELO_ALERGENOS = QWEN_MAX')

# 2) Remove Gemini key/client compatibility block and require Alibaba instead.
pattern = re.compile(
    r"# ======================================================\n# API KEY\n# ======================================================\n.*?"
    r"# ======================================================\n# LECTURA DE ARCHIVOS\n# ======================================================",
    re.S,
)
replacement = '''# ======================================================
# QWEN / ALIBABA MODEL STUDIO
# ======================================================
# La clave permanece exclusivamente en Streamlit Secrets. No se muestra al cliente.
try:
    ensure_configured()
except RuntimeError as exc:
    st.error(f"❌ {exc}")
    st.stop()


# ======================================================
# LECTURA DE ARCHIVOS
# ======================================================'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit("No se pudo sustituir el bloque de API Gemini")

# 3) Scanned PDF: Qwen vision instead of Gemini compatibility wrapper.
s = s.replace("def extract_text_from_pdf_scanned_with_gemini(file):", "def extract_text_from_pdf_scanned_with_qwen(file):")
s = s.replace("        model = _GeminiModelCompat(MODELO_A_USAR)\n", "")
old_scan = '''                response = model.generate_content(
                    [
                        "Transcribe literalmente todo el texto visible de esta página de menú. "
                        "No resumas. No inventes. Devuelve texto plano.",
                        img,
                    ],
                    request_options={"timeout": 120},
                )
                page_text = (response.text or "").strip()'''
new_scan = '''                page_text = (transcribe_menu_page(img) or "").strip()'''
if old_scan not in s:
    raise SystemExit("No se encontró el bloque de transcripción escaneada")
s = s.replace(old_scan, new_scan, 1)
s = s.replace("extract_text_from_pdf_scanned_with_gemini(uploaded_file)", "extract_text_from_pdf_scanned_with_qwen(uploaded_file)")

# 4) Remove Gemini structured helper. Qwen helpers live in qwen_core.py.
pattern = re.compile(r"\ndef _gemini_menu_json\(contents\):\n.*?\n\nALLERGEN_AI_SCHEMA =", re.S)
s, n = pattern.subn("\nALLERGEN_AI_SCHEMA =", s, count=1)
if n != 1:
    raise SystemExit("No se pudo eliminar _gemini_menu_json")

# 5) Replace specialist allergen function with Qwen Max reasoning.
start = s.index("def infer_allergens_with_best_model(data):")
end = s.index("def _word_or_phrase(text, phrase):", start)
new_infer = '''def infer_allergens_with_best_model(data):
    dishes = []
    for c_idx, category in enumerate(data.get("categories", [])):
        for d_idx, dish in enumerate(category.get("dishes", [])):
            dishes.append({
                "category_index": c_idx,
                "dish_index": d_idx,
                "category": str(category.get("name") or ""),
                "name": str(dish.get("name") or ""),
                "description": str(dish.get("description") or ""),
            })
    if not dishes:
        return data

    system_instruction = """
Eres un especialista en clasificación de los 14 alérgenos de declaración obligatoria del Reglamento (UE) 1169/2011 y en cocina de restauración española e internacional.
Tu trabajo es estimar qué alérgenos contiene normalmente cada plato usando TODA la información disponible: nombre, descripción, categoría y conocimiento culinario de preparaciones estándar.
No te limites a buscar palabras literales: razona sobre la composición habitual de platos reconocibles (por ejemplo croquetas, tiramisú, carbonara, rebozados, pesto, hummus, salsas, panes y masas).
No inventes contaminación cruzada ni trazas si no están indicadas. Respeta expresiones explícitas como "sin gluten". Distingue cacahuete de frutos de cáscara y crustáceos de moluscos.
Si una receta tiene variantes razonables, elige la clasificación más probable y baja la confianza, en vez de omitir automáticamente todos los alérgenos.
Los únicos valores permitidos son: gluten, crustaceos, huevos, pescado, cacahuetes, soja, lacteos, frutos de cascara, apio, mostaza, sesamo, sulfitos, altramuces, moluscos.
La selección podrá ser corregida manualmente después por el establecimiento.
"""
    prompt = (
        "Analiza todos estos platos en una sola pasada. Devuelve un objeto JSON con una clave items. "
        "Cada item debe contener category_index, dish_index, allergens, confidence (alta/media/baja) y reason. "
        "Mantén category_index y dish_index exactamente.\\n\\n" + json.dumps(dishes, ensure_ascii=False)
    )

    try:
        result, model_name = allergen_reasoning_json(system_instruction, prompt)
        seen = 0
        for item in result.get("items", []):
            c_idx = int(item.get("category_index", -1))
            d_idx = int(item.get("dish_index", -1))
            if c_idx < 0 or d_idx < 0:
                continue
            try:
                dish = data["categories"][c_idx]["dishes"][d_idx]
            except (KeyError, IndexError, TypeError):
                continue
            dish["allergens"] = get_ordered_allergens(item.get("allergens", []))
            dish["_allergen_ai_confidence"] = item.get("confidence", "")
            dish["_allergen_ai_reason"] = item.get("reason", "")
            seen += 1
        if seen:
            data["_allergen_model"] = model_name
            return data
        raise ValueError("Qwen Max no devolvió platos clasificables")
    except Exception as exc:
        data["_allergen_model"] = "reglas locales (fallback)"
        data["_allergen_model_error"] = str(exc)[-800:]
        return data

'''
s = s[:start] + new_infer + s[end:]

# 6) Main menu analysis through Qwen Flash.
s = s.replace('''            if content_type == "image":
                data = _gemini_menu_json([prompt, content])
            else:
                data = _gemini_menu_json(prompt + "\\n\\nMENÚ:\\n" + str(content))''', '''            if content_type == "image":
                data = menu_json_from_image(prompt, content)
            else:
                data = menu_json_from_text(prompt, content)''')

# 7) Audio through Qwen Omni.
old_audio = '''    part = genai_types.Part.from_bytes(data=audio_bytes, mime_type=_audio_mime(audio_file))
    data = _gemini_menu_json([audio_prompt, part])'''
new_audio = '''    data = audio_menu_json(audio_prompt, audio_bytes, _audio_mime(audio_file))'''
if old_audio not in s:
    raise SystemExit("No se encontró el bloque Gemini de audio")
s = s.replace(old_audio, new_audio, 1)

# 8) Translation through Qwen Flash.
old_translation = '''    response = GENAI_CLIENT.models.generate_content(
        model=MODELO_A_USAR,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=TRANSLATION_SCHEMA,
        ),
    )
    translated_payload = parse_json_response(response.text)'''
new_translation = '''    translated_payload = translate_json(prompt)'''
if old_translation not in s:
    raise SystemExit("No se encontró el bloque Gemini de traducción")
s = s.replace(old_translation, new_translation, 1)

# 9) Vendor wording cleanup.
s = s.replace("si Gemini ya dejó el número dentro del nombre", "si la IA ya dejó el número dentro del nombre")
s = s.replace("sirven para reforzar a Gemini", "sirven para reforzar a la IA")

# 10) Guardrail: allergens must remain AFTER price in all principal exports.
required_fragments = [
    'price_run = p.add_run("\\t" + format_price(dish.get("price", "")))',
    '_add_allergen_icons_to_run(p, dish.get("allergens", []), width_cm=0.75)',
    'f\'<span class="price">{html_escape(format_price(dish.get("price", "")))}</span>\'',
    'f\'<span class="dish-icons">{icons}</span></div>{desc_html}</div>\'',
]
for frag in required_fragments:
    if frag not in s:
        raise SystemExit(f"Falta guardrail de precio/alérgenos: {frag}")

# Verify ordering within main Word function.
word_anchor = s.index('price_run = p.add_run("\\t" + format_price(dish.get("price", "")))')
icon_anchor = s.index('_add_allergen_icons_to_run(p, dish.get("allergens", []), width_cm=0.75)', word_anchor)
if not word_anchor < icon_anchor:
    raise SystemExit("Los alérgenos Word no están después del precio")

# Verify PDF ordering.
pdf_price = s.index('f\'<span class="price">{html_escape(format_price(dish.get("price", "")))}</span>\'')
pdf_icons = s.index('f\'<span class="dish-icons">{icons}</span></div>{desc_html}</div>\'', pdf_price)
if not pdf_price < pdf_icons:
    raise SystemExit("Los alérgenos PDF no están después del precio")

# No Gemini runtime remnants should remain.
for forbidden in ("GENAI_CLIENT", "genai_types", "GEMINI_API_KEY", "_GeminiModelCompat", "_gemini_menu_json"):
    if forbidden in s:
        raise SystemExit(f"Quedó una dependencia Gemini activa: {forbidden}")

if s == original:
    raise SystemExit("La migración no produjo cambios")

path.write_text(s, encoding="utf-8")
print("Qwen core migration applied successfully")
