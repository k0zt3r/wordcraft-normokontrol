import copy
import unittest
from list_checks import format_simple, process
from test_list_structure import model, item
from test_rules_checks import paragraph as p


class SimpleListTests(unittest.TestCase):
    def test_terminal_edit_detects_format_changes_outside_replacement(self):
        from list_checks import _terminal_edit
        from text_edits import replace
        from unittest.mock import patch
        source = p('Длинный пункт списка. Конец')
        source['runs'][0]['propertiesForTest'] = {'language': 'ru'}

        def corrupt(candidate, *args):
            result = replace(candidate, *args)
            candidate['runs'][0]['propertiesForTest']['language'] = 'en'
            return result
        with patch('text_edits.replace', side_effect=corrupt):
            with self.assertRaisesRegex(RuntimeError, 'форматирование'):
                _terminal_edit(source, 19, 20, ';')
        self.assertEqual(source['runs'][0]['propertiesForTest']['language'], 'ru')

    def test_terminal_edit_preserves_split_unicode_styles(self):
        from list_checks import _terminal_edit
        source = p('первый пункт.хвост')
        source['runs'] = [{'len': len(text.encode()), 'props': {'italic': italic}}
                          for text, italic in [('первый ', True), ('пункт', True), ('.', False), ('хвост', True)]]
        updated = _terminal_edit(source, 12, 13, ';')
        self.assertEqual(updated['text'], 'первый пункт;хвост')
        self.assertEqual(updated['runs'][-1], source['runs'][-1])

    def simple(self, entries=None):
        return model([p('Необходимо выполнить:')] + (entries or [item('первое действие.'), item('второе действие;')]))

    def test_only_terminal_punctuation_changes_and_is_idempotent(self):
        doc = self.simple()
        before = copy.deepcopy(doc)
        changes=[]
        format_simple(doc, changes, [])
        self.assertEqual([b['text'] for b in doc['body'][2:]], ['первое действие;', 'второе действие.'])
        self.assertEqual(doc['numbering'], before['numbering'])
        self.assertEqual(doc['body'][:2], before['body'][:2])
        for old,new in zip(before['body'][2:],doc['body'][2:]):
            self.assertEqual(new['text'][:-1], old['text'][:-1])
            self.assertEqual(new['props'], old['props'])
        issues=[];process(doc, [], issues)
        self.assertNotIn('list-punctuation',{i['code'] for i in issues})
        fixed=copy.deepcopy(doc);format_simple(doc, changes, [])
        self.assertEqual(doc,fixed)
        self.assertEqual(len(changes),1)

    def test_manual_list_keeps_markers_and_capitalization(self):
        doc=self.simple([p('- Москва'),p('- ФСТЭК;')])
        format_simple(doc,[],[])
        self.assertEqual([x['text'] for x in doc['body'][2:]], ['- Москва;', '- ФСТЭК.'])

    def test_check_only_is_completely_immutable(self):
        doc=self.simple();before=copy.deepcopy(doc);changes=[];issues=[]
        format_simple(doc,changes,issues,check_only=True)
        self.assertEqual(doc,before)
        self.assertEqual((changes,issues),([],[]))

    def test_items_are_formatted_independently_without_changing_structure(self):
        cases = [
            ([item('Первое. Второе предложение.'), item('второй пункт;')],
             ['Первое. Второе предложение;', 'второй пункт.'], ()),
            ([item('родитель:'), item('возможный подпункт.')],
             ['родитель:', 'возможный подпункт.'], (0,)),
            ([item('первый пункт'), item('вложенный пункт', depth=1)],
             ['первый пункт.', 'вложенный пункт.'], ()),
            ([item('первый пункт'), dict(item('второй пункт'), fields=[{'instr': 'REF'}])],
             ['первый пункт;', 'второй пункт'], (1,)),
            ([item('первый пункт'), dict(item('второй пункт'), objects=[{'type': 'image'}])],
             ['первый пункт;', 'второй пункт'], (1,)),
            ([item('первый пункт'), dict(item('второй пункт'), runs=[{'len': 1}])],
             ['первый пункт;', 'второй пункт'], (1,)),
            ([item('вопрос?'), item('второй пункт')], ['вопрос?', 'второй пункт.'], (0,)),
            ([item('цитата «текст»'), item('второй пункт')], ['цитата «текст»', 'второй пункт.'], (0,)),
            ([item('закончено...'), item('второй пункт')], ['закончено...', 'второй пункт.'], (0,)),
            ([item('действие и т.д.'), item('второй пункт')], ['действие и т.д.;', 'второй пункт.'], ()),
        ]
        for entries, expected, protected in cases:
            with self.subTest(expected=expected):
                doc = self.simple(entries)
                before = copy.deepcopy(doc)
                changes = []
                format_simple(doc, changes, [])
                self.assertEqual([x['text'] for x in doc['body'][2:]], expected)
                self.assertEqual(doc['numbering'], before['numbering'])
                self.assertEqual(doc['body'][:2], before['body'][:2])
                for old, updated in zip(before['body'][2:], doc['body'][2:]):
                    self.assertEqual(old['props'], updated['props'])
                for index in protected:
                    self.assertEqual(doc['body'][index + 2], before['body'][index + 2])
                fixed = copy.deepcopy(doc)
                change_count = len(changes)
                format_simple(doc, changes, [])
                self.assertEqual(doc, fixed)
                self.assertEqual(len(changes), change_count)

    def test_native_lists_do_not_require_colon_or_merge_neighboring_ids(self):
        cases = [
            (model([item('первый'), item('второй')]), ['первый;', 'второй.']),
            (model([p('Выполните:'), p(''), item('первый'), item('второй')]),
             ['Выполните:', '', 'первый;', 'второй.']),
            (model([item('предыдущий:', num=25), item('первый'), item('второй')]),
             ['предыдущий:', 'первый;', 'второй.']),
            (self.simple([item('первый'), item('второй'), item('другая группа', num=25)]),
             ['Необходимо выполнить:', 'первый;', 'второй.', 'другая группа']),
        ]
        for doc, expected in cases:
            with self.subTest(expected=expected):
                before = copy.deepcopy(doc)
                format_simple(doc, [], [])
                self.assertEqual([x['text'] for x in doc['body'][1:]], expected)
                self.assertEqual(doc['numbering'], before['numbering'])
                for old, updated in zip(before['body'], doc['body']):
                    self.assertEqual(old['props'], updated['props'])

    def test_run_formatting_and_bookmark_position_are_retained(self):
        first=item('первый пункт\ufffc')
        first['runs']=[{'len':len('первый '.encode()),'props':{'italic':True}},
                       {'len':len('пункт\ufffc'.encode()),'props':{'bold':False}}]
        first['objects']=[{'type':'bookmarkEnd','off':len('первый пункт'.encode())}]
        doc=self.simple([first,item('второй пункт')])
        format_simple(doc,[],[])
        updated=doc['body'][2]
        self.assertEqual(updated['text'],'первый пункт;\ufffc')
        self.assertEqual(updated['runs'][0],first['runs'][0])
        self.assertEqual(updated['objects'][0]['off'],len('первый пункт;'.encode()))

    def test_boundaries_do_not_block_following_explicit_lists_or_edit_contents(self):
        for separator in ({'kind': 'table', 'rows': []}, p('Заключение')):
            doc = model([p('Выполните:'), separator, item('первый'), item('второй')])
            before = copy.deepcopy(doc)
            format_simple(doc, [], [])
            self.assertEqual(doc['body'][:3], before['body'][:3])
            self.assertEqual([x['text'] for x in doc['body'][3:]], ['первый;', 'второй.'])
        for heading in ('Приложение А', 'Список литературы', 'Список использованных источников'):
            doc = model([p('Выполните:'), p(heading), item('первый'), item('второй')])
            before = copy.deepcopy(doc)
            format_simple(doc, [], [])
            self.assertEqual(doc, before)
        begin=dict(p('\ufffc'),objects=[{'type':'fieldStart','instr':'TOC'}])
        end=dict(p('\ufffc'),objects=[{'type':'fieldEnd'}])
        doc=model([p('Содержание'),begin,p('Выполните:'),item('первый'),item('второй'),end])
        before=copy.deepcopy(doc);format_simple(doc,[],[])
        self.assertEqual(doc,before)


if __name__=='__main__':
    unittest.main()
