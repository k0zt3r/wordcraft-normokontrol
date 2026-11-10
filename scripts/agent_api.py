"""Versioned, GUI-free operations shared by JSON CLI and MCP adapters."""
from collections import Counter
from contextlib import redirect_stdout
import importlib
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1
_MISSING = object()


def _engine():
    # Give the engine its historical name for its local imports, but never import
    # the identically named root launcher. Package imports and scripts both work.
    folder = str(ROOT / 'scripts')
    if folder not in sys.path:
        sys.path.insert(0, folder)
    existing = sys.modules.get('normokontrol')
    if existing and Path(existing.__file__).resolve() == ROOT / 'scripts/normokontrol.py':
        return existing
    spec = importlib.util.spec_from_file_location('normokontrol', ROOT / 'scripts/normokontrol.py')
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get('normokontrol')
    sys.modules['normokontrol'] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if previous is None:
            sys.modules.pop('normokontrol', None)
        else:
            sys.modules['normokontrol'] = previous
        raise
    return module


def _object(properties=None, required=()):
    return {'type': 'object', 'properties': properties or {},
            'required': list(required), 'additionalProperties': False}


STRING = {'type': 'string', 'minLength': 1}
BOOL = {'type': 'boolean'}
METADATA = _object({
    **{key: {'type': 'string'} for key in (
        'code', 'author', 'supervisor', 'group', 'stamp_title', 'supervisor_title',
        'title', 'discipline', 'work_type', 'city', 'year', 'faculty', 'department',
        'work_code', 'division_code', 'specialty', 'account', 'document_code',
        'approval_person', 'approval_title')},
    **{key: BOOL for key in ('generate_code', 'include_year', 'approval')},
})
COMMON = {
    'out': dict(STRING, description='Папка результатов; существующие результаты не перезаписываются.'),
    'mode': {'type': 'string', 'enum': ['full', 'compact'], 'description': 'По умолчанию full; compact без построения рамок полного режима.'},
    'wordcraft': dict(STRING, description='Необязательный абсолютный путь к wordcraft-cli.exe.'),
}
FORMAT = {
    **COMMON,
    'format_text': dict(BOOL, description='По умолчанию true. false сохраняет оформление текста, но разрешает исправления переносов и полей.'),
    'cover_mode': {'type':'string','enum':['new','preserve'],'description':'В полном режиме new по умолчанию: новый титульник перед целым исходным документом; preserve: сохранить распознанный существующий титульник.'},
    'metadata': METADATA,
    'toc_template': BOOL, 'bibliography_template': BOOL,
    'toc_entries': {'type': 'array', 'items': STRING},
    'bibliography_entries': {'type': 'array', 'items': STRING},
    'optional_sections': {'type': 'array', 'items': {'type': 'string', 'enum': ['annotation', 'normative', 'abbreviations']}},
}


def _tool(name, description, schema, readonly=True):
    return {'name': name, 'description': description, 'inputSchema': schema,
            'annotations': {'readOnlyHint': readonly, 'destructiveHint': False,
                            'openWorldHint': False}}


TOOLS = [
    _tool('doctor', 'Проверить Python, Wordcraft, PyMuPDF, профиль и шрифты. Не открывает GUI. Проверяйте data.ready перед обработкой.', _object({'wordcraft': STRING})),
    _tool('get_capabilities', 'Начните здесь: операции, схемы параметров, порядок работы, ограничения и справочники.', _object()),
    _tool('check_document', 'Проверить DOCX без автоматических исправлений. Создаёт отдельную экспортированную копию, PDF и отчёты. Исходник не изменяет.', _object({'input': STRING, **COMMON}, ['input']), False),
    _tool('format_document', 'Оформить отдельную копию DOCX. Прочитайте issues: успешная обработка не означает отсутствие замечаний.', _object({'input': STRING, **FORMAT}, ['input', 'out']), False),
    _tool('create_document', 'Создать заготовку из шаблона. Не придумывает содержание и реквизиты. Выберите новую папку результатов.', _object(FORMAT, ['out']), False),
    _tool('get_report', 'Прочитать report.json или папку результатов; отфильтровать замечания по severity и code.', _object({'path': STRING, 'severity': {'type': 'string', 'enum': ['error', 'warning', 'review']}, 'code': STRING}, ['path'])),
    _tool('get_requirement', 'Прочитать локальный реестр требований и индекс пунктов. reference — точный номер, например 6.2; search — текст поиска. Исторические обзоры не являются нормой.', _object({'reference': STRING, 'search': STRING})),
]


