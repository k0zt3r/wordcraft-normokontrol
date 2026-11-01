"""Conservative checks of explicit text properties and appendix references."""
import re


def check_rules(model, mode, issues):
    from normokontrol import (body_start, paragraphs, effective_para, effective_char,
                             visible_text_runs, heading_level, CAPTION, auto_toc_text,
                             detect_tocs, norm, MM, add_issue)
    body = model['body']
    start = body_start(model)
    automatic = auto_toc_text(body)
    toc = set(detect_tocs(body))
    headings = set()
    counters = {}
    appendices = []
    ordinary = []
    for path, para in paragraphs(body):
        if path[0] < start or path[0] in toc or tuple(path) in automatic:
            continue
        text = para.get('text', '').strip()
        if not text:
            continue
        props = effective_para(model, para)
        level = heading_level(para, model.get('styles', {})) if len(path) == 1 else None
        if level:
            if (props.get('spaceAfter') or 0) < 28 - .1:
                add_issue(issues, 'heading-spacing', f'Проверьте два интервала после заголовка (приложение Е): {text}')
            match = re.match(r'^(\d+(?:\.\d+)*)\s+\S', text)
            if match:
                number = tuple(map(int, match[1].split('.')))
                if number in headings:
                    add_issue(issues, 'heading-number', f'Повтор номера раздела: {match[1]}.')
                parent = number[:-1]
                previous = counters.get(parent, 0)
                if number[-1] != previous + 1:
                    add_issue(issues, 'heading-sequence', f'Проверьте последовательность разделов (§7.2): {text}')
                if parent and parent not in headings:
                    add_issue(issues, 'heading-parent', f'Не найден родительский раздел: {text}')
                counters[parent] = number[-1]
                headings.add(number)
            appendix = re.fullmatch(r'приложение\s+([а-яёa-z]|\d+)', norm(text))
            if appendix:
                appendices.append((path[0], appendix[1]))
        elif len(path) == 1 and not CAPTION.match(text) and not para.get('objects') and not para.get('fields'):
            ordinary.append((path[0], text))
            # Commands, formulas and native numbering need their own layout rules.
            if not props.get('numbering') and not re.search(r'[\n\t{}=;]|https?://|^(?:sudo |for |if |def |class )', text):
                expected = (10 if mode == 'full' else 12.5) * MM
                if abs((props.get('indentFirst') or 0) - expected) > .5:
                    add_issue(issues, 'paragraph-indent', f'Абзацный отступ отличается от {10 if mode == "full" else 12.5} мм (§7.1.4): {text[:100]}')
        for run, visible in visible_text_runs(para):
            color = effective_char(model, para, run).get('color')
            # Theme/automatic colors cannot be inferred safely from their token.
            if isinstance(color, dict) and 'Rgb' in color and color['Rgb'] != [0, 0, 0]:
                add_issue(issues, 'text-color', f'Цвет текста отличается от чёрного (§7.1.3): {visible[:100]}')
    if mode != 'full':
        return
    seen = set()
    first_refs = []
    for index, letter in appendices:
        if letter in seen:
            add_issue(issues, 'appendix-duplicate', f'Повтор обозначения приложения: {letter.upper()}.')
        seen.add(letter)
        if letter in set('ёзйочьыъio'):
            add_issue(issues, 'appendix-letter', f'Недопустимое обозначение приложения (§7.10.5): {letter.upper()}.')
        pattern = r'(?<!\w)приложени\w*\s+' + re.escape(letter) + r'(?!\w)'
        refs = [i for i, text in ordinary if re.search(pattern, norm(text))]
        if not refs:
            add_issue(issues, 'appendix-reference', f'Не найдена текстовая ссылка на приложение {letter.upper()} (§7.10.2).')
        else:
            first_refs.append((index, min(refs), letter))
    for left, right in zip(first_refs, first_refs[1:]):
        if left[1] > right[1]:
            add_issue(issues, 'appendix-order', f'Проверьте порядок первых ссылок на приложения {left[2].upper()} и {right[2].upper()} (§7.10.2).')
