"""Independent installer diagnostics and dependency selection."""
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

import agent_api
import normokontrol
import setup_support


class SetupSupportTests(unittest.TestCase):
    def test_installed_wordcraft_configuration_and_private_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configured = root / 'external-cli.exe'
            configured.write_bytes(b'fixture')
            private = root / 'wordcraft/wordcraft-cli.exe'
            private.parent.mkdir()
            private.write_bytes(b'fixture')
            (root / '.normokontrol-dependencies.json').write_text(
                '{"wordcraft_cli": ' + __import__('json').dumps(str(configured)) + '}', encoding='utf-8')
            with patch.object(normokontrol, '__file__', str(root / 'scripts/normokontrol.py')), \
                    patch.dict(normokontrol.os.environ, {'WORDCRAFT_CLI': ''}):
                self.assertEqual(normokontrol.find_cli(), str(configured.resolve()))
                configured.unlink()
                self.assertEqual(normokontrol.find_cli(), str(private.resolve()))

    def test_present_python_does_not_hide_missing_pdf_dependency(self):
        engine = MagicMock()
        engine.PROFILE = {'stamp_font': 'Times New Roman'}
        engine.find_cli.return_value = 'wordcraft-cli.exe'
        version = types.SimpleNamespace(returncode=0, stdout='wordcraft-cli 0.16.0', stderr='')
        with patch.object(agent_api, '_engine', return_value=engine), \
                patch.object(agent_api.importlib, 'import_module', side_effect=ImportError('No PyMuPDF')), \
                patch.object(agent_api.subprocess, 'run', return_value=version), \
                patch.object(agent_api, '_font_check', return_value={'ok': True}):
            result = agent_api.doctor()
        self.assertFalse(result['ready'])
        self.assertTrue(result['checks']['python']['ok'])
        self.assertTrue(result['checks']['wordcraft']['ok'])
        self.assertFalse(result['checks']['pymupdf']['ok'])

    def test_external_wordcraft_rejects_old_version_before_mcp(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'wordcraft-cli.exe'
            path.write_bytes(b'fixture')
            old = types.SimpleNamespace(returncode=0, stdout='wordcraft-cli 0.15.2', stderr='')
            with patch.object(setup_support.subprocess, 'run', return_value=old), \
                    patch.object(agent_api, '_engine') as engine:
                with self.assertRaisesRegex(ValueError, '0.16.0'):
                    setup_support.inspect_wordcraft(path)
                engine.assert_not_called()

    def test_verifier_fails_instead_of_claiming_ready_when_tk_window_fails(self):
        import tkinter
        diagnosis = {'ok': True, 'data': {'ready': True, 'checks': {
            'python': {'ok': True}, 'tkinter': {'ok': True}, 'pymupdf': {'ok': True}}}}
        with patch.object(agent_api, 'invoke', return_value=diagnosis), \
                patch.object(tkinter, 'Tk', side_effect=RuntimeError('Broken Tk')):
            result = setup_support.verify()
        self.assertFalse(result['data']['ready'])
        self.assertTrue(result['data']['checks']['pymupdf']['ok'])
        self.assertFalse(result['data']['checks']['tkinter']['ok'])


if __name__ == '__main__':
    unittest.main()
