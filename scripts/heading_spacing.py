"""Calibrate two line intervals against the installed Wordcraft renderer."""
import json


def measure(wc, folder):
    from format_profile import PROFILE
    from normokontrol import byte_len, font
    import pymupdf
    wc.call('new_document', template='blank')
    source=folder/'spacing-probe.json'
    rendered=folder/'spacing-probe.pdf'
    seed=folder/'spacing-blank.json'
    wc.save(seed)
    model=json.loads(seed.read_text(encoding='utf-8'))
    model['body']=[]
    for text in ('Spacing probe A','Spacing probe B','Spacing probe C'):
        para={'kind':'para','text':text,'runs':[{'len':byte_len(text),'props':{}}],
              'props':{'spaceBefore':0,'spaceAfter':0,
                       'lineSpacing':{'rule':'multiple','value':PROFILE['line_spacing']}}}
        font(para,PROFILE['text_size'])
        model['body'].append(para)
    source.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
    wc.open(source)
    wc.save(rendered)
    with pymupdf.open(rendered) as pdf:
        points={s['text']:s['origin'][1] for b in pdf[0].get_text('dict')['blocks'] if 'lines' in b
                for line in b['lines'] for s in line['spans']}
    steps=[points['Spacing probe B']-points['Spacing probe A'],
           points['Spacing probe C']-points['Spacing probe B']]
    if min(steps)<=0 or abs(steps[0]-steps[1])>.1:
        raise ValueError('Не удалось измерить шаг строк Wordcraft для расстояния после заголовков.')
    return round(sum(steps)/len(steps),4)
