import io
import hashlib
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from urllib.error import HTTPError
from zipfile import ZipFile
from unittest.mock import patch
import updater


class UpdateTests(unittest.TestCase):
    def installed_root(self, directory):
        root = Path(directory)
        (root / '.normokontrol-installed.json').write_text('{}')
        (root / 'VERSION').write_text('1.5.0')
        return root

    def release(self, payload=b'installer bytes', release_version='1.6.0'):
        filename = updater.installer_filename(release_version)
        return {'tag_name': 'v' + release_version, 'draft': False, 'prerelease': False,
                'assets': [{'name': filename, 'size': len(payload),
                    'browser_download_url': f'https://github.com/{updater.REPO}/releases/download/v{release_version}/{filename}',
                    'digest': 'sha256:' + hashlib.sha256(payload).hexdigest()}]}

    def test_installer_check_requires_published_exe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.installed_root(directory)
            missing = HTTPError('url', 404, 'Not Found', None, None)
            with patch.object(updater, 'fetch', side_effect=missing):
                result = updater.check(root)
            self.assertFalse(result['available'])
            self.assertEqual(result['reason'], 'no_installer_release')
            release = self.release()
            release['assets'] = []
            with patch.object(updater, 'fetch', return_value=json.dumps(release).encode()) as fetch:
                result = updater.check(root)
            self.assertFalse(result['available'])
            self.assertEqual(result['reason'], 'no_installer_asset')
            self.assertIn('/releases/latest', fetch.call_args.args[0])
            release = self.release()
            with patch.object(updater, 'fetch', return_value=json.dumps(release).encode()):
                result = updater.check(root)
            self.assertTrue(result['available'])
            self.assertEqual(result['distribution'], 'installer')
            self.assertEqual(result['version'], '1.6.0')

    def test_source_zip_channel_keeps_commit_based_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'VERSION').write_text('1.5.0')
            with patch.object(updater, 'fetch', side_effect=[json.dumps({'sha': 'a' * 40}).encode(), b'1.6.0']) as fetch:
                result = updater.check(root)
            self.assertTrue(result['available'])
            self.assertEqual(result['sha'], 'a' * 40)
            self.assertIn('/commits/main', fetch.call_args_list[0].args[0])

    def test_installer_check_validates_semver_and_ignores_old_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.installed_root(directory)
            for release_version in ('1.4.9', '1.5.0'):
                with patch.object(updater, 'fetch', return_value=json.dumps(self.release(release_version=release_version)).encode()):
                    self.assertFalse(updater.check(root)['available'])
            with patch.object(updater, 'fetch', return_value=json.dumps(self.release(release_version='1.10.0')).encode()):
                self.assertTrue(updater.check(root)['available'])
            release = self.release()
            release['tag_name'] = 'v1.6.0-rc1'
            with patch.object(updater, 'fetch', return_value=json.dumps(release).encode()), self.assertRaises(ValueError):
                updater.check(root)

    def test_installer_checksum_sidecar_must_name_the_actual_exe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.installed_root(directory)
            release = self.release()
            asset = release['assets'][0]
            expected = asset.pop('digest').split(':')[1]
            with patch.object(updater, 'fetch', return_value=json.dumps(release).encode()):
                result = updater.check(root)
            self.assertFalse(result['available'])
            self.assertEqual(result['reason'], 'no_installer_checksum')
            release['assets'].append({'name': asset['name'] + '.sha256',
                'browser_download_url': asset['browser_download_url'] + '.sha256'})
            checksum = f"{expected}  {asset['name']}\n".encode()
            with patch.object(updater, 'fetch', side_effect=[json.dumps(release).encode(), checksum]):
                result = updater.check(root)
            self.assertTrue(result['available'])
            self.assertEqual(result['sha256'], expected)
            bad = f'{expected}  other.exe\n'.encode()
            with patch.object(updater, 'fetch', side_effect=[json.dumps(release).encode(), bad]), self.assertRaises(ValueError):
                updater.check(root)

    def test_installer_rejects_foreign_or_misleading_release_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.installed_root(directory)
            for url in ('https://example.org/update.exe',
                        f'https://github.com/{updater.REPO}/releases/download/v1.5.0/Normokontrol-1.6.0-windows-x64-setup.exe',
                        f'https://github.com/{updater.REPO}/releases/download/v1.6.0/Normokontrol-1.6.0-windows-x64-setup.exe?redirect=other'):
                release = self.release()
                release['assets'][0]['browser_download_url'] = url
                with patch.object(updater, 'fetch', return_value=json.dumps(release).encode()), self.assertRaises(ValueError):
                    updater.check(root)

    def test_installer_streams_verified_bytes_then_launches_normal_wizard(self):
        payload = b'verified installer' * 100000
        with tempfile.TemporaryDirectory() as directory:
            root = self.installed_root(directory)
            with patch.object(updater, 'fetch', return_value=json.dumps(self.release(payload)).encode()):
                update = updater.check(root)
            result = None
            try:
                with patch.object(updater, 'urlopen', return_value=io.BytesIO(payload)), patch.object(updater.subprocess, 'Popen') as start:
                    result = updater.install(update, root)
                self.assertEqual(result['kind'], 'installer')
                self.assertEqual(Path(result['path']).read_bytes(), payload)
                arguments = start.call_args.args[0]
                self.assertEqual(arguments[0], result['path'])
                self.assertEqual(arguments[1], '/DIR=' + str(root.resolve()))
                self.assertFalse(start.call_args.kwargs.get('shell', False))
                self.assertEqual((root / 'VERSION').read_text(), '1.5.0')
            finally:
                if result:
                    updater.remove_failed_installer_cache(Path(result['path']).parent)

    def test_installer_hash_size_and_launch_failures_clean_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.installed_root(directory)
            with patch.object(updater, 'fetch', return_value=json.dumps(self.release()).encode()):
                update = updater.check(root)
            original_mkdtemp = tempfile.mkdtemp
            created = []
            def track_cache(*args, **kwargs):
                folder = original_mkdtemp(*args, **kwargs)
                created.append(Path(folder))
                return folder
            for payload in (b'wrong installer', b'short', b'too large installer bytes'):
                with patch.object(updater, 'urlopen', return_value=io.BytesIO(payload)), \
                        patch.object(updater.subprocess, 'Popen') as start, \
                        patch.object(updater.tempfile, 'mkdtemp', side_effect=track_cache), \
                        self.assertRaises(ValueError):
                    updater.install(update, root)
                start.assert_not_called()
                self.assertFalse(created[-1].exists())
            with patch.object(updater, 'urlopen', return_value=io.BytesIO(b'installer bytes')), \
                    patch.object(updater.subprocess, 'Popen', side_effect=OSError('cannot launch')), \
                    patch.object(updater.tempfile, 'mkdtemp', side_effect=track_cache), \
                    self.assertRaises(OSError):
                updater.install(update, root)
            self.assertFalse(created[-1].exists())
            malicious = dict(update, url='https://evil.example/installer.exe')
            with patch.object(updater, 'urlopen') as download, patch.object(updater.subprocess, 'Popen') as start, self.assertRaises(ValueError):
                updater.install(malicious, root)
            download.assert_not_called()
            start.assert_not_called()

    def test_zip_update_cannot_change_installer_managed_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.normokontrol-installed.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'установщик'):
                updater.install({'sha': 'a' * 40}, root)
            with self.assertRaisesRegex(ValueError, 'установщик'):
                updater.install_archive(b'not an archive', '1.5.0', root)

    def test_actual_agent_interface_survives_zip_install(self):
        stream = io.BytesIO()
        current = (updater.ROOT / 'VERSION').read_text(encoding='utf-8').strip()
        with ZipFile(stream, 'w') as archive:
            for name in updater.REQUIRED:
                archive.writestr('project/' + name, (updater.ROOT / name).read_bytes())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'requirements.txt').write_bytes((updater.ROOT / 'requirements.txt').read_bytes())
            updater.install_archive(stream.getvalue(), current, root)
            for name in ('AGENTS.md', 'references/agent-interface.md',
                         'scripts/agent_api.py', 'scripts/agent_mcp.py'):
                self.assertTrue((root / name).is_file(), name)
            reply = subprocess.run([sys.executable, str(root / 'normokontrol.py'),
                                    '--agent', 'get_capabilities'], cwd=updater.ROOT.parent,
                                   capture_output=True, text=True, encoding='utf-8', timeout=20)
            self.assertEqual(reply.returncode, 0, reply.stderr)
            result = json.loads(reply.stdout)
            self.assertTrue(result['ok'])
            self.assertEqual(result['data']['version'], current)
            self.assertEqual(len(result['data']['tools']), 7)

    def test_commit_failure_restores_old_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'requirements.txt').write_text('dependency')
            (root/'run.cmd').write_text('old')
            replace=updater.os.replace
            def fail(source,target):
                if '.staged' in str(source) and Path(target)==root/'scripts/normokontrol.py':
                    raise OSError('commit failed')
                return replace(source,target)
            with patch.object(updater.os,'replace',fail),self.assertRaises(OSError):
                updater.install_archive(self.archive(),'1.2.0',root)
            self.assertEqual((root/'run.cmd').read_text(),'old')
            self.assertFalse((root/'VERSION').exists())
            self.assertFalse((root/'.normokontrol-update.json').exists())

    def test_recovery_after_interrupted_process(self):
        import runpy
        from atomic_files import write_json
        recover=runpy.run_path(str(updater.ROOT/'_normokontrol_recovery.py'))['recover']
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);backup=root/'normokontrol-backup-test';backup.mkdir()
            (backup/'run.cmd').write_text('old')
            (root/'run.cmd').write_text('partly updated')
            (root/'VERSION').write_text('new')
            write_json(root/'.normokontrol-update.json',{'backup':backup.name,'files':[
                {'path':'run.cmd','existed':True},{'path':'VERSION','existed':False}]})
            self.assertTrue(recover(root))
            self.assertEqual((root/'run.cmd').read_text(),'old')
            self.assertFalse((root/'VERSION').exists())

    def archive(self, extra=None):
        stream = io.BytesIO()
        files = {'VERSION': '1.2.0', 'requirements.txt': 'dependency', 'run.cmd': 'new',
                 'scripts/normokontrol.py': 'new', 'scripts/normokontrol_gui.py': 'new'}
        for required in updater.REQUIRED:
            files.setdefault(required,'fixture')
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
