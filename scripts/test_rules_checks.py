import copy
import unittest

import normokontrol as nk
from rules_checks import check_rules


def paragraph(text, **props):
    return {'kind': 'para', 'text': text, 'props': props,
            'runs': [{'len': nk.byte_len(text), 'props': {}}]}


class RuleTests(unittest.TestCase):
    def test_contract_clauses_and_bullets_are_not_headings_from_numbers_alone(self):
        from structure import analyze
        numbered = {'nums':[{'id':1,'abstractId':1}],
                    'abstracts':[{'id':1,'levels':[{'format':'bullet','text':'-'}]}]}
        model={'body':[paragraph('Введение'), paragraph('1.1 Краткий заголовок'),
               paragraph('1.2. Стороны обязуются обеспечить сохранность всех переданных документов; доступ предоставляется только уполномоченным сотрудникам.'),
               paragraph('Ссылка на нормативный документ', numbering={'num':1,'level':0}, outlineLevel=1)],
               'styles':{},'numbering':numbered}
        structure=analyze(model)
        self.assertEqual(structure['levels'],{0:1,1:2})
        before=model['body'][2]['text']
        from normative import prepare
        prepare(model,[],[])
        self.assertEqual(model['body'][2]['text'],before)

    def test_native_heading_numbering_overrides_outline(self):
        numbering = {'nums': [{'id': 1, 'abstractId': 4}], 'abstracts': [
            {'id': 4, 'levels': [{'format': 'decimal', 'text': '%1.'},
                                 {'format': 'decimal', 'text': '%1.%2.'},
                                 {'format': 'decimal', 'text': '%1.%2.%3.'}]}]}
        styles = {'styles': [{'id': 'WrongHeading', 'para': {'outlineLevel': 0,
                  'pageBreakBefore': True, 'numbering': {'num': 1, 'level': 1}}}]}
        p = paragraph('Внутренние риски', style='WrongHeading')
        self.assertEqual(nk.heading_level(p, styles, numbering), 2)
        model = {'body': [paragraph('Глава 1. Теория'), p], 'styles': styles, 'numbering': numbering}
        nk.normalize_model(model, 'full', [])
        self.assertFalse(p['props']['pageBreakBefore'])
        self.assertEqual(p['props']['spaceAfter'], 24.15)
        p['props']['numbering']['level'] = 2
        self.assertEqual(nk.heading_level(p, styles, numbering), 3)
        self.assertEqual(nk.heading_level(paragraph('Глава 2. Практика'), {}), 1)
        self.assertEqual(nk.heading_level(paragraph('2 Практика'), {}), 1)
        self.assertEqual(nk.heading_level(paragraph('2.1 Подраздел'), {}), 2)

    def codes(self, body):
        model = {'body': body, 'styles': {}}
        original = copy.deepcopy(model)
        issues = []
        check_rules(model, 'full', issues)
        self.assertEqual(model, original)
        return {item['code'] for item in issues}

    def test_heading_sequence_parent_and_duplicate(self):
        codes = self.codes([paragraph('Введение'), paragraph('1 Раздел'),
                            paragraph('1.1 Подраздел'), paragraph('1.3 Пропуск'),
                            paragraph('1.3 Повтор'), paragraph('3.1 Без раздела')])
        self.assertTrue({'heading-sequence', 'heading-parent', 'heading-number'} <= codes)
        valid = self.codes([paragraph('1 Раздел', spaceAfter=24.15),
                            paragraph('1.1 Подраздел', spaceAfter=24.15),
                            paragraph('2 Раздел', spaceAfter=24.15, outlineLevel=0)])
        self.assertFalse(valid)

    def test_inherited_color_indent_and_heading_spacing(self):
        p = paragraph('Основной текст', style='Body')
        model = {'body': [paragraph('Введение'), p], 'styles': {'styles': [
            {'id': 'Body', 'para': {'indentFirst': 0}, 'chr': {'color': {'Rgb': [255, 0, 0]}}}]}}
        issues = []
        check_rules(model, 'full', issues)
        self.assertTrue({'heading-spacing', 'text-color', 'paragraph-indent'} <= {i['code'] for i in issues})

    def test_appendix_refs_order_and_exclusions(self):
        codes = self.codes([paragraph('Введение', spaceAfter=24.15),
            paragraph('Сначала см. приложение Б.', indentFirst=10*nk.MM),
            paragraph('Затем см. приложение А.', indentFirst=10*nk.MM),
            paragraph('Приложение А', spaceAfter=24.15), paragraph('Приложение Б', spaceAfter=24.15),
            paragraph('Приложение Ё', spaceAfter=24.15), paragraph('Приложение Б', spaceAfter=24.15)])
        self.assertTrue({'appendix-order', 'appendix-letter', 'appendix-reference', 'appendix-duplicate'} <= codes)
        self.assertNotIn('paragraph-indent', self.codes([
            paragraph('Введение', spaceAfter=24.15), paragraph('sudo command'),
            paragraph('Таблица 1 — Название'), paragraph('x = y')]))

    def test_normalize_keeps_required_heading_gap(self):
        model = {'body': [paragraph('Введение')], 'styles': {}}
        nk.normalize_model(model, 'full', [])
        self.assertEqual(model['body'][0]['props']['spaceAfter'], 24.15)
        self.assertNotIn('heading-spacing', self.codes(model['body']))

    def test_dotted_subheadings_override_wrong_style_and_page_break(self):
        for title, level in [('1.1. Подраздел', 2), ('1.2 Подраздел', 2),
                             ('1.1.1. Пункт', 3), ('1.1.1.1. Подпункт', 4),
                             ('1. Глава', 1)]:
            with self.subTest(title=title):
                p = paragraph(title, style='Heading1', pageBreakBefore=True)
                model = {'body': [paragraph('Введение'), p], 'styles': {'styles': [
                    {'id': 'Heading1', 'para': {'outlineLevel': 0, 'pageBreakBefore': True}}]}}
                self.assertEqual(nk.heading_level(p, model['styles']), level)
                nk.normalize_model(model, 'full', [])
                self.assertEqual(p['props']['outlineLevel'], level - 1)
                self.assertEqual(p['props']['spaceAfter'], 24.15)
                self.assertEqual(p['props']['pageBreakBefore'], level == 1)
                self.assertTrue(p['props']['keepNext'])

    def test_subheading_checks_preserve_check_only_input(self):
        codes = self.codes([paragraph('1 Глава', spaceAfter=24.15),
                            paragraph('1.1. Подраздел', pageBreakBefore=True, spaceAfter=0)])
        self.assertTrue({'subheading-spacing', 'subheading-page-break', 'heading-number-dot'} <= codes)


if __name__ == '__main__':
    unittest.main()
