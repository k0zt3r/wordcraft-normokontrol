"""Independent import checks and guards around text-preserving transformations."""
import re
import unicodedata
import xml.etree.ElementTree as ET
from zipfile import ZipFile

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def canonical(text):
    return re.sub(r'\s+', '', unicodedata.normalize('NFC', text).replace('\ufffc', ''))


def imported_text(model):
    from normokontrol import paragraphs, auto_toc_text
    generated = auto_toc_text(model['body'])
    result = []
    for path, p in paragraphs(model['body']):
        if tuple(path) in generated:
            result.append(generated[tuple(path)])
        elif not p.get('fields') and not any(o.get('type', '').startswith('field') for o in p.get('objects', [])):
            result.append(p.get('text', ''))
    return canonical(''.join(result))


def original_text(path):
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
    result, field_stack = [], []

    def visit(node):
        if node.tag == W + 'txbxContent':
            return  # Textbox stories are checked separately on roundtrip.
        if node.tag == W + 'p':
            def inline(element):
                if element.tag == W+'txbxContent':
                    return
                yield element
                for child in element:
                    yield from inline(child)
            elements = list(inline(node))
            has_field = any(e.tag in {W+'fldChar', W+'fldSimple'} for e in elements)
            for e in elements:
                if e.tag == W+'fldChar':
                    kind = e.get(W+'fldCharType')
                    if kind == 'begin':
                        field_stack.append(True)
                    elif kind == 'end' and field_stack:
                        field_stack.pop()
                elif e.tag == W+'t' and not has_field and not field_stack:
                    result.append(e.text or '')
                elif e.tag == W+'noBreakHyphen' and not has_field and not field_stack:
                    result.append('\u2011')
                elif e.tag == W+'softHyphen' and not has_field and not field_stack:
                    result.append('\u00ad')
            return
        for child in node:
            visit(child)
    visit(root.find(W+'body'))
    return canonical(''.join(result))


def check_import(path, model):
    if original_text(path) != imported_text(model):
        raise RuntimeError('Импорт Wordcraft изменил обычный текст исходного DOCX. Результат не выдан; сохраните отдельную совместимую копию документа.')


def prose(model):
    """Ignore bibliography numbers only; retain all other visible prose and order."""
    from normokontrol import paragraphs, norm
    bibliography = False
    result = []
    for path, p in paragraphs(model['body']):
        text = p.get('text', '')
        if norm(text) in {'список литературы','список использованных источников','библиографический список'}:
            bibliography = True
        if norm(text).startswith('приложение '):
            bibliography = False
        if bibliography:
            if len(path)>1 and path[2] == 0 and re.fullmatch(r'\s*\d+\s*', text):
                continue
            text = re.sub(r'^\s*(?:\[\d+\]|\d+[.)])\s+', '', text)
        result.append(text)
    return canonical(''.join(result))


def preserving(model, action, *args, **kwargs):
    before = prose(model)
    result = action(model, *args, **kwargs)
    if prose(model) != before:
        raise RuntimeError(f'Преобразование {action.__name__} изменило защищённый текст. Результат не выдан.')
    return result
