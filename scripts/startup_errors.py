"""Visible GUI-startup failures without depending on a working Tcl/Tk install."""
from datetime import datetime
import os
from pathlib import Path
import sys
import tempfile
import traceback


def _write_log(path, details):
    with path.open('a', encoding='utf-8') as stream:
        stream.write(details)


def _safe_stderr(message):
    try:
        print(message, file=sys.stderr)
    except Exception:
        # pythonw can have no usable stderr; reporting must not replace the
        # original startup error with an error in the reporting code itself.
        pass


def _notify(message):
    if os.name == 'nt':
        import ctypes
        # MB_OK | MB_ICONERROR. This Windows dialog does not import tkinter.
        ctypes.windll.user32.MessageBoxW(None, message, 'Нормоконтроль: ошибка запуска', 0x10)
    else:
        _safe_stderr(message)


def show_startup_error(error, root):
    """Append diagnostics, show a visible error and return the log Path or None.

    Call only for failed GUI startup. CLI/MCP callers retain their own error
    output. Every reporting step is guarded so the original failure survives.
    """
    try:
        description = f'{type(error).__name__}: {error}'
        details = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        details = (f'\n--- {datetime.now().isoformat(timespec="seconds")} ---\n'
                   f'Python executable: {sys.executable}\nPython version: {sys.version}\n'
                   f'{details}\n')
    except Exception:
        description = 'Не удалось получить текст ошибки запуска.'
        details = f'\nОшибка запуска. Python: {sys.executable}\nВерсия: {sys.version}\n'

    log_path = None
    try:
        candidate = Path(root) / 'startup.log'
        _write_log(candidate, details)
        log_path = candidate
    except Exception:
        try:
            candidate = Path(tempfile.gettempdir()) / 'WordcraftNormokontrol-startup.log'
            _write_log(candidate, details)
            log_path = candidate
        except Exception:
            pass

    location = str(log_path) if log_path is not None else 'Не удалось записать журнал: нет доступа к папке программы и временной папке.'
    message = (f'Не удалось открыть окно нормоконтроля.\n\n{description}\n\n'
               f'Интерпретатор: {sys.executable}\nЖурнал: {location}\n\n'
               'Если ошибка связана с Tcl/Tk или tkinter, установите компонент Tcl/Tk '
               'в установщике Python либо используйте установщик нормоконтроля.\n'
               'Зависимости нужно устанавливать тем же Python, который указан выше: '
               'python -m pip install -r requirements.txt.')
    try:
        _notify(message)
    except Exception:
        _safe_stderr(message)
    return log_path
