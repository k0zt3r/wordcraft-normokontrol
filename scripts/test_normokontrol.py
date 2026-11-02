"""Integration checks against the installed Wordcraft; no writes to source documents."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from docx import Document
from docx.shared import Pt

import normokontrol as nk
from irgups_data import generate_number, prepare_metadata, unit_code, UNIVERSITY_NAME, UNIVERSITY_SHORT


class NormokontrolTests(unittest.TestCase):
    def test_dotted_subheadings_wordcraft_roundtrip(self):
        with tempfile.TemporaryDirectory(prefix='subheading-test-') as directory:
            folder = Path(directory)
            doc = Document()
            for title in ('Введение', '1 Глава', '1.1. Подраздел', '1.1.1. Пункт', '1.2 Подраздел'):
                heading = doc.add_heading(title, 1)
                heading.paragraph_format.page_break_before = True
                doc.add_paragraph('Текст сразу после заголовка.')
            source = folder / 'source.docx'
            doc.save(source)
            report = nk.process(source, folder / 'result', progress=lambda _: None)
            result = Document(folder / 'result' / report['docx_name'])
            subs = [p for p in result.paragraphs if p.text in {'1.1 Подраздел', '1.1.1 Пункт', '1.2 Подраздел'}]
            self.assertEqual(len(subs), 3)
            for p in subs:
                self.assertFalse(p.paragraph_format.page_break_before)
                self.assertEqual(p.paragraph_format.space_after.pt, 24.15)
            self.assertFalse(any(i['code'] in {'subheading-spacing', 'subheading-page-break'} for i in report['issues']))
            self.assertFalse(any(i['code'] == 'heading-number-dot' for i in report['issues']))

    def test_native_list_marker_and_heading_indent(self):
        from list_formatting import normalize
        model = {'numbering': {'nums': [{'id': 1, 'abstractId': 0}],
                 'abstracts': [{'id': 0, 'levels': [{'format': 'bullet', 'text': '•', 'indent': 72, 'hanging': 18, 'chr': {'font': 'Symbol'}}]}]}, 'styles': {}}
        para = {'props': {'numbering': {'num': 1, 'level': 0}, 'indentLeft': 72}}
        self.assertTrue(normalize(model, para, None, {}))
        level = model['numbering']['abstracts'][-1]['levels'][0]
        self.assertEqual(level['text'], '-')
        self.assertEqual(level['suffix'], 'space')
        self.assertEqual(para['props']['indentFirst'], 10 * nk.MM)
        self.assertEqual(para['props']['indentLeft'], 0)
        self.assertEqual(para['props']['align'], 'justify')
        self.assertEqual(model['numbering']['abstracts'][0]['levels'][0]['text'], '•')

    def test_simple_list_punctuation_and_alignment_roundtrip(self):
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        with tempfile.TemporaryDirectory(prefix='simple-lists-') as directory:
            folder = Path(directory)
            doc = Document()
            doc.add_paragraph('Курсовая работа')
            doc.add_paragraph('Иркутск 2026')
            doc.add_heading('Введение', 1)
            doc.add_paragraph('Предусмотрены следующие меры:')
            for text in ('первая мера', 'вторая мера'):
                p = doc.add_paragraph(text)
                props = p._p.get_or_add_pPr()
                number = OxmlElement('w:numPr')
                level = OxmlElement('w:ilvl'); level.set(qn('w:val'), '0')
                instance = OxmlElement('w:numId'); instance.set(qn('w:val'), '1')
                number.extend([level, instance]); props.append(number)
            source = folder / 'source.docx'
            doc.save(source)
            original = hashlib.sha256(source.read_bytes()).hexdigest()
            for check in (True, False):
                report = nk.process(source, folder / str(check), check_only=check, progress=lambda _: None)
                out = Document(Path(report['output']) / report['docx_name'])
                items = [p for p in out.paragraphs if p.text.startswith(('первая мера', 'вторая мера'))]
                self.assertEqual([p.text for p in items], ['первая мера', 'вторая мера'] if check else ['первая мера;', 'вторая мера.'])
                if not check:
                    from docx.enum.text import WD_ALIGN_PARAGRAPH
                    self.assertTrue(all(p.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY for p in items))
                    self.assertFalse(any(i['code'] == 'list-punctuation' for i in report['issues']))
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original)

    def test_whitespace_cleanup_preserves_runs_and_breaks(self):
        import copy
        from whitespace_cleanup import clean
        body = [{'kind': 'para', 'text': 'Введение'},
                {'kind': 'para', 'text': 'Один  два ', 'runs': [{'len': len('Один  '.encode()), 'props': {'italic': True}}, {'len': len('два '.encode())}]},
                {'kind': 'para', 'text': ' '}, {'kind': 'para', 'text': '\f'},
                {'kind': 'para', 'text': '\ufffc', 'objects': [{'type': 'image'}]}]
        model = {'body': body, 'styles': {}}
        before = copy.deepcopy(model)
        clean(model, [], [], check_only=True)
        self.assertEqual(model, before)
        clean(model, [], [])
        self.assertEqual(body[1]['text'], 'Один два')
        self.assertTrue(body[1]['runs'][0]['props']['italic'])
        self.assertEqual(body[2]['text'], '\f')
        self.assertEqual(body[3]['objects'][0]['type'], 'image')

    def test_caption_checks_do_not_mutate(self):
        import copy
        from captions import fill_captions
        model = {'body': [{'kind': 'para', 'text': 'Введение'},
                         {'kind': 'para', 'text': 'Рисунок 1 — Схема'},
                         {'kind': 'para', 'text': '\ufffc', 'objects': [{'type': 'image'}]},
                         {'kind': 'table', 'rows': []}], 'styles': {}}
        original = copy.deepcopy(model)
        issues = []
        fill_captions(model, [], issues, check_only=True)
        self.assertEqual(model, original)
        self.assertTrue(any(i['code'] == 'caption-position' for i in issues))
        self.assertTrue(any(i['code'] == 'caption-missing' for i in issues))

    def test_missing_captions_and_repeat_run(self):
        from captions import fill_captions
        def p(text):
            return {'kind': 'para', 'text': text}
        model = {'body': [p('Титульник'), p('Введение'),
                         {'kind': 'para', 'text': '\ufffc', 'objects': [{'type': 'image'}]},
                         {'kind': 'table', 'rows': []},
                         {'kind': 'para', 'text': '\ufffc', 'objects': [{'type': 'image'}]},
                         p('Список использованных источников'), {'kind': 'table', 'rows': []}], 'styles': {}}
        changes, issues = [], []
        fill_captions(model, changes, issues)
        texts = [b.get('text', '') for b in model['body']]
        self.assertIn('Рисунок 1 — Впишите название рисунка', texts)
        self.assertIn('Рисунок 2 — Впишите название рисунка', texts)
        self.assertIn('Таблица 1 — Впишите название таблицы', texts)
        self.assertEqual(len(changes), 3)
        fill_captions(model, changes, issues)
        self.assertEqual(len(changes), 3)

    def test_auto_contents_field_roundtrip(self):
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            doc = Document()
            doc.add_paragraph('Тестовая работа')
            doc.add_page_break()
            doc.add_paragraph('Содержание')
            p = doc.add_paragraph()
            for kind in ('begin', 'instruction', 'separate'):
                element = OxmlElement('w:instrText' if kind == 'instruction' else 'w:fldChar')
                if kind == 'instruction':
                    element.text = ' TOC \\o "1-3" \\h '
                else:
                    element.set(qn('w:fldCharType'), kind)
                p.add_run()._r.append(element)
            p.add_run('Введение\t3')
            p = doc.add_paragraph('Заключение\t4')
            end = OxmlElement('w:fldChar')
            end.set(qn('w:fldCharType'), 'end')
            p.add_run()._r.append(end)
            doc.add_page_break()
            doc.add_heading('Введение', 1)
            doc.add_paragraph('Контрольный текст работы.')
            doc.add_heading('Заключение', 1)
            doc.add_paragraph('Выводы по работе.')
            source = folder / 'auto.docx'
            doc.save(source)
            for check in (False, True):
                report = nk.process(source, out=folder / str(check), check_only=check, progress=lambda _: None)
                self.assertFalse(any(i['code'] == 'toc-missing' for i in report['issues']))
                result = Document(folder / str(check) / report['docx_name'])
                self.assertIn('Контрольный текст работы.', [p.text for p in result.paragraphs])

    def test_auto_contents_keeps_surrounding_text(self):
        para = {'kind': 'para', 'text': 'До\ufffcстарые строки\ufffcПосле',
                'objects': [{'type': 'fieldStart', 'instr': 'TOC'}, {'type': 'fieldEnd'}]}
        self.assertEqual(nk.auto_toc_text([para])[(0,)], 'ДоПосле')
        nested=[{'kind':'para','text':'\ufffc','objects':[{'type':'fieldStart','instr':'PAGE'}]},
                {'kind':'para','text':'Обычный текст вне TOC'},
                {'kind':'para','text':'\ufffcСтроки TOC\ufffcПосле',
                 'objects':[{'type':'fieldStart','instr':'TOC'},{'type':'fieldEnd'}]},
                {'kind':'para','text':'\ufffc','objects':[{'type':'fieldEnd'}]}]
        self.assertEqual(nk.auto_toc_text(nested),{(2,):'После'})
        with self.assertRaises(ValueError):
            nk.auto_toc_text([{'kind':'para','text':'\ufffcНе закрыто',
                              'objects':[{'type':'fieldStart','instr':'TOC'}]}])

    def test_manual_indent_runs_and_year_without_comma(self):
        p = {'kind': 'para', 'text': '  Текст', 'runs': [{'len': 2}, {'len': 10}]}
        nk.trim_manual_indent(p)
        self.assertEqual(p['text'], 'Текст')
        self.assertEqual(p['runs'], [{'len': 10}])
        model = {'body': [{'kind': 'para', 'text': '\ufffcИркутск 2024', 'objects': [{'type': 'opaque', 'off': 0}]},
                          {'kind': 'para', 'text': 'Введение'}], 'styles': {}}
        nk.fill_cover(model, {'year': '2026'}, [])
        self.assertEqual(model['body'][0]['text'], '\ufffcИркутск, 2026')
        self.assertEqual(model['body'][0]['objects'][0]['off'], 0)

    def test_visible_font_runs(self):
        parts = ['\ufffc\ufffc', 'Актуальность темы', ' ', 'Текст']
        para = {'text': ''.join(parts), 'runs': [{'len': len(t.encode('utf-8'))} for t in parts]}
        self.assertEqual([text for _, text in nk.visible_text_runs(para)], ['Актуальность темы', 'Текст'])

    def test_registration_from_pdf_examples_and_locked_institution(self):
        self.assertEqual(generate_number('ПП','450200','23.05.05'),'ПП.450200.23.05.05.ПЗ')
        self.assertEqual(generate_number('ДП','450200','23.05.05',account='001',year='2017'),
                         'ДП.450200.23.05.05.001-2017.ПЗ')
        self.assertEqual(generate_number('КР','420200','10.03.01',year='2026',include_year=True),
                         'КР.420200.10.03.01-2026.ПЗ')
        self.assertEqual(unit_code('Информационные системы и защита информации'),'420200')
        self.assertIsNone(unit_code('Транспортное машиностроение'))
        for kwargs in ({'division':'4202'}, {'specialty':'10'}, {'work':'ДП'}, {'work':'ОН'}):
            params=dict(work='КР',division='420200',specialty='10.03.01');params.update(kwargs)
            with self.assertRaises(ValueError): generate_number(**params)
        meta=prepare_metadata({'university':'Иной вуз','university_short':'ИВ'})
        self.assertEqual(meta['university'],UNIVERSITY_NAME)
        self.assertEqual(meta['university_short'],UNIVERSITY_SHORT)
    def test_references_and_ranges(self):
        self.assertTrue(nk.reference_exists('На рисунке Б.1 показано устройство.', 'Рисунок', 'Б.1'))
        self.assertTrue(nk.reference_exists('На рисунках Б.2–Б.5.', 'Рисунок', 'Б.3'))
        self.assertTrue(nk.reference_exists('См. рис. Б.1.', 'Рисунок', 'Б.1'))
        self.assertFalse(nk.reference_exists('См. рисунок Б.10.', 'Рисунок', 'Б.1'))
        self.assertEqual(nk.norm('\ufffc\f\ufffcВведение'), 'введение')

    def test_contents_with_merged_header_and_continuation(self):
        def para(text):
            return {'kind': 'para', 'text': text}
        def row(*texts):
            return {'cells': [{'blocks': [para(t)]} for t in texts]}
        body = [para('\ufffc'), {'kind': 'table', 'rows': [row('Содержание'), row('', '', 'Введение', '4')]},
                para('\f'), {'kind': 'table', 'rows': [row('', 'Заключение', '53')]},
                para('\ufffc\fВведение'), {'kind': 'table', 'rows': [row('Данные', '1')]}]
        self.assertEqual(nk.detect_tocs(body), [1, 3])
        self.assertEqual(nk.body_start({'body': body}), 1)
        before = nk.stable_text({'body': body}, 1)
        body[3]['rows'][0]['cells'][-1]['blocks'][0]['text'] = '54'
        self.assertEqual(nk.stable_text({'body': body}, 1), before)
        body[1]['rows'][0]['cells'][0]['blocks'][0]['text'] = 'Удалённый заголовок'
        self.assertNotEqual(nk.stable_text({'body': body}, 1), before)
        self.assertTrue(nk.reference_exists("На рисунке 2.18: опыт.", "Рисунок", "2.18"))
        self.assertTrue(nk.reference_exists("На рисунках 2.7–2.9.", "Рисунок", "2.8"))
        self.assertTrue(nk.reference_exists("См. таблицу 1.1.", "Таблица", "1.1"))
        self.assertFalse(nk.reference_exists("См. таблицу 1.10.", "Таблица", "1.1"))
        self.assertFalse(nk.reference_exists("См. рисунок 2.1.", "Рисунок", "2.18"))

    def test_real_wordcraft_pipeline(self):
        try:
            cli = nk.find_cli()
        except RuntimeError as error:
            self.skipTest(str(error))
        with tempfile.TemporaryDirectory(prefix="normokontrol-test-") as directory:
            folder = Path(directory)
            source = folder / "Работа с пробелами.docx"
            doc = Document()
            doc.add_heading("Содержание", level=1)
            toc = doc.add_table(rows=4, cols=4)
            titles = ["Введение", "1 Основная часть", "Заключение", "Список использованных источников"]
            for row, title in zip(toc.rows, titles):
                row.cells[2].text = title
                row.cells[3].text = "999"
            doc.add_heading("Введение", level=1)
            para = doc.add_paragraph("Текст введения. Подробности приведены в таблице 1.1.")
            para.runs[0].font.name = "Arial"
            para.runs[0].font.size = Pt(9)
            para.runs[0].bold = True
            doc.add_heading("1 Основная часть", level=1)
            doc.add_paragraph("Таблица 1.1 – Пример данных")
            table = doc.add_table(rows=3, cols=2)
            for i, row in enumerate(table.rows):
                for j, cell in enumerate(row.cells):
                    cell.text = f"Ячейка {i}, {j}"
            doc.add_paragraph('for x in /srv/*; do\n  echo "$x"\ndone')
            doc.add_heading("Заключение", level=1)
            doc.add_paragraph("Результат проверен.")
            doc.add_heading("Список использованных источников", level=1)
            bibliography = doc.add_table(rows=1, cols=2)
            bibliography.cell(0, 0).text = "1"
            bibliography.cell(0, 1).text = "Описание источника."
            doc.save(source)
            before = hashlib.sha256(source.read_bytes()).hexdigest()

            checked = nk.process(source, folder / "check", check_only=True, cli=cli, progress=lambda _: None)
            self.assertTrue(any(item["code"] in {"font", "font-size", "bold"} for item in checked["issues"]))
            self.assertTrue(any(item["code"] == "toc-page" for item in checked["issues"]))

            result = nk.process(source, folder / "fixed", cli=cli, progress=lambda _: None)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
            self.assertTrue((folder / "fixed" / result["pdf_name"]).is_file())
            self.assertTrue((folder / "fixed" / "report.html").is_file())
            final = Document(folder / "fixed" / result["docx_name"])
            fixed_para = next(p for p in final.paragraphs if p.text.startswith("Текст введения"))
            self.assertEqual(fixed_para.runs[0].font.name, "Times New Roman")
            self.assertEqual(fixed_para.runs[0].font.size.pt, 14)
            self.assertFalse(fixed_para.runs[0].bold)
            introduction = next(p for p in final.paragraphs if p.text == 'Введение')
            self.assertAlmostEqual(introduction.paragraph_format.space_after.pt, 24.15, places=1)
            self.assertFalse(any(item['code'] in {'heading-spacing', 'paragraph-indent', 'text-color'}
                                 for item in result['issues']))
            shell = next(p for p in final.paragraphs if p.text.startswith('for x in'))
            self.assertEqual(shell.alignment, 0)  # Left, not stretched across manual line breaks.
            final_toc = next(t for t in final.tables if len(t.columns) == 4)
            self.assertTrue(all(row.cells[3].text != "999" for row in final_toc.rows))
            self.assertFalse(any(item["code"] == "toc-page" for item in result["issues"]))
            self.assertFalse(any(item["code"] == "frame-missing" for item in result["issues"]))
            import pymupdf
            with pymupdf.open(folder / "fixed" / result["pdf_name"]) as pdf:
                self.assertNotIn("Изм.", pdf[0].get_text())
                for page in list(pdf)[1:]:
                    self.assertIn("Изм.", page.get_text())
                    drawings = page.get_drawings()
                    bottom=page.rect.height-5*nk.MM
                    big=any(s['text']=='Литера' for b in page.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans'])
                    stamp_top=bottom-(40 if big else 15)*nk.MM
                    stamp_spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans'] if s['bbox'][1]>=stamp_top-.1]
                    self.assertTrue(stamp_spans)
                    self.assertTrue(all('ISOCPEUR' in s['font'].upper() and abs(s['size']-9)<.01 for s in stamp_spans))
                    if big:
                        def vertical(x,y0,y1):
                            return any(abs(d['rect'].x0-x)<.02 and abs(d['rect'].x1-x)<.02 and
                                       abs(d['rect'].y0-y0)<.02 and abs(d['rect'].y1-y1)<.02 for d in drawings)
                        sx=20*nk.MM
                        self.assertTrue(vertical(sx+135*nk.MM,stamp_top+15*nk.MM,bottom))
                        self.assertTrue(vertical(sx+150*nk.MM,stamp_top+15*nk.MM,stamp_top+25*nk.MM))
                        self.assertTrue(vertical(sx+165*nk.MM,stamp_top+15*nk.MM,stamp_top+25*nk.MM))
                        self.assertFalse(vertical(sx+120*nk.MM,stamp_top+15*nk.MM,bottom))
                        self.assertIn('Пров.',page.get_text())
                        self.assertNotIn('Реценз.',page.get_text())
                    frame = next(d for d in drawings if abs(d['rect'].x0 - 20 * nk.MM) < .02 and
                                 abs(d['rect'].y0 - 5 * nk.MM) < .02 and d['rect'].height > 700)
                    self.assertAlmostEqual(frame['width'], .75, places=3)
                    self.assertEqual(frame['items'][0][0], 're')
                    # Every stroke in the lower 15 mm stamp has the same width.
                    for drawing in drawings:
                        if drawing['rect'].y0 > page.rect.height - 20 * nk.MM and drawing.get('type') != 'f':
                            self.assertAlmostEqual(drawing['width'], .75, places=3)
                    # Expand the outer rectangle and the stamp lines into segments.
                    segments = []
                    for drawing in drawings:
                        if drawing is not frame and drawing['rect'].y0 + .02 < page.rect.height - 45 * nk.MM:
                            continue
                        for item in drawing['items']:
                            if item[0] == 'l':
                                segments.append((item[1], item[2]))
                            elif item[0] == 're':
                                r = item[1]
                                segments.extend(((r.tl,r.tr),(r.tr,r.br),(r.br,r.bl),(r.bl,r.tl)))
                    def on_segment(p, a, b):
                        if abs(a.x-b.x) < .001:
                            return abs(p.x-a.x) < .001 and min(a.y,b.y)-.001 <= p.y <= max(a.y,b.y)+.001
                        return abs(p.y-a.y) < .001 and min(a.x,b.x)-.001 <= p.x <= max(a.x,b.x)+.001
                    for si, segment in enumerate(segments):
                        for point in segment:
                            self.assertTrue(any(on_segment(point,*other) for oi,other in enumerate(segments) if oi!=si),
                                            f'Unjoined line endpoint: {point}')
            with self.assertRaises(ValueError):
                nk.process(source, folder / "fixed", cli=cli, progress=lambda _: None)

            compact = nk.process(source, folder / "compact", mode="compact", cli=cli, progress=lambda _: None)
            compact_doc = Document(folder / "compact" / compact["docx_name"])
            self.assertAlmostEqual(compact_doc.sections[0].left_margin.mm, 30, places=1)
            self.assertIn("PAGE", compact_doc.sections[0].footer._element.xml)
            self.assertTrue(result["automated_only"])

    def test_new_document_course_templates_and_optional_fields(self):
        try:
            cli = nk.find_cli()
        except RuntimeError as error:
            self.skipTest(str(error))
        with tempfile.TemporaryDirectory(prefix="normokontrol-new-test-") as directory:
            output = Path(directory) / "empty"
            report = nk.create_document(output, cli=cli, toc_template=True,
                                        bibliography_template=True, progress=lambda _: None)
            doc = Document(output / report['docx_name'])
            toc = next(t for t in doc.tables if len(t.columns) == 4)
            refs = next(t for t in doc.tables if len(t.rows) == 25)
            self.assertEqual(len(toc.rows), 15)
            self.assertEqual(len(refs.columns), 2)
            self.assertTrue(all(not c.text for row in toc.rows for c in row.cells))
            self.assertTrue(all(not c.text for row in refs.rows for c in row.cells))
            text = '\n'.join(p.text for p in doc.paragraphs) + '\n'.join(c.text for t in doc.tables for row in t.rows for c in row.cells)
            signatures=next(t for t in doc.tables if len(t.rows)==1 and len(t.columns)==2)
            for cell in signatures.rows[0].cells:
                self.assertFalse(cell.paragraphs[1].text)
                self.assertFalse(cell.paragraphs[2].text)
            self.assertEqual(report['pages'], 3)
            empty=nk.create_document(Path(directory)/'blank-no-options',cli=cli,progress=lambda _:None)
            self.assertTrue(empty['created_from_template'])
            self.assertTrue((Path(directory)/'blank-no-options'/empty['docx_name']).is_file())
            empty_doc=Document(Path(directory)/'blank-no-options'/empty['docx_name'])
            self.assertFalse(any(p.text.startswith('Таблица ') for p in empty_doc.paragraphs))
            filled = nk.create_document(Path(directory) / 'filled', cli=cli, toc_template=True,
                        bibliography_template=True, metadata={'author':'Иванов И.И.', 'group':'БИ.4-23-1',
                        'supervisor':'Петров П.П.', 'supervisor_title':'доцент, к.т.н.', 'title':'Тестовая работа',
                        'work_type':'КУРСОВАЯ РАБОТА', 'discipline':'Тест', 'city':'Иркутск', 'year':'2026'},
                        toc_entries=['Введение', '1 Основная часть', 'Заключение'],
                        bibliography_entries=['Первый источник.', 'Второй источник.'], progress=lambda _: None)
            final = Document(Path(directory) / 'filled' / filled['docx_name'])
            self.assertEqual(filled['pages'], 3)
            strings = '\n'.join(p.text for p in final.paragraphs) + '\n'.join(c.text for t in final.tables for r in t.rows for c in r.cells)
            for text in ('Иванов И.И.', 'Петров П.П.', 'доцент, к.т.н.', 'Тестовая работа', 'Первый источник.'):
                self.assertIn(text, strings)
            final_toc = next(t for t in final.tables if len(t.columns) == 4)
            self.assertEqual(len(final_toc.rows), 3)

            extras=nk.create_document(Path(directory)/'extras',cli=cli,toc_template=True,bibliography_template=True,
                metadata={'generate_code':True,'work_code':'ДП','division_code':'420200','specialty':'10.03.01',
                          'account':'001','year':'2026','approval':True,'approval_person':'Иванов И.И.',
                          'approval_title':'Заведующий кафедрой'},
                optional_sections=['annotation','normative','abbreviations'],progress=lambda _:None)
            import pymupdf
            with pymupdf.open(Path(directory)/'extras'/extras['pdf_name']) as pdf:
                all_text='\n'.join(p.get_text() for p in pdf)
                self.assertIn('ДП.420200.10.03.01.001-2026.ПЗ',all_text)
                self.assertIn('К ЗАЩИТЕ ДОПУСКАЮ',all_text)
                self.assertEqual(len(pdf),6)
                self.assertIn('Аннотация',pdf[1].get_text())
                self.assertIn('Содержание',pdf[2].get_text())
                self.assertIn('Листов',pdf[1].get_text())
                self.assertNotIn('Листов',pdf[2].get_text())
                self.assertIn('Нормативные ссылки',pdf[3].get_text())
                self.assertIn('Обозначения и сокращения',pdf[4].get_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
