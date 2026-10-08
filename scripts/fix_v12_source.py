from pathlib import Path

path = Path("scripts/v12_core_patch.py")
text = path.read_text(encoding="utf-8")
text = text.replace("return f'''<!doctype html><html><head><meta charset=\"utf-8\"><style>", "return f\"\"\"<!doctype html><html><head><meta charset=\"utf-8\"><style>")
text = text.replace("{footer_html}</body></html>'''", "{footer_html}</body></html>\"\"\"")
path.write_text(text, encoding="utf-8")
print("PASS fixed v12 patch quoting")
