"""Read-only list diagnostics; ambiguous hierarchy never changes author text."""
import re

MARKER = re.compile(r'^\s*(?:[-–—]\s+|\d+[.)]\s+|[а-яё]\)\s+)', re.I)


def initial_abbreviation(text):
    token = re.match(r'[A-Za-zА-ЯЁа-яё][A-Za-zА-ЯЁа-яё0-9_-]*', text)
    return bool(token and sum(c.isalpha() for c in token[0]) >= 2 and token[0].isupper())


def excerpt(text):
    # Preserve the trailing introduction, often lost after a long first sentence.
    return text if len(text) <= 180 else text[:60] + ' … ' + text[-110:]


def _list_entry(model, para):
    """Explicit list metadata only; prose and punctuation do not create a list."""
    from normokontrol import effective_para
    if para.get('kind') != 'para':
        return None
    ref = effective_para(model, para).get('numbering') or {}
    numbering = model.get('numbering', {})
    num = next((n for n in numbering.get('nums', []) if n['id'] == ref.get('num')), None)
    abstract = next((a for a in numbering.get('abstracts', []) if num and a['id'] == num['abstractId']), None)
    depth = ref.get('level', 0)
    native = abstract['levels'][depth] if abstract and 0 <= depth < len(abstract.get('levels', [])) else None
    visible = para.get('text', '').replace('\ufffc', '').strip()
    marker = MARKER.match(visible)
    if native and native.get('format') in {'bullet', 'decimal', 'lowerLetter', 'upperLetter'}:
        return ('native', ref['num']), depth, visible
    if marker:
        token = marker[0].strip()
        family = 'digit' if token[0].isdigit() else 'dash' if token[0] in '-–—' else 'letter'
        return ('manual', family), 0, visible[marker.end():]
    return None


def _terminal_edit(para, start, end, ending):
    """Stage an exact terminal replacement and verify unrelated run data."""
    import copy
    from text_edits import replace
    old = para.get('text', '')
    candidate = copy.deepcopy(para)
    if not replace(candidate, start, end, ending):
        return None
    expected = old[:start] + ending + old[end:]
    if candidate['text'] != expected:
        raise RuntimeError('Исправление окончания перечисления изменило защищённый текст.')
    # Byte styles before and after the planned span must be identical. Run
    # splitting is permitted; changing their formatting metadata is not.
    def styles(p):
        result = []
        for run in p.get('runs', []):
            meta = {k: v for k, v in run.items() if k != 'len'}
            result.extend([meta] * run['len'])
        return result
    lo, hi = len(old[:start].encode('utf-8')), len(old[:end].encode('utf-8'))
    old_styles, new_styles = styles(para), styles(candidate)
    added = len(ending.encode('utf-8'))
    if (len(new_styles) != len(expected.encode('utf-8'))
            or old_styles[:lo] != new_styles[:lo] or old_styles[hi:] != new_styles[lo + added:]):
        raise RuntimeError('Исправление окончания перечисления изменило форматирование текста.')
    expected_objects = copy.deepcopy(para.get('objects', []))
    delta = added - (hi - lo)
    for obj in expected_objects:
        if isinstance(obj.get('off'), int) and obj['off'] >= hi:
            obj['off'] += delta
    if candidate.get('objects', []) != expected_objects:
        raise RuntimeError('Исправление окончания перечисления изменило служебные объекты.')
    metadata = lambda p: {k: v for k, v in p.items() if k not in {'text', 'runs', 'objects'}}
    if metadata(candidate) != metadata(para):
        raise RuntimeError('Исправление окончания перечисления изменило свойства абзаца.')
    return candidate


