"""Check list grammar conservatively and normalize unambiguous list markers."""
import re

MARKER = re.compile(r'^\s*(?:[-–—]\s+|\d+[.)]\s+|[а-яё]\)\s+)', re.I)
COMMON_STARTS=set('шифрование контроль обучение резервное регулярное регулярно установка установить проведение провести разработка разработать использование использовать обеспечение обеспечить ограничение ограничить организация организовать проверка проверить рассмотреть изучить оценить определить выявить анализ анализировать рассмотрение изучение оценка определение отсутствие недостаточное недостаточные преднамеренные непреднамеренные мониторинг многофакторная сотрудничать выбрать выбор повышение повышать признание вовлечение мотивационные бонусы карьерные'.split())


def initial_abbreviation(text):
    token=re.match(r'[A-Za-zА-ЯЁа-яё][A-Za-zА-ЯЁа-яё0-9_-]*',text)
    if not token:
        return False
    word=token[0]
    return sum(c.isalpha() for c in word)>=2 and word.isupper() and word.lower() not in COMMON_STARTS


def process(model, changes, issues, check_only=False):
    from text_edits import replace
    from normokontrol import body_start, effective_para, effective_char, visible_text_runs, norm, add_issue
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
        first=cluster[0][0]
        previous=next((b for b in reversed(body[start:first]) if norm(b.get('text',''))),None)
        introduced=bool(previous and previous['kind']=='para' and norm(previous.get('text','')).endswith(':'))
        for k,(i,depth,content) in enumerate(cluster):
            p=body[i]
            if content and content[0].isupper() and not initial_abbreviation(content):
                word=re.match(r'[А-ЯЁа-яё]+',content)
                if introduced and word and word[0].lower() in COMMON_STARTS and not word[0].isupper() and not check_only:
                    raw=p['text']
                    offset=raw.find(word[0])
                    if offset>=0 and replace(p,offset,offset+1,word[0][0].lower()):
                        changes.append('Пункт перечисления после двоеточия начат со строчной буквы.')
                else:
                    add_issue(issues,'list-case-review',f'Проверьте строчную букву в перечислении; имена собственные и аббревиатуры сохраняются: {content[:100]}')
            if len(cluster)<2 and not introduced:
                continue
            following=next((item for item in cluster[k+1:] if item[1]<=depth),None)
            ending=';' if following else '.'
            text=p.get('text','')
            if content.rstrip().endswith(':'):
                continue  # Parent item introducing nested children.
            complex_objects=any(o.get('type') not in {'bookmarkStart','bookmarkEnd'} for o in p.get('objects',[]))
            if not content or (re.search(r'[.!?]\s+\S',content) and not introduced) or complex_objects or p.get('fields'):
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
