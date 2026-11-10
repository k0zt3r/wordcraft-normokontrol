"""One structural index shared by formatting, contents and rule checks."""
import re


def question_indices(model, structure=None):
    """Numbered questions are not syntactic enumerations under §7.2.7.

    Question marks are explicit evidence. Imperative prompts additionally
    need a question-section heading and a following unnumbered answer.
    """
    from normokontrol import norm, effective_para
    structure = structure if structure is not None else analyze(model)
    levels, body = structure['levels'], model['body']
    section, result = None, set()
    section_name = re.compile(r'^(?:ответы на )?(?:(?:контрольные|проверочные) )?вопросы(?: для (?:самопроверки|самоконтроля))?$')
    marker = re.compile(r'^\s*\d+[.)]\s+')
    numbering = model.get('numbering', {})
    nums = {n['id']: n for n in numbering.get('nums', [])}
    abstracts = {a['id']: a for a in numbering.get('abstracts', [])}

    def numbered(para):
        if marker.match(para.get('text', '')):
            return True
        ref = effective_para(model, para).get('numbering') or {}
        abstract = abstracts.get(nums.get(ref.get('num'), {}).get('abstractId'), {})
        definitions = abstract.get('levels', [])
        return ref.get('level', 0) == 0 and bool(definitions) and definitions[0].get('format') == 'decimal'

    for i, para in enumerate(body):
        if para.get('kind') != 'para':
            continue
        text = norm(para.get('text', ''))
        name = re.sub(r'^\d+(?:\.\d+)*[.)]?\s+', '', text)
        if section_name.fullmatch(name):
            section = levels.get(i, 1)
            continue
        if numbered(para) and '?' in text:
            result.add(i)
            continue
        if i in levels and section is not None and levels[i] <= section:
            section = None
        if section is not None and numbered(para):
            following = next(((j, b) for j, b in enumerate(body[i+1:], i+1)
                              if b.get('kind') != 'para' or norm(b.get('text', ''))), None)
            if following:
                j, answer = following
                if answer.get('kind') == 'para' and j not in levels and not numbered(answer):
                    result.add(i)
    return result


def cover_end(model):
    """Use the city/year as a boundary, not the first heading several sheets later."""
    from normokontrol import norm, paragraphs, SPECIAL
    body=model['body']
    city=re.compile(r'^[а-яёa-z][а-яёa-z .-]*?,?\s+(?:19|20)\d{2}(?:\s*г\.?)?$')
    institutional = False
    for i,block in enumerate(body[:100]):
        texts=[norm(p.get('text','')) for _,p in paragraphs([block])]
        institutional = institutional or any('университет' in text or 'фгбоу' in text for text in texts)
        if institutional and block.get('section'):
            return i+1  # Explicit title boundary works even when city/year are blank.
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
        if (manual and '.' in manual[1] and
                (props.get('outlineLevel') is None or props['outlineLevel'] >= 9)):
            content = text[manual.end(1):].lstrip('. ')
            prose = (len(content) > 140 or re.search(r'[;!?]|[.!?]\s+\S', content)
                     or (content.endswith('.') and len(content.split()) > 10))
            if prose:
                # §7.2.9 permits numbered clauses without headings. Do not
                # promote contractual prose to a chapter solely from its number.
                uncertain.append(i)
                continue
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
