"""Normalize list definitions as well as paragraph-level indentation."""
import copy
import re


def normalize(model, para, heading, cache):
    from normokontrol import effective_para, MM, FONT
    effective = effective_para(model, para)
    ref = effective.get('numbering')
    if not ref:
        return False
    numbering = model.get('numbering', {})
    nums, abstracts = numbering.get('nums', []), numbering.get('abstracts', [])
    num = next((n for n in nums if n['id'] == ref.get('num')), None)
    abstract = next((a for a in abstracts if num and a['id'] == num['abstractId']), None)
    level_index = ref.get('level', 0)
    if not abstract or not 0 <= level_index < len(abstract.get('levels', [])):
        return False
    level = abstract['levels'][level_index]
    if level['format'] != 'bullet' and not heading:
        return False
    key = (num['id'], bool(heading))
    if key not in cache:
        cloned = copy.deepcopy(abstract)
        cloned['id'] = max((a['id'] for a in abstracts), default=0) + 1
        cloned_num = copy.deepcopy(num)
        cloned_num.update(id=max((n['id'] for n in nums), default=0) + 1, abstractId=cloned['id'])
        abstracts.append(cloned)
        nums.append(cloned_num)
        cache[key] = (cloned_num, cloned)
    cloned_num, cloned = cache[key]
    target = cloned['levels'][level_index]
    # Number starts at the paragraph indent; a space avoids wide tab stops.
    indent = 0.0 if heading and effective.get('align') == 'center' else 10 * MM
    target.update(indent=indent, hanging=0.0, suffix='space', align='left')
    target.pop('tab', None)
    target['chr'] = {'font': FONT, 'size': 14.0}
    if level['format'] == 'bullet':
        target['text'] = '-'
    elif heading and level['format'] == 'decimal':
        target['text'] = target.get('text', '').rstrip('.')
    props = para.setdefault('props', {})
    props.update(numbering={'num': cloned_num['id'], 'level': level_index},
                 indentLeft=0.0, indentRight=0.0, indentFirst=indent, tabs=[])
    if not heading:
        props['align'] = 'left'
    return True
