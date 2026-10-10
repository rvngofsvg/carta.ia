import base64
import json
import logging
import os
import urllib.error
import urllib.request
from io import BytesIO

import streamlit as st
from PIL import Image

QWEN_FLASH = "qwen3.8-flash"
QWEN_MAX = "qwen3.8-max"
QWEN_OMNI = "qwen3.8-omni-flash"

_LOG = logging.getLogger("carta_ia.private_usage")
_LOG.setLevel(logging.INFO)

# Singapore / International public compatibility endpoint. A workspace-specific
# endpoint can be provided in Streamlit Secrets without changing source code.
_DEFAULT_CHAT_ENDPOINT = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"

# Public list prices used only for a PRIVATE backend estimate in logs. The API
# usage payload itself is always recorded so billing can be reconciled later.
# Values are USD per 1M text tokens for the International/Singapore deployment.
_TEXT_RATES = {
    QWEN_FLASH: {"input": 0.15, "output": 0.47},
    QWEN_MAX: {"input": 2.00, "output": 6.00},
    QWEN_OMNI: {"input": 0.15, "output": 0.47},
}


def _secret(name, default=""):
    try:
        value = st.secrets[name]
        if value:
            return str(value).strip()
    except Exception:
        pass
    return str(os.getenv(name, default) or "").strip()


def api_key():
    return _secret("DASHSCOPE_API_KEY")


def _api_host():
    host = _secret("DASHSCOPE_API_HOST")
    if not host:
        return ""
    host = host.strip().rstrip("/")
    # Accept either the bare API Host shown by Alibaba or a copied compatible-mode URL.
    for suffix in ("/compatible-mode/v1/chat/completions", "/compatible-mode/v1", "/api/v1"):
        if host.endswith(suffix):
            host = host[:-len(suffix)].rstrip("/")
            break
    return host


def chat_endpoint():
    configured = _secret("DASHSCOPE_TEXT_ENDPOINT")
    if configured:
        return configured.rstrip("/")
    host = _api_host()
    if host:
        return host + "/compatible-mode/v1/chat/completions"
    return _DEFAULT_CHAT_ENDPOINT.rstrip("/")


def ensure_configured():
    if not api_key():
        raise RuntimeError("Falta DASHSCOPE_API_KEY en los Secrets de Streamlit.")


def _post_json(payload, timeout=240):
    ensure_configured()
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        chat_endpoint(),
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key()}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            parsed = json.loads(response.read().decode("utf-8"))
            if not isinstance(parsed, dict):
                raise RuntimeError(
                    f"Alibaba devolvió un wrapper API inesperado ({type(parsed).__name__}); se esperaba un objeto JSON."
                )
            return parsed
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        hint = ""
        if exc.code in (401, 403, 404):
            hint = " Comprueba que DASHSCOPE_API_HOST corresponde a la misma región/workspace que DASHSCOPE_API_KEY."
        raise RuntimeError(f"Alibaba Model Studio respondió HTTP {exc.code}: {detail[:900]}{hint}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"No se pudo conectar con Alibaba Model Studio: {exc.reason}") from exc


def _usage_dict(response):
    usage = response.get("usage") or {}
    if not isinstance(usage, dict):
        return {}
    return usage


def _estimate_text_cost(model, usage):
    rates = _TEXT_RATES.get(model)
    if not rates:
        return None
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    if not prompt and not completion:
        return None
    return (prompt / 1_000_000) * rates["input"] + (completion / 1_000_000) * rates["output"]


def _log_usage(model, purpose, response):
    # PRIVATE: emitted only to application/server logs. Never rendered in Streamlit UI.
    usage = _usage_dict(response)
    record = {
        "event": "CARTA_IA_QWEN_USAGE",
        "model": model,
        "purpose": purpose,
        "usage": usage,
    }
    estimate = _estimate_text_cost(model, usage)
    if estimate is not None:
        record["estimated_text_cost_usd"] = round(estimate, 8)
    _LOG.info(json.dumps(record, ensure_ascii=False, sort_keys=True))


def _extract_text(response):
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError("Alibaba no devolvió ninguna respuesta de texto.")
    message = (choices[0] or {}).get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    texts.append(str(text))
        if texts:
            return "\n".join(texts)
    raise RuntimeError("Alibaba devolvió una respuesta sin contenido de texto utilizable.")


def chat(messages, model=QWEN_FLASH, purpose="general", enable_thinking=False,
         reasoning_effort=None, json_object=False, modalities=None, timeout=240):
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "enable_thinking": bool(enable_thinking),
    }
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    if json_object:
        payload["response_format"] = {"type": "json_object"}
    if modalities:
        payload["modalities"] = modalities
    response = _post_json(payload, timeout=timeout)
    _log_usage(model, purpose, response)
    return _extract_text(response), _usage_dict(response)


