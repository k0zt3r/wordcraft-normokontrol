"""Conservative checks of explicit text properties and appendix references."""
import re


def check_rules(model, mode, issues, heading_gap=None):
    from format_profile import PROFILE
    from structure import analyze
    structure = analyze(model)
    from normokontrol import (body_start, paragraphs, effective_para, effective_char,
                             visible_text_runs, CAPTION, auto_toc_text,
                             norm, MM, add_issue, NUMBERED_HEADING)
    body = model['body']
    bibliography=False
    for block in body:
        label=norm(block.get('text',''))
        if label in {'список использованных источников','библиографический список','список литературы'}:
            bibliography=True
            continue
        if label.startswith('приложение '):
            bibliography=False
        if bibliography and block['kind']=='table':
            for row in block.get('rows',[]):
                if len(row['cells'])<2:continue
                description=' '.join(p.get('text','') for _,p in paragraphs(row['cells'][-1]['blocks']))
                if norm(description).startswith(('http://','https://')):
                    add_issue(issues,'bibliography-format-review','Описание источника начинается с URL. Проверьте состав и порядок библиографических сведений по §6.10 и разделу 9; недостающие данные не выдумываются.')
    start = body_start(model)
    automatic = auto_toc_text(body)
    toc = structure['toc']
    headings = set()
    counters = {}
    appendices = []
    ordinary = []
    for path, para in paragraphs(body):
        if path[0] < start or path[0] in toc or tuple(path) in automatic:
            continue
        text = para.get('text', '').strip()
        if not norm(text):
            continue
        props = effective_para(model, para)
        level = structure['levels'].get(path[0]) if len(path) == 1 else None
        if level:
            if level == 1 and abs((props.get('spaceAfter') or 0) - (heading_gap if heading_gap is not None else PROFILE['chapter_gap_pt'])) > .1:
                add_issue(issues, 'heading-spacing', f'Проверьте два интервала после заголовка (приложение Е): {text}', path=path)
            if level > 1:
                if abs((props.get('spaceAfter') or 0) - (heading_gap if heading_gap is not None else PROFILE['subheading_gap_pt'])) > .1:
                    add_issue(issues, 'subheading-spacing', f'Проверьте расстояние между заголовком и текстом по общему правилу приложения Е (два интервала): {text}', path=path)
                if props.get('pageBreakBefore'):
                    add_issue(issues, 'subheading-page-break', f'Перед подразделом задан принудительный переход на новую страницу; §7.2.10 требует его только для разделов: {text}', path=path)
            match = NUMBERED_HEADING.match(text)
            number = structure['numbers'].get(path[0])
            if number:
                if match and match[2]:
                    add_issue(issues, 'heading-number-dot', f'Точка после номера заголовка (§7.2.2): {text}', path=path)
                if number in headings:
                    add_issue(issues, 'heading-number', f'Повтор номера раздела: {".".join(map(str,number))}.', path=path)
                parent = number[:-1]
                previous = counters.get(parent, 0)
                if number[-1] != previous + 1:
                    add_issue(issues, 'heading-sequence', f'Проверьте последовательность разделов (§7.2): {text}', path=path)
                if parent and parent not in headings:
                    add_issue(issues, 'heading-parent', f'Не найден родительский раздел: {text}', path=path)
                counters[parent] = number[-1]
                headings.add(number)
            appendix = re.fullmatch(r'приложение\s+([а-яёa-z]|\d+)', norm(text))
            if appendix:
                appendices.append((path[0], appendix[1]))
        elif len(path) == 1 and not CAPTION.match(text) and not para.get('objects') and not para.get('fields'):
            ordinary.append((path[0], text))
            # Commands, formulas and native numbering need their own layout rules.
            if not props.get('numbering') and not re.search(r'[\n\t{}=;]|https?://|^(?:sudo |for |if |def |class )', text):
                expected = PROFILE['body_indent_mm' if mode == 'full' else 'compact_indent_mm'] * MM
                if abs((props.get('indentFirst') or 0) - expected) > .5:
                    add_issue(issues, 'paragraph-indent', f'Абзацный отступ отличается от {10 if mode == "full" else 12.5} мм (§7.1.4): {text[:100]}', path=path)
        for run, visible in visible_text_runs(para):
            color = effective_char(model, para, run).get('color')
            # Theme/automatic colors cannot be inferred safely from their token.
            if isinstance(color, dict) and 'Rgb' in color and color['Rgb'] != [0, 0, 0]:
                add_issue(issues, 'text-color', f'Цвет текста отличается от чёрного (§7.1.3): {visible[:100]}', path=path)
    if mode != 'full':
        return
    for index in structure['uncertain']:
        add_issue(issues, 'heading-ambiguous', f'Неясно, глава это или пункт списка; принудительный перенос не добавлен: {body[index]["text"][:100]}')
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