def format_simple(model, changes, issues, check_only=False):
    """Apply terminal ;/. only to a whole, explicitly introduced simple list."""
    from normokontrol import body_start, auto_toc_text, norm
    from structure import analyze
    if check_only:
        return
    body = model['body']
    start = body_start(model)
    structure = analyze(model)
    excluded = set(structure['toc']) | set(structure['levels']) | {p[0] for p in auto_toc_text(body)}
    clusters, current = [], []
    for i, p in enumerate(body):
        if i < start:
            continue
        text = norm(p.get('text', ''))
        if text in {'список литературы', 'список использованных источников', 'библиографический список'} or text.startswith('приложение '):
            break
        entry = None if i in excluded else _list_entry(model, p)
        if current and (entry is None or entry[0] != current[-1][1][0]):
            clusters.append(current)
            current = []
        if entry is not None:
            current.append((i, entry))
    if current:
        clusters.append(current)
    for cluster in clusters:
        first, last = cluster[0][0], cluster[-1][0]
        if len(cluster) < 2 or first <= start:
            continue
        intro = body[first - 1]
        # Do not turn one side of a mixed-ID/marker list into an independent
        # simple group, and never look backwards across a blank paragraph.
        if (intro.get('kind') != 'para' or first - 1 in excluded
                or _list_entry(model, intro) or intro.get('fields') or intro.get('objects')
                or not intro.get('text', '').rstrip().endswith(':')
                or (last + 1 < len(body) and _list_entry(model, body[last + 1]))):
            continue
        if len({entry[1] for _, entry in cluster}) != 1:
            continue
        staged = []
        safe = True
        for order, (i, (_, _, content)) in enumerate(cluster):
            p = body[i]
            if (not content or content.endswith(':') or re.search(r'[.!?]\s+\S', content)
                    or p.get('fields') or any(o.get('type') not in {'bookmarkStart', 'bookmarkEnd'} for o in p.get('objects', []))
                    or any(c in p.get('text', '') for c in '\n\r\f\t')
                    or content.endswith(('!', '?', '…', '"', "'", '»', '”', '’', ')', ']', '}'))
                    or content.endswith(('..', ';;'))
                    or re.search(r'(?:[A-Za-zА-Яа-яЁё]\.){2,}$|(?:\s|^)[A-ZА-ЯЁ]\.$', content)):
                safe = False
                break
            text = p['text']
            end = len(text)
            while end and (text[end - 1].isspace() or text[end - 1] == '\ufffc'):
                end -= 1
            ending = ';' if order < len(cluster) - 1 else '.'
            if not end or text[end - 1] == ending:
                continue
            begin = end - 1 if text[end - 1] in ';.' else end
            updated = _terminal_edit(p, begin, end, ending)
            if updated is None:
                safe = False
                break
            staged.append((i, updated))
        if safe:
            for i, updated in staged:
                body[i] = updated
            if staged:
                changes.append(f'Исправлены только окончания {len(staged)} пунктов однозначного перечисления после двоеточия по приложению Д; слова и регистр сохранены.')


