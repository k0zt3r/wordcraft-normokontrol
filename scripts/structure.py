"""One structural index shared by formatting, contents and rule checks."""
import re


def analyze(model):
    from normokontrol import norm, heading_level, effective_para, NUMBERED_HEADING, detect_tocs, paragraphs
    body = model['body']
    styles = model.get('styles', {})
    numbering = model.get('numbering', {})
    toc = set(detect_tocs(body))
    toc_names = {norm(p.get('text', '')) for i in toc for _, p in paragraphs([body[i]])}
    levels, numbers, uncertain = {}, {}, []
    native_counts = {}
    known_chapters = set()
    for i, p in enumerate(body):
        if p['kind'] != 'para' or i in toc or not norm(p.get('text', '')):
            continue
        text = norm(p.get('text', ''))
        level = heading_level(p, styles, numbering)
        props = effective_para(model, p)
        manual = NUMBERED_HEADING.match(text)
        chapter = re.match(r'^глава\s+(\d+)(?:[.\s:–—-]|$)', text)
        if manual and '.' not in manual[1] and props.get('outlineLevel', 9) >= 9:
            number = int(manual[1])
            child = any(b['kind'] == 'para' and re.match(r'^' + str(number) + r'\.\d', norm(b.get('text', '')))
                        for b in body[i+1:])
            if not child and text not in toc_names and number - 1 not in known_chapters:
                level = None
                if not manual[2]:
                    uncertain.append(i)
        if level is None:
            continue
        levels[i] = level
        if chapter:
            number = (int(chapter[1]),)
        elif manual:
            number = tuple(map(int, manual[1].split('.')))
        else:
            ref = props.get('numbering') or {}
            num = next((n for n in numbering.get('nums', []) if n['id'] == ref.get('num')), None)
            abstract = next((a for a in numbering.get('abstracts', []) if num and a['id'] == num['abstractId']), None)
            index = ref.get('level', 0)
            if not abstract or index >= len(abstract.get('levels', [])):
                continue
            definition = abstract['levels'][index]
            if definition.get('format') != 'decimal':
                continue
            counts = native_counts.setdefault(num['id'], {})
            counts[index] = counts.get(index, definition.get('start', 1) - 1) + 1
            for deeper in list(counts):
                if deeper > index:
                    del counts[deeper]
            tokens = re.findall(r'%([1-9])', definition.get('text', ''))
            number = tuple(counts.get(int(t)-1, abstract['levels'][int(t)-1].get('start',1)) for t in tokens)
        if number:
            numbers[i] = number
            if len(number) == 1:
                known_chapters.add(number[0])
    return {'levels': levels, 'numbers': numbers, 'uncertain': uncertain, 'toc': toc}
