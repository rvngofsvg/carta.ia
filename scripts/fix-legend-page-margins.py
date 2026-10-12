from pathlib import Path

path = Path('app.py')
s = path.read_text(encoding='utf-8')

old = '''        if section.bottom_margin < Cm(3.8):
            section.bottom_margin = Cm(3.8)
        section.footer_distance = Cm(0.12)
        usable_cm = max(12.0, (section.page_width - section.left_margin - section.right_margin) / 360000.0)
'''
new = '''        # Alinea visualmente la leyenda con la sangría real del cuerpo de la carta.
        # Antes ocupaba todo el ancho imprimible y quedaba demasiado pegada al borde inferior.
        if section.bottom_margin < Cm(4.2):
            section.bottom_margin = Cm(4.2)
        section.footer_distance = Cm(0.45)
        raw_usable_cm = max(12.0, (section.page_width - section.left_margin - section.right_margin) / 360000.0)
        usable_cm = max(12.0, raw_usable_cm - 1.6)  # 0,8 cm extra por lado, igual que el cuerpo.
'''
if old not in s:
    raise SystemExit('No se encontró el bloque Word esperado')
s = s.replace(old, new, 1)

old_pdf = '            width: 180mm;\n            height: 36mm;'
new_pdf = '            width: 164mm;\n            height: 36mm;'
if old_pdf not in s:
    raise SystemExit('No se encontró el ancho PDF esperado')
s = s.replace(old_pdf, new_pdf, 1)

path.write_text(s, encoding='utf-8')
print('Applied legend page-margin alignment')
