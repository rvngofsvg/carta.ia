from pathlib import Path

path = Path('qwen_core.py')
s = path.read_text(encoding='utf-8')
original = s

old_post = '''    try:\n        with urllib.request.urlopen(req, timeout=timeout) as response:\n            return json.loads(response.read().decode("utf-8"))\n'''
new_post = '''    try:\n        with urllib.request.urlopen(req, timeout=timeout) as response:\n            parsed = json.loads(response.read().decode("utf-8"))\n            if not isinstance(parsed, dict):\n                raise RuntimeError(\n                    f"Alibaba devolvió un wrapper API inesperado ({type(parsed).__name__}); se esperaba un objeto JSON."\n                )\n            return parsed\n'''
if old_post not in s:
    raise SystemExit('No se encontró _post_json esperado')
s = s.replace(old_post, new_post, 1)

old_parse = '''def parse_json_text(text):\n    raw = (text or "").replace("```json", "").replace("```", "").strip()\n    start = raw.find("{")\n    end = raw.rfind("}") + 1\n    if start != -1 and end > start:\n        raw = raw[start:end]\n    return json.loads(raw)\n\n\n'''
new_parse = r'''def parse_json_text(text):
    raw = (text or "").replace("```json", "").replace("```", "").strip()
    if not raw:
        raise ValueError("La IA devolvió una respuesta JSON vacía.")

    # Primero respeta el JSON completo. Esto permite detectar correctamente
    # arrays de nivel raíz en vez de recortarlos desde el primer '{'.
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Recuperación conservadora cuando el modelo añade texto antes/después.
    obj_start = raw.find("{")
    obj_end = raw.rfind("}") + 1
    if obj_start != -1 and obj_end > obj_start:
        return json.loads(raw[obj_start:obj_end])
    arr_start = raw.find("[")
    arr_end = raw.rfind("]") + 1
    if arr_start != -1 and arr_end > arr_start:
        return json.loads(raw[arr_start:arr_end])
    raise ValueError("No se encontró JSON válido en la respuesta de la IA.")


_MENU_JSON_CONTRACT = r"""
CONTRATO JSON OBLIGATORIO PARA CARTA IA:
- La raíz DEBE ser un objeto JSON, NUNCA un array.
- Usa EXACTAMENTE estas claves en inglés:
{
  "restaurant_name": "Nombre del restaurante o MENÚ si no aparece",
  "texto_extra": "Texto auxiliar o cadena vacía",
  "categories": [
    {
      "name": "Nombre de categoría",
      "category_text": "Nota de categoría o cadena vacía",
      "dishes": [
        {
          "number": "Número o cadena vacía",
          "name": "Nombre del plato",
          "description": "Descripción o cadena vacía",
          "price": "Precio sin inventar o cadena vacía",
          "allergens": [],
          "review_notes": []
        }
      ]
    }
  ]
}
No devuelvas una lista como raíz. No renombres categories/dishes/price/allergens.
""".strip()


def _as_text(value, default=""):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return default
    return str(value).strip()


def _normalize_menu_payload(payload):
    """Normaliza respuestas razonables de Qwen al contrato interno de Carta IA.

    El objetivo es tolerar wrappers o arrays de categorías/platos sin permitir
    que una forma JSON inesperada llegue a app.py y provoque `.get` sobre listas.
    """
    if isinstance(payload, list):
        # Caso frecuente: [{restaurant_name, categories, ...}]
        if len(payload) == 1 and isinstance(payload[0], dict) and any(
            key in payload[0] for key in ("categories", "categorias", "menu", "data", "result")
        ):
            payload = payload[0]
        # Array de categorías.
        elif payload and all(
            isinstance(item, dict) and any(k in item for k in ("dishes", "platos"))
            for item in payload
        ):
            payload = {"restaurant_name": "MENÚ", "texto_extra": "", "categories": payload}
        # Array de platos: lo conservamos dentro de una categoría genérica.
        elif payload and all(isinstance(item, dict) for item in payload):
            payload = {
                "restaurant_name": "MENÚ",
                "texto_extra": "",
                "categories": [{"name": "Carta", "category_text": "", "dishes": payload}],
            }
        else:
            raise ValueError("Qwen devolvió un array que no contiene categorías o platos reconocibles.")

    if not isinstance(payload, dict):
        raise ValueError(f"Qwen devolvió {type(payload).__name__}; se esperaba un objeto de carta.")

    # Algunos modelos añaden un wrapper aunque se solicite JSON Object.
    if not any(k in payload for k in ("categories", "categorias", "dishes", "platos")):
        for wrapper in ("menu", "data", "result"):
            wrapped = payload.get(wrapper)
            if isinstance(wrapped, (dict, list)):
                payload = _normalize_menu_payload(wrapped)
                break

    categories = payload.get("categories")
    if categories is None:
        categories = payload.get("categorias")
    if categories is None and any(k in payload for k in ("dishes", "platos")):
        categories = [payload]
    if isinstance(categories, dict):
        categories = [categories]
    if not isinstance(categories, list):
        raise ValueError("La respuesta de Qwen no contiene una lista de categorías válida.")

    normalized_categories = []
    total_dishes = 0
    for cat in categories:
        if not isinstance(cat, dict):
            continue
        dishes = cat.get("dishes")
        if dishes is None:
            dishes = cat.get("platos")
        if dishes is None:
            dishes = cat.get("items", [])
        if isinstance(dishes, dict):
            dishes = [dishes]
        if not isinstance(dishes, list):
            dishes = []

        normalized_dishes = []
        for dish in dishes:
            if isinstance(dish, str):
                dish = {"name": dish}
            if not isinstance(dish, dict):
                continue

            allergens = dish.get("allergens")
            if allergens is None:
                allergens = dish.get("alergenos", [])
            if isinstance(allergens, str):
                allergens = [a.strip() for a in allergens.split(",") if a.strip()]
            if not isinstance(allergens, list):
                allergens = []

            notes = dish.get("review_notes")
            if notes is None:
                notes = dish.get("notas_revision", [])
            if isinstance(notes, str):
                notes = [notes] if notes.strip() else []
            if not isinstance(notes, list):
                notes = []

            name = _as_text(dish.get("name") if "name" in dish else dish.get("nombre"))
            if not name:
                continue
            normalized_dishes.append({
                "number": _as_text(dish.get("number") if "number" in dish else dish.get("numero")),
                "name": name,
                "description": _as_text(dish.get("description") if "description" in dish else dish.get("descripcion")),
                "price": _as_text(dish.get("price") if "price" in dish else dish.get("precio")),
                "allergens": [str(a).strip() for a in allergens if str(a).strip()],
                "review_notes": [str(n).strip() for n in notes if str(n).strip()],
            })

        if not normalized_dishes:
            continue
        total_dishes += len(normalized_dishes)
        normalized_categories.append({
            "name": _as_text(
                cat.get("name") if "name" in cat else cat.get("nombre"),
                "Categoría",
            ) or "Categoría",
            "category_text": _as_text(
                cat.get("category_text") if "category_text" in cat else cat.get("texto_categoria")
            ),
            "dishes": normalized_dishes,
        })

    if not normalized_categories or total_dishes == 0:
        raise ValueError("Qwen respondió, pero no devolvió ningún plato utilizable. No se generará una carta vacía.")

    restaurant_name = _as_text(payload.get("restaurant_name"))
    if not restaurant_name:
        restaurant_name = _as_text(payload.get("nombre_restaurante")) or "MENÚ"
    texto_extra = _as_text(payload.get("texto_extra"))
    if not texto_extra:
        texto_extra = _as_text(payload.get("extra_text"))

    return {
        "restaurant_name": restaurant_name,
        "texto_extra": texto_extra,
        "categories": normalized_categories,
    }


'''
if old_parse not in s:
    raise SystemExit('No se encontró parse_json_text esperado')
