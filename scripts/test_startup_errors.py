"""Startup reporting remains usable when Python GUI dependencies are broken."""
import ctypes
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import startup_errors


class StartupErrorTests(unittest.TestCase):
    def test_traceback_and_interpreter_are_logged_and_shown(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(startup_errors, '_notify') as notify:
            try:
                raise RuntimeError('Не найден init.tcl')
            except RuntimeError as error:
                path = startup_errors.show_startup_error(error, folder)
            self.assertEqual(path, Path(folder) / 'startup.log')
            log = path.read_text(encoding='utf-8')
            self.assertIn('Traceback (most recent call last)', log)
            self.assertIn('RuntimeError: Не найден init.tcl', log)
            self.assertIn(sys.executable, log)
            self.assertIn(sys.version, log)
            message = notify.call_args.args[0]
            for value in ('Не найден init.tcl', sys.executable, str(path), 'Tcl/Tk', 'requirements.txt'):
                self.assertIn(value, message)
            startup_errors.show_startup_error(ValueError('Повторный запуск'), folder)
            self.assertIn('Повторный запуск', path.read_text(encoding='utf-8'))
            self.assertIn('Не найден init.tcl', path.read_text(encoding='utf-8'))

    def test_unwritable_root_uses_temporary_log(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(startup_errors, '_notify'):
            root = Path(folder) / 'missing-directory'
            with patch.object(startup_errors.tempfile, 'gettempdir', return_value=folder):
                path = startup_errors.show_startup_error(ImportError('tkinter missing'), root)
            self.assertEqual(path, Path(folder) / 'WordcraftNormokontrol-startup.log')
            self.assertIn('ImportError: tkinter missing', path.read_text(encoding='utf-8'))

    def test_logging_and_notification_failure_do_not_raise(self):
        diagnostic = io.StringIO()
        with patch.object(startup_errors, '_write_log', side_effect=PermissionError('Read only')), \
                patch.object(startup_errors, '_notify', side_effect=OSError('No desktop')), \
                patch.object(startup_errors.sys, 'stderr', diagnostic):
            path = startup_errors.show_startup_error(RuntimeError('Original failure'), '.')
        self.assertIsNone(path)
        self.assertIn('Original failure', diagnostic.getvalue())
        self.assertIn('Не удалось записать журнал', diagnostic.getvalue())

    def test_windows_dialog_does_not_need_tkinter(self):
        messagebox = unittest.mock.Mock()
        library = types.SimpleNamespace(user32=types.SimpleNamespace(MessageBoxW=messagebox))
        with patch.object(startup_errors.os, 'name', 'nt'), \
                patch.object(ctypes, 'windll', library, create=True):
            startup_errors._notify('Ошибка без Tk')
        messagebox.assert_called_once_with(None, 'Ошибка без Tk', 'Нормоконтроль: ошибка запуска', 0x10)

    def test_non_windows_reports_to_stderr(self):
        diagnostic = io.StringIO()
        with patch.object(startup_errors.os, 'name', 'posix'), \
                patch.object(startup_errors.sys, 'stderr', diagnostic):
            startup_errors._notify('Original failure')
        self.assertIn('Original failure', diagnostic.getvalue())


if __name__ == '__main__':
    unittest.main()
