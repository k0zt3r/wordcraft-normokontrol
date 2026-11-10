"""Final-document locations, duplicate text and safe local report links."""
import unittest
from unittest.mock import Mock

from reporting import finding_link, locate_findings, render


class FindingTests(unittest.TestCase):
    def test_missing_caret_does_not_abort_report_or_hide_the_finding(self):
        from normokontrol import add_issue
        from runtime import PositionUnavailable
        issues = []
        add_issue(issues, 'font', 'Paragraph in a non-addressable cell', path=[0])
        engine = Mock()
        engine.locate.side_effect = PositionUnavailable('No caret')
        locate_findings(issues, {'body': [{'kind': 'para', 'text': 'Protected paragraph'}]}, engine)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['location_status'], 'unavailable')
        self.assertNotIn('x', issues[0]['location'])
        self.assertIn('не предоставил точные координаты', render(issues))
        engine.locate.side_effect = RuntimeError('Engine failed')
        with self.assertRaisesRegex(RuntimeError, 'Engine failed'):
            locate_findings(issues, {'body': [{'kind': 'para', 'text': 'Protected paragraph'}]}, engine)

    def test_embedded_highlight_uses_reported_duplicate_and_leaves_pdf_unchanged(self):
        import base64
        import hashlib
        from pathlib import Path
        import re
        import tempfile
        import pymupdf
        from reporting import highlighted_places
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'review.pdf'
            with pymupdf.open() as doc:
                page = doc.new_page()
                page.insert_text((72, 80), 'Repeated target line')
                page.insert_text((72, 400), 'Repeated target line')
                doc.save(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            issue = dict(code='font', message='Font check', page=1,
                         location=dict(path=[2], x=72, y=389, text='Repeated target line'))
            duplicate = dict(issue, code='font-size')
            global_issue = dict(code='structure', message='Missing section', page=None)
            links, html = highlighted_places(path, [issue, duplicate, global_issue])
            self.assertEqual(len(links), 2)
            self.assertEqual(links[id(issue)], links[id(duplicate)])
            self.assertEqual(html.count('<img '), 1)
            self.assertIn('href="#place-1"', render([issue], path.name, links))
            data = base64.b64decode(re.search('base64,([A-Za-z0-9+/=]+)', html)[1])
            pixmap = pymupdf.Pixmap(data)
            pixels = memoryview(pixmap.samples)
            yellow_rows = [i // (pixmap.width * pixmap.n) for i in range(0, len(pixels), pixmap.n)
                           if pixels[i] > 180 and pixels[i+1] > 140 and pixels[i+2] < 210]
            self.assertTrue(yellow_rows, 'The embedded crop must visibly contain the yellow highlight')
            self.assertLess(max(yellow_rows), pixmap.height / 2)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            with pymupdf.open(path) as doc:
                self.assertIsNone(doc[0].first_annot)

    def test_explicit_position_distinguishes_identical_paragraphs(self):
        from normokontrol import add_issue
        issues = []
        add_issue(issues, 'font', 'Повторяющийся текст', path=[1])
        engine = Mock()
        engine.locate.return_value = dict(page=2, x=30, y=40)
        locate_findings(issues, {'body': [{'kind': 'para', 'text': 'Одинаковый текст'}] * 2}, engine)
        engine.locate.assert_called_once_with([1])
        self.assertEqual(issues[0]['page'], 2)

    def test_unique_excerpt_located_once_for_repeated_checks(self):
        engine = Mock()
        engine.locate.return_value = dict(page=4, x=80, y=200)
        issues = [dict(code='font', message=f'{label}: Проверяемый абзац документа', page=None)
                  for label in ('Шрифт', 'Отступ')]
        locate_findings(issues, {'body': [{'kind': 'para', 'text': 'Проверяемый абзац документа.'}]}, engine)
        engine.locate.assert_called_once_with([0])
        self.assertEqual([i['page'] for i in issues], [4, 4])
        self.assertEqual(issues[0]['location']['path'], [0])
        link = finding_link(issues[0], 'работа #1.pdf')
        self.assertIn('#page=4&amp;zoom=125,60,160', link)
        self.assertIn('%23', link)

    def test_ambiguous_or_document_wide_findings_are_not_guessed(self):
        engine = Mock()
        issues = [dict(code='font', message='Шрифт: Повторяющийся абзац документа', page=2),
                  dict(code='structure', message='Не найдено заключение.', page=None)]
        model = {'body': [{'kind': 'para', 'text': 'Повторяющийся абзац документа'}] * 2}
        locate_findings(issues, model, engine)
        engine.locate.assert_not_called()
        self.assertNotIn('location', issues[0])
        self.assertIn('#page=2', finding_link(issues[0], 'work.pdf'))
        self.assertEqual(finding_link(issues[1], 'work.pdf'), '')

    def test_nested_table_path_and_html_escaping(self):
        engine = Mock()
        engine.locate.return_value = dict(page=3, x=30, y=40)
        issues = [dict(code='font', message='Проверка: Текст внутри таблицы <script>', page=None)]
        model = {'body': [{'kind': 'table', 'rows': [{'cells': [{'blocks': [
            {'kind': 'para', 'text': 'Текст внутри таблицы <script>'}]}]}]}]}
        locate_findings(issues, model, engine)
        self.assertEqual(issues[0]['location']['path'], [0, 0, 0, 0])
        output = render(issues, 'a"&.pdf')
        self.assertNotIn('<script>', output)
        self.assertIn('a%22%26.pdf#page=3', output)


if __name__ == '__main__':
    unittest.main()
