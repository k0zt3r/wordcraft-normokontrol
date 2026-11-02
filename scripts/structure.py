"""One structural index shared by formatting, contents and rule checks."""
import re


def cover_end(model):
    """Use the city/year as a boundary, not the first heading several sheets later."""
    from normokontrol import norm, paragraphs, SPECIAL
    body=model['body']
    city=re.compile(r'^[а-яёa-z][а-яёa-z .-]*?,?\s+(?:19|20)\d{2}(?:\s*г\.?)?$')
    for i,block in enumerate(body[:100]):
        if block['kind']=='para' and norm(block.get('text','')) in SPECIAL:
            return None
        if any(city.fullmatch(norm(p.get('text',''))) for _,p in paragraphs([block])):
            end=i+1
            while end<len(body) and body[end]['kind']=='para' and not norm(body[end].get('text','')):
                if any(o.get('type') not in {'bookmarkStart','bookmarkEnd'} for o in body[end].get('objects',[])):
                    break
                end+=1
            return end
    return None


def analyze(model):
    from normokontrol import norm, heading_level, effective_para, NUMBERED_HEADING, detect_tocs, paragraphs, manual_toc_indices, SPECIAL
    body = model['body']
    styles = model.get('styles', {})
    numbering = model.get('numbering', {})
    toc = set(detect_tocs(body))
    toc.update(manual_toc_indices(body))
    toc_names = {norm(p.get('text', '')) for i in toc for _, p in paragraphs([body[i]])}
    levels, numbers, uncertain = {}, {}, []
    native_counts = {}
    child_chapters = {}
    for i,p in enumerate(body):
        match = NUMBERED_HEADING.match(norm(p.get('text',''))) if p['kind']=='para' else None
        if match and '.' in match[1]:
            child_chapters[int(match[1].split('.')[0])] = i
    for i, p in enumerate(body):
        if p['kind'] != 'para' or i in toc or not norm(p.get('text', '')):
            continue
        text = norm(p.get('text', ''))
        level = heading_level(p, styles, numbering)
        props = effective_para(model, p)
        manual = NUMBERED_HEADING.match(text)
        chapter = re.match(r'^глава\s+(\d+)(?:[.\s:–—-]|$)', text)
        if manual and '.' not in manual[1] and (props.get('outlineLevel') is None or props['outlineLevel'] >= 9):
            number = int(manual[1])
            child = child_chapters.get(number,-1) > i
            if not child and text not in toc_names:
                level = None
                if not manual[2]:
                    uncertain.append(i)
        if level is None:
            continue
        levels[i] = level
        if text in SPECIAL:
            continue
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
    return {'levels': levels, 'numbers': numbers, 'uncertain': uncertain, 'toc': toc}
