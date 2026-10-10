from pathlib import Path

site = Path('serval_eider_patch/sitecustomize.py')
setup = Path('serval_eider_patch/setup.py')
qa = Path('.github/workflows/validate-eider-footer.yml')

s = site.read_text(encoding='utf-8')
old = 'INLINE_ICON_MIN_CM = 0.75'
new = 'INLINE_ICON_MIN_CM = 0.46'
if old not in s and new not in s:
    raise SystemExit('No se encontró INLINE_ICON_MIN_CM esperado')
s = s.replace(old, new)
site.write_text(s, encoding='utf-8')

p = setup.read_text(encoding='utf-8')
p = p.replace('version="1.0.5"', 'version="1.0.6"')
if 'version="1.0.6"' not in p:
    raise SystemExit('No se pudo actualizar la versión del parche')
setup.write_text(p, encoding='utf-8')

q = qa.read_text(encoding='utf-8')
q = q.replace(
    "assert 'def _nil_table_borders(table):' in source, 'No se eliminó la cuadrícula interna'",
    "assert 'def nil_table_borders(table):' in source, 'No se eliminó la cuadrícula interna'",
)
q = q.replace(
    "assert 'outer_border = {\"val\": \"single\", \"sz\": \"10\"' in source, 'Marco exterior profesional no aplicado'",
    "assert 'def set_outer_border(table, color):' in source and 'node.set(qn(\"w:sz\"), \"10\")' in source, 'Marco exterior profesional no aplicado'",
)
# Asegura que el paquete legacy ya no pueda volver a inflar los iconos inline.
needle = "assert '.dish-icon{{width:4.6mm;height:4.6mm;object-fit:contain;}}' in source, 'Iconos PDF de plato siguen demasiado grandes'"
if needle in q and "INLINE_ICON_MIN_CM = 0.46" not in q:
    q = q.replace(
        needle,
        needle + "\n          legacy_patch = Path('serval_eider_patch/sitecustomize.py').read_text(encoding='utf-8')\n          assert 'INLINE_ICON_MIN_CM = 0.46' in legacy_patch, 'El parche legacy vuelve a inflar los iconos Word'",
    )
qa.write_text(q, encoding='utf-8')

assert 'INLINE_ICON_MIN_CM = 0.46' in site.read_text(encoding='utf-8')
assert 'version="1.0.6"' in setup.read_text(encoding='utf-8')
assert 'def nil_table_borders(table):' in qa.read_text(encoding='utf-8')
print('Legacy inline icon minimum and QA updated')
