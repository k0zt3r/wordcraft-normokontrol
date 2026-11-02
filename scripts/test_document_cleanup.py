import copy
from pathlib import Path
import tempfile
import unittest

from docx import Document
import pymupdf
import normokontrol as nk
from document_cleanup import prepare
from test_rules_checks import paragraph


class CleanupTests(unittest.TestCase):
    def test_literal_list_is_not_a_chapter(self):
        for title in ('1. Видеонаблюдение', '2. Датчики', '3. Контроль'):
            self.assertIsNone(nk.heading_level(paragraph(title), {}))
        self.assertEqual(nk.heading_level(paragraph('1 Теория'), {}), 1)
        self.assertEqual(nk.heading_level(paragraph('Глава 1. Теория'), {}), 1)
        self.assertEqual(nk.heading_level(paragraph('1. Глава', outlineLevel=0), {}), 1)

    def test_cleanup_readonly_and_duplicate_break(self):
        body = [paragraph('Введение'), paragraph('3.\tКонтроль'), paragraph('\f'), paragraph('Заключение')]
        model = {'body': body, 'styles': {}}
        original = copy.deepcopy(model)
        prepare(model, [], [], check_only=True)
        self.assertEqual(model, original)
        prepare(model, [], [])
        self.assertEqual(body[1]['text'], '3. Контроль')
        self.assertEqual(body[2]['text'], '')
        separate = {'body': [paragraph('Введение'), paragraph('\f'), paragraph('Обычный текст')], 'styles': {}}
        prepare(separate, [], [])
        self.assertEqual(separate['body'][1]['text'], '\f')

    def test_decimal_native_list_uses_space(self):
        from list_formatting import normalize
        model = {'styles': {}, 'numbering': {'nums': [{'id':1,'abstractId':0}],
            'abstracts': [{'id':0, 'levels':[{'format':'decimal','text':'%1.','suffix':'tab','tab':72}]}]}}
        p = paragraph('Контроль', numbering={'num':1,'level':0})
        normalize(model,p,None,{})
        level=model['numbering']['abstracts'][-1]['levels'][0]
        self.assertEqual(level['suffix'],'space')
        self.assertEqual(level['text'],'%1)')
        self.assertNotIn('tab',level)

    def test_bibliography_check_only_preserves_input(self):
        model={'body':[paragraph('Введение'),paragraph('Список литературы'),
                       paragraph('Описание источника.',numbering={'num':1,'level':0})], 'styles':{}}
        original=copy.deepcopy(model)
        issues=[]
        prepare(model,[],issues,check_only=True)
        self.assertEqual(model,original)
        self.assertTrue(any(i['code']=='bibliography-table' for i in issues))

    def test_real_lists_blank_page_bibliography_and_code_font(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            doc=Document()
            doc.add_heading('Введение',1)
            doc.add_paragraph('Текст введения.')
            doc.add_heading('Глава 1. Теория',1)
            for title in ('1. Видеонаблюдение','2. Датчики','3.\tКонтроль','4. Сигнализация'):
                doc.add_paragraph(title)
                doc.add_paragraph('Пояснение к пункту перечисления.')
            doc.add_paragraph('Автоматический пункт',style='List Number')
            doc.add_page_break()
            doc.add_heading('Заключение',1)
            doc.add_paragraph('Выводы по работе.')
            doc.add_heading('Список использованных источников',1)
            doc.add_paragraph('Первый источник.',style='List Bullet')
            doc.add_paragraph('Второй источник.',style='List Bullet')
            source=folder/'source.docx'
            doc.save(source)
            code='КР.420200.10.03.01.ПЗ'
            report=nk.process(source,folder/'out',metadata={'code':code},progress=lambda _:None)
            result=Document(folder/'out'/report['docx_name'])
            for p in result.paragraphs:
                if p.text.startswith(('1. Виде','2. Дат','3. Конт','4. Сиг')):
                    self.assertFalse(p.paragraph_format.page_break_before)
                    self.assertEqual(p.paragraph_format.space_after.pt,0)
            table=result.tables[-1]
            self.assertEqual([r.cells[0].text for r in table.rows],['1','2'])
            self.assertEqual([r.cells[1].text for r in table.rows],['Первый источник.','Второй источник.'])
            with pymupdf.open(folder/'out'/report['pdf_name']) as pdf:
                self.assertEqual(len(pdf),5)  # cover, introduction, chapter, conclusion, sources
                for page in pdf:
                    self.assertTrue(page.get_text(clip=pymupdf.Rect(65,20,page.rect.width-20,page.rect.height-90)).strip())
                    for b in page.get_text('dict')['blocks']:
                        for line in b.get('lines',[]):
                            for span in line['spans']:
                                if span['text']==code and span['bbox'][1]>page.rect.height-60:
                                    self.assertAlmostEqual(span['size'],16,places=1)
                                if span['text']=='Изм.':
                                    self.assertAlmostEqual(span['size'],9,places=1)


if __name__ == '__main__':
    unittest.main()
