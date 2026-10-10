from pathlib import Path

p = Path('app.py')
s = p.read_text(encoding='utf-8')
repls = {
    'margin: 15mm 15mm 42mm 15mm;': 'margin: 15mm 15mm 45mm 15mm;',
    'height: 33mm;': 'height: 36mm;',
    'height: 11.2mm;': 'height: 12mm;',
    'font-size: 7.2pt;': 'font-size: 7.0pt;',
}
for old, new in repls.items():
    if old not in s and new not in s:
        raise SystemExit(f'No se encontró CSS esperado: {old}')
    s = s.replace(old, new)

for expected in ('height: 36mm;', 'margin: 15mm 15mm 45mm 15mm;', 'height: 12mm;', 'font-size: 7.0pt;'):
    assert expected in s
p.write_text(s, encoding='utf-8')
print('PDF footer clipping refinement applied')
