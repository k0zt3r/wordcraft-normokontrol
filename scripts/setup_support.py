"""Installer health check; the installed runtime is independent of system Python."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
MIN_WORDCRAFT = (0, 16, 0)


def inspect_wordcraft(path):
    from agent_api import _engine
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise ValueError('Wordcraft CLI не найден: ' + str(target))
    result = subprocess.run([str(target), '--version'], capture_output=True, text=True,
                            encoding='utf-8', timeout=15,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    match = re.search(r'\b(\d+)\.(\d+)\.(\d+)\b', result.stdout)
    if result.returncode or not match or tuple(map(int, match.groups())) < MIN_WORDCRAFT:
        raise ValueError('Нужен Wordcraft 0.16.0 или новее: ' + result.stdout.strip())
    with _engine().Wordcraft(str(target)) as wordcraft:
        tools = wordcraft.rpc('tools/list', {}).get('tools', [])
        required = {'new_document', 'open_document', 'save_document', 'execute', 'batch'}
        if not required.issubset({tool.get('name') for tool in tools}):
            raise ValueError('В Wordcraft отсутствуют необходимые MCP-инструменты.')
        wordcraft.call('new_document', template='blank')
        layout = wordcraft.execute('document.layout')
        if not isinstance(layout.get('pages'), list):
            raise ValueError('Не поддерживается формат вёрстки Wordcraft.')
    return {'path': str(target), 'version': result.stdout.strip(), 'mcp_verified': True}


def verify(wordcraft=None, managed=False):
    from agent_api import invoke
    from atomic_files import write_json
    if wordcraft:
        inspection = inspect_wordcraft(wordcraft)
        write_json(ROOT / '.normokontrol-dependencies.json', {
            'wordcraft_cli': inspection['path'], 'wordcraft_managed': managed})
    result = invoke('doctor', {'wordcraft': wordcraft} if wordcraft else {})
    if result['ok']:
        try:
            packages = subprocess.run([sys.executable, '-I', '-m', 'pip', '--isolated', 'check'],
                capture_output=True, text=True, encoding='utf-8', timeout=60,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            result['data']['checks']['python_packages'] = {
                'ok': packages.returncode == 0, 'detail': packages.stdout.strip() or packages.stderr.strip()}
        except Exception as error:
            result['data']['checks']['python_packages'] = {'ok': False, 'detail': str(error)}
        # Validate a real Tk window with the privately shipped Tcl/Tk. It stays
        # hidden and is destroyed before control returns to the installer.
        try:
            import tkinter
            root = tkinter.Tk()
            try:
                root.withdraw()
                root.update()
            finally:
                root.destroy()
            result['data']['checks']['tkinter']['window_verified'] = True
        except Exception as error:
            result['data']['checks']['tkinter'] = {'ok': False, 'detail': str(error)}
        result['data']['ready'] = all(c['ok'] for c in result['data']['checks'].values())
    return result


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-install', action='store_true', required=True)
    parser.add_argument('--wordcraft')
    parser.add_argument('--managed-wordcraft', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = verify(args.wordcraft, args.managed_wordcraft)
    except Exception as error:
        result = {'schema_version': 1, 'ok': False, 'status': 'error', 'data': None,
                  'error': {'type': type(error).__name__, 'message': str(error)}}
    from atomic_files import write_json
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] and result['data']['ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
