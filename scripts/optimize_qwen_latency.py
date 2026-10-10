from pathlib import Path

qpath = Path('qwen_core.py')
q = qpath.read_text(encoding='utf-8')

old = '''def allergen_reasoning_json(system_instruction, prompt):
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

new = '''def _allergen_source_dishes(prompt):
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
         "\\n\\nClasifica con rapidez y criterio culinario. Marca confidence='baja' solo si la receta realmente es ambigua. "
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
            "Devuelve allergens, confidence y reason breve. No analices otros platos.\\n\\n" +
            json.dumps(uncertain, ensure_ascii=False) +
            "\\n\\nDevuelve exclusivamente JSON válido con la clave items."
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
                 "\\n\\nDevuelve exclusivamente JSON válido con la clave items. reason máximo 12 palabras."},
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
'''

if old not in q:
    raise SystemExit('No se encontró la función allergen_reasoning_json esperada')
q = q.replace(old, new, 1)
q = q.replace('img.save(buf, format="JPEG", quality=92, optimize=True)', 'img.save(buf, format="JPEG", quality=88, optimize=True)', 1)
qpath.write_text(q, encoding='utf-8')

apath = Path('app.py')
a = apath.read_text(encoding='utf-8')
a = a.replace('MAX_IMAGE_SIDE = 2200', 'MAX_IMAGE_SIDE = 1800', 1)
apath.write_text(a, encoding='utf-8')

print('Applied adaptive Qwen latency optimization')
