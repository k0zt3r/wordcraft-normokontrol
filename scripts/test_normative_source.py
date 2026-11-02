import hashlib
import json
from pathlib import Path
import unittest
import tempfile
from normokontrol import byte_len
from normative import prepare,code


class NormativeTests(unittest.TestCase):
    def test_report_numbers_changes_and_links_actual_clauses(self):
        import re
        from reporting import render_changes,render_sources,change_details,severity
        changes=['Учебный шифр приведён к формуле §6.2.',
                 'Расстояние после заголовков: два интервала (приложение Е).',
                 'Техническая очистка пробелов.']
        rendered=render_changes(changes)+render_sources(changes)
        self.assertIn('<ol>',rendered)
        self.assertEqual([c['number'] for c in change_details(changes)],[1,2,3])
        for target in re.findall(r'href="#([^"]+)"',rendered):
            if target!='changes':self.assertIn(f'id="{target}"',rendered)
        self.assertIn('Расстояние между заголовком и текстом',rendered)
        self.assertIn('прямой пункт положения не установлен',rendered)
        self.assertEqual(severity('cover-approval'),'review')

    def test_spacing_is_two_measured_wordcraft_steps_after_docx_roundtrip(self):
        from docx import Document
        import pymupdf
        import normokontrol as nk
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            doc=Document()
            doc.add_heading('Введение',1)
            doc.add_paragraph('First\nSecond')
            source=folder/'input.docx'
            doc.save(source)
            report=nk.process(source,folder/'out',mode='compact',progress=lambda _:None)
            with pymupdf.open(folder/'out'/report['pdf_name']) as pdf:
                points={s['text']:s['origin'][1] for b in pdf[0].get_text('dict')['blocks'] if 'lines' in b
                        for line in b['lines'] for s in line['spans']}
            step=points['Second']-points['First']
            gap=points['First']-points['Введение']
            self.assertAlmostEqual(gap,2*step,delta=.1)

    def test_long_manual_contents_is_preserved_without_duplicate_table(self):
        from docx import Document
        import normokontrol as nk
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            doc=Document()
            doc.add_heading('Содержание',1)
            entries=['Введение ................ 2','1 Раздел ................ 3','1.1 Подраздел ................ 4']
            for text in entries:doc.add_paragraph(text)
            doc.add_heading('Введение',1)
            for i in range(11):
                p=doc.add_paragraph('Ordinary body paragraph '+str(i))
                p.paragraph_format.page_break_before=True
            source=folder/'input.docx'
            doc.save(source)
            report=nk.process(source,folder/'out',progress=lambda _:None)
            final=Document(folder/'out'/report['docx_name'])
            self.assertEqual(sum(p.text=='Содержание' for p in final.paragraphs),1)
            self.assertFalse(any('таблица содержания' in change.lower() or 'содержание заполнено' in change.lower() for change in report['changes']))
            self.assertTrue(all(entry in [p.text for p in final.paragraphs] for entry in entries))
            self.assertTrue(any(i['code']=='toc-manual-review' for i in report['issues']))

    def test_legacy_preferences_cannot_override_normative_values(self):
        from format_profile import load, DEFAULT_PATH
        defaults=json.loads(DEFAULT_PATH.read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as directory:
            local=Path(directory)/'profile.json'
            local.write_text(json.dumps({'font':'Arial','text_size':10,'subheading_gap_pt':0,
                                         'stamp_code_size':18}),encoding='utf-8')
            actual=load(local)
        for key in ('font','text_size','subheading_gap_pt'):
            self.assertEqual(actual[key],defaults[key])
        self.assertEqual(actual['stamp_code_size'],18)

    def test_source_complete_and_bound_to_pdf(self):
        root=Path(__file__).resolve().parent.parent
        data=json.loads((root/'references/norm-source/source.json').read_text(encoding='utf-8'))
        self.assertEqual(len(data['pages']),46)
        self.assertEqual(data['sha256'],hashlib.sha256((root/'Normokontrol.pdf').read_bytes()).hexdigest())
        self.assertTrue(all((root/'references/norm-source'/asset['file']).is_file() for asset in data['assets']))

    def test_course_code_is_not_vkr_account(self):
        self.assertEqual(code('КР.420200.10.03.01.119.ПЗ'),'КР.420200.10.03.01.ПЗ')
        self.assertEqual(code('ДП.420200.10.03.01.001-2026.ПЗ'),'ДП.420200.10.03.01.001-2026.ПЗ')

    def test_chapter_context_fixes_subsection_prefix(self):
        def p(text):return {'kind':'para','text':text,'runs':[{'len':byte_len(text)}]}
        model={'body':[p('Введение'),p('Глава 3. Раздел'),p('1.1. Подраздел'),p('Список литературы')],'styles':{}}
        issues=[]
        prepare(model,[],issues)
        self.assertEqual(model['body'][1]['text'],'3 Раздел')
        self.assertEqual(model['body'][2]['text'],'3.1 Подраздел')
        self.assertEqual(model['body'][3]['text'],'Список использованных источников')
        self.assertTrue(any(i['code']=='heading-reference-review' for i in issues))


if __name__=='__main__':unittest.main()