def parse_json_text(text):
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


def _pil_data_uri(image):
    if not isinstance(image, Image.Image):
        raise TypeError("Se esperaba una imagen PIL.")
    img = image.convert("RGB")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=88, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def menu_json_from_text(prompt, menu_text):
    text, _ = chat(
        [{"role": "user", "content": prompt + "\n\nMENÚ:\n" + str(menu_text) + "\n\n" + _MENU_JSON_CONTRACT + "\n\nDevuelve únicamente ese objeto JSON válido."}],
        model=QWEN_FLASH,
        purpose="menu_structure_text",
        enable_thinking=False,
        json_object=True,
    )
    return _normalize_menu_payload(parse_json_text(text))


def menu_json_from_image(prompt, image):
    content = [
        {"type": "text", "text": prompt + "\n\n" + _MENU_JSON_CONTRACT + "\n\nAnaliza esta carta y devuelve únicamente ese objeto JSON válido."},
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


def transcribe_menu_page(image):
    content = [
        {"type": "text", "text": "Transcribe literalmente todo el texto visible de esta página de menú. No resumas, no inventes y devuelve solo texto plano."},
        {"type": "image_url", "image_url": {"url": _pil_data_uri(image)}},
    ]
    text, _ = chat(
        [{"role": "user", "content": content}],
        model=QWEN_FLASH,
        purpose="scanned_pdf_page",
        enable_thinking=False,
    )
    return text.strip()


def _allergen_source_dishes(prompt):
    """Recover the compact dish list already embedded in the allergen prompt."""
    try:
        start = prompt.find("[")
        end = prompt.rfind("]") + 1
        if start >= 0 and end > start:
            value = json.loads(prompt[start:end])
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    except Exception:
        pass
    return []


def _valid_allergen_result(result):
    return isinstance(result, dict) and isinstance(result.get("items"), list)


def _merge_allergen_items(base_result, reviewed_result):
    merged = {}
    for item in base_result.get("items", []):
        if not isinstance(item, dict):
            continue
        try:
            key = (int(item.get("category_index", -1)), int(item.get("dish_index", -1)))
        except Exception:
            continue
        merged[key] = item
    for item in reviewed_result.get("items", []):
        if not isinstance(item, dict):
            continue
        try:
            key = (int(item.get("category_index", -1)), int(item.get("dish_index", -1)))
        except Exception:
            continue
        if key[0] >= 0 and key[1] >= 0:
            merged[key] = item
    return {"items": list(merged.values())}


def allergen_reasoning_json(system_instruction, prompt):
    """Fast adaptive allergen cascade.

    Flash classifies every dish without chain-of-thought. Max is reserved for
    genuinely uncertain dishes, with LOW reasoning only. This keeps interactive
    latency low while retaining a stronger reviewer for ambiguous recipes.
    """
    errors = []
    fast_messages = [
        {"role": "system", "content": system_instruction.strip()},
        {"role": "user", "content": prompt.strip() +
         "\n\nClasifica con rapidez y criterio culinario. Marca confidence='baja' solo si la receta realmente es ambigua. "
         "reason debe ser muy breve (máximo 12 palabras). Devuelve exclusivamente JSON válido con la clave items."},
    ]

    # Fast path: no thinking. Alibaba documents materially lower latency here.
    try:
        text, _ = chat(
            fast_messages,
            model=QWEN_FLASH,
            purpose="allergen_fast_pass",
            enable_thinking=False,
            json_object=True,
            timeout=55,
        )
        fast_result = parse_json_text(text)
        if not _valid_allergen_result(fast_result):
            raise ValueError("respuesta JSON sin items")

        # Escalate only low-confidence items, plus medium-confidence empty
        # classifications where an omission is more costly than a quick review.
        review_keys = set()
        for item in fast_result.get("items", []):
            if not isinstance(item, dict):
                continue
            confidence = str(item.get("confidence") or "").strip().lower()
            allergens = item.get("allergens") or []
            if confidence == "baja" or (confidence == "media" and not allergens):
                try:
                    review_keys.add((int(item.get("category_index", -1)), int(item.get("dish_index", -1))))
                except Exception:
                    pass

        if not review_keys:
            return fast_result, QWEN_FLASH

        source = _allergen_source_dishes(prompt)
        uncertain = []
        for dish in source:
            try:
                key = (int(dish.get("category_index", -1)), int(dish.get("dish_index", -1)))
            except Exception:
                continue
            if key in review_keys:
                uncertain.append(dish)

        # If the prompt cannot be recovered, preserve the complete Flash answer
        # rather than paying for a full Max pass.
        if not uncertain:
            return fast_result, QWEN_FLASH

        review_prompt = (
            "Revisa SOLO estos platos ambiguos. Mantén category_index y dish_index. "
            "Devuelve allergens, confidence y reason breve. No analices otros platos.\n\n" +
            json.dumps(uncertain, ensure_ascii=False) +
            "\n\nDevuelve exclusivamente JSON válido con la clave items."
        )
        try:
            max_text, _ = chat(
                [
                    {"role": "system", "content": system_instruction.strip()},
                    {"role": "user", "content": review_prompt},
                ],
                model=QWEN_MAX,
                purpose="allergen_selective_review",
                enable_thinking=True,
                reasoning_effort="low",
                json_object=True,
                timeout=60,
            )
            reviewed = parse_json_text(max_text)
            if _valid_allergen_result(reviewed):
                return _merge_allergen_items(fast_result, reviewed), f"{QWEN_FLASH}+{QWEN_MAX}"
        except Exception as exc:
            errors.append(f"selective {QWEN_MAX}: {exc}")

        # Flash classification is still usable if the selective reviewer fails.
        return fast_result, QWEN_FLASH
    except Exception as exc:
        errors.append(f"{QWEN_FLASH}: {exc}")

    # Last-resort reviewer: Max LOW over the full compact dish list.
    try:
        text, _ = chat(
            [
                {"role": "system", "content": system_instruction.strip()},
                {"role": "user", "content": prompt.strip() +
                 "\n\nDevuelve exclusivamente JSON válido con la clave items. reason máximo 12 palabras."},
            ],
            model=QWEN_MAX,
            purpose="allergen_full_fallback",
            enable_thinking=True,
            reasoning_effort="low",
            json_object=True,
            timeout=70,
        )
        result = parse_json_text(text)
        if _valid_allergen_result(result):
            return result, QWEN_MAX
        raise ValueError("respuesta JSON sin items")
    except Exception as exc:
        errors.append(f"{QWEN_MAX}: {exc}")

    raise RuntimeError("No se pudo completar la clasificación automática de alérgenos. " + " | ".join(errors)[-1400:])


def translate_json(prompt):
    text, _ = chat(
        [{"role": "user", "content": prompt + "\n\nDevuelve JSON válido."}],
        model=QWEN_FLASH,
        purpose="translation",
        enable_thinking=False,
        json_object=True,
    )
    return parse_json_text(text)


def audio_menu_json(prompt, audio_bytes, mime_type="audio/wav"):
    fmt = (mime_type or "audio/wav").split("/")[-1].lower()
    if fmt in ("mpeg", "mpga"):
        fmt = "mp3"
    data_uri = f"data:{mime_type};base64," + base64.b64encode(audio_bytes).decode("ascii")
    content = [
        {
            "type": "input_audio",
            "input_audio": {"data": data_uri, "format": fmt},
        },
        {"type": "text", "text": prompt + "\n\n" + _MENU_JSON_CONTRACT + "\n\nDevuelve únicamente ese objeto JSON válido."},
    ]
    text, _ = chat(
        [{"role": "user", "content": content}],
        model=QWEN_OMNI,
        purpose="menu_structure_audio",
        enable_thinking=False,
        modalities=["text"],
        timeout=300,
    )
    try:
        return _normalize_menu_payload(parse_json_text(text))
    except Exception:
        repair, _ = chat(
            [{"role": "user", "content": "Convierte esto a JSON válido sin añadir información:\n\n" + text + "\n\nDevuelve JSON válido."}],
            model=QWEN_FLASH,
            purpose="audio_json_repair",
            enable_thinking=False,
            json_object=True,
        )
        return _normalize_menu_payload(parse_json_text(repair))
