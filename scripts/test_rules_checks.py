import copy
import unittest

import normokontrol as nk
from rules_checks import check_rules


def paragraph(text, **props):
    return {'kind': 'para', 'text': text, 'props': props,
            'runs': [{'len': nk.byte_len(text), 'props': {}}]}


class RuleTests(unittest.TestCase):
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
        valid = self.codes([paragraph('1 Раздел', spaceAfter=28),
                            paragraph('1.1 Подраздел', spaceAfter=28),
                            paragraph('2 Раздел', spaceAfter=28)])
        self.assertFalse(valid)

    def test_inherited_color_indent_and_heading_spacing(self):
        p = paragraph('Основной текст', style='Body')
        model = {'body': [paragraph('Введение'), p], 'styles': {'styles': [
            {'id': 'Body', 'para': {'indentFirst': 0}, 'chr': {'color': {'Rgb': [255, 0, 0]}}}]}}
        issues = []
        check_rules(model, 'full', issues)
        self.assertTrue({'heading-spacing', 'text-color', 'paragraph-indent'} <= {i['code'] for i in issues})

    def test_appendix_refs_order_and_exclusions(self):
        codes = self.codes([paragraph('Введение', spaceAfter=28),
            paragraph('Сначала см. приложение Б.', indentFirst=10*nk.MM),
            paragraph('Затем см. приложение А.', indentFirst=10*nk.MM),
            paragraph('Приложение А', spaceAfter=28), paragraph('Приложение Б', spaceAfter=28),
            paragraph('Приложение Ё', spaceAfter=28), paragraph('Приложение Б', spaceAfter=28)])
        self.assertTrue({'appendix-order', 'appendix-letter', 'appendix-reference', 'appendix-duplicate'} <= codes)
        self.assertNotIn('paragraph-indent', self.codes([
            paragraph('Введение', spaceAfter=28), paragraph('sudo command'),
            paragraph('Таблица 1 — Название'), paragraph('x = y')]))

    def test_normalize_keeps_required_heading_gap(self):
        model = {'body': [paragraph('Введение')], 'styles': {}}
        nk.normalize_model(model, 'full', [])
        self.assertEqual(model['body'][0]['props']['spaceAfter'], 28)
        self.assertNotIn('heading-spacing', self.codes(model['body']))


if __name__ == '__main__':
    unittest.main()
