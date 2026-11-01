"""Conservative cleanup of plain body paragraphs; preserve run formatting."""
import copy
import re


def clean(model, changes, issues, check_only=False):
    from normokontrol import body_start, auto_toc_text, add_issue
    body = model['body']
    start = body_start(model)
    automatic = auto_toc_text(body)
    remove = []
    count = 0
    for index, p in enumerate(body):
        if index < start or p['kind'] != 'para' or (index,) in automatic:
            continue
        text = p.get('text', '')
        props = p.get('props', {})
        if p.get('objects') or p.get('fields') or p.get('section') or any(c in text for c in '\n\r\t\f\ufffc'):
            continue
        if props.get('pageBreakBefore') or props.get('numbering'):
            continue
        if not text.strip():
            remove.append(index)
            continue
        # Avoid literal source-code/alignment blocks.
        if re.search(r'[{};=]|https?://|^\s*(?:sudo |for |if |def |class )', text):
            continue
        deletions = set()
        for match in re.finditer(r' {2,}|^ +| +$', text):
            keep = 0 if match.start() == 0 or match.end() == len(text) else 1
            deletions.update(range(match.start() + keep, match.end()))
        if not deletions:
            continue
        count += 1
        if check_only:
            continue
        offset, char_index, runs, chunks = 0, 0, [], []
        data = text.encode('utf-8')
        for run in p.get('runs', []):
            chunk = data[offset:offset + run['len']].decode('utf-8')
            offset += run['len']
            kept = ''.join(c for j, c in enumerate(chunk, char_index) if j not in deletions)
            char_index += len(chunk)
            if kept:
                new = copy.deepcopy(run)
                new['len'] = len(kept.encode('utf-8'))
                runs.append(new)
                chunks.append(kept)
        if offset == len(data):
            p['text'], p['runs'] = ''.join(chunks), runs
    if check_only:
        if count or remove:
            add_issue(issues, 'whitespace', f'Лишние пробелы: {count} абз.; пустые абзацы основного текста: {len(remove)}. Режим оформления может очистить их.')
    else:
        for index in reversed(remove):
            del body[index]
        if count or remove:
            changes.append(f'Очищены пробелы в {count} абз.; удалено пустых абзацев основного текста: {len(remove)}. Разрывы страниц и сложные объекты сохранены.')
