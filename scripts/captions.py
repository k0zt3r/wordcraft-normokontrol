"""Fill missing captions without changing existing reference targets."""
import re


def fill_captions(model, changes, issues, check_only=False):
    from format_profile import PROFILE
    from normokontrol import (body_start, detect_tocs, auto_toc_text, norm,
                             next_block, paragraphs, byte_len, font, add_issue)
    body = model['body']
    start = body_start(model)
    excluded = set(detect_tocs(body)) | {p[0] for p in auto_toc_text(body)}
    pattern = re.compile(r'^\s*(Рисунок|Таблица)(?:\s+(\d+(?:\.\d+)*|[А-ЯA-Z]\.\d+))?(?:\s*[—–-]\s*(.*))?\s*$', re.I)
    reserved = {'рисунок': set(), 'таблица': set()}
    for b in body:
        match = pattern.fullmatch(b.get('text', ''))
        if match and match[2] and match[2].isdigit():
            reserved[match[1].lower()].add(int(match[2]))
    counters = {'рисунок': 0, 'таблица': 0}
    plans = []
    bibliography = False
    for i, block in enumerate(body):
        if i < start or i in excluded:
            continue
        text = norm(block.get('text', ''))
        if re.match(r'^приложение\s+[а-яa-z](?:\s|$)', text):
            break  # Appendix numbering is separate from the main text.
        if text in {'список литературы', 'список использованных источников', 'библиографический список'}:
            bibliography = True
        if bibliography:
            continue
        kind = None
        caption_index = None
        if block['kind'] == 'table':
            kind = 'таблица'
            prior = next((j for j in range(i - 1, -1, -1) if norm(body[j].get('text', '')) or body[j]['kind'] != 'para'), None)
            if prior is not None:
                candidate = pattern.fullmatch(body[prior].get('text', ''))
                if candidate and candidate[1].lower() == kind:
                    caption_index = prior
        elif block['kind'] == 'para' and any(o.get('type') in {'image', 'chart', 'smartArt'} for o in block.get('objects', [])):
            # Mixed text/image paragraphs and grouped drawings need human interpretation.
            if text:
                add_issue(issues, 'caption-review', 'Рисунок находится в абзаце с текстом: проверьте подпись вручную.')
                continue
            kind = 'рисунок'
            j, following = next_block(body, i)
            candidate = pattern.fullmatch(following.get('text', '')) if following else None
            if candidate and candidate[1].lower() == kind:
                caption_index = j
        if kind is None:
            continue
        counters[kind] += 1
        match = pattern.fullmatch(body[caption_index].get('text', '')) if caption_index is not None else None
        if caption_index is None:
            if kind == 'таблица':
                _, other = next_block(body, i)
            else:
                prior = next((j for j in range(i - 1, -1, -1) if norm(body[j].get('text', '')) or body[j]['kind'] != 'para'), None)
                other = body[prior] if prior is not None else None
            wrong = pattern.fullmatch(other.get('text', '')) if other else None
            if wrong and wrong[1].lower() == kind:
                side = 'над рисунком; перенесите её под рисунок' if kind == 'рисунок' else 'под таблицей; перенесите её над таблицей'
                add_issue(issues, 'caption-position', f'Подпись «{other["text"]}» расположена {side}.')
                continue
        if match and match[2] and match[3]:
            if 'Впишите название' in match[3]:
                add_issue(issues, 'caption-placeholder', f'Заполните название: {body[caption_index]["text"]}')
            continue
        if caption_index is not None and (body[caption_index].get('objects') or body[caption_index].get('fields')):
            add_issue(issues, 'caption-review', 'Подпись содержит поля Word: проверьте её заполнение вручную.')
            continue
        number = match[2] if match and match[2] else None
        if not number:
            number = counters[kind]
            while number in reserved[kind]:
                number += 1
            reserved[kind].add(number)
        name = match[3] if match and match[3] else ('Впишите название рисунка' if kind == 'рисунок' else 'Впишите название таблицы')
        title = f'{kind.capitalize()} {number} — {name}'
        add_issue(issues, 'caption-placeholder', f'Проверьте название и ссылки: {title}')
        if check_only:
            side = 'под рисунком' if kind == 'рисунок' else 'над таблицей'
            add_issue(issues, 'caption-missing', f'Нет полной подписи {side}. Пример: {title}')
            continue
        p = {'kind': 'para', 'text': title, 'runs': [{'len': byte_len(title)}],
             'props': {'align': 'center' if kind == 'рисунок' else 'left', 'indentFirst': 0.0,
                       'keepLines': True, 'keepNext': kind == 'таблица'}}
        font(p, PROFILE['text_size'])
        plans.append((caption_index if caption_index is not None else i + (kind == 'рисунок'), caption_index is not None, p))
    for _, (index, replace, para) in sorted(enumerate(plans), key=lambda item: (item[1][0], item[0]), reverse=True):
        if replace:
            body[index] = para
        else:
            body.insert(index, para)
        changes.append('Заполнена подпись: ' + para['text'])
