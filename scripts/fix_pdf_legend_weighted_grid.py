from pathlib import Path

p = Path('app.py')
s = p.read_text(encoding='utf-8')

old_grid = '''        .legend-grid {
            display: flex;
            flex-wrap: wrap;
            align-content: flex-start;
            width: 100%;
        }
        .legend-item {
            width: 14.285714%;
            height: 13mm;
            text-align: center;
            font-size: 7.0pt;
            font-weight: 700;
            line-height: 1.04;
            padding: 0.15mm 0.35mm;
            box-sizing: border-box;
            hyphens: none;
            word-break: normal;
            overflow-wrap: normal;
        }
        .legend-item img {
            display: block;
            width: 6.8mm;
            height: 6.8mm;
            object-fit: contain;
            margin: 0 auto 0.15mm;
        }
'''
new_grid = '''        .legend-grid {
            display: grid;
            grid-template-columns: 1fr 1.12fr .92fr .98fr 1.22fr 1.02fr 1fr;
            grid-template-rows: 12.4mm 12.4mm;
            align-content: start;
            width: 100%;
        }
        .legend-item {
            min-width: 0;
            height: 12.4mm;
            text-align: center;
            font-size: 6.8pt;
            font-weight: 700;
            line-height: 1.02;
            padding: 0.10mm 0.25mm;
            box-sizing: border-box;
            hyphens: none;
            word-break: normal;
            overflow-wrap: normal;
        }
        .legend-item img {
            display: block;
            width: 6.3mm;
            height: 6.3mm;
            object-fit: contain;
            margin: 0 auto 0.10mm;
        }
'''
if old_grid not in s:
    raise SystemExit('No se encontró el bloque CSS PDF esperado')
s = s.replace(old_grid, new_grid, 1)

# Break the longest label where the second line remains balanced.
s = s.replace('"sulfitos": "DIÓXIDO DE AZUFRE<br>Y SULFITOS"',
              '"sulfitos": "DIÓXIDO DE<br>AZUFRE Y SULFITOS"')

checks = [
    'display: grid;',
    'grid-template-columns: 1fr 1.12fr .92fr .98fr 1.22fr 1.02fr 1fr;',
    'grid-template-rows: 12.4mm 12.4mm;',
    'height: 12.4mm;',
    'font-size: 6.8pt;',
    'width: 6.3mm;',
    'height: 6.3mm;',
    'DIÓXIDO DE<br>AZUFRE Y SULFITOS',
]
for x in checks:
    assert x in s, x
p.write_text(s, encoding='utf-8')
print('Weighted PDF allergen grid applied')
