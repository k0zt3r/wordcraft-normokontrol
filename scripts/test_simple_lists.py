import copy
import unittest
from list_checks import format_simple, process
from test_list_structure import model, item
from test_rules_checks import paragraph as p


class SimpleListTests(unittest.TestCase):
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

    def test_entire_ambiguous_clusters_are_unchanged(self):
        cases=[
            [item('Первое. Второе предложение.'),item('второй пункт;')],
            [item('родитель:'),item('возможный подпункт.')],
            [item('первый пункт'),item('вложенный пункт',depth=1)],
            [item('первый пункт'),dict(item('второй пункт'),fields=[{'instr':'REF'}])],
            [item('первый пункт'),dict(item('второй пункт'),objects=[{'type':'image'}])],
            [item('первый пункт'),dict(item('второй пункт'),runs=[{'len':1}])],
            [item('вопрос?'),item('второй пункт')],
            [item('цитата «текст»'),item('второй пункт')],
            [item('закончено...'),item('второй пункт')],
            [item('действие и т.д.'),item('второй пункт')],
        ]
        for entries in cases:
            with self.subTest(entries=entries):
                doc=self.simple(entries);before=copy.deepcopy(doc);changes=[]
                format_simple(doc,changes,[])
                self.assertEqual(doc,before)
                self.assertEqual(changes,[])

    def test_no_colon_blank_or_neighboring_other_list_id(self):
        docs=[model([item('первый'),item('второй')]),
              model([p('Выполните:'),p(''),item('первый'),item('второй')]),
              model([item('предыдущий:',num=25),item('первый'),item('второй')]),
              self.simple([item('первый'),item('второй'),item('другая группа',num=25)])]
        for doc in docs:
            before=copy.deepcopy(doc);format_simple(doc,[],[])
            self.assertEqual(doc,before)

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

    def test_table_heading_and_generated_contents_are_boundaries(self):
        for separator in ({'kind':'table','rows':[]},p('Заключение'),p('Приложение А')):
            doc=model([p('Выполните:'),separator,item('первый'),item('второй')])
            before=copy.deepcopy(doc);format_simple(doc,[],[])
            self.assertEqual(doc,before)
        begin=dict(p('\ufffc'),objects=[{'type':'fieldStart','instr':'TOC'}])
        end=dict(p('\ufffc'),objects=[{'type':'fieldEnd'}])
        doc=model([p('Содержание'),begin,p('Выполните:'),item('первый'),item('второй'),end])
        before=copy.deepcopy(doc);format_simple(doc,[],[])
        self.assertEqual(doc,before)


if __name__=='__main__':
    unittest.main()
