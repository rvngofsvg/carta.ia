from pathlib import Path

app_path = Path('app.py')
qwen_path = Path('qwen_core.py')
app = app_path.read_text(encoding='utf-8')
qwen = qwen_path.read_text(encoding='utf-8')

if 'MAX_IMAGE_SIDE = 1800' not in app:
    raise SystemExit('MAX_IMAGE_SIDE esperado no encontrado')
app = app.replace('MAX_IMAGE_SIDE = 1800', 'MAX_IMAGE_SIDE = 3200', 1)

old_prepare = '''    if img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
    clean = BytesIO()
    img.save(clean, format="JPEG", quality=92, optimize=True)
    clean.seek(0)
    final_img = Image.open(clean).copy()
    uploaded_file.seek(0)
    return final_img, original_info
'''
new_prepare = '''    if img.mode != "RGB":
        img = img.convert("RGB")
    # Conserva mucho más detalle para cartas con tipografía pequeña. Qwen 3.8
    # acepta imágenes de alta resolución; evitamos además una compresión JPEG
    # intermedia que antes degradaba el texto antes de enviarlo al modelo.
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
    final_img = img.copy()
    uploaded_file.seek(0)
    return final_img, original_info
'''
if old_prepare not in app:
    raise SystemExit('prepare_image_for_ai esperado no encontrado')
app = app.replace(old_prepare, new_prepare, 1)

old_encode = '    img.save(buf, format="JPEG", quality=88, optimize=True)\n'
new_encode = '    img.save(buf, format="JPEG", quality=94, optimize=True, subsampling=0)\n'
if old_encode not in qwen:
    raise SystemExit('_pil_data_uri JPEG esperado no encontrado')
qwen = qwen.replace(old_encode, new_encode, 1)

app_path.write_text(app, encoding='utf-8')
qwen_path.write_text(qwen, encoding='utf-8')
print('Menu image fidelity improved: 3200px, single high-quality JPEG encode')
