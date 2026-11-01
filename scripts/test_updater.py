import io
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile
from unittest.mock import patch
import updater


class UpdateTests(unittest.TestCase):
    def archive(self, extra=None):
        stream = io.BytesIO()
        files = {'VERSION': '1.2.0', 'requirements.txt': 'dependency', 'run.cmd': 'new',
                 'scripts/normokontrol.py': 'new', 'scripts/normokontrol_gui.py': 'new'}
        files.update(extra or {})
        with ZipFile(stream, 'w') as z:
            for name, text in files.items():
                z.writestr('project/' + name, text)
        return stream.getvalue()

    def test_update_preserves_documents_and_backup(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'requirements.txt').write_text('dependency')
            (root / 'run.cmd').write_text('old')
            (root / 'work.docx').write_bytes(b'personal')
            backup = updater.install_archive(self.archive({'work.docx': 'bad', '.env': 'bad'}), '1.2.0', root)
            self.assertEqual((root / 'run.cmd').read_text(), 'new')
            self.assertEqual((backup / 'run.cmd').read_text(), 'old')
            self.assertEqual((root / 'work.docx').read_bytes(), b'personal')
            self.assertFalse((root / '.env').exists())

    def test_rejects_traversal_and_dependency_change(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'requirements.txt').write_text('dependency')
            for extra in ({'../outside.py': 'bad'}, {'requirements.txt': 'changed'}):
                with self.assertRaises(ValueError):
                    updater.install_archive(self.archive(extra), '1.2.0', root)
            self.assertFalse((root / 'VERSION').exists())

    def test_rolls_back_failed_write(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'requirements.txt').write_text('dependency')
            (root / 'run.cmd').write_text('old')
            write = Path.write_bytes
            def fail(path, data):
                if path.name == 'normokontrol.py':
                    raise OSError('test failure')
                return write(path, data)
            with patch.object(Path, 'write_bytes', fail), self.assertRaises(OSError):
                updater.install_archive(self.archive(), '1.2.0', root)
            self.assertEqual((root / 'run.cmd').read_text(), 'old')
            self.assertFalse((root / 'VERSION').exists())


if __name__ == '__main__':
    unittest.main()
