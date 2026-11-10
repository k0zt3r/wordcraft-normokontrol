"""Opt-in ZIP and installer updates from the project's fixed GitHub origin."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import os
import runpy
import subprocess
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zipfile import ZipFile

REPO = 'k0zt3r/wordcraft-normokontrol'
ROOT = Path(__file__).resolve().parent.parent
INSTALLER_LIMIT = 512 * 1024 * 1024
INSTALLER_CACHE_PREFIX = 'normokontrol-installer-update-'
REQUIRED = ('VERSION','run.cmd','normokontrol.py','_normokontrol_recovery.py','requirements.txt','AGENTS.md',
            'references/agent-interface.md','scripts/agent_api.py','scripts/agent_mcp.py',
            'scripts/setup_support.py','scripts/startup_errors.py',
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
    root = Path(root)
    if (root / '.normokontrol-deb').exists():
        raise ValueError('Обновите DEB-пакет через apt или установите новый .deb из выпуска проекта.')
    if (root / '.normokontrol-installed.json').exists():
        return check_installer(root)
    commit = json.loads(fetch(f'https://api.github.com/repos/{REPO}/commits/main'))['sha']
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Некорректный ответ GitHub.')
    latest = fetch(f'https://raw.githubusercontent.com/{REPO}/{commit}/VERSION').decode().strip()
    current = (root / 'VERSION').read_text().strip()
    return {'sha': commit, 'version': latest, 'available': version(latest) > version(current)}


def installer_filename(release_version):
    version(release_version)
    return f'Normokontrol-{release_version}-windows-x64-setup.exe'


def validate_release_url(url, filename, release_version):
    if not isinstance(url, str):
        raise ValueError('Не указан официальный адрес установщика.')
    parsed = urlsplit(url)
    expected = rf'/{re.escape(REPO)}/releases/download/v?{re.escape(release_version)}/{re.escape(filename)}'
    if (parsed.scheme != 'https' or parsed.netloc != 'github.com' or
            parsed.query or parsed.fragment or not re.fullmatch(expected, parsed.path)):
        raise ValueError('Адрес обновления установщика находится вне официального релиза проекта.')
    return url


def release_asset(assets, filename):
    matches = [item for item in assets if isinstance(item, dict) and item.get('name') == filename]
    if len(matches) > 1:
        raise ValueError('В релизе несколько файлов установщика с одинаковым именем.')
    return matches[0] if matches else None


def check_installer(root):
    current = (Path(root) / 'VERSION').read_text(encoding='utf-8').strip()
    version(current)
    unavailable = {'distribution': 'installer', 'version': current, 'available': False}
    try:
        release = json.loads(fetch(f'https://api.github.com/repos/{REPO}/releases/latest'))
    except HTTPError as error:
        if error.code == 404:
            return dict(unavailable, reason='no_installer_release')
        raise
    tag = release.get('tag_name', '')
    if not isinstance(tag, str) or not re.fullmatch(r'v?\d+\.\d+\.\d+', tag):
        raise ValueError('Некорректная версия релиза установщика.')
    latest = tag.removeprefix('v')
    unavailable['version'] = latest
    if release.get('draft') or release.get('prerelease'):
        return dict(unavailable, reason='no_stable_installer_release')
    if version(latest) <= version(current):
        return dict(unavailable, reason='not_newer')
    assets = release.get('assets', [])
    if not isinstance(assets, list):
        raise ValueError('Некорректный список файлов релиза.')
    filename = installer_filename(latest)
    asset = release_asset(assets, filename)
    if asset is None:
        return dict(unavailable, reason='no_installer_asset')
    url = validate_release_url(asset.get('browser_download_url'), filename, latest)
    size = asset.get('size')
    if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= INSTALLER_LIMIT:
        raise ValueError('Некорректный или слишком большой размер установщика.')
    digest = asset.get('digest')
    if digest is not None:
        if not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest):
            raise ValueError('Некорректная контрольная сумма установщика в релизе.')
        expected = digest.split(':', 1)[1].lower()
    else:
        checksum = release_asset(assets, filename + '.sha256')
        if checksum is None:
            return dict(unavailable, reason='no_installer_checksum')
        checksum_url = validate_release_url(checksum.get('browser_download_url'), filename + '.sha256', latest)
        text = fetch(checksum_url).decode('utf-8-sig').strip()
        match = re.fullmatch(rf'([0-9a-fA-F]{{64}})[ \t]+\*?{re.escape(filename)}', text)
        if not match:
            raise ValueError('Файл SHA-256 не соответствует имени установщика.')
        expected = match[1].lower()
    return {'distribution': 'installer', 'version': latest, 'available': True,
            'url': url, 'sha256': expected, 'size': size}


def remove_failed_installer_cache(folder):
    folder = Path(folder)
    if (folder.is_symlink() or folder.resolve().parent != Path(tempfile.gettempdir()).resolve()
            or not folder.name.startswith(INSTALLER_CACHE_PREFIX)):
        raise ValueError('Некорректный путь временного установщика.')
    if folder.exists():
        shutil.rmtree(folder)


def install_installer(update, root):
    if not isinstance(update, dict) or update.get('distribution') != 'installer' or update.get('available') is not True:
        raise ValueError('Некорректное обновление установщика. Сначала выполните проверку обновлений.')
    latest = update.get('version', '')
    if not isinstance(latest, str) or version(latest) <= version((Path(root) / 'VERSION').read_text(encoding='utf-8').strip()):
        raise ValueError('Версия установщика должна быть новее установленной.')
    filename = installer_filename(latest)
    url = validate_release_url(update.get('url'), filename, latest)
    expected = update.get('sha256', '')
    size = update.get('size')
    if not isinstance(expected, str) or not re.fullmatch('[0-9a-fA-F]{64}', expected):
        raise ValueError('Не указана проверенная контрольная сумма установщика.')
    if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= INSTALLER_LIMIT:
        raise ValueError('Некорректный размер установщика.')
    folder = Path(tempfile.mkdtemp(prefix=INSTALLER_CACHE_PREFIX))
    try:
        partial = folder / (filename + '.part')
        installer = folder / filename
        digest, received = hashlib.sha256(), 0
        with urlopen(Request(url, headers={'User-Agent': 'wordcraft-normokontrol-updater'}), timeout=30) as response:
            with partial.open('xb') as stream:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    received += len(block)
                    if received > size or received > INSTALLER_LIMIT:
                        raise ValueError('Размер скачанного установщика превышает ожидаемый.')
                    stream.write(block)
                    digest.update(block)
        if received != size:
            raise ValueError('Установщик скачан не полностью: размер не совпадает с релизом.')
        if digest.hexdigest() != expected.lower():
            raise ValueError('SHA-256 установщика не совпадает с релизом. Установщик не запущен.')
        os.replace(partial, installer)
        subprocess.Popen([str(installer), '/DIR=' + str(Path(root).resolve())],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return {'kind': 'installer', 'path': str(installer)}
    except BaseException:
        remove_failed_installer_cache(folder)
        raise


def install(update, root=ROOT):
    root = Path(root)
    if (root / '.normokontrol-installed.json').exists():
        return install_installer(update, root)
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
    if (root / '.normokontrol-installed.json').exists():
        raise ValueError('Для этой установки используйте новый установщик; ZIP-обновление не обновляет приватный Python и библиотеки.')
    if (root/'.normokontrol-update.json').exists():
        raise ValueError('Предыдущее обновление не завершено. Перезапустите программу для восстановления.')
    allowed = {'VERSION', 'normokontrol.py', 'run.cmd', 'requirements.txt',
               'requirements-dev.txt', 'README.md', 'AGENTS.md', 'LICENSE', 'Normokontrol.pdf', '_normokontrol_recovery.py'}
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
    if (ROOT / '.normokontrol-deb').exists():
        messagebox.showinfo('Обновления', 'Установите новый .deb из выпуска проекта через apt. Настройки пользователя сохраняются.', parent=root)
        return
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
            if value.get('reason') in {'no_installer_release', 'no_stable_installer_release', 'no_installer_asset', 'no_installer_checksum'}:
                messagebox.showinfo('Обновления', 'Новый установщик с проверяемой контрольной суммой ещё не опубликован. Текущая установка не изменена.', parent=dialog)
            else:
                messagebox.showinfo('Обновления', 'Установлена актуальная версия.', parent=dialog)
        elif kind == 'error':
            messagebox.showerror('Не удалось обновить', value, parent=dialog)
        else:
            if isinstance(value, dict) and value.get('kind') == 'installer':
                messagebox.showinfo('Установщик запущен', 'Открыт мастер обновления. Завершите установку в его окне.\nПрограмма сейчас закроется; реквизиты и результаты сохраняются.', parent=dialog)
            else:
                messagebox.showinfo('Готово', 'Обновление установлено. Откройте run.cmd заново.\nРезервная копия сохранена в папке программы.', parent=dialog)
            root.destroy()
            return
        dialog.destroy()
    threading.Thread(target=worker, args=('check',), daemon=True).start()
    dialog.after(100, poll)
