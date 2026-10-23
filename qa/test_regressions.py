import copy
import hashlib
import json
from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qa.audit_runtime import MENU, load_app
import qwen_core as q
from word_legend import LEGEND_PATH, set_eider_footer
from docx import Document
from PIL import Image

app = load_app()


class RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Path('qa/after').mkdir(parents=True, exist_ok=True)

    def test_eur_prices_do_not_duplicate_currency(self):
        from ai_design import _format_price
        for formatter in (app.format_price, _format_price):
            self.assertEqual(formatter('12,50 EUR'), '12,50 €')
            self.assertEqual(formatter('12,50 eur'), '12,50 €')
            self.assertEqual(formatter('12,50 €'), '12,50 €')
            self.assertEqual(formatter(''), '')

    def test_exact_artwork_in_all_word_exports(self):
        image = LEGEND_PATH.read_bytes()
        for builder in (app.create_word, app.create_clean_word,
                        app.create_editable_word_clean_template,
                        app.create_premium_editable_word, app.create_landscape_book_word):
            with self.subTest(builder=builder.__name__):
                raw = builder(MENU).getvalue()
                doc = Document(BytesIO(raw))
                with ZipFile(BytesIO(raw)) as archive:
                    self.assertIn(image, [archive.read(n) for n in archive.namelist() if n.startswith('word/media/')])
                for section in doc.sections:
                    for footer in (section.footer, section.first_page_footer, section.even_page_footer):
                        self.assertEqual(len(footer._element.xpath('.//pic:pic')), 1)
                        ext = footer._element.xpath('.//wp:extent')[0]
                        w, h = int(ext.get('cx')), int(ext.get('cy'))
                        with Image.open(LEGEND_PATH) as im:
                            self.assertAlmostEqual(w/h, im.width/im.height, places=4)
                        self.assertGreater(section.bottom_margin, h + section.footer_distance)
                        self.assertLessEqual(w, section.page_width-section.left_margin-section.right_margin)
                    set_eider_footer(section)
                    self.assertEqual(len(section.footer._element.xpath('.//pic:pic')), 1)
                # No original legend linked from body or header.
                for part in [doc.part] + [s.header.part for s in doc.sections]:
                    self.assertNotIn(image, [r.target_part.blob for r in part.rels.values() if not r.is_external and r.reltype.endswith('/image')])

    def test_without_allergens_is_clean(self):
        for columns in (False, True):
            doc = Document(app.create_client_word_without_allergens(MENU, two_columns=columns))
            self.assertEqual(len(doc.inline_shapes), 0)
            self.assertTrue(all(not s.footer._element.xpath('.//pic:pic') for s in doc.sections))
            self.assertIn('12,50', '\n'.join(p.text for p in doc.paragraphs))

    def test_all_templates_and_zip(self):
        for theme in app.EDITABLE_WORD_THEMES:
            for columns in (False, True):
                doc = Document(app.create_editable_word_clean_template(MENU, theme, columns))
                self.assertEqual(len(doc.sections[0].footer._element.xpath('.//pic:pic')), 1)
                if columns:
                    self.assertEqual(len(doc.sections), 2)
                    self.assertNotEqual(doc.sections[0]._sectPr.xpath('./w:cols')[0].get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}num'), '2')
        with ZipFile(app.create_editable_templates_zip(MENU)) as archive:
            self.assertEqual(len(archive.namelist()), len(app.EDITABLE_WORD_THEMES))

    def test_qwen_normalization_preserves_data(self):
        data = copy.deepcopy(MENU)
        data.update(header_text='Cabecera', footer_text='Pie', notes=['Aviso'])
        data['categories'][0]['notes'] = 'Nota de categoria'
        normalized = q._normalize_menu_payload({'data': data})
        self.assertEqual(normalized, data)
        for empty in ([], {}, {'categories': []}):
            with self.assertRaises(ValueError):
                q._normalize_menu_payload(empty)

    def test_partial_duplicate_and_invalid_allergen_answers(self):
        source = [{'category_index': 0, 'dish_index': i} for i in range(2)]
        item = {'category_index': 0, 'dish_index': 0, 'allergens': []}
        for items in ([], [item], [item, item], [dict(item, dish_index='0')]):
            self.assertFalse(q._valid_allergen_result({'items': items}, source))
        complete = {'items': [item, dict(item, dish_index=1)]}
        self.assertTrue(q._valid_allergen_result(complete, source))
        with patch.object(q, 'chat', side_effect=[(json.dumps({'items': [item]}), {}), (json.dumps(complete), {})]):
            result, model = q.allergen_reasoning_json('system', json.dumps(source))
            self.assertEqual(result, complete)
            self.assertEqual(model, q.QWEN_MAX)

    def test_truncated_response_rejected(self):
        with self.assertRaises(ValueError):
            q._extract_text({'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]})

    def test_translation_preserves_prices_and_allergens(self):
        payload = app._translation_payload(MENU)
        payload['categories'][0]['dishes'][0]['name'] = 'Cheese salad'
        with patch.object(app, 'translate_json', return_value=payload):
            translated = app.translate_menu_data(MENU, 'Ingles')
        for original, translated_dish in zip(MENU['categories'][0]['dishes'], translated['categories'][0]['dishes']):
            self.assertEqual(original['price'], translated_dish['price'])
            self.assertEqual(original['allergens'], translated_dish['allergens'])
        payload['categories'][0]['dishes'].append(payload['categories'][0]['dishes'][0])
        with patch.object(app, 'translate_json', return_value=payload), self.assertRaises(ValueError):
            app.translate_menu_data(MENU, 'Ingles')

    def test_image_fallback_and_real_transport_contract(self):
        calls = []
        def post(payload, timeout=240):
            calls.append(payload)
            content = '[]' if len(calls) == 1 else json.dumps(MENU)
            return {'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}]}
        with patch.object(q, '_post_json', side_effect=post):
            result = q.menu_json_from_image('Extract menu', Image.new('RGB', (100, 100)))
        self.assertEqual(result, MENU)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]['messages'][0]['content'][1]['image_url'], calls[1]['messages'][0]['content'][1]['image_url'])

    def test_pdf_exports_and_long_menu(self):
        import fitz
        long_menu = copy.deepcopy(MENU)
        long_menu['categories'][0]['dishes'] *= 50
        for allergens in (False, True):
            pdf = app.create_client_pdf_bytes(long_menu, with_allergens=allergens)
            self.assertIsNotNone(pdf)
            with fitz.open(stream=pdf, filetype='pdf') as doc:
                self.assertGreater(len(doc), 1)
                text = ''.join(p.get_text() for p in doc)
                self.assertEqual(text.count('Tomate fresco'), 50)
                self.assertEqual('1169/2011' in text, allergens)
        Path('qa/after/long.docx').write_bytes(app.create_word(long_menu).getvalue())

    def test_design_pdf_without_remote_generation(self):
        from ai_design import create_ai_menu_pdf
        background = BytesIO()
        Image.new('RGB', (600, 850), 'white').save(background, format='PNG')
        pdf = create_ai_menu_pdf(MENU, background.getvalue(), app.ICON_MAP)
        self.assertTrue(pdf.startswith(b'%PDF'))
        Path('qa/after/design.pdf').write_bytes(pdf)

    def test_ui_navigation_edit_and_downloads(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=90).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.radio), 1)
        at.session_state.menu_data = copy.deepcopy(MENU)
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.tabs), 7)
        self.assertGreaterEqual(len(at.get('download_button')), 9)
        price = next(w for w in at.text_input if w.label == 'Precio')
        price.set_value('19,75').run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state.menu_data['categories'][0]['dishes'][0]['price'], '19,75')


if __name__ == '__main__':
    unittest.main(verbosity=2)
