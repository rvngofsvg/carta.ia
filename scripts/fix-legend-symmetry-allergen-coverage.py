from pathlib import Path

app_path = Path('app.py')
qwen_path = Path('qwen_core.py')
app = app_path.read_text(encoding='utf-8')
qwen = qwen_path.read_text(encoding='utf-8')

# 1) Word footer: seven mathematically equal columns.
old = '''            col_weights = [1.00, 1.12, 0.92, 0.98, 1.12, 1.02, 1.00]\n            weight_total = sum(col_weights)\n            col_widths = [usable_cm * weight / weight_total for weight in col_weights]\n'''
new = '''            # Simetría visual real: las siete posiciones deben ser equidistantes.\n            # Los nombres largos ya llevan saltos de línea controlados, por lo que\n            # no necesitamos deformar el ancho de sus columnas.\n            col_widths = [usable_cm / 7.0] * 7\n'''
if old not in app:
    raise SystemExit('No se encontró el reparto ponderado de columnas Word')
app = app.replace(old, new, 1)

# 2) PDF footer: same seven equal columns.
old = '            grid-template-columns: 1fr 1.12fr .92fr .98fr 1.22fr 1.02fr 1fr;'
new = '            grid-template-columns: repeat(7, 1fr);'
if old not in app:
    raise SystemExit('No se encontró el reparto ponderado de columnas PDF')
app = app.replace(old, new, 1)

# 3) Deterministic obvious-allergen backstop.
old = '''        "almeja", "almejas", "chipiron", "chipirón", "vieira", "vieiras", "ostra", "ostras", "navaja",\n        "navajas", "berberecho", "berberechos", "zamburiña", "zamburiñas", "salsa de ostras",\n'''
new = '''        "almeja", "almejas", "chipiron", "chipirón", "chipirones", "vieira", "vieiras", "ostra", "ostras", "navaja",\n        "navajas", "berberecho", "berberechos", "zamburiña", "zamburiñas", "caracol", "caracoles", "salsa de ostras",\n'''
if old not in app:
    raise SystemExit('No se encontró el bloque V11 de moluscos')
app = app.replace(old, new, 1)

old = '''        "tortilla española", "tortilla espanola", "tortilla francesa", "revuelto", "huevo poche", "huevo poché",\n'''
new = '''        "tortilla española", "tortilla espanola", "tortilla francesa",\n        "tortilla de jamon", "tortilla de jamón", "tortilla de chorizo", "tortilla de bacon",\n        "tortilla de lomo", "tortilla de queso", "revuelto", "huevo poche", "huevo poché",\n'''
if old not in app:
    raise SystemExit('No se encontró el bloque V11 de huevo/tortilla')
app = app.replace(old, new, 1)

# More useful recipe-review notes for dishes where the name alone is not legal proof.
needle = '''    (r"\\bfrit[oa]s?\\b|\\bfritura\\b|\\bfreidora\\b", [], "Fritura/freidora: revisar el protocolo real de contaminación cruzada."),\n'''
addition = '''    (r"\\balb[oó]ndigas?\\b", ["gluten", "huevos"], "Albóndigas: confirmar pan/harina y huevo de la receta concreta."),\n    (r"\\bcallos\\b|\\bmanitas?\\b.*\\bsalsa\\b", ["gluten", "apio", "sulfitos"], "Guiso/salsa: revisar espesante, fondo y vino de la receta concreta."),\n    (r"\\badobad[oa]s?\\b|\\bchorizo\\b|\\bsalchich[oó]n\\b", ["sulfitos", "lacteos"], "Adobo/embutido: revisar etiqueta o ficha técnica del proveedor."),\n'''
if needle not in app:
    raise SystemExit('No se encontró punto de inserción de review patterns')
app = app.replace(needle, addition + needle, 1)

# Extend smoke tests with the exact omissions visible in the user's real menu.
needle = '''        ("Marisco del día", "", set(), {"crustaceos", "moluscos"}),\n'''
addition = '''        ("Chipirones en su tinta", "", {"moluscos"}, set()),\n        ("Caracoles", "", {"moluscos"}, set()),\n        ("Tortilla de Jamón", "", {"huevos"}, set()),\n'''
if needle not in app:
    raise SystemExit('No se encontró smoke test de Marisco')
app = app.replace(needle, needle + addition, 1)

# 4) Qwen cascade: if Flash returns NO allergens for a recipe-risk dish, send only
# that dish to Max LOW even when Flash claimed high confidence.
needle = '''        if not review_keys:\n            return fast_result, QWEN_FLASH\n\n        source = _allergen_source_dishes(prompt)\n'''
replacement = '''        # A high-confidence empty answer is not enough for dishes whose name\n        # strongly suggests a composed recipe, sauce, frying or processed product.\n        # Review only those empty cases; plain grilled meat can legitimately remain empty.\n        source = _allergen_source_dishes(prompt)\n        fast_by_key = {}\n        for item in fast_result.get("items", []):\n            if not isinstance(item, dict):\n                continue\n            try:\n                key = (int(item.get("category_index", -1)), int(item.get("dish_index", -1)))\n            except Exception:\n                continue\n            fast_by_key[key] = item\n\n        recipe_risk_terms = (\n            "albóndig", "albondig", "callos", "manitas", "salsa", "adobad",\n            "salchich", "choriz", "hamburgues", "tortilla", "croquet", "frit",\n            "calamar", "chipir", "mejill", "caracol", "bacala", "queso", "huevo",\n            "pesto", "hummus", "romesco", "teriyaki",\n        )\n        for dish in source:\n            try:\n                key = (int(dish.get("category_index", -1)), int(dish.get("dish_index", -1)))\n            except Exception:\n                continue\n            fast_item = fast_by_key.get(key)\n            if not fast_item or (fast_item.get("allergens") or []):\n                continue\n            haystack = (str(dish.get("name") or "") + " " + str(dish.get("description") or "")).lower()\n            if any(term in haystack for term in recipe_risk_terms):\n                review_keys.add(key)\n\n        if not review_keys:\n            return fast_result, QWEN_FLASH\n\n        # source was already recovered above to support risk-based selective review.\n'''
if needle not in qwen:
    raise SystemExit('No se encontró la cascada selectiva Qwen esperada')
qwen = qwen.replace(needle, replacement, 1)

app_path.write_text(app, encoding='utf-8')
qwen_path.write_text(qwen, encoding='utf-8')
print('Applied legend symmetry + allergen coverage fixes')
