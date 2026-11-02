"""Opt-in updates for ZIP installations from the project's fixed GitHub origin."""
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import os
import runpy
from urllib.request import Request, urlopen
from zipfile import ZipFile

REPO = 'k0zt3r/wordcraft-normokontrol'
ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ('VERSION','run.cmd','normokontrol.py','_normokontrol_recovery.py','requirements.txt',
            'Normokontrol.pdf','references/norm-source/requirements.json',
            'references/norm-source/source.json','references/norm-source/clauses.json',
            'references/norm-source/full-text.md',
            'assets/course-templates.json','assets/format-profile.json',
            *('scripts/'+name+'.py' for name in ('normokontrol','normokontrol_gui','irgups_data','captions',
               'list_formatting','whitespace_cleanup','document_cleanup','rules_checks','structure',
               'integrity','format_profile','pdf_checks','atomic_files','runtime','reporting','preferences','cover_checks','list_checks','text_edits',
               'artifact_cleanup','document_policy','illustration_checks','normative','heading_spacing','updater')))


def fetch(url):
    with urlopen(Request(url, headers={'User-Agent': 'wordcraft-normokontrol-updater'}), timeout=30) as response:
        data = response.read(30 * 1024 * 1024 + 1)
        if len(data) > 30 * 1024 * 1024:
            raise ValueError('Слишком большой ответ сервера.')
        return data


def version(text):
    if not re.fullmatch(r'\d+\.\d+\.\d+', text.strip()):
        raise ValueError('Не удалось определить версию обновления.')
    return tuple(map(int, text.strip().split('.')))


def check(root=ROOT):
    commit = json.loads(fetch(f'https://api.github.com/repos/{REPO}/commits/main'))['sha']
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Некорректный ответ GitHub.')
    latest = fetch(f'https://raw.githubusercontent.com/{REPO}/{commit}/VERSION').decode().strip()
    current = (root / 'VERSION').read_text().strip()
    return {'sha': commit, 'version': latest, 'available': version(latest) > version(current)}


def install(update, root=ROOT):
    if (root / '.git').exists():
        raise ValueError('Это Git-копия проекта. Обновите её командой git pull; автоматическая установка предназначена для ZIP-копий.')
    sha = update['sha']
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('Некорректный номер обновления.')
    payload = fetch(f'https://codeload.github.com/{REPO}/zip/{sha}')
    return install_archive(payload, update['version'], root)


def install_archive(payload, expected_version, root):
    from atomic_files import write_json
    root=Path(root).resolve()
    if (root/'.normokontrol-update.json').exists():
        raise ValueError('Предыдущее обновление не завершено. Перезапустите программу для восстановления.')
    allowed = {'VERSION', 'normokontrol.py', 'run.cmd', 'requirements.txt',
               'requirements-dev.txt', 'README.md', 'LICENSE', 'Normokontrol.pdf', '_normokontrol_recovery.py'}
    files = {}
    with ZipFile(io.BytesIO(payload)) as archive:
        if sum(i.file_size for i in archive.infolist()) > 60 * 1024 * 1024:
            raise ValueError('Слишком большой архив обновления.')
        for item in archive.infolist():
            parts = PurePosixPath(item.filename).parts
            if item.is_dir():
                continue
            if len(parts) < 2 or any(p in {'.', '..'} or ':' in p or '\\' in p for p in parts):
                raise ValueError('Небезопасный путь в архиве.')
            rel = Path(*parts[1:])
            norm_asset=rel.as_posix().startswith('references/norm-source/') and rel.suffix in {'.png','.jpg','.jpeg','.svg'}
            if str(rel) not in allowed and not norm_asset and not (parts[1] in {'scripts', 'assets', 'references'} and rel.suffix in {'.py', '.json', '.md', '.yaml'}):
                continue
            if not (root / rel).resolve().is_relative_to(root.resolve()):
                raise ValueError('Файл обновления находится вне папки программы.')
            if rel in files:
                raise ValueError('Повторяющийся файл в архиве.')
            files[rel] = archive.read(item)
    for required in REQUIRED:
        if Path(required) not in files:
            raise ValueError('Архив обновления неполон.')
    if files[Path('VERSION')].decode().strip() != expected_version:
        raise ValueError('Версия архива не совпадает с проверенной.')
    if files[Path('requirements.txt')].splitlines() != (root / 'requirements.txt').read_bytes().splitlines():
        raise ValueError('В этой версии изменились зависимости. Скачайте новый ZIP и выполните установку по README.')
    backup = Path(tempfile.mkdtemp(prefix='normokontrol-backup-', dir=root))
    staged=backup/'.staged'
    entries=[]
    # Recovery loader and launcher must precede application changes; VERSION commits last.
    first={'_normokontrol_recovery.py':0,'normokontrol.py':1,'run.cmd':2}
    ordered=sorted(files,key=lambda rel:(99 if rel==Path('VERSION') else first.get(rel.as_posix(),3),rel.as_posix()))
    for rel in ordered:
        target=root/rel
        (staged/rel).parent.mkdir(parents=True,exist_ok=True)
        (staged/rel).write_bytes(files[rel])
        if target.exists():
            (backup/rel).parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(target,backup/rel)
        entries.append({'path':rel.as_posix(),'existed':target.exists()})
    journal=root/'.normokontrol-update.json'
    write_json(journal,{'backup':backup.name,'files':entries,'pid':os.getpid()})
    try:
        for rel in ordered:
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged/rel,target)
        journal.unlink()
    except BaseException:
        # Load trusted recovery from the running checkout, not the archive under test.
        recovery=runpy.run_path(str(ROOT/'_normokontrol_recovery.py'))
        recovery['recover'](root,force=True)
        raise
    return backup


def show_updates(root, busy):
    import queue
    import threading
    from tkinter import messagebox
    if busy():
        messagebox.showinfo('Обновления', 'Дождитесь завершения обработки документа.', parent=root)
        return
    events = queue.Queue()
    def worker(action, *args):
        try:
            events.put((action, check() if action == 'check' else install(*args)))
        except Exception as error:
            events.put(('error', str(error)))
    # Modal window prevents starting document processing during installation.
    import tkinter as tk
    from tkinter import ttk
    dialog = tk.Toplevel(root)
    dialog.title('Обновления')
    dialog.transient(root)
    dialog.grab_set()
    dialog.protocol('WM_DELETE_WINDOW', lambda: None)
    label = ttk.Label(dialog, text='Проверяем обновления на GitHub…', padding=24)
    label.pack()
    def poll():
        try:
            kind, value = events.get_nowait()
        except queue.Empty:
            dialog.after(100, poll)
            return
        if kind == 'check' and value['available']:
            if messagebox.askyesno('Обновление', f"Доступна версия {value['version']}. Установить и закрыть программу?", parent=dialog):
                label.configure(text='Скачиваем и устанавливаем обновление…')
                threading.Thread(target=worker, args=('install', value), daemon=True).start()
                dialog.after(100, poll)
                return
        elif kind == 'check':
            messagebox.showinfo('Обновления', 'Установлена актуальная версия.', parent=dialog)
        elif kind == 'error':
            messagebox.showerror('Не удалось обновить', value, parent=dialog)
        else:
            messagebox.showinfo('Готово', 'Обновление установлено. Откройте run.cmd заново.\nРезервная копия сохранена в папке программы.', parent=dialog)
            root.destroy()
            return
        dialog.destroy()
    threading.Thread(target=worker, args=('check',), daemon=True).start()
    dialog.after(100, poll)
