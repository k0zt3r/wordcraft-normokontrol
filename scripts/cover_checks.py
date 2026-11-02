"""Check cover details and position the city/year using actual pagination."""
import json
import re

CITY_YEAR = re.compile(r'^[А-ЯЁA-Z][А-Яа-яЁёA-Za-z .-]*?[,]?\s+(?:19|20)\d{2}(?:\s*г\.?)?$')


def verify_requested(model, metadata, issues):
    from normokontrol import body_start,paragraphs,norm,add_issue
    text=' '.join(norm(p.get('text','')) for _,p in paragraphs(model['body'][:body_start(model)]))
    labels={'author':'студент','group':'группа','supervisor':'руководитель','supervisor_title':'должность',
            'title':'тема','discipline':'дисциплина','city':'город','year':'год','code':'шифр'}
    for key,label in labels.items():
        if metadata.get(key) and norm(str(metadata[key])) not in text:
            add_issue(issues,'metadata-unapplied',f'Не удалось однозначно заменить реквизит «{label}» в существующем титульнике. Проверьте его вручную; данные в штампе не подтверждают замену на титуле.')


def fill_known_fields(model,metadata,changes):
    """Handle labelled signatures across arbitrary table grids, not fixed cell offsets."""
    from normokontrol import body_start,paragraphs,norm
    from text_edits import replace
    role=None
    updated=0
    for _,p in paragraphs(model['body'][:body_start(model)]):
        text=p.get('text','')
        clean=norm(text)
        if re.match(r'^(?:выполнил|выполнила|исполнитель|студент|обучающийся)',clean):
            role='author'
        elif re.match(r'^(?:проверил|проверила|руководитель)',clean):
            role='supervisor'
        elif re.match(r'^(?:консультант|нормоконтрол|к защите)',clean):
            role=None
        if metadata.get('group'):
            group=re.search(r'\b[А-ЯA-Z]{1,8}\.\d+-\d{2}-\d+\b',text)
            if group and text[group.start():group.end()]!=metadata['group']:
                updated+=bool(replace(p,group.start(),group.end(),metadata['group']))
                text=p['text']
        if role and metadata.get(role):
            matches=list(re.finditer(r'\b[А-ЯЁ][а-яё-]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.',text))
            if len(matches)==1 and matches[0][0]!=metadata[role]:
                match=matches[0]
                updated+=bool(replace(p,match.start(),match.end(),metadata[role]))
    if updated:
        changes.append(f'Реквизиты подписей уточнены по явным меткам в титульнике: {updated}.')


def inspect(model, issues):
    from normokontrol import body_start, paragraphs, norm, add_issue
    from irgups_data import WORK_TYPES
    start=body_start(model)
    cover=list(paragraphs(model['body'][:start]))
    titles={norm(t) for t in WORK_TYPES.values()}
    kinds=[p for _,p in cover if norm(p.get('text','')) in titles]
    if not kinds:
        add_issue(issues,'cover-work-type','На титульном листе не распознан вид работы; проверьте реквизит по §6.2.')
    for p in kinds:
        first=next((c for c in p.get('text','') if c.isalpha()),'')
        if first and first.islower():
            add_issue(issues,'cover-capital','Вид работы на титульном листе должен начинаться с заглавной буквы.')
    if any(norm(p.get('text',''))=='курсовая работа' for p in kinds) and not any('дисциплин' in norm(p.get('text','')) for _,p in cover):
        add_issue(issues,'cover-discipline-review','На титульнике курсовой не распознана дисциплина. Сверьте с заданием; буквальная фраза «по дисциплине» в §6.2 не установлена.')
    if not any(CITY_YEAR.fullmatch(p.get('text','').replace('\ufffc','').strip()) for _,p in cover):
        add_issue(issues,'cover-city-year','На титульном листе не распознаны город и год. Укажите их, не подставляя вымышленные данные.')


