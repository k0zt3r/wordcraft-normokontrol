import hashlib
import json
from pathlib import Path
import unittest
import tempfile
from normokontrol import byte_len
from normative import prepare,code


class NormativeTests(unittest.TestCase):
    def test_legacy_preferences_cannot_override_normative_values(self):
        from format_profile import load, DEFAULT_PATH
        defaults=json.loads(DEFAULT_PATH.read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as directory:
            local=Path(directory)/'profile.json'
            local.write_text(json.dumps({'font':'Arial','text_size':10,'subheading_gap_pt':0,
                                         'stamp_code_size':18}),encoding='utf-8')
            actual=load(local)
        for key in ('font','text_size','subheading_gap_pt'):
            self.assertEqual(actual[key],defaults[key])
        self.assertEqual(actual['stamp_code_size'],18)

    def test_source_complete_and_bound_to_pdf(self):
        root=Path(__file__).resolve().parent.parent
        data=json.loads((root/'references/norm-source/source.json').read_text(encoding='utf-8'))
        self.assertEqual(len(data['pages']),46)
        self.assertEqual(data['sha256'],hashlib.sha256((root/'Normokontrol.pdf').read_bytes()).hexdigest())
        self.assertTrue(all((root/'references/norm-source'/asset['file']).is_file() for asset in data['assets']))

    def test_course_code_is_not_vkr_account(self):
        self.assertEqual(code('КР.420200.10.03.01.119.ПЗ'),'КР.420200.10.03.01.ПЗ')
        self.assertEqual(code('ДП.420200.10.03.01.001-2026.ПЗ'),'ДП.420200.10.03.01.001-2026.ПЗ')

    def test_chapter_context_fixes_subsection_prefix(self):
        def p(text):return {'kind':'para','text':text,'runs':[{'len':byte_len(text)}]}
        model={'body':[p('Введение'),p('Глава 3. Раздел'),p('1.1. Подраздел'),p('Список литературы')],'styles':{}}
        issues=[]
        prepare(model,[],issues)
        self.assertEqual(model['body'][1]['text'],'3 Раздел')
        self.assertEqual(model['body'][2]['text'],'3.1 Подраздел')
        self.assertEqual(model['body'][3]['text'],'Список использованных источников')
        self.assertTrue(any(i['code']=='heading-reference-review' for i in issues))


if __name__=='__main__':unittest.main()
