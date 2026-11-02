import copy
import unittest
from list_checks import process
from test_rules_checks import paragraph as p


def model(entries):
    numbering={'nums':[{'id':24,'abstractId':1},{'id':25,'abstractId':1}],
               'abstracts':[{'id':1,'levels':[{'format':'bullet','text':'-'},
                                            {'format':'bullet','text':'-'}]}]}
    return {'body':[p('Введение')]+entries,'styles':{},'numbering':numbering}


def item(text,depth=0,num=24):
    return p(text,numbering={'num':num,'level':depth})


class ListStructureTests(unittest.TestCase):
    def test_flat_efimova_group_is_reviewed_without_text_edits(self):
        doc=model([item('Регулярное обучение. Обучение должно включать:'),
                   item('Основы безопасности информации. Объяснение принципов.'),
                   item('Политики и процедуры компании. Ознакомление сотрудников.'),
                   item('Примеры утечек и их последствия. Обсуждение случаев.'),
                   item('Информирование о рисках. Это может включать:'),
                   item('Проведение вебинаров и семинаров.')])
        original=copy.deepcopy(doc)
        for check_only in (False,True):
            changes=[];issues=[]
            process(doc,changes,issues,check_only=check_only)
            self.assertEqual(doc,original)
            self.assertEqual(changes,[])
            reviews=[i['message'] for i in issues if i['code']=='list-structure-review']
            self.assertEqual(len(reviews),2)
            self.assertIn('Основы безопасности',reviews[0])
            self.assertIn('Проведение вебинаров',reviews[1])
            repeated=[];process(doc,[],repeated,check_only=check_only)
            self.assertEqual(repeated,issues)

    def test_native_nesting_and_internal_colon_are_not_flat_warnings(self):
        for entries in ([item('Меры:'),item('Первый подпункт',1),item('Второй подпункт',1)],
                        [item('Настройка: пример внутри предложения.'),item('Далее.')]):
            issues=[];process(model(entries),[],issues)
            self.assertNotIn('list-structure-review',{i['code'] for i in issues})

    def test_independent_list_ids_and_boundaries(self):
        boundaries=[{'kind':'table','rows':[]},p('Обычный абзац.'),p('Заключение'),
                    dict(p('\ufffc'),objects=[{'type':'image'}]),p('Список литературы'),
                    p('Приложение А')]
        for boundary in boundaries:
            doc=model([item('Меры:'),boundary,item('Продолжение.')])
            issues=[];process(doc,[],issues)
            self.assertNotIn('list-structure-review',{i['code'] for i in issues})
        issues=[];process(model([item('Меры:'),item('Другая группа.',num=25)]),[],issues)
        self.assertNotIn('list-structure-review',{i['code'] for i in issues})

    def test_names_acronyms_and_formatting_are_unchanged(self):
        doc=model([item('Меры:'),item('Москва'),item('ФСТЭК'),item('UTF-8')])
        before=copy.deepcopy(doc);issues=[]
        process(doc,[],issues)
        self.assertEqual(doc,before)
        messages=[i['message'] for i in issues if i['code']=='list-case-review']
        self.assertTrue(any('Москва' in x for x in messages))
        self.assertFalse(any('ФСТЭК' in x or 'UTF-8' in x for x in messages))

    def test_generated_contents_is_not_list_content(self):
        begin=dict(p('\ufffc'),objects=[{'type':'fieldStart','instr':'TOC'}])
        end=dict(p('\ufffc'),objects=[{'type':'fieldEnd'}])
        doc=model([p('Содержание'),begin,item('Меры:'),item('Старая строка содержания.'),end,p('Заключение')])
        before=copy.deepcopy(doc);issues=[]
        process(doc,[],issues)
        self.assertEqual(doc,before)
        self.assertFalse(any(i['code'].startswith('list-') for i in issues))


if __name__=='__main__':
    unittest.main()
