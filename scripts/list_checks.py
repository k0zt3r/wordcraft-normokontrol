"""Read-only list diagnostics; ambiguous hierarchy never changes author text."""
import re

MARKER = re.compile(r'^\s*(?:[-–—]\s+|\d+[.)]\s+|[а-яё]\)\s+)', re.I)


def initial_abbreviation(text):
    token = re.match(r'[A-Za-zА-ЯЁа-яё][A-Za-zА-ЯЁа-яё0-9_-]*', text)
    return bool(token and sum(c.isalpha() for c in token[0]) >= 2 and token[0].isupper())


def excerpt(text):
    # Preserve the trailing introduction, often lost after a long first sentence.
    return text if len(text) <= 180 else text[:60] + ' … ' + text[-110:]


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
