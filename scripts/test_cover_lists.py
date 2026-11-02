import copy
from pathlib import Path
import tempfile
import unittest

from docx import Document
from docx.shared import Pt
import pymupdf
import normokontrol as nk
from list_checks import process
from test_rules_checks import paragraph as p
from text_edits import replace


class CoverListTests(unittest.TestCase):
    def test_cover_boundary_stops_before_images(self):
        from structure import cover_end
        model={'body':[p('Курсовая работа'),p('Иркутск 2026'),p('\f'),
                       dict(p('\ufffc'),objects=[{'type':'image'}]),p('Введение')], 'styles':{}}
        self.assertEqual(cover_end(model),3)

    def test_lab_sources_optional_and_bare_chapters(self):
        from document_policy import required
        from structure import analyze
        model={'body':[p('Отчёт по лабораторной работе'),p('Иркутск 2026'),
                       p('Теоретическая часть',align='center'),p('Практическая часть',align='center')], 'styles':{}}
        self.assertEqual(required(model),())
        self.assertEqual(analyze(model)['levels'][2],1)

    def test_invisible_artifacts_preserve_overlays(self):
        from artifact_cleanup import process
        model={'body':[dict(p('\ufffc\ufffc'),objects=[{'type':'shape','fill':None,'stroke':None},
              {'type':'shape','fill':[255,255,255],'stroke':None,'float':{'wrap':'inFrontOfText'}}])]}
        process(model,[],[])
        self.assertEqual(len(model['body'][0]['objects']),1)

    def test_plain_list_punctuation_and_markers(self):
        model={'body':[p('Введение'),p('1. первый пункт.'),p('2. второй пункт;')],'styles':{}}
        process(model,[],[])
        self.assertEqual([x['text'] for x in model['body'][1:]],['1) первый пункт;','2) второй пункт.'])
        before=copy.deepcopy(model)
        process(model,[],[])
        self.assertEqual(model,before)

    def test_check_only_keeps_case_and_text(self):
        model={'body':[p('Введение'),p('- Москва'),p('- ФСТЭК')],'styles':{}}
        before=copy.deepcopy(model);issues=[]
        process(model,[],issues,check_only=True)
        self.assertEqual(model,before)
        self.assertIn('list-case-review',{i['code'] for i in issues})

    def test_nested_list_last_item_before_outer_continuation(self):
        numbering={'nums':[{'id':1,'abstractId':1}], 'abstracts':[{'id':1,'levels':[
            {'format':'bullet','text':'-'},{'format':'decimal','text':'%2)'}]}]}
        model={'body':[p('Введение'),p('- родитель:'),
            p('первый подпункт',numbering={'num':1,'level':1}),
            p('второй подпункт',numbering={'num':1,'level':1}),p('- продолжение')],
            'styles':{},'numbering':numbering}
        process(model,[],[])
        self.assertTrue(model['body'][3]['text'].endswith(';'))
        self.assertTrue(model['body'][4]['text'].endswith('.'))

    def test_bookmarks_and_runs_survive_punctuation_edit(self):
        para=p('текст\ufffc')
        para['objects']=[{'type':'bookmarkEnd','off':nk.byte_len('текст')}]
        self.assertTrue(replace(para,5,5,'.'))
        self.assertEqual(para['text'],'текст.\ufffc')
        self.assertEqual(sum(r['len'] for r in para['runs']),nk.byte_len(para['text']))
        self.assertEqual(para['objects'][0]['off'],nk.byte_len('текст.'))

    def test_existing_cover_and_second_page_without_contents(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            doc=Document()
            doc.add_paragraph('Факультет «Тест»')
            department=doc.add_paragraph('Кафедра «Тест»')
            department.paragraph_format.space_after=Pt(66)
            doc.add_paragraph('курсовая работа')
            doc.add_paragraph('по дисциплине «Тест»')
            doc.add_paragraph('Тестовая тема')
            table=doc.add_table(rows=1,cols=2)
            table.cell(0,0).text='Выполнил\nстудент\nИванов И.И.'
            table.cell(0,1).text='Руководитель\nдоцент\nПетров П.П.'
            doc.add_paragraph('Иркутск 2026')
            doc.add_heading('Введение',1);doc.add_paragraph('Текст введения.')
            doc.add_heading('1 Глава',1);doc.add_paragraph('Текст главы.')
            doc.add_heading('Содержание',1);doc.add_table(rows=1,cols=4)
            source=root/'source.docx';doc.save(source)
            report=nk.process(source,root/'out',progress=lambda _:None)
            result=Document(root/'out'/report['docx_name'])
            self.assertIn('Курсовая работа',[x.text for x in result.paragraphs])
            with pymupdf.open(root/'out'/report['pdf_name']) as pdf:
                self.assertGreater(pdf[0].search_for('Иркутск')[0].y0,pdf[0].rect.height-100)
                big=[i+1 for i,page in enumerate(pdf) if 'Литера' in page.get_text()]
                self.assertEqual(big,[2])
            self.assertNotIn('cover-city-position',{i['code'] for i in report['issues']})


if __name__=='__main__':
    unittest.main()
