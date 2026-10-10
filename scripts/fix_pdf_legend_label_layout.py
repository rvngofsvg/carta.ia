from pathlib import Path

p = Path('app.py')
s = p.read_text(encoding='utf-8')

# Force the three long labels to exactly two visual lines in the PDF footer.
repls = {
    '"frutos de cascara": "FRUTOS DE CÁSCARA"': '"frutos de cascara": "FRUTOS DE<br>CÁSCARA"',
    '"sesamo": "GRANOS DE SÉSAMO"': '"sesamo": "GRANOS DE<br>SÉSAMO"',
    '"sulfitos": "DIÓXIDO DE AZUFRE Y SULFITOS"': '"sulfitos": "DIÓXIDO DE AZUFRE<br>Y SULFITOS"',
    'height: 12mm;': 'height: 13mm;',
    'padding: 0.3mm 0.5mm;': 'padding: 0.15mm 0.35mm;',
    'width: 7.4mm;': 'width: 6.8mm;',
    'height: 7.4mm;': 'height: 6.8mm;',
    'margin: 0 auto 0.25mm;': 'margin: 0 auto 0.15mm;',
}
for old, new in repls.items():
    if old not in s and new not in s:
        raise SystemExit(f'No se encontró patrón esperado: {old}')
    s = s.replace(old, new)

# Keep HTML tags only for visible labels, but ensure ALT text has no markup.
s = s.replace(
    'icon = f\'<img src="{src}" alt="{html_escape(labels[allergen])}">\' if src else ""',
    'alt_label = labels[allergen].replace("<br>", " ")\n            icon = f\'<img src="{src}" alt="{html_escape(alt_label)}">\' if src else ""',
)

for expected in (
    'FRUTOS DE<br>CÁSCARA',
    'GRANOS DE<br>SÉSAMO',
    'DIÓXIDO DE AZUFRE<br>Y SULFITOS',
    'height: 13mm;',
    'width: 6.8mm;',
    'height: 6.8mm;',
):
    assert expected in s, expected

p.write_text(s, encoding='utf-8')
print('PDF legend long-label layout fixed')
