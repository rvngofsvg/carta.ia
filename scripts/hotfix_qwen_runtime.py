from pathlib import Path
import re

# --- qwen_core.py ---
q = Path('qwen_core.py')
s = q.read_text(encoding='utf-8')

# Add shared API host support while keeping Singapore legacy endpoint as fallback.
old = '''def chat_endpoint():
    configured = _secret("DASHSCOPE_TEXT_ENDPOINT")
    return (configured or _DEFAULT_CHAT_ENDPOINT).rstrip("/")
'''
new = '''def _api_host():
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
'''
if old not in s:
    raise SystemExit('chat_endpoint block not found')
s = s.replace(old, new, 1)

# More actionable region errors without exposing secrets.
s = s.replace(
    'raise RuntimeError(f"Alibaba Model Studio respondió HTTP {exc.code}: {detail[:1200]}") from exc',
    '''hint = ""
        if exc.code in (401, 403, 404):
            hint = " Comprueba que DASHSCOPE_API_HOST corresponde a la misma región/workspace que DASHSCOPE_API_KEY."
        raise RuntimeError(f"Alibaba Model Studio respondió HTTP {exc.code}: {detail[:900]}{hint}") from exc''',
    1,
)

start = s.index('def allergen_reasoning_json(system_instruction, prompt):')
end = s.index('\ndef translate_json(prompt):', start)
new_func = '''def allergen_reasoning_json(system_instruction, prompt):
    """Classify allergens with bounded reasoning and a fast automatic fallback.

    Qwen 3.8 xhigh can allocate an extremely large reasoning budget and is not
    appropriate for an interactive restaurant menu. Medium keeps strong
    reasoning while avoiding multi-minute stalls. Qwen 3.8 supports JSON Object
    output in thinking mode, so request valid JSON directly.
    """
    messages = [
        {"role": "system", "content": system_instruction.strip()},
        {"role": "user", "content": prompt.strip() + "\\n\\nDevuelve exclusivamente JSON válido con la clave items."},
    ]
    errors = []

    # Primary: strongest model, bounded reasoning.
    try:
        text, _ = chat(
            messages,
            model=QWEN_MAX,
            purpose="allergen_reasoning",
            enable_thinking=True,
            reasoning_effort="medium",
            json_object=True,
            timeout=120,
        )
        result = parse_json_text(text)
        if isinstance(result, dict) and isinstance(result.get("items"), list):
            return result, QWEN_MAX
        raise ValueError("respuesta JSON sin items")
    except Exception as exc:
        errors.append(f"{QWEN_MAX}: {exc}")

    # Automatic fallback: Flash still uses culinary reasoning, but without a
    # long thinking pass. This prevents a blank allergen export if Max is
    # temporarily unavailable or not enabled for the API key.
    try:
        fallback_messages = [
            {"role": "system", "content": system_instruction.strip()},
            {"role": "user", "content": prompt.strip() + "\\n\\nResuelve con criterio culinario y devuelve exclusivamente JSON válido con la clave items."},
        ]
        text, _ = chat(
            fallback_messages,
            model=QWEN_FLASH,
            purpose="allergen_reasoning_fallback",
            enable_thinking=True,
            reasoning_effort="medium",
            json_object=True,
            timeout=90,
        )
        result = parse_json_text(text)
        if isinstance(result, dict) and isinstance(result.get("items"), list):
            return result, QWEN_FLASH
        raise ValueError("respuesta JSON sin items")
    except Exception as exc:
        errors.append(f"{QWEN_FLASH}: {exc}")

    raise RuntimeError("No se pudo completar la clasificación automática de alérgenos. " + " | ".join(errors)[-1400:])

'''
s = s[:start] + new_func + s[end:]
q.write_text(s, encoding='utf-8')

# --- ai_design.py ---
a = Path('ai_design.py')
s = a.read_text(encoding='utf-8')
old = '''def _dashscope_endpoint():
    # Permite fijar un endpoint regional/workspace-specific en Secrets sin tocar código.
    configured = _secret("DASHSCOPE_IMAGE_ENDPOINT")
    if configured:
        return configured.rstrip("/")
    # Endpoint internacional heredado de Singapore; Alibaba indica que sigue operativo.
    return "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
'''
new = '''def _dashscope_endpoint():
    # Endpoint explícito de imagen tiene prioridad.
    configured = _secret("DASHSCOPE_IMAGE_ENDPOINT")
    if configured:
        return configured.rstrip("/")
    # Un único API Host regional puede alimentar texto e imagen.
    host = _secret("DASHSCOPE_API_HOST")
    if host:
        host = host.strip().rstrip("/")
        for suffix in ("/compatible-mode/v1/chat/completions", "/compatible-mode/v1", "/api/v1"):
            if host.endswith(suffix):
                host = host[:-len(suffix)].rstrip("/")
                break
        return host + "/api/v1/services/aigc/multimodal-generation/generation"
    # Compatibilidad legacy para claves creadas en Singapore.
    return "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
'''
if old not in s:
    raise SystemExit('image endpoint block not found')
s = s.replace(old, new, 1)
a.write_text(s, encoding='utf-8')

# --- app.py ---
p = Path('app.py')
s = p.read_text(encoding='utf-8')
s = s.replace(
    '3) Puedes proponer una primera estimación de alérgenos entre estas claves: {allergen_keys}.',
    '3) Debes proponer una primera estimación razonada de alérgenos entre estas claves: {allergen_keys}; no los dejes vacíos por defecto si la receta habitual permite una inferencia razonable.',
    1,
)

# If specialist AI fully fails, preserve the first-pass Qwen estimates and let
# deterministic rules enrich them, but mark it internally for logs/support.
old = '''    except Exception as exc:
        data["_allergen_model"] = "reglas locales (fallback)"
        data["_allergen_model_error"] = str(exc)[-800:]
        return data
'''
new = '''    except Exception as exc:
        data["_allergen_model"] = "estimación inicial + reglas locales"
        data["_allergen_model_error"] = str(exc)[-1200:]
        return data
'''
if old not in s:
    raise SystemExit('allergen fallback block not found')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')

print('Qwen runtime hotfix applied')
