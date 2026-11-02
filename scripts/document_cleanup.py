"""Remove redundant chapter breaks and format existing source lists as tables."""
import copy
import json
import re
from pathlib import Path


def prepare(model, changes, issues, check_only=False):
    from normokontrol import norm, heading_level, body_start, add_issue, byte_len, effective_para, SPECIAL
    body = model['body']
    start = body_start(model)
    # Replace literal alignment tabs after a list number, retaining run formatting.
    for p in body[start:]:
        if p['kind'] != 'para' or p.get('objects') or p.get('fields'):
            continue
        text = p.get('text', '')
        match = re.match(r'^\s*\d+[.)]([ \t]+)\S', text)
        if not match or '\t' not in match[1]:
            continue
        if check_only:
            add_issue(issues, 'list-tab', 'После номера перечисления стоит табуляция; режим оформления заменяет её пробелом.')
            continue
        offset, index, runs, chunks = 0, 0, [], []
        data = text.encode('utf-8')
        for run in p.get('runs', []):
            chunk = data[offset:offset+run['len']].decode('utf-8')
            offset += run['len']
            value = ''.join((' ' if j == match.start(1) else '') if match.start(1) <= j < match.end(1) else c
                            for j,c in enumerate(chunk,index))
            index += len(chunk)
            if value:
                item=copy.deepcopy(run)
                item['len']=byte_len(value)
                runs.append(item)
                chunks.append(value)
        if offset == len(data):
            p['text'],p['runs']=''.join(chunks),runs
            changes.append('Табуляция после номера перечисления заменена одним пробелом.')
    # A standalone manual break before a chapter duplicates pageBreakBefore.
    for index in range(start, len(body)):
        p = body[index]
        text = p.get('text', '')
        if p['kind'] != 'para' or '\f' not in text or norm(text) or p.get('section') or p.get('fields'):
            continue
        if any(o.get('type') not in {'bookmarkStart', 'bookmarkEnd'} for o in p.get('objects', [])):
            continue
        following = next((b for b in body[index+1:] if b['kind'] != 'para' or norm(b.get('text', ''))), None)
        if not following or following['kind'] != 'para' or heading_level(following, model.get('styles', {}), model.get('numbering')) != 1:
            continue
        if check_only:
            add_issue(issues, 'redundant-page-break', 'Ручной разрыв перед главой/структурным разделом может создавать пустую страницу.')
            continue
        # Preserve positional bookmark markers and run properties.
        data, offset, runs = text.encode('utf-8'), 0, []
        for run in p.get('runs', []):
            chunk = data[offset:offset+run['len']].decode('utf-8')
            offset += run['len']
            item = copy.deepcopy(run)
            item['len'] = byte_len(chunk.replace('\f', ''))
            if item['len']:
                runs.append(item)
        if offset != len(data):
            continue
        p['text'], p['runs'] = text.replace('\f', ''), runs
        changes.append('Убран дублирующий ручной разрыв перед главой/структурным разделом.')
    aliases = {'список литературы', 'список использованных источников', 'библиографический список'}
    refs = next((i for i,b in enumerate(body) if b['kind']=='para' and norm(b.get('text','')) in aliases), None)
    if refs is None:
        return
    end = len(body)
    for i in range(refs + 1, len(body)):
        text = norm(body[i].get('text', ''))
        if body[i]['kind'] != 'para' or text in SPECIAL or re.match(r'^(?:приложение\s|глава\s)', text):
            end = i
            break
    entries = [p for p in body[refs+1:end] if norm(p.get('text',''))]
    if not entries:
        return
    # Positional parts and manual page/section breaks require separate treatment.
    if any(p.get('section') or '\f' in p.get('text','') for p in body[refs+1:end]):
        add_issue(issues, 'bibliography-review', 'Список источников содержит разрывы разделов/страниц: проверьте его таблицу вручную.')
        return
    if check_only:
        add_issue(issues, 'bibliography-table', 'Список источников оформлен абзацами/перечислением; режим оформления преобразует его в таблицу без границ.')
        return
    marker = re.compile(r'^\s*(?:\[(\d+)\]|(\d+)[.)])\s+')
    explicit = [marker.match(p.get('text','')) for p in entries]
    native = [bool(effective_para(model,p).get('numbering')) for p in entries]
    # Explicit/native list markers delimit entries; other paragraphs continue them.
    marked = any(explicit) or any(native)
    groups = []
    for p, match, listed in zip(entries, explicit, native):
        if marked:
            if match or listed:
                groups.append([])
            elif not groups:
                add_issue(issues,'bibliography-review','Перед первым номером источника есть текст: список оставлен для ручной проверки.')
                return
        else:
            # A URL at the beginning is an explicit independent source cue.
            if not re.match(r'^https?://', norm(p.get('text',''))):
                add_issue(issues,'bibliography-review','Неясно, где заканчивается источник и начинается следующий: список оставлен без преобразования.')
                return
            groups.append([])
        item=copy.deepcopy(p)
        if match:
            if p.get('objects') or p.get('fields'):
                add_issue(issues,'bibliography-review','Ручной номер источника совмещён с полями/объектами: список оставлен без преобразования.')
                return
            remaining=byte_len(p['text'][:match.end()])
            runs=[]
            for run in item.get('runs',[]):
                take=min(remaining,run['len']);remaining-=take
                if run['len']>take:
                    run['len']-=take;runs.append(run)
            if remaining:
                add_issue(issues,'bibliography-review','Не удалось безопасно выделить номер источника: проверьте список вручную.')
                return
            item['text']=item['text'][match.end():];item['runs']=runs
        groups[-1].append(item)
    template = json.loads((Path(__file__).resolve().parent.parent/'assets/course-templates.json').read_text(encoding='utf-8'))['bibliography']
    table = copy.deepcopy(template)
    table['rows'] = []
    for number, group in enumerate(groups, 1):
        row = copy.deepcopy(template['rows'][0])
        label = row['cells'][0]['blocks'][0]
        label.update(text=str(number), runs=[{'len':byte_len(str(number)), 'props':{}}])
        for item in group:
            item.setdefault('props',{}).update(numbering={'num':0,'level':0}, outlineLevel=9,
                                              pageBreakBefore=False, keepNext=False, indentLeft=0.0, indentFirst=0.0, tabs=[])
        row['cells'][1]['blocks'] = group
        table['rows'].append(row)
    # Keep empty paragraphs with bookmark anchors in the same order.
    if any(p.get('objects') and not norm(p.get('text','')) for p in body[refs+1:end]):
        add_issue(issues, 'bibliography-review', 'В списке источников есть отдельные закладки: преобразуйте его в таблицу вручную.')
        return
    body[refs+1:end] = [table]
    changes.append('Существующие источники помещены в таблицу без границ; маркеры заменены номерами без точки, описания сохранены.')
