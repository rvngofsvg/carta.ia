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


def chat_endpoint():
    configured = _secret("DASHSCOPE_TEXT_ENDPOINT")
    return (configured or _DEFAULT_CHAT_ENDPOINT).rstrip("/")


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
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Alibaba Model Studio respondió HTTP {exc.code}: {detail[:1200]}") from exc
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
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        raw = raw[start:end]
    return json.loads(raw)


def _pil_data_uri(image):
    if not isinstance(image, Image.Image):
        raise TypeError("Se esperaba una imagen PIL.")
    img = image.convert("RGB")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def menu_json_from_text(prompt, menu_text):
    text, _ = chat(
        [{"role": "user", "content": prompt + "\n\nMENÚ:\n" + str(menu_text) + "\n\nDevuelve JSON válido."}],
        model=QWEN_FLASH,
        purpose="menu_structure_text",
        enable_thinking=False,
        json_object=True,
    )
    return parse_json_text(text)


def menu_json_from_image(prompt, image):
    content = [
        {"type": "text", "text": prompt + "\n\nAnaliza esta carta y devuelve JSON válido."},
        {"type": "image_url", "image_url": {"url": _pil_data_uri(image)}},
    ]
    text, _ = chat(
        [{"role": "user", "content": content}],
        model=QWEN_FLASH,
        purpose="menu_structure_image",
        enable_thinking=False,
        json_object=True,
    )
    return parse_json_text(text)


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


def allergen_reasoning_json(system_instruction, prompt):
    # Max performs the culinary reasoning. We intentionally do not request JSON
    # mode while thinking is enabled because Alibaba documents compatibility
    # limitations between thinking and structured output on some routes.
    text, _ = chat(
        [
            {"role": "user", "content": system_instruction.strip() + "\n\n" + prompt.strip() + "\n\nAl final devuelve exclusivamente un objeto JSON con la clave items."},
        ],
        model=QWEN_MAX,
        purpose="allergen_reasoning",
        enable_thinking=True,
        reasoning_effort="xhigh",
        json_object=False,
        timeout=300,
    )
    try:
        return parse_json_text(text), QWEN_MAX
    except Exception:
        # Cheap deterministic repair pass; no extra reasoning and no semantic rewrite.
        repair_prompt = (
            "Convierte la respuesta siguiente a JSON válido SIN cambiar ninguna decisión semántica. "
            "Debe conservar category_index, dish_index, allergens, confidence y reason. Devuelve JSON válido.\n\n" + text
        )
        fixed, _ = chat(
            [{"role": "user", "content": repair_prompt}],
            model=QWEN_FLASH,
            purpose="allergen_json_repair",
            enable_thinking=False,
            json_object=True,
        )
        return parse_json_text(fixed), QWEN_MAX


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
        {"type": "text", "text": prompt + "\n\nDevuelve únicamente JSON válido."},
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
        return parse_json_text(text)
    except Exception:
        repair, _ = chat(
            [{"role": "user", "content": "Convierte esto a JSON válido sin añadir información:\n\n" + text + "\n\nDevuelve JSON válido."}],
            model=QWEN_FLASH,
            purpose="audio_json_repair",
            enable_thinking=False,
            json_object=True,
        )
        return parse_json_text(repair)
