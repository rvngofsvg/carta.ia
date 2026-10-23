"""Explicit opt-in integration test: real Alibaba calls, synthetic menu only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import copy
from io import BytesIO
from zipfile import ZipFile
from PIL import Image, ImageDraw, ImageFont
from docx import Document
import qwen_core as q
import app

OUT = Path('qa/after/live')
OUT.mkdir(parents=True, exist_ok=True)
TEXT = '''RESTAURANTE PRUEBA EIDER
IVA incluido. Reservas: 900 123 456

ENTRANTES
1. Ensalada de queso y nueces - 12,50 EUR
Tomate, queso de leche de vaca y nueces.
2. Hummus con sesamo - 8,00 EUR
Garbanzos, tahini de sesamo y aceite de oliva.
3. Ensalada de apio y mostaza - 9,25 EUR
Apio fresco, mostaza y aceite de oliva.

PRINCIPALES
4. Salmon con salsa de soja - 18,90 EUR
Salmon, salsa de soja con trigo y arroz.
5. Gambas con almejas - 22,00 EUR
Gambas, almejas, ajo y aceite de oliva.
6. Tortilla con pan - 7,50 EUR
Huevos, patatas y pan de trigo.

OTROS
7. Aperitivo de cacahuetes y altramuces - 4,00 EUR
Cacahuetes y altramuces en salmuera.
8. Copa de vino blanco - 3,50 EUR
Vino blanco. Contiene sulfitos.
'''
EXPECTED = [
 ('Ensalada de queso y nueces', '12.50', {'lacteos','frutos de cascara'}),
 ('Hummus con sesamo', '8.00', {'sesamo'}),
 ('Ensalada de apio y mostaza', '9.25', {'apio','mostaza'}),
 ('Salmon con salsa de soja', '18.90', {'pescado','soja','gluten'}),
 ('Gambas con almejas', '22.00', {'crustaceos','moluscos'}),
 ('Tortilla con pan', '7.50', {'huevos','gluten'}),
 ('Aperitivo de cacahuetes y altramuces', '4.00', {'cacahuetes','altramuces'}),
 ('Copa de vino blanco', '3.50', {'sulfitos'}),
]

calls = []
original_post = q._post_json
def tracked_post(payload, timeout=240):
    record = {'model': payload['model'], 'success': False}
    calls.append(record)
    try:
        response = original_post(payload, timeout)
        record['success'] = True
        record['usage'] = response.get('usage', {})
        return response
    except Exception as exc:
        record['error'] = str(exc).replace(q.api_key(), '[REDACTED]')
        raise
q._post_json = tracked_post

def validate(data):
    assert data, 'Analysis returned no menu'
    assert not data.get('_allergen_model_error'), 'Allergen classifier fell back to local rules'
    dishes = [d for c in data['categories'] for d in c['dishes']]
    assert len(data['categories']) == 3, 'Category count changed'
    assert len(dishes) == len(EXPECTED), 'Dish count changed'
    details = []
    for dish, (name, price, required) in zip(dishes, EXPECTED):
        assert app.normalize_text(name) in app.normalize_text(dish['name']), ('Dish order/name changed', dish['name'])
        actual_price = dish['price'].replace('EUR','').replace('€','').replace(',','.').strip()
        assert float(actual_price) == float(price), ('Price changed', dish['name'])
        assert dish['description'], ('Description lost', dish['name'])
        missing = required - set(dish['allergens'])
        assert not missing, ('Missing allergens', dish['name'], sorted(missing))
        details.append({'name':dish['name'], 'price':dish['price'], 'allergens':dish['allergens'], 'extra_allergens':sorted(set(dish['allergens'])-required), 'description':dish['description']})
    return details

def main():
    q.ensure_configured()
    report = {'calls':calls, 'checks':{}}
    (OUT/'source.txt').write_text(TEXT, encoding='utf-8')
    im = Image.new('RGB', (1800, 1700), 'white')
    draw = ImageDraw.Draw(im)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 30)
    draw.multiline_text((60,50), TEXT, fill='black', font=font, spacing=14)
    im.save(OUT/'source.png')
    for kind, content in [('text',TEXT), ('image',im)]:
        print('START',kind,flush=True)
        try:
            data = app.analyze_content(content,kind)
            if data:
                (OUT/f'{kind}_menu.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            report['checks'][kind] = validate(data)
            print('PASS',kind,flush=True)
        except Exception as exc:
            report['checks'][kind] = {'error':str(exc).replace(q.api_key(),'[REDACTED]')}
            print('FAIL',kind, type(exc).__name__,flush=True)
        (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not (OUT/'text_menu.json').exists():
        return
    data = json.loads((OUT/'text_menu.json').read_text(encoding='utf-8'))
    print('START translation',flush=True)
    try:
        translated = app.translate_menu_data(data,'Inglés')
        for c,tc in zip(data['categories'],translated['categories']):
            for d,td in zip(c['dishes'],tc['dishes']):
                assert d['price']==td['price'] and d['allergens']==td['allergens']
        (OUT/'translated_menu.json').write_text(json.dumps(translated,ensure_ascii=False,indent=2),encoding='utf-8')
        report['checks']['translation'] = 'PASS'
    except Exception as exc:
        report['checks']['translation'] = {'error':str(exc).replace(q.api_key(),'[REDACTED]')}
    print('START downloads',flush=True)
    for name, builder in [('allergens',app.create_word),('no_allergens',app.create_client_word_without_allergens),('clean',app.create_clean_word),('editable',app.create_editable_word_clean_template),('book',app.create_landscape_book_word)]:
        raw = builder(data).getvalue()
        (OUT/f'{name}.docx').write_bytes(raw)
        doc = Document(BytesIO(raw))
        pics = len(doc.sections[0].footer._element.xpath('.//pic:pic'))
        assert pics == (0 if name=='no_allergens' else 1)
        report['checks'][name] = {'bytes':len(raw),'footer_images':pics}
    for flag in (True,False):
        pdf = app.create_client_pdf_bytes(data,with_allergens=flag)
        assert pdf and pdf.startswith(b'%PDF')
        (OUT/f'pdf_{flag}.pdf').write_bytes(pdf)
        report['checks'][f'pdf_{flag}'] = len(pdf)
    pack = app.create_editable_templates_zip(data)
    (OUT/'templates.zip').write_bytes(pack.getvalue())
    with ZipFile(pack) as z:
        report['checks']['template_pack'] = len(z.namelist())
    (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('DONE',flush=True)

if __name__=='__main__':
    main()