class RequestError(ValueError):
    pass


def _validate(value, schema, path='arguments'):
    kind = schema['type']
    valid = {'object': isinstance(value, dict), 'array': isinstance(value, list),
             'string': isinstance(value, str), 'boolean': isinstance(value, bool)}[kind]
    if not valid:
        raise RequestError(f'{path}: ожидается {kind}.')
    if 'enum' in schema and value not in schema['enum']:
        raise RequestError(f'{path}: допустимо {schema["enum"]}.')
    if kind == 'string' and len(value.strip()) < schema.get('minLength', 0):
        raise RequestError(f'{path}: пустое значение недопустимо.')
    if kind == 'object':
        unknown = set(value) - set(schema['properties'])
        missing = set(schema['required']) - set(value)
        if unknown or missing:
            raise RequestError(f'{path}: неизвестные поля {sorted(unknown)}; обязательные отсутствующие поля {sorted(missing)}.')
        for key, item in value.items():
            _validate(item, schema['properties'][key], f'{path}.{key}')
    if kind == 'array':
        for index, item in enumerate(value):
            _validate(item, schema['items'], f'{path}[{index}]')


def _font_check(font_name='Times New Roman'):
    if os.name != 'nt':
        import subprocess
        try:
            found = []
            for style in ('Regular', 'Italic'):
                result = subprocess.run(
                    ['fc-match', '-f', '%{family}\n%{style}\n%{file}\n', f'{font_name}:style={style}'],
                    capture_output=True, text=True, encoding='utf-8', timeout=10, check=True)
                lines = result.stdout.splitlines()
                if len(lines) < 3 or font_name.casefold() not in {s.strip().casefold() for s in lines[0].split(',')}:
                    raise ValueError(f'Fontconfig подставляет другой шрифт вместо {font_name} {style}.')
                if style == 'Italic' and not any(s in lines[1].casefold() for s in ('italic', 'oblique')):
                    raise ValueError(f'Не найден {font_name} Italic.')
                found.append({'name': lines[0] + ' ' + lines[1], 'file': lines[2]})
            return {'ok': True, 'family': font_name, 'fonts': found,
                    'detail': 'Семейство проверено через Fontconfig; подстановка дополнительно проверяется в PDF.'}
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            return {'ok': False, 'family': font_name, 'detail': str(error)}
    import winreg
    import pymupdf
    family = ''.join(c for c in font_name.casefold() if c.isalnum())
    fonts, seen = [], set()
    folders = [Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts']
    if os.environ.get('LOCALAPPDATA'):
        folders.append(Path(os.environ['LOCALAPPDATA']) / 'Microsoft/Windows/Fonts')

    def inspect(path):
        path = Path(path)
        if path in seen or not path.is_file():
            return
        seen.add(path)
        try:
            font = pymupdf.Font(fontfile=str(path))
            name = ''.join(c for c in font.name.casefold() if c.isalnum())
            if family in name:
                fonts.append({'name': font.name, 'file': str(path)})
        except Exception:
            return

    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts') as key:
                for index in range(winreg.QueryInfoKey(key)[1]):
                    name, value, _ = winreg.EnumValue(key, index)
                    if family in ''.join(c for c in name.casefold() if c.isalnum()):
                        path = Path(value)
                        if path.is_absolute():
                            inspect(path)
                        else:
                            for folder in folders:
                                inspect(folder / path)
        except OSError:
            continue
    # Per-user fonts can be present without readable registry entries (including
    # restricted agent sessions). Inspect their embedded family, not filenames.
    # Standard family filenames avoid scanning every installed font in the
    # ordinary case. Custom profiles still work with arbitrary font filenames.
    prefix = {'timesnewroman': 'times', 'isocpeur': 'iso'}.get(family, '')
    for folder in folders:
        for pattern in (prefix + '*.ttf', prefix + '*.otf'):
            for path in folder.glob(pattern):
                inspect(path)
    regular = any(not any(style in f['name'].casefold() for style in ('italic', 'bold')) for f in fonts)
    italic = any('italic' in f['name'].casefold() and 'bold' not in f['name'].casefold() for f in fonts)
    return {'ok': regular and italic, 'family': font_name,
            'detail': f'Нужны {font_name} Regular и Italic из выбранного профиля; фактическая подстановка дополнительно проверяется в PDF.',
            'fonts': fonts}


def doctor(wordcraft=None):
    checks = {'python': {'ok': sys.version_info >= (3, 11), 'version': sys.version.split()[0], 'executable': sys.executable}}
    try:
        import tkinter
        interpreter = tkinter.Tcl()
        checks['tkinter'] = {'ok': True, 'tcl': interpreter.eval('info patchlevel'), 'tk': tkinter.TkVersion}
    except Exception as error:
        checks['tkinter'] = {'ok': False, 'detail': str(error), 'remedy': 'Восстановите Python с Tcl/Tk или переустановите приложение полным установщиком.'}
    try:
        pdf = importlib.import_module('pymupdf')
        checks['pymupdf'] = {'ok': True, 'version': getattr(pdf, 'VersionBind', 'unknown')}
    except Exception as error:
        checks['pymupdf'] = {'ok': False, 'detail': str(error), 'remedy': 'Установите requirements.txt выбранным интерпретатором Python.'}
    try:
        engine = _engine()
        checks['profile'] = {'ok': True, 'values': engine.PROFILE, 'source': str(ROOT / 'Normokontrol.pdf')}
    except Exception as error:
        checks['profile'] = {'ok': False, 'detail': str(error)}
        engine = None
    try:
        if engine is None:
            raise RuntimeError('Сначала исправьте профиль и целостность нормативного источника.')
        cli = engine.find_cli(wordcraft)
        reply = subprocess.run([cli, '--version'], capture_output=True, text=True,
                               encoding='utf-8', timeout=15,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if reply.returncode:
            raise RuntimeError(reply.stderr.strip() or f'Wordcraft exit code {reply.returncode}')
        with engine.Wordcraft(cli) as wc:
            wc.rpc('tools/list', {})
        checks['wordcraft'] = {'ok': True, 'path': cli, 'version': reply.stdout.strip(), 'mcp_verified': True}
    except Exception as error:
        checks['wordcraft'] = {'ok': False, 'detail': str(error), 'remedy': 'Установите Wordcraft с wordcraft-cli.exe или передайте wordcraft.'}
    try:
        checks['stamp_fonts'] = _font_check(engine.PROFILE['stamp_font'] if engine is not None else 'Times New Roman')
    except Exception as error:
        checks['stamp_fonts'] = {'ok': False, 'detail': str(error)}
    return {'ready': all(item['ok'] for item in checks.values()), 'checks': checks}


def capabilities():
    from_version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    # This operation remains available even with a broken local profile.
    if str(ROOT / 'scripts') not in sys.path:
        sys.path.insert(0, str(ROOT / 'scripts'))
    from irgups_data import WORK_TYPES, DOCUMENT_CODES, DIRECTORY
    return {'version': from_version, 'tools': TOOLS, 'workflow': [
        'get_capabilities', 'doctor', 'check_document', 'format_document', 'get_report'],
        'work_types': WORK_TYPES, 'document_codes': DOCUMENT_CODES, 'departments': DIRECTORY,
        'path_base': str(Path.cwd()),
        'limits': ['Только DOCX; исходник не перезаписывается.',
                   'check_document экспортирует копию через Wordcraft; байтовое тождество копии исходнику не обещается.',
                   'Отслеживаемые исправления нужно принять или отклонить в отдельной копии.',
                   'Нет произвольного редактирования содержания и генерации научного текста.',
                   'Автоматические проверки не заменяют просмотр человеком и Microsoft Word.',
                   'MCP выполняет запросы последовательно; отмена активного запроса протоколом не поддерживается.'],
        'statuses': {'completed': 'Операция выполнена.', 'completed_with_findings': 'Обработка выполнена, есть замечания.', 'error': 'Операция не выполнена; смотрите error.'}}


def _result(report):
    if not isinstance(report, dict) or not isinstance(report.get('issues'), list):
        raise RequestError('Некорректный отчёт: ожидается объект с массивом issues.')
    folder = Path(report['output']).expanduser().resolve()
    counts = Counter(item.get('severity', 'warning') for item in report['issues'])
    artifacts = {'report_json': str(folder / 'report.json'), 'report_html': str(folder / 'report.html')}
    for kind in ('docx', 'pdf'):
        name = report[f'{kind}_name']
        if not isinstance(name, str) or Path(name).name != name:
            raise RequestError(f'Некорректное имя артефакта: {kind}.')
        artifacts[kind] = str(folder / name)
    return {'artifacts': artifacts, 'issue_counts': {level: counts[level] for level in ('error', 'warning', 'review')}, 'report': report}


def get_report(path, severity=None, code=None):
    target = Path(path).expanduser().resolve()
    if target.is_dir():
        target /= 'report.json'
    report = json.loads(target.read_text(encoding='utf-8-sig'))
    result = _result(report)
    selected = [i for i in report['issues'] if (severity is None or i.get('severity') == severity) and (code is None or i.get('code') == code)]
    result.update(issues=selected, matched_issues=len(selected), total_issues=len(report['issues']))
    return result


def get_requirement(reference=None, search=None):
    registry = json.loads((ROOT / 'references/norm-source/requirements.json').read_text(encoding='utf-8'))
    if hashlib.sha256((ROOT / 'Normokontrol.pdf').read_bytes()).hexdigest() != registry['source_sha256']:
        raise ValueError('PDF нормоконтроля изменён; извлечение и реестр требований требуют повторной сверки.')
    clauses = json.loads((ROOT / 'references/norm-source/clauses.json').read_text(encoding='utf-8'))
    def matches(item, key):
        return (reference is None or item[key] == reference) and (search is None or search.casefold() in json.dumps(item, ensure_ascii=False).casefold())
    return {'source': str(ROOT / 'Normokontrol.pdf'), 'source_sha256': registry['source_sha256'],
            'precedence': registry['precedence'], 'rules': [r for r in registry['rules'] if matches(r, 'source')],
            'clauses': [c for c in clauses if c['page'] > 5 and matches(c, 'clause')],
            'note': 'Индекс пунктов не заменяет контекст PDF; растровые надписи не распознавались OCR.'}


def _process(name, arguments):
    options = dict(arguments)
    source = options.pop('input', None)
    out = options.pop('out', None)
    options['cli'] = options.pop('wordcraft', None)
    options['progress'] = lambda message: print(message, file=sys.stderr, flush=True)
    engine = _engine()
    if name == 'check_document':
        report = engine.process(source, out, check_only=True, **options)
    elif name == 'create_document':
        report = engine.create_document(out, **options)
    else:
        report = engine.process(source, out, **options)
    return _result(report)


def invoke(name, arguments=_MISSING):
    """Return the same JSON-serializable envelope through Python, CLI and MCP."""
    try:
        tool = next((t for t in TOOLS if t['name'] == name), None)
        if tool is None:
            raise RequestError(f'Неизвестная операция: {name}. Используйте get_capabilities.')
        arguments = {} if arguments is _MISSING else arguments
        _validate(arguments, tool['inputSchema'])
        # Libraries and future engine progress messages must not corrupt stdout.
        with redirect_stdout(sys.stderr):
            if name == 'get_capabilities':
                data = capabilities()
            elif name in {'doctor', 'get_report', 'get_requirement'}:
                data = globals()[name](**arguments)
            else:
                data = _process(name, arguments)
        findings = bool(data.get('report', {}).get('issues'))
        return {'schema_version': SCHEMA_VERSION, 'ok': True,
                'status': 'completed_with_findings' if findings else 'completed', 'data': data, 'error': None}
    except Exception as error:
        code = 'invalid_request' if isinstance(error, RequestError) else 'invalid_document_or_options' if isinstance(error, ValueError) else 'io_error' if isinstance(error, OSError) else 'processing_error'
        return {'schema_version': SCHEMA_VERSION, 'ok': False, 'status': 'error', 'data': None,
                'error': {'code': code, 'type': type(error).__name__, 'message': str(error)}}


def cli_main(argv=None):
    import argparse
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise RequestError(message)
    parser = Parser(description='Нормоконтроль: одна операция, JSON в stdout; прогресс в stderr.')
    parser.add_argument('--agent', required=True, help='Операция; начните с get_capabilities или doctor.')
    parser.add_argument('--request', help='UTF-8 JSON с аргументами; - читает stdin. По умолчанию {}.')
    try:
        args = parser.parse_args(argv)
        request = json.loads(sys.stdin.read() if args.request == '-' else Path(args.request).read_text(encoding='utf-8-sig')) if args.request else {}
        result = invoke(args.agent, request)
    except (OSError, ValueError) as error:
        result = {'schema_version': SCHEMA_VERSION, 'ok': False, 'status': 'error', 'data': None,
                  'error': {'code': 'invalid_request', 'type': type(error).__name__, 'message': str(error)}}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 1
