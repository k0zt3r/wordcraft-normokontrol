"""Agent contract, clean CLI output and real document roundtrips."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from docx import Document
import agent_api as api


class AgentAPITests(unittest.TestCase):
    def test_schema_rejects_typos_types_and_unsupported_options(self):
        for name, arguments in [
            ('unknown', {}), ('doctor', []), ('doctor', None), ('doctor', {'wordcaft': 'wrong'}),
            ('format_document', {'input': 'a.docx'}),
            ('format_document', {'input': 'a.docx', 'out': 'out', 'format_text': 'false'}),
            ('check_document', {'input': 'a.docx', 'metadata': {'author': 'Ignored?'}}),
            ('create_document', {'out': 'out', 'metadata': {'year': 2026}}),
            ('create_document', {'out': 'out', 'metadata': {'unknown': 'value'}}),
            ('create_document', {'out': 'out', 'optional_sections': ['unknown']}),
            ('format_document', {'input':'a.docx','out':'out','cover_mode':'guess'}),
        ]:
            with self.subTest(name=name, arguments=arguments), patch.object(api, '_engine') as engine:
                result = api.invoke(name, arguments)
                self.assertFalse(result['ok'])
                self.assertEqual(result['error']['code'], 'invalid_request')
                engine.assert_not_called()

    def test_source_registry_and_capabilities_available_with_broken_engine(self):
        with patch.object(api, '_engine', side_effect=ValueError('Broken profile')):
            result = api.invoke('get_capabilities')
            self.assertTrue(result['ok'])
            self.assertEqual(len(result['data']['tools']), 7)
            rule = api.invoke('get_requirement', {'reference': '6.2'})
            self.assertTrue(rule['ok'])
            self.assertTrue(rule['data']['rules'])
            self.assertTrue(all(c['page'] > 5 for c in rule['data']['clauses']))
            diagnosis = api.invoke('doctor')
            self.assertTrue(diagnosis['ok'])
            self.assertFalse(diagnosis['data']['ready'])
            self.assertFalse(diagnosis['data']['checks']['profile']['ok'])

    def test_cli_json_stdin_unicode_and_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            for arguments, expected_code in [({'search': 'шифр'}, 0), ({'search': 42}, 1)]:
                reply = subprocess.run([sys.executable, str(api.ROOT / 'normokontrol.py'),
                                        '--agent', 'get_requirement', '--request', '-'],
                                       cwd=folder, input=json.dumps(arguments, ensure_ascii=False),
                                       text=True, encoding='utf-8', capture_output=True, timeout=20)
                self.assertEqual(reply.returncode, expected_code, reply.stderr)
                result = json.loads(reply.stdout)
                self.assertEqual(result['schema_version'], 1)
                self.assertEqual(result['ok'], expected_code == 0)
            reply = subprocess.run([sys.executable, str(api.ROOT / 'normokontrol.py'),
                                    '--agent', 'doctor', '--request', '-'], cwd=folder,
                                   input='{bad', text=True, encoding='utf-8', capture_output=True, timeout=20)
            self.assertEqual(reply.returncode, 1)
            self.assertEqual(json.loads(reply.stdout)['error']['code'], 'invalid_request')
            reply = subprocess.run([sys.executable, str(api.ROOT / 'normokontrol.py'),
                                    '--agent', 'doctor', '--request'], cwd=folder,
                                   text=True, encoding='utf-8', capture_output=True, timeout=20)
            self.assertEqual(reply.returncode, 1)
            self.assertEqual(json.loads(reply.stdout)['error']['code'], 'invalid_request')

    def test_requirements_reject_changed_source(self):
        with patch.object(Path, 'read_bytes', return_value=b'changed source'):
            result = api.invoke('get_requirement', {'reference': '6.2'})
        self.assertFalse(result['ok'])
        self.assertIn('PDF', result['error']['message'])

    def test_real_check_format_report_and_no_overwrite(self):
        engine = api._engine()
        try:
            engine.find_cli()
        except RuntimeError as error:
            self.skipTest(str(error))
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / 'Исходник.docx'
            doc = Document()
            doc.add_paragraph('Курсовая работа')
            doc.add_paragraph('Иркутск 2026')
            doc.add_heading('Введение', 1)
            doc.add_paragraph('Текст учебной работы.')
            doc.save(source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            for name in ('check_document', 'format_document'):
                output = folder / name
                arguments = {'input': str(source), 'out': str(output)}
                if name == 'check_document':
                    reply = subprocess.run([sys.executable, str(api.ROOT / 'normokontrol.py'),
                        '--agent', name, '--request', '-'], cwd=folder,
                        input=json.dumps(arguments, ensure_ascii=False), text=True,
                        encoding='utf-8', capture_output=True, timeout=60)
                    self.assertEqual(reply.returncode, 0, reply.stderr)
                    result = json.loads(reply.stdout)
                    self.assertIn('Wordcraft', reply.stderr)
                else:
                    result = api.invoke(name, arguments)
                self.assertTrue(result['ok'], result['error'])
                self.assertEqual(result['status'], 'completed_with_findings')
                data = result['data']
                self.assertEqual(data['report']['check_only'], name == 'check_document')
                self.assertTrue(all(Path(p).is_file() for p in data['artifacts'].values()))
                report = api.invoke('get_report', {'path': str(output), 'severity': 'review'})
                self.assertTrue(report['ok'], report['error'])
                self.assertTrue(all(i['severity'] == 'review' for i in report['data']['issues']))
                before = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in data['artifacts'].values()}
                repeat = api.invoke(name, {'input': str(source), 'out': str(output)})
                self.assertFalse(repeat['ok'])
                self.assertEqual(before, {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in before})
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)
            preserved=api.invoke('format_document', {'input':str(source), 'out':str(folder/'preserved'),
                                                   'cover_mode':'preserve'})
            self.assertTrue(preserved['ok'],preserved['error'])
            self.assertEqual(preserved['data']['report']['cover_mode'],'preserve')

    def test_real_create_template(self):
        try:
            api._engine().find_cli()
        except RuntimeError as error:
            self.skipTest(str(error))
        with tempfile.TemporaryDirectory() as folder:
            result = api.invoke('create_document', {'out': str(Path(folder) / 'new'),
                'metadata': {'author': 'И.И. Иванов', 'title': 'Проверка интерфейса'}})
            self.assertTrue(result['ok'], result['error'])
            self.assertTrue(result['data']['report']['created_from_template'])
            self.assertTrue(Path(result['data']['artifacts']['docx']).is_file())


if __name__ == '__main__':
    unittest.main()
