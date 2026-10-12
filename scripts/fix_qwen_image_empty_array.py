from pathlib import Path

path = Path('qwen_core.py')
source = path.read_text(encoding='utf-8')

old_normalize = '''def _normalize_menu_payload(payload):
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
'''

new_normalize = '''def _payload_shape(payload):
    """Describe solo la forma del JSON para logs privados, sin guardar contenido del menú."""
    if isinstance(payload, list):
        types = sorted({type(item).__name__ for item in payload})
        return {"type": "list", "length": len(payload), "item_types": types}
    if isinstance(payload, dict):
        return {"type": "dict", "keys": sorted(str(k) for k in payload.keys())[:30]}
    return {"type": type(payload).__name__}


def _normalize_menu_payload(payload):
    """Normaliza respuestas razonables de Qwen al contrato interno de Carta IA.

    El objetivo es tolerar wrappers o arrays de categorías/platos sin permitir
    que una forma JSON inesperada llegue a app.py y provoque `.get` sobre listas.
    """
    if isinstance(payload, list):
        # Algunos modelos envuelven el JSON como único string dentro de un array.
        if len(payload) == 1 and isinstance(payload[0], str):
            try:
                return _normalize_menu_payload(parse_json_text(payload[0]))
            except Exception:
                pass

        # Ignora elementos auxiliares nulos/textuales si también hay objetos útiles.
        dict_items = [item for item in payload if isinstance(item, dict)]
        if dict_items and len(dict_items) != len(payload):
            payload = dict_items

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
'''

if old_normalize not in source:
    raise SystemExit('No se encontró el bloque de normalización esperado; abortando sin tocar qwen_core.py')
source = source.replace(old_normalize, new_normalize, 1)

old_image = '''def menu_json_from_image(prompt, image):
    content = [
        {"type": "text", "text": prompt + "\\n\\n" + _MENU_JSON_CONTRACT + "\\n\\nAnaliza esta carta y devuelve únicamente ese objeto JSON válido."},
        {"type": "image_url", "image_url": {"url": _pil_data_uri(image)}},
    ]
    text, _ = chat(
        [{"role": "user", "content": content}],
        model=QWEN_FLASH,
        purpose="menu_structure_image",
        enable_thinking=False,
        json_object=True,
    )
    return _normalize_menu_payload(parse_json_text(text))
'''

new_image = '''def menu_json_from_image(prompt, image):
    """Extrae una carta de imagen con fallback visual real.

    Flash sigue siendo la ruta normal y barata. Solo si devuelve JSON vacío o una
    forma no utilizable se reanaliza la MISMA imagen con Omni y, como último
    recurso, Max. No intentamos "reparar" un [] porque ahí no existe información
    que recuperar: hay que volver a mirar la imagen.
    """
    image_uri = _pil_data_uri(image)
    errors = []
    attempts = (
        (QWEN_FLASH, "menu_structure_image", False),
        (QWEN_OMNI, "menu_structure_image_omni_fallback", False),
        (QWEN_MAX, "menu_structure_image_max_fallback", False),
    )

    for attempt_index, (model, purpose, thinking) in enumerate(attempts):
        recovery = ""
        if attempt_index:
            recovery = (
                "\\n\\nIMPORTANTE: un intento anterior no produjo una carta utilizable. "
                "Vuelve a LEER DIRECTAMENTE LA IMAGEN desde cero. No reconstruyas datos de una respuesta anterior. "
                "Si hay texto visible de menú, extrae todas las categorías, platos y precios legibles. "
                "La raíz debe ser el objeto JSON del contrato, nunca []."
            )
        content = [
            {
                "type": "text",
                "text": prompt + "\\n\\n" + _MENU_JSON_CONTRACT +
                        "\\n\\nAnaliza esta carta y devuelve únicamente ese objeto JSON válido." + recovery,
            },
            {"type": "image_url", "image_url": {"url": image_uri}},
        ]
        try:
            text, _ = chat(
                [{"role": "user", "content": content}],
                model=model,
                purpose=purpose,
                enable_thinking=thinking,
                json_object=True,
                timeout=180,
            )
            parsed = parse_json_text(text)
            try:
                return _normalize_menu_payload(parsed)
            except Exception as exc:
                _LOG.warning(json.dumps({
                    "event": "CARTA_IA_MENU_IMAGE_INVALID_SHAPE",
                    "model": model,
                    "shape": _payload_shape(parsed),
                    "error": str(exc)[:300],
                }, ensure_ascii=False, sort_keys=True))
                errors.append(f"{model}: {exc}")
        except Exception as exc:
            errors.append(f"{model}: {exc}")

    raise RuntimeError(
        "Qwen no pudo extraer una carta válida de esta imagen tras reintentar el análisis visual. "
        "Comprueba que la foto muestre texto de menú legible y vuelve a intentarlo. Detalle: " +
        " | ".join(errors)[-1200:]
    )
'''

if old_image not in source:
    raise SystemExit('No se encontró menu_json_from_image esperado; abortando sin tocar qwen_core.py')
source = source.replace(old_image, new_image, 1)

path.write_text(source, encoding='utf-8')
print('Qwen image empty-array fallback applied')
