"""Build a self-contained per-user Windows installer from verified artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / 'build'
CACHE = BUILD / 'downloads'
STAGE = BUILD / 'installer'
MANIFEST = Path(__file__).with_name('dependencies.json')
PACKAGE_LOCK = Path(__file__).with_name('requirements-lock.txt')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(item, cache=CACHE):
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / item['filename']
    if target.is_file() and sha256(target) == item['sha256']:
        return target
    partial = target.with_name(target.name + '.' + uuid.uuid4().hex + '.part')
    for attempt in range(3):
        print(f'Downloading {item["filename"]} (attempt {attempt + 1})', flush=True)
        try:
            request = urllib.request.Request(item['url'], headers={'User-Agent': 'wordcraft-normokontrol-builder'})
            with urllib.request.urlopen(request, timeout=90) as response, partial.open('wb') as output:
                shutil.copyfileobj(response, output)
            if sha256(partial) != item['sha256']:
                raise ValueError(f'SHA-256 mismatch: {item["filename"]}')
            partial.replace(target)
            return target
        except Exception:
            partial.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(2)


def owned_remove(path):
    path = Path(path).resolve()
    if not path.is_relative_to(BUILD.resolve()) or path == BUILD.resolve() or path.is_symlink():
        raise ValueError(f'Refusing to remove non-build directory: {path}')
    if path.exists():
        shutil.rmtree(path)


def run(args, **kwargs):
    print('Running:', ' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def payload_files():
    # Explicit public application sources: never package personal settings, work,
    # fonts, Git metadata, caches, test documents or development environments.
    for name in ('VERSION', 'README.md', 'AGENTS.md', 'LICENSE', 'Normokontrol.pdf',
                 'normokontrol.py', '_normokontrol_recovery.py', 'run.cmd', 'requirements.txt',
                 'installer/README.md', 'installer/dependencies.json', 'installer/requirements-lock.txt'):
        yield ROOT / name
    for folder in ('scripts', 'references', 'assets'):
        for path in sorted((ROOT / folder).rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts or path.name.startswith('test_'):
                continue
            relative = path.relative_to(ROOT).as_posix()
            allowed = path.suffix.lower() in {'.py', '.json', '.md'}
            allowed |= relative.startswith('references/norm-source/') and path.suffix.lower() in {'.svg', '.png', '.jpg', '.jpeg'}
            allowed |= relative.startswith('assets/screenshots/') and path.suffix.lower() == '.png'
            if allowed:
                yield path


def stage_runtime(manifest):
    archive = download(manifest['python'])
    temporary = BUILD / 'runtime-extract'
    owned_remove(temporary)
    temporary.mkdir(parents=True)
    with tarfile.open(archive) as bundle:
        bundle.extractall(temporary, filter='data')
    runtime = STAGE / 'runtime'
    shutil.move(str(temporary / 'python'), runtime)
    owned_remove(temporary)
    interpreter = runtime / 'python.exe'
    if not interpreter.is_file():
        raise RuntimeError('Python distribution layout changed: python.exe missing.')
    wheels = BUILD / 'wheelhouse'
    wheels.mkdir(parents=True, exist_ok=True)
    expected = set(re.findall(r'--hash=sha256:([a-f0-9]{64})', PACKAGE_LOCK.read_text(encoding='utf-8')))
    cached = {sha256(path) for path in wheels.glob('*.whl')}
    cache_args = ['--no-index', '--find-links', wheels] if expected and expected.issubset(cached) else []
    run([interpreter, '-I', '-m', 'pip', '--isolated', 'download', '--only-binary=:all:',
         '--disable-pip-version-check', '--dest', wheels, '--require-hashes', '-r', PACKAGE_LOCK, *cache_args])
    run([interpreter, '-I', '-m', 'pip', '--isolated', 'install', '--no-index',
         '--find-links', wheels, '--disable-pip-version-check', '--no-warn-script-location',
         '--require-hashes', '-r', PACKAGE_LOCK])
    run([interpreter, '-I', '-m', 'pip', '--isolated', 'check'])
    # Check real Tcl/Tk rather than accepting a Python executable with no GUI.
    run([interpreter, '-I', '-c',
         'import tkinter, pymupdf; root=tkinter.Tk(); root.withdraw(); root.update(); root.destroy(); print("Tk and PyMuPDF ready")'])
    frozen = subprocess.check_output([str(interpreter), '-I', '-m', 'pip', '--isolated', 'freeze'], text=True)
    notices = STAGE / 'app/THIRD_PARTY'
    notices.mkdir(parents=True, exist_ok=True)
    wheel_hashes = '\n'.join(f'{sha256(p)}  {p.name}' for p in sorted(wheels.glob('*.whl')))
    (notices / 'requirements-lock.txt').write_text(frozen + '\n# Cached wheel SHA-256\n' + wheel_hashes + '\n', encoding='utf-8')
    shutil.copy2(MANIFEST, notices / 'dependencies.json')
    shutil.copy2(PACKAGE_LOCK, notices / 'requirements-wheels.txt')
    # Preserve upstream Python and package license files in their runtime trees.
    (notices / 'README.txt').write_text(
        'Python runtime: astral-sh/python-build-standalone, CPython and bundled library licenses in runtime.\n'
        'Python packages: see runtime/Lib/site-packages/*dist-info/licenses and metadata.\n'
        'PyMuPDF is AGPL-3.0 or commercially licensed by Artifex; its license is not replaced by the project MIT license.\n'
        'Wordcraft is downloaded unmodified from its official release; upstream licenses stay in wordcraft/.\n'
        'Full corresponding application source: https://github.com/k0zt3r/wordcraft-normokontrol\n', encoding='utf-8')
    return interpreter


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage-only', action='store_true', help='Prepare and verify payload without compiling EXE.')
    parser.add_argument('--download-wordcraft', action='store_true', help='Cache the pinned Wordcraft ZIP for offline installation/testing.')
    args = parser.parse_args(argv)
    if sys.platform != 'win32':
        parser.error('Installer builds require 64-bit Windows and Python 3.12+.')
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    owned_remove(STAGE)
    (STAGE / 'app').mkdir(parents=True)
    for source in payload_files():
        target = STAGE / 'app' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    marker = {'schema_version': 1, 'distribution': 'windows-installer', 'version': version}
    (STAGE / 'app/.normokontrol-installed.json').write_text(json.dumps(marker), encoding='utf-8')
    include = '\n'.join(f'#define Wordcraft{key} "{manifest["wordcraft"][field]}"'
                        for key, field in [('URL', 'url'), ('SHA256', 'sha256'), ('Version', 'version')])
    (STAGE / 'dependencies.iss').write_text(include + '\n', encoding='utf-8')
    stage_runtime(manifest)
    if args.download_wordcraft:
        download(manifest['wordcraft'])
    if args.stage_only:
        print('Staged:', STAGE)
        return 0
    compiler_setup = download(manifest['inno'])
    compiler = BUILD / 'tools/inno' / 'ISCC.exe'
    compiler_marker = compiler.parent / 'source.sha256'
    if not compiler.is_file() or not compiler_marker.is_file() or compiler_marker.read_text() != manifest['inno']['sha256']:
        compiler.parent.mkdir(parents=True, exist_ok=True)
        run([compiler_setup, '/PORTABLE=1', '/CURRENTUSER', '/VERYSILENT',
             '/SUPPRESSMSGBOXES', '/NORESTART', f'/DIR={compiler.parent}'])
        compiler_marker.write_text(manifest['inno']['sha256'])
    destination = ROOT / 'dist'
    destination.mkdir(exist_ok=True)
    run([compiler, f'/DStageDir={STAGE}', f'/DOutputDir={destination}',
         f'/DAppVersion={version}', ROOT / 'installer/normokontrol.iss'])
    executable = destination / f'Normokontrol-{version}-windows-x64-setup.exe'
    if not executable.is_file():
        raise RuntimeError('Compiler did not produce expected installer: ' + str(executable))
    checksum = sha256(executable)
    executable.with_suffix('.exe.sha256').write_text(f'{checksum}  {executable.name}\n', encoding='ascii')
    print(f'Built {executable}\nSHA256 {checksum}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
