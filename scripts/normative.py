"""Text/structure corrections derived from the bundled regulation, not preferences."""
import re


def code(value):
    match=re.fullmatch(r'(КР|КП|УП|ПП|ОП|ЛР|РГР|К|Р)\.(\d{6})\.(\d{2}\.\d{2}\.\d{2})(?:\.\d+)?(?:-\d{4})?\.(ПЗ|СБ|ВО|ГЧ|МЭ|МЧ|ТУ)',value)
    return '.'.join(match.groups()) if match else value


def prepare(model,changes,issues):
    from normokontrol import norm,paragraphs,body_start,REG_NUMBER_RE,add_issue,NUMBERED_HEADING,UNNUMBERED_CHAPTERS
    from structure import analyze
    from text_edits import replace
    structure=analyze(model)
    chapter=None
    for i,p in enumerate(model['body']):
        if p['kind']!='para':continue
        raw=p.get('text','')
        text=norm(raw)
        level=structure['levels'].get(i)
        if level and i>=body_start(model) and i not in structure['toc']:
            explicit=re.match(r'^глава\s+(\d+)[.]?\s+',text)
            manual=NUMBERED_HEADING.match(text)
            number=structure['numbers'].get(i)
            if level==1 and text in UNNUMBERED_CHAPTERS:
                number=((chapter or 0)+1,)
            if level==1 and number:
                chapter=number[0]
            if number and level>1 and chapter is not None:
                number=(chapter,)+number[1:]
            if number and not p.get('fields') and all(o.get('type') in {'bookmarkStart','bookmarkEnd'} for o in p.get('objects',[])):
                start=next((j for j,c in enumerate(raw) if c!='\ufffc' and not c.isspace()),0)
                end=start
                prefix=re.match(r'(?:Глава\s+)?\d+(?:\.\d+)*\.?\s+',raw[start:],re.I) if explicit or manual else None
                if prefix:end=start+prefix.end()
                label='.'.join(map(str,number))+' '
                if replace(p,start,end,label):
                    p.setdefault('props',{})['numbering']={'num':0,'level':0}
                    if number!=structure['numbers'].get(i):
                        add_issue(issues,'heading-reference-review','Исправлена принадлежность подраздела главе. Проверьте ссылки на старые номера; неоднозначные ссылки автоматически не заменяются.')
        if text=='список литературы':
            start=raw.lower().find('список литературы')
            if start>=0:replace(p,start,start+len('список литературы'),'Список использованных источников')
    for _,p in paragraphs(model['body'][:body_start(model)]):
        for match in reversed(list(REG_NUMBER_RE.finditer(p.get('text','')))):
            corrected=code(match[0])
            if corrected!=match[0] and replace(p,match.start(),match.end(),corrected):
                changes.append('Учебный шифр приведён к формуле §6.2 без учётного номера ВКР.')