def process(model, changes, issues, check_only=False):
    """Both modes report suggestions; native marker formatting happens elsewhere."""
    from normokontrol import body_start, effective_para, effective_char, visible_text_runs, norm, add_issue, auto_toc_text
    from structure import analyze
    structure = analyze(model)
    body = model['body']
    start = body_start(model)
    numbering = model.get('numbering', {})
    excluded = set(structure['toc']) | {path[0] for path in auto_toc_text(body)}
    clusters, current = [], []

    def finish():
        nonlocal current
        if current:
            clusters.append(current)
            current = []

    for i, p in enumerate(body):
        if i < start:
            continue
        text = norm(p.get('text', ''))
        if text in {'список литературы', 'список использованных источников', 'библиографический список'} or text.startswith('приложение '):
            break
        objects = p.get('objects', [])
        if (p['kind'] != 'para' or i in structure['levels'] or i in excluded
                or p.get('fields') or any(o.get('type') not in {'bookmarkStart', 'bookmarkEnd'} for o in objects)):
            finish()
            continue
        props = effective_para(model, p)
        ref = props.get('numbering') or {}
        num = next((n for n in numbering.get('nums', []) if n['id'] == ref.get('num')), None)
        abstract = next((a for a in numbering.get('abstracts', []) if num and a['id'] == num['abstractId']), None)
        depth = ref.get('level', 0)
        native = abstract['levels'][depth] if abstract and 0 <= depth < len(abstract.get('levels', [])) else None
        raw = p.get('text', '')
        visible = raw.replace('\ufffc', '').strip()
        manual = MARKER.match(visible)
        if not ((native and native.get('format') in {'bullet', 'decimal', 'lowerLetter', 'upperLetter'}) or manual):
            finish()
            continue
        # Different Word list IDs are independent lists, not evidence of nesting.
        group = ('native', ref['num']) if native else ('manual',)
        if current and current[-1]['group'] != group:
            finish()
        content = MARKER.sub('', visible, count=1) if manual else visible
        runs = list(visible_text_runs(p))
        if runs and all(effective_char(model, p, r).get('italic') for r, _ in runs):
            add_issue(issues, 'list-italic-review', f'Весь пункт выделен курсивом: проверьте обоснованность по §7.1.3 и приложению Д: {visible[:100]}')
        if ((native and native.get('format') == 'decimal' and not native.get('text', '').endswith(')'))
                or (manual and re.match(r'^\s*\d+\.\s+', visible))):
            add_issue(issues, 'list-marker', f'Проверьте цифровой маркер перечисления: по §7.2.7 используют номер со скобкой. Текст не изменён: {visible[:100]}')
        current.append({'index': i, 'depth': depth, 'content': content, 'group': group})
    finish()

    for cluster in clusters:
        first = cluster[0]['index']
        previous = None
        for j in range(first - 1, start - 1, -1):
            b = body[j]
            if b['kind'] != 'para' or j in structure['levels'] or j in excluded or b.get('objects') or b.get('fields'):
                break
            if norm(b.get('text', '')):
                previous = b
                break
        introduced = bool(previous and norm(previous.get('text', '')).endswith(':'))
        for k, item in enumerate(cluster):
            i, depth, content = item['index'], item['depth'], item['content']
            if content and content[0].isupper() and not initial_abbreviation(content):
                add_issue(issues, 'list-case-review', f'Проверьте начало пункта перечисления по приложению Д: строчная буква зависит от конструкции; имена собственные сохраняются. Текст не изменён: {content[:100]}')
            if content.endswith(':'):
                following = cluster[k + 1:]
                if following and following[0]['depth'] == depth:
                    suspects = []
                    for following_item in following:
                        if following_item['depth'] != depth:
                            break
                        suspects.append(following_item)
                        if following_item['content'].endswith(':') or len(suspects) == 3:
                            break
                    examples = '; '.join(f'«{s["content"][:100]}»' for s in suspects)
                    add_issue(issues, 'list-structure-review',
                              f'Проверьте структуру перечисления после «{excerpt(content)}» '
                              f'(абзац {i + 1}): следующие пункты имеют тот же уровень {depth + 1}: {examples}. '
                              'Возможны подпункты или продолжение самостоятельного списка; двоеточие не доказывает вложенность. '
                              'Уточните роль вводного абзаца и границы группы по §7.2.7, §7.2.8 и приложению Д. Уровни и текст не изменены.')
                continue
            if len(cluster) < 2 and not introduced:
                continue
            following = next((entry for entry in cluster[k + 1:] if entry['depth'] <= depth), None)
            ending = ';' if following else '.'
            # Full sentences may legitimately be independent list items.
            if re.search(r'[.!?]\s+\S', content):
                add_issue(issues, 'list-punctuation-review', f'Пункт содержит несколько предложений: проверьте оформление и окончание по приложению Д; ожидаемая пунктуация зависит от структуры. Текст не изменён: {content[:100]}')
            elif content and not content.rstrip().endswith(ending):
                add_issue(issues, 'list-punctuation', f'Проверьте окончание пункта перечисления: для связанного перечисления здесь ожидается «{ending}». Текст не изменён: {content[:100]}')
