"""Check list grammar conservatively and normalize unambiguous list markers."""
import re

MARKER = re.compile(r'^\s*(?:[-–—]\s+|\d+[.)]\s+|[а-яё]\)\s+)', re.I)


def process(model, changes, issues, check_only=False):
    from text_edits import replace
    from normokontrol import body_start, effective_para, effective_char, visible_text_runs, norm, add_issue, byte_len
    from structure import analyze
    structure=analyze(model)
    body=model['body']
    start=body_start(model)
    numbering=model.get('numbering',{})
    clusters=[]
    current=[]
    def finish():
        nonlocal current
        if current:
            clusters.append(current)
            current=[]
    for i,p in enumerate(body):
        if i<start:
            continue
        text=norm(p.get('text',''))
        if text in {'список литературы','список использованных источников','библиографический список'} or text.startswith('приложение '):
            break
        if p['kind']!='para' or i in structure['levels']:
            finish()
            continue
        props=effective_para(model,p)
        ref=props.get('numbering') or {}
        num=next((n for n in numbering.get('nums',[]) if n['id']==ref.get('num')),None)
        abstract=next((a for a in numbering.get('abstracts',[]) if num and a['id']==num['abstractId']),None)
        level=ref.get('level',0)
        native=abstract['levels'][level] if abstract and 0<=level<len(abstract.get('levels',[])) else None
        raw=p.get('text','')
        manual=MARKER.match(raw)
        is_list=(native and native.get('format') in {'bullet','decimal','lowerLetter','upperLetter'}) or manual
        if not is_list:
            finish()
            continue
        if check_only and native and native.get('format')=='decimal' and not native.get('text','').endswith(')'):
            add_issue(issues,'list-marker','Автоматическое цифровое перечисление следует оформлять номером со скобкой (§7.2.7).')
        visible=raw.replace('\ufffc','').strip()
        content=MARKER.sub('',visible,count=1) if manual else visible
        if content and content[0].isupper():
            add_issue(issues,'list-case-review',f'Проверьте строчную букву в перечислении (приложение Д); имена собственные и аббревиатуры сохраняются: {visible[:100]}')
        runs=list(visible_text_runs(p))
        if runs and all(effective_char(model,p,r).get('italic') for r,_ in runs):
            add_issue(issues,'list-italic-review',f'Весь пункт выделен курсивом: проверьте обоснованность по §7.1.3 и приложению Д: {visible[:100]}')
        if manual and re.match(r'^\s*\d+\.\s+',raw):
            if check_only:
                add_issue(issues,'list-marker','Цифровое перечисление следует оформлять со скобкой: '+visible[:100])
            elif not p.get('objects') and not p.get('fields'):
                point=re.match(r'^(\s*\d+)\.',raw).end()-1
                if replace(p,point,point+1,')'):
                    changes.append('Цифровой маркер перечисления заменён на номер со скобкой.')
        current.append((i,level,content))
    finish()
    for cluster in clusters:
        if len(cluster)<2:
            continue  # Isolated labels followed by prose need human interpretation.
        for k,(i,depth,content) in enumerate(cluster):
            p=body[i]
            following=next((item for item in cluster[k+1:] if item[1]<=depth),None)
            ending=';' if following else '.'
            text=p.get('text','')
            if content.rstrip().endswith(':'):
                continue  # Parent item introducing nested children.
            complex_objects=any(o.get('type') not in {'bookmarkStart','bookmarkEnd'} for o in p.get('objects',[]))
            if not content or re.search(r'[.!?]\s+\S',content) or complex_objects or p.get('fields'):
                add_issue(issues,'list-punctuation-review',f'Проверьте окончание пункта перечисления; ожидается «{ending}» с учётом вложенности: {content[:100]}')
                continue
            end=len(text)
            while end and (text[end-1].isspace() or text[end-1]=='\ufffc'):
                end-=1
            if not end:
                continue
            if text[end-1]==ending:
                continue
            if check_only:
                add_issue(issues,'list-punctuation',f'Пункт перечисления должен завершаться «{ending}»: {content[:100]}')
                continue
            begin=end-1 if text[end-1] in ';.' else end
            if replace(p,begin,end,ending):
                changes.append('Исправлено окончание пункта перечисления по приложению Д.')
