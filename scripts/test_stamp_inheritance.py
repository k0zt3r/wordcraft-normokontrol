"""Rendered regression for stamp labels inheriting body paragraph indents."""
from pathlib import Path
import hashlib
import re
import tempfile
import unittest

from docx import Document
from docx.shared import Cm
import pymupdf
import normokontrol as nk


class StampInheritanceTests(unittest.TestCase):
    def test_stamp_labels_remain_complete_with_indented_normal_style(self):
        with tempfile.TemporaryDirectory(prefix='stamp-inheritance-') as directory:
            root = Path(directory)
            document = Document()
            normal = document.styles['Normal'].paragraph_format
            normal.first_line_indent = Cm(1)
            normal.left_indent = Cm(.3)
            normal.right_indent = Cm(.3)
            document.add_paragraph('Лабораторная работа')
            document.add_paragraph('Иркутск, 2026')
            for title in ('1 Первый раздел', '2 Второй раздел'):
                heading = document.add_heading(title, 1)
                heading.paragraph_format.page_break_before = True
                document.add_paragraph('Текст пользователя сохраняется без изменения.')
            source = root / 'source.docx'
            document.save(source)
            original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            report = nk.process(source, root / 'result', format_text=False,
                                metadata={'author': 'Рыжих М.С.', 'supervisor': 'Бутин А.А.',
                                          'group': 'БИ.4-23-1', 'code': 'ЛР.420200.10.03.01.ПЗ',
                                          'stamp_title': 'Проверка подписей'}, progress=lambda _: None)
            with pymupdf.open(root / 'result' / report['pdf_name']) as pdf:
                self.assertGreaterEqual(len(pdf), 3)
                for index, page in enumerate(pdf):
                    if index == 0:
                        continue
                    region = pymupdf.Rect(0, page.rect.height - 45 * nk.MM,
                                           page.rect.width, page.rect.height)
                    lines = page.get_text(clip=region).splitlines()
                    text = ' '.join(lines)
                    for label in ('Изм.', 'Лист', '№ докум.', 'Подпись', 'Дата'):
                        # PDF extraction can merge adjacent cells onto one line
                        # with Times New Roman; still require each complete label.
                        self.assertRegex(text, r'(?<!\S)' + re.escape(label) + r'(?!\S)', (index + 1, lines))
                    if index == 1:
                        for label in ('Разраб.', 'Пров.', 'Н.контр.', 'Утв.',
                                      'Рыжих М.С.', 'Бутин А.А.', 'Литера', 'Листов'):
                            self.assertRegex(text, r'(?<!\S)' + re.escape(label) + r'(?!\S)', lines)
                    spans = [span for block in page.get_text('dict', clip=region)['blocks']
                             if 'lines' in block for line in block['lines'] for span in line['spans']]
                    expected_font = nk.STAMP_FONT.replace(' ', '').upper()
                    self.assertTrue(all(expected_font in span['font'].replace(' ', '').upper() for span in spans))
                    code = [span for span in spans if 'ЛР.420200.10.03.01.ПЗ' in span['text']]
                    self.assertTrue(code)
                    self.assertTrue(all(abs(span['size'] - 16) < .01 for span in code))
                    labels = [span for span in spans if 'Изм.' in span['text']]
                    self.assertTrue(labels)
                    self.assertTrue(all(abs(span['size'] - 9) < .01 for span in labels))
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original_hash)


if __name__ == '__main__':
    unittest.main()
