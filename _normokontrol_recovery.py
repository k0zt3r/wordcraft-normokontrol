"""Standalone standard-library recovery, loaded before any application module."""
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile

JOURNAL = '.normokontrol-update.json'
ROOT_FILES = {'VERSION','README.md','LICENSE','Normokontrol.pdf','normokontrol.py','run.cmd',
              'requirements.txt','requirements-dev.txt','_normokontrol_recovery.py'}


def process_alive(pid):
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype=wintypes.BOOL
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        kernel.CloseHandle.restype=wintypes.BOOL
        handle=kernel.OpenProcess(0x1000,False,int(pid))
        if not handle:
            return ctypes.get_last_error()==5  # Access denied: do not touch a live installer.
        try:
            code=wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle,ctypes.byref(code))) and code.value==259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(int(pid),0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False


def safe_path(root, relative):
    rel=PurePosixPath(relative)
    if rel.is_absolute() or not rel.parts or any(p in {'.','..'} or ':' in p or '\\' in p for p in rel.parts):
        raise ValueError('Некорректный путь восстановления.')
    norm_asset=relative.startswith('references/norm-source/') and rel.suffix in {'.png','.jpg','.jpeg','.svg'}
    if relative not in ROOT_FILES and not norm_asset and not (rel.parts[0] in {'scripts','assets','references'} and rel.suffix in {'.py','.json','.md','.yaml'}):
        raise ValueError('Журнал содержит файл вне программы.')
    target=root/Path(*rel.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('Путь восстановления выходит за папку программы.')
    return target


def recover(root, force=False):
    root=Path(root).resolve()
    journal=root/JOURNAL
    if not journal.exists():
        return False
    data=json.loads(journal.read_text(encoding='utf-8'))
    pid=data.get('pid')
    if pid and not force and process_alive(pid):
        raise RuntimeError('Другой экземпляр программы устанавливает обновление. Дождитесь его завершения.')
    backup=root/data['backup']
    if backup.is_symlink() or backup.resolve().parent != root or not backup.name.startswith('normokontrol-backup-'):
        raise ValueError('Некорректная резервная копия обновления.')
    entries=data['files']
    # Validate every path and backup before touching any current file.
    for entry in entries:
        safe_path(root,entry['path'])
        old=safe_path(backup,entry['path'])
        if entry['existed'] and not old.is_file():
            raise RuntimeError('Резервная копия обновления неполна: '+entry['path'])
    for entry in entries:
        target=safe_path(root,entry['path'])
        if entry['existed']:
            target.parent.mkdir(parents=True,exist_ok=True)
            fd,temporary=tempfile.mkstemp(prefix='.recover-',dir=target.parent)
            os.close(fd)
            try:
                shutil.copy2(safe_path(backup,entry['path']),temporary)
                os.replace(temporary,target)
            finally:
                Path(temporary).unlink(missing_ok=True)
        else:
            target.unlink(missing_ok=True)
    journal.unlink()
    return True
