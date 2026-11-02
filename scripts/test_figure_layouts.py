"""Regression coverage for picture grids, nested captions and acronym lists."""
import copy
from pathlib import Path
import tempfile
import unittest

from test_rules_checks import paragraph
from captions import fill_captions,is_figure_layout
from illustration_checks import check
import normokontrol as nk


def picture():
    p=paragraph('\ufffc')
    p['objects']=[{'type':'image'}]
    return p


def table(*cells):
    return {'kind':'table','rows':[{'cells':[{'blocks':blocks} for blocks in cells]}]}


class FigureLayoutTests(unittest.TestCase):
    def test_figure_grid_is_preserved_in_format_and_check_modes(self):
        grid=table([picture(),paragraph('Рисунок 1 — Первый снимок')],
                   [picture(),paragraph('Рисунок 2 — Второй снимок')])
        for check_only in (False,True):
            model={'body':[paragraph('Введение'),copy.deepcopy(grid)],'styles':{}}
            original=copy.deepcopy(model);issues=[];changes=[]
            fill_captions(model,changes,issues,check_only=check_only)
            self.assertTrue(is_figure_layout(grid))
            self.assertEqual(model,original)
            self.assertEqual(changes,[])
            self.assertEqual(issues,[])

    def test_data_table_with_an_image_still_requires_its_own_caption(self):
        grid=table([paragraph('Устройство'),picture()],
                   [paragraph('Характеристика'),paragraph('Значение: 42')])
        model={'body':[paragraph('Введение'),grid],'styles':{}}
        self.assertFalse(is_figure_layout(grid))
        issues=[]
        fill_captions(model,[],issues)
        self.assertTrue(model['body'][1]['text'].startswith('Таблица 1'))
        self.assertIn('caption-placeholder',{i['code'] for i in issues})

    def test_nested_caption_order_includes_cells_and_nested_tables(self):
        nested=table([paragraph('Рисунок 2.3 — Вложенный рисунок')])
        grid=table([picture(),paragraph('Рисунок 2.2 — Левый')],[nested])
        model={'body':[paragraph('Введение'),paragraph('Рисунок 2.1 — Начало'),grid,
                       paragraph('Рисунок 2.4 — Конец')],'styles':{}}
        issues=[];check(model,issues)
        self.assertEqual(issues,[])
        model['body'].append(paragraph('Рисунок 2.4 — Повтор'))
        issues=[];check(model,issues)
        self.assertIn('caption-number-duplicate',{i['code'] for i in issues})
        model['body'][-1]['text']='Рисунок 2.6 — Пропуск'
        issues=[];check(model,issues)
        self.assertIn('caption-number-order',{i['code'] for i in issues})

    def test_nested_caption_numbers_are_reserved_for_new_captions(self):
        model={'body':[paragraph('Введение'),
                       table([picture(),paragraph('Рисунок 1 — В ячейке')]),picture()],
               'styles':{}}
        fill_captions(model,[],[])
        self.assertTrue(model['body'][-1]['text'].startswith('Рисунок 2 —'))

    def test_missing_reference_to_nested_figure_is_reported(self):
        model={'body':[paragraph('Введение'),
                       table([picture(),paragraph('Рисунок 1 — Без ссылки')])],'styles':{}}
        issues=[];nk.structural_checks(None,model,'compact',issues)
        self.assertEqual([i['message'] for i in issues if i['code']=='reference'],
                         ['Не найдена текстовая ссылка: рисунок 1.'])
        model['body'].insert(1,paragraph('Результат приведён на рисунке 1.'))
        issues=[];nk.structural_checks(None,model,'compact',issues)
        self.assertNotIn('reference',{i['code'] for i in issues})

    def test_uppercase_acronyms_are_preserved_without_case_warnings(self):
        from list_checks import process
        for check_only in (False,True):
            entries=['- SUID (4000) – права владельца;',
                     '- SGID (2000) – права группы;',
                     '- ОС – операционная система;',
                     '- POSIX ACL – списки доступа;',
                     '- UTF-8 – кодировка.']
            model={'body':[paragraph('Введение'),paragraph('Механизмы:')]+
                          [paragraph(text) for text in entries],'styles':{}}
            original=copy.deepcopy(model);issues=[]
            process(model,[],issues,check_only=check_only)
            self.assertEqual(model,original)
            self.assertNotIn('list-case-review',{i['code'] for i in issues})
        model={'body':[paragraph('Введение'),paragraph('- КОНТРОЛЬ доступа;'),
                       paragraph('- Контроль доступа.')],'styles':{}}
        issues=[];process(model,[],issues,check_only=True)
        self.assertEqual(sum(i['code']=='list-case-review' for i in issues),2)

    def test_wordcraft_roundtrip_preserves_picture_grid_and_caption_sequence(self):
        from docx import Document
        from docx.shared import Inches
        from PIL import Image
        from normokontrol import inventory
        import pymupdf
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            image=root/'sample.png'
            Image.new('RGB',(240,120),'#123456').save(image)
            doc=Document();doc.add_heading('Введение',1)
            doc.add_paragraph('Результаты показаны на рисунках 1–3.')
            grid=doc.add_table(rows=1,cols=2)
            for i,cell in enumerate(grid.rows[0].cells,1):
                cell.paragraphs[0].add_run().add_picture(str(image),width=Inches(1.5))
                cell.add_paragraph(f'Рисунок {i} — Снимок {i}')
            doc.add_paragraph().add_run().add_picture(str(image),width=Inches(1.5))
            doc.add_paragraph('Рисунок 3 — Отдельный снимок')
            source=root/'source.docx';doc.save(source)
            report=nk.process(source,root/'out',progress=lambda _:None)
            result=root/'out'/report['docx_name']
            self.assertEqual(inventory(source)['media'],inventory(result)['media'])
            self.assertFalse(any(i['code'] in {'caption-number-order','caption-number-duplicate',
                                             'caption-placeholder','caption-missing','reference'}
                                 for i in report['issues']))
            final=Document(result)
            self.assertFalse(any(p.text.startswith('Таблица ') for p in final.paragraphs))
            with pymupdf.open(root/'out'/report['pdf_name']) as pdf:
                locations={number:next(i for i,p in enumerate(pdf) if f'Рисунок {number}' in p.get_text())
                           for number in (1,2,3)}
                self.assertEqual(locations[1],locations[2])


if __name__=='__main__':unittest.main()
