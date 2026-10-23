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
from word_legend import LEGEND_PATH, LEGEND_WIDTH, ORIGINAL_LEGEND_PATH, eider_legend_data_uri, set_eider_footer
from docx import Document
from PIL import Image, ImageChops

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
                        self.assertAlmostEqual(w, min(LEGEND_WIDTH, section.page_width-section.left_margin-section.right_margin), delta=10000)
                    set_eider_footer(section)
                    self.assertEqual(len(section.footer._element.xpath('.//pic:pic')), 1)
                # No original legend linked from body or header.
                for part in [doc.part] + [s.header.part for s in doc.sections]:
                    self.assertNotIn(image, [r.target_part.blob for r in part.rels.values() if not r.is_external and r.reltype.endswith('/image')])

    def test_cropped_legend_removes_white_background_without_changing_white_render(self):
        source = Image.open(ORIGINAL_LEGEND_PATH).convert('RGB')
        source_diff = ImageChops.difference(source, Image.new('RGB', source.size, 'white'))
        content = source_diff.convert('L').point(lambda p: 255 if p else 0).getbbox()
        self.assertIsNotNone(content)
        left, top, right, bottom = content
        padding = 12
        expected_box = (left-padding, top-padding, right+padding, bottom+padding)
        expected = source.crop(expected_box)
        cropped = Image.open(LEGEND_PATH).convert('RGBA')
        self.assertEqual(cropped.size, expected.size)
        self.assertLess(cropped.getchannel('A').getextrema()[0], 255)
        rendered_on_white = Image.alpha_composite(Image.new('RGBA', cropped.size, 'white'), cropped).convert('RGB')
        self.assertIsNone(ImageChops.difference(expected, rendered_on_white).getbbox())

    def test_without_allergens_is_clean(self):
        for columns in (False, True):
            doc = Document(app.create_client_word_without_allergens(MENU, two_columns=columns))
            self.assertEqual(len(doc.inline_shapes), 0)
            self.assertTrue(all(not s.footer._element.xpath('.//pic:pic') for s in doc.sections))
            self.assertTrue(all(not s.header._element.xpath('.//pic:pic') for s in doc.sections))
            self.assertIn('12,50', '\n'.join(p.text for p in doc.paragraphs))

    def test_eider_template_default_and_dish_allergen_price_order(self):
        self.assertEqual(Path(app.PLANTILLA_PATH).name, 'plantilla_base_carta_eider.docx')

        with_allergens = Document(app.create_word(MENU))
        self.assertEqual(with_allergens.sections[0].header.paragraphs[0].text, 'Restaurante QA')
        self.assertEqual(len(with_allergens.sections[0].footer._element.xpath('.//pic:pic')), 1)
        self.assertFalse(with_allergens.sections[0].header._element.xpath('.//pic:pic'))
        self.assertNotIn('Plato\t00,00', '\n'.join(p.text for p in with_allergens.paragraphs))

        def assert_icons_before_leader_price(doc, dish_fragment):
            row = next(p for p in doc.paragraphs if dish_fragment in p.text)
            runs = row.runs
            name_index = next(i for i, run in enumerate(runs) if dish_fragment in run.text)
            icon_indices = [i for i, run in enumerate(runs) if run._r.xpath('.//pic:pic')]
            price_index = next(i for i, run in enumerate(runs) if run.text.startswith('\t'))
            self.assertTrue(icon_indices)
            self.assertLess(name_index, min(icon_indices))
            self.assertLess(max(icon_indices), price_index)
            self.assertTrue(row._p.xpath(".//w:tab[@w:leader='dot']"))

        assert_icons_before_leader_price(with_allergens, 'Ensalada de queso y nueces')

        without_allergens = Document(app.create_client_word_without_allergens(MENU))
        self.assertEqual(without_allergens.sections[0].header.paragraphs[0].text, 'Restaurante QA')
        self.assertFalse(without_allergens.sections[0].footer._element.xpath('.//pic:pic'))
        self.assertFalse(without_allergens.sections[0].header._element.xpath('.//pic:pic'))
        self.assertFalse(without_allergens.inline_shapes)
        self.assertNotIn('Plato\t00,00', '\n'.join(p.text for p in without_allergens.paragraphs))

        book = Document(app.create_landscape_book_word(MENU))
        assert_icons_before_leader_price(book, 'Ensalada de queso y nueces')
        portrait_width = int(with_allergens.sections[0].footer._element.xpath('.//wp:extent')[0].get('cx'))
        landscape_width = int(book.sections[0].footer._element.xpath('.//wp:extent')[0].get('cx'))
        self.assertAlmostEqual(portrait_width, landscape_width, delta=10000)
        clean = Document(app.create_clean_word(MENU))
        self.assertEqual(clean.sections[0].header.paragraphs[0].text, 'Restaurante QA')
        self.assertEqual(len(clean.sections[0].footer._element.xpath('.//pic:pic')), 1)

    def test_all_templates_and_zip(self):
        for theme in app.EDITABLE_WORD_THEMES:
            for columns in (False, True):
                doc = Document(app.create_editable_word_clean_template(MENU, theme, columns))
                self.assertEqual(len(doc.sections[0].footer._element.xpath('.//pic:pic')), 1)
                row = next(p for p in doc.paragraphs if 'Ensalada de queso y nueces' in p.text)
                self.assertEqual(len(row._p.xpath('.//pic:pic')), 2)
                self.assertTrue(row._p.xpath(".//w:tab[@w:leader='dot']"))
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

    def test_exports_wait_for_allergen_review_acknowledgement(self):
        from streamlit.testing.v1 import AppTest
        pending = copy.deepcopy(MENU)
        pending['categories'][0]['dishes'][0]['review_notes'] = ['Revisar la ficha técnica de la salsa.']
        at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=90).run()
        at.session_state.menu_data = pending
        at.run()
        self.assertFalse(at.exception)
        labels = [button.label for button in at.get('download_button')]
        self.assertTrue(any('SIN ALÉRGENOS' in label for label in labels))
        self.assertFalse(any('CON ALÉRGENOS' in label or 'plantilla de Word' in label or 'WORD HORIZONTAL' in label for label in labels))
        ack = next(box for box in at.checkbox if 'He comprobado estos platos' in box.label)
        ack.set_value(True).run()
        self.assertFalse(at.exception)
        labels = [button.label for button in at.get('download_button')]
        self.assertTrue(any('WORD CON ALÉRGENOS' in label for label in labels))
        self.assertTrue(any('plantilla de Word' in label for label in labels))
        self.assertTrue(any('WORD HORIZONTAL' in label for label in labels))

    def test_low_confidence_allergen_result_becomes_review_note(self):
        data = copy.deepcopy(MENU)
        result = {'items': [
            {'category_index': 0, 'dish_index': 0, 'allergens': ['lacteos'], 'confidence': 'baja', 'reason': 'Receta ambigua.'},
            {'category_index': 0, 'dish_index': 1, 'allergens': [], 'confidence': 'alta', 'reason': 'Sin ingredientes declarados.'},
        ]}
        with patch.object(app, 'allergen_reasoning_json', return_value=(result, 'qwen3.8-max')):
            app.infer_allergens_with_best_model(data)
        dish = data['categories'][0]['dishes'][0]
        self.assertTrue(any('El resultado no es seguro' in note for note in dish['review_notes']))
        self.assertIn('Receta ambigua.', dish['review_notes'][-1])
        self.assertEqual(app.menu_preflight(data)['review_count'], 1)

    def test_radar_and_universal_extractor_navigation(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=90).run()
        at.radio[0].set_value('🔎 Buscar información').run()
        self.assertFalse(at.exception)
        at.text_input[0].set_value('Restaurante QA')
        at.text_input[1].set_value('Madrid')
        at.button[0].click().run()
        self.assertFalse(at.exception)
        markdown = '\n'.join(item.value for item in at.markdown)
        self.assertIn('Ver el mapa', markdown)
        self.assertIn('Ver fotos y redes', markdown)
        self.assertIn('Leer opiniones', markdown)
        self.assertNotIn('Google Maps', markdown)
        self.assertNotIn('Instagram', markdown)
        self.assertNotIn('TripAdvisor', markdown)
        at.radio[0].set_value('📄 Sacar texto de un archivo').run()
        self.assertFalse(at.exception)
        self.assertEqual(at.title[0].value, 'Sacar texto de un archivo 📄')
        uploader = next(widget for widget in at.get('file_uploader') if widget.label == 'Sube tu archivo')
        uploader.set_value(('carta_qa.txt', b'Ensalada QA\n12,50 EUR', 'text/plain'))
        at.run()
        next(button for button in at.button if button.label == '🔄 Sacar el texto').click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any(button.label == '⬇️ Descargar Word con el texto' for button in at.get('download_button')))
        exported = Document(BytesIO(at.session_state.universal_bytes))
        self.assertIn('Ensalada QA', '\n'.join(paragraph.text for paragraph in exported.paragraphs))
        self.assertNotIn('Plato\t00,00', '\n'.join(paragraph.text for paragraph in exported.paragraphs))
        self.assertFalse(exported.sections[0].header._element.xpath('.//pic:pic'))

    def test_text_extractors_read_pdf_and_docx(self):
        import fitz
        source_pdf = BytesIO()
        pdf_doc = fitz.open()
        pdf_page = pdf_doc.new_page()
        pdf_page.insert_text((72, 72), 'Carta QA - Ensalada 12,50 EUR')
        source_pdf.write(pdf_doc.tobytes())
        source_pdf.seek(0)
        self.assertIn('Ensalada', app.extract_text_from_pdf(source_pdf))
        source_docx = Document()
        source_docx.add_paragraph('Carta QA · Ensalada 12,50 EUR')
        docx_buffer = BytesIO()
        source_docx.save(docx_buffer)
        docx_buffer.seek(0)
        self.assertIn('Ensalada', app.extract_text_from_docx(docx_buffer))

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
                for page in doc:
                    legend_rects = [rect for image in page.get_images(full=True)
                                    if image[2:4] == (7257, 1049)
                                    for rect in page.get_image_rects(image[0])]
                    self.assertEqual(len(legend_rects), 1 if allergens else 0)
                    if legend_rects:
                        body_bottom = max(block[3] for block in page.get_text('blocks') if block[6] == 0)
                        self.assertLess(body_bottom, legend_rects[0].y0)
        Path('qa/after/long.docx').write_bytes(app.create_word(long_menu).getvalue())

    def test_design_pdf_without_remote_generation(self):
        import fitz
        from ai_design import create_ai_menu_pdf
        background = BytesIO()
        Image.new('RGB', (600, 850), 'white').save(background, format='PNG')
        pdf = create_ai_menu_pdf(MENU, background.getvalue(), app.ICON_MAP)
        self.assertTrue(pdf.startswith(b'%PDF'))
        with fitz.open(stream=pdf, filetype='pdf') as document:
            self.assertTrue(any(image[2:4] == (7257, 1049) for image in document[0].get_images(full=True)))
        Path('qa/after/design.pdf').write_bytes(pdf)

    def test_all_premium_visual_structures_render(self):
        import fitz
        from pdf_backend import render_pdf
        for variant in ('cards', 'soft', 'compact', 'mesa', 'table'):
            with self.subTest(variant=variant):
                html = app.create_premium_v6_html(MENU, theme_key='cafe', variant=variant, show_dish_icons=True)
                self.assertIn('Ensalada de queso y nueces', html)
                self.assertIn(eider_legend_data_uri(), html)
                self.assertIn('class="dish-dots"' if variant != 'table' else 'class="table-dots"', html)
                pdf = render_pdf(html, app.BASE_DIR)
                self.assertTrue(pdf.startswith(b'%PDF'))
                with fitz.open(stream=pdf, filetype='pdf') as document:
                    text = app.normalize_text(''.join(page.get_text() for page in document)).lower()
                    self.assertIn('ensalada de queso y nueces', text)
                    self.assertTrue(any(image[2:4] == (7257, 1049) for image in document[0].get_images(full=True)))

    def test_visual_word_uses_selected_colors_and_icons(self):
        cafe = Document(app.create_premium_editable_word(MENU, theme_key='cafe'))
        burdeos = Document(app.create_premium_editable_word(MENU, theme_key='burdeos'))
        self.assertNotEqual(cafe.paragraphs[0].runs[0].font.color.rgb, burdeos.paragraphs[0].runs[0].font.color.rgb)
        row = next(p for p in burdeos.paragraphs if 'Ensalada de queso y nueces' in p.text)
        self.assertEqual(len(row._p.xpath('.//pic:pic')), 2)
        self.assertTrue(row._p.xpath(".//w:tab[@w:leader='dot']"))

    def test_long_visual_pdf_keeps_all_dishes_and_legend_on_each_page(self):
        import fitz
        from pdf_backend import render_pdf
        long_menu = copy.deepcopy(MENU)
        long_menu['categories'][0]['dishes'] *= 15
        html = app.create_premium_v6_html(long_menu, theme_key='noir', show_dish_icons=True)
        with fitz.open(stream=render_pdf(html, app.BASE_DIR), filetype='pdf') as document:
            self.assertGreater(len(document), 1)
            self.assertEqual(sum(page.get_text().count('ENSALADA DE QUESO Y NUECES') for page in document), 15)
            for page in document:
                legends = [rect for image in page.get_images(full=True)
                           if image[2:4] == (7257, 1049)
                           for rect in page.get_image_rects(image[0])]
                self.assertEqual(len(legends), 1)
                dish_blocks = [block for block in page.get_text('blocks')
                               if block[6] == 0 and 'ENSALADA DE QUESO Y NUECES' in block[4]]
                self.assertTrue(all(block[3] < legends[0].y0 for block in dish_blocks))

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

    def test_generator_tabs_remain_visible_before_menu_is_loaded(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=90).run()
        self.assertFalse(at.exception)
        self.assertEqual(at.title[0].value, 'Crear una carta 🥘')
        self.assertEqual(
            at.radio[0].options,
            ['📝 Crear carta', '🔎 Buscar información', '📄 Sacar texto de un archivo'],
        )
        self.assertNotIn('Carta IA', at.title[0].value)
        self.assertNotIn('Serval', ' '.join(at.radio[0].options))
        self.assertEqual(len(at.tabs), 7)
        tab_labels = [tab.label for tab in at.tabs]
        self.assertIn('📝 Word para editar', tab_labels)
        self.assertIn('📖 Carta horizontal', tab_labels)
        self.assertTrue(any('Sube o lee una carta' in item.value for item in at.info))
        self.assertEqual(len(at.get('download_button')), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