s = s.replace(old_parse, new_parse, 1)

old_text_content = '''        [{"role": "user", "content": prompt + "\\n\\nMENÚ:\\n" + str(menu_text) + "\\n\\nDevuelve JSON válido."}],'''
new_text_content = '''        [{"role": "user", "content": prompt + "\\n\\nMENÚ:\\n" + str(menu_text) + "\\n\\n" + _MENU_JSON_CONTRACT + "\\n\\nDevuelve únicamente ese objeto JSON válido."}],'''
if old_text_content not in s:
    raise SystemExit('No se encontró prompt de texto esperado')
s = s.replace(old_text_content, new_text_content, 1)

old_image_content = '''        {"type": "text", "text": prompt + "\\n\\nAnaliza esta carta y devuelve JSON válido."},'''
new_image_content = '''        {"type": "text", "text": prompt + "\\n\\n" + _MENU_JSON_CONTRACT + "\\n\\nAnaliza esta carta y devuelve únicamente ese objeto JSON válido."},'''
if old_image_content not in s:
    raise SystemExit('No se encontró prompt de imagen esperado')
s = s.replace(old_image_content, new_image_content, 1)

# Solo las dos primeras ocurrencias corresponden a estructura de menú texto/imagen.
old_return = '    return parse_json_text(text)\n'
positions = []
start = 0
while True:
    idx = s.find(old_return, start)
    if idx == -1:
        break
    positions.append(idx)
    start = idx + len(old_return)
if len(positions) < 2:
    raise SystemExit('No se encontraron returns de menú esperados')
# Reemplazamos por función, para no afectar traducción.
start_text = s.index('def menu_json_from_text')
end_text = s.index('def menu_json_from_image', start_text)
block = s[start_text:end_text].replace(old_return, '    return _normalize_menu_payload(parse_json_text(text))\n', 1)
s = s[:start_text] + block + s[end_text:]
start_img = s.index('def menu_json_from_image')
end_img = s.index('def transcribe_menu_page', start_img)
block = s[start_img:end_img].replace(old_return, '    return _normalize_menu_payload(parse_json_text(text))\n', 1)
s = s[:start_img] + block + s[end_img:]

# Audio también debe respetar el contrato de carta.
s = s.replace(
    '{"type": "text", "text": prompt + "\\n\\nDevuelve únicamente JSON válido."},',
    '{"type": "text", "text": prompt + "\\n\\n" + _MENU_JSON_CONTRACT + "\\n\\nDevuelve únicamente ese objeto JSON válido."},',
    1,
)
start_audio = s.index('def audio_menu_json')
# Cambia retorno directo y retorno reparado solo dentro del bloque de audio.
audio = s[start_audio:]
audio = audio.replace('        return parse_json_text(text)\n', '        return _normalize_menu_payload(parse_json_text(text))\n', 1)
audio = audio.replace('        return parse_json_text(repair)\n', '        return _normalize_menu_payload(parse_json_text(repair))\n', 1)
s = s[:start_audio] + audio

if s == original:
    raise SystemExit('El hotfix no produjo cambios')

path.write_text(s, encoding='utf-8')
print('Qwen menu JSON contract hotfix applied')
