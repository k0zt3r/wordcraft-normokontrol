"""Cooperative cancellation shared by GUI and the private Wordcraft process."""


class ProcessingCancelled(RuntimeError):
    pass


class PositionUnavailable(RuntimeError):
    """Wordcraft has no caret geometry for this document position."""


def open_path(path):
    """Open a local result with the desktop's registered application."""
    import os
    import subprocess
    import sys
    if os.name == 'nt':
        os.startfile(str(path))
    else:
        subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(path)])


def check_cancel(event):
    if event is not None and event.is_set():
        raise ProcessingCancelled('Обработка отменена. Исходный документ не изменён.')