def format_cover(model, changes):
    from normokontrol import body_start, paragraphs, norm, font, MM
    from text_edits import replace
    from format_profile import PROFILE
    from irgups_data import WORK_TYPES
    start=body_start(model)
    kinds={norm(t) for t in WORK_TYPES.values()}
    for path,p in paragraphs(model['body'][:start]):
        # Imported title spacers can contain page breaks and bookmark anchors.
        # There is one cover section boundary; internal title page breaks duplicate it.
        for match in reversed(list(re.finditer('\f',p.get('text','')))):
            replace(p,match.start(),match.end(),'')
        p.setdefault('props',{}).update(pageBreakBefore=False,keepNext=False)
        text=norm(p.get('text',''))
        if not text:
            if not p.get('fields'):
                p.setdefault('props',{}).update(spaceBefore=0.0,spaceAfter=0.0,keepNext=False,
                                              lineSpacing={'rule':'exactly','value':1.0})
                p.setdefault('mark',{})['size']=1.0
            continue
        font(p,PROFILE['text_size'])
        props=p.setdefault('props',{})
        props.update(spaceBefore=0.0,spaceAfter=0.0,spaceBeforeAuto=False,spaceAfterAuto=False,
                     lineSpacing={'rule':'multiple','value':1.0})
        if len(path)==1:
            props.update(indentFirst=0.0,indentLeft=0.0,indentRight=0.0)
            if 'к защите допускаю' not in text:
                props['align']='center'
        if text.startswith('кафедра'):
            props['spaceAfter']=PROFILE['cover_department_gap_pt']
        if text.startswith('факультет'):
            props['spaceBefore']=12.0
        if text in kinds:
            props.update(spaceBefore=24.0,spaceAfter=12.0)
            raw=p['text']
            index=next((i for i,c in enumerate(raw) if c.isalpha()),None)
            if index is not None and raw[index].islower():
                p['text']=raw[:index]+raw[index].upper()+raw[index+1:]
        if text.startswith('по дисциплине'):
            props['spaceAfter']=12.0
        if re.match(r'^(?:кр|кп|др|дп|лр|уп|пп|оп|ргр)\.\d',text):
            props.update(spaceBefore=12.0,spaceAfter=24.0)
        if len(path)>1:
            props['lineSpacing']={'rule':'multiple','value':1.15}
        for r in p.get('runs',[]):
            r.setdefault('props',{}).update(italic=False,italicCs=False)
        p.setdefault('mark',{}).update(italic=False,italicCs=False)
    if start and model['body'][start-1].get('section'):
        model['body'][start-1]['section']['marginBottom']=PROFILE['cover_bottom_mm']*MM
    for i,block in enumerate(model['body'][:start]):
        if i!=start-1:
            block.pop('section',None)
        if block['kind']=='table':
            block.setdefault('props',{})['float']=None
            for row in block.get('rows',[]):
                row.setdefault('props',{}).pop('height',None)
                row['props'].pop('heightRule',None)
    changes.append('Оформлен существующий титульник: устранены избыточные интервалы, вид работы начинается с заглавной буквы; реквизиты сохранены.')


def position(wc, model, temporary, changes, issues, do_fix=True):
    from normokontrol import body_start, norm, MM, add_issue
    from format_profile import PROFILE
    start=body_start(model)
    candidates=[i for i,p in enumerate(model['body'][:start]) if p['kind']=='para' and
                CITY_YEAR.fullmatch(p.get('text','').replace('\ufffc','').strip())]
    if len(candidates)!=1:
        return
    index=candidates[0]
    pos=wc.locate([index])
    section=model['body'][start-1].get('section',model['lastSection'])
    target=section.get('pageH',297*MM)-PROFILE['cover_bottom_mm']*MM-1.5*PROFILE['text_size']
    if do_fix:
        # Imported covers may anchor an overlay to this paragraph. Keep its page
        # position when moving the city, rather than dragging it off the sheet.
        anchored=False
        for obj in model['body'][index].get('objects',[]):
            floating=obj.get('float') or {}
            if floating.get('vRel')=='paragraph' and floating.get('wrap')=='inFrontOfText':
                floating.update(vRel='page',y=pos['y']+floating.get('y',0))
                anchored=True
        if anchored:
            path=temporary/'cover-anchor.json'
            path.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            wc.open(path)
            pos=wc.locate([index])
        for attempt in range(4):
            if pos['page']!=1 or abs(pos['y']-target)<=2:
                break
            props=model['body'][index].setdefault('props',{})
            before=props.get('spaceBefore',0)
            props['spaceBefore']=max(0.0,before+target-pos['y'])
            # Wordcraft caches documents by path: each revision needs a new path.
            path=temporary/f'cover-position-{attempt}.json'
            path.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            wc.open(path)
            pos=wc.locate([index])
            if pos['page']!=1:
                props['spaceBefore']=before
                path=temporary/f'cover-rollback-{attempt}.json'
                path.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
                wc.open(path)
                pos=wc.locate([index])
                break
        if pos['page']==1 and abs(pos['y']-target)<=2:
            changes.append('Город и год размещены внизу титульного листа по фактической вёрстке.')
    if pos['page']!=1 or abs(pos['y']-target)>20:
        add_issue(issues,'cover-city-position','Город и год должны располагаться внизу единственного титульного листа по образцам приложения Б; проверьте вёрстку.',pos['page'])
