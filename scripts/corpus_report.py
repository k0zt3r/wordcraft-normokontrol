"""Produce a technical corpus summary without embedding private documents."""
from collections import Counter
import html
import json
from pathlib import Path


def build(root):
    root=Path(root)
    inventory=json.loads((root/'corpus-final/inventory.json').read_text(encoding='utf-8'))
    final=json.loads((root/'corpus-final/summary.json').read_text(encoding='utf-8'))
    baseline=json.loads((root/'corpus-baseline-1.2.2/summary.json').read_text(encoding='utf-8'))
    stress=json.loads((root/'corpus-stress-final/summary.json').read_text(encoding='utf-8'))
    counts=Counter((r['scenario'],r['status']) for r in final)
    warnings=Counter()
    for r in final:
        if r['scenario']=='format':
            warnings.update(r.get('issues',{}))
    remaining=[r['files'] for r in final if r.get('unapplied_fields')]
    summary={'files':len(inventory),'unique':len({x['sha256'] for x in inventory}),
        'runs':len(final),'final':{a+':'+b:c for (a,b),c in counts.items()},
        'baseline':dict(Counter(r['status'] for r in baseline if r['scenario']=='format')),
        'metadata_with_unapplied':remaining,'format_warning_counts':warnings,'stress':stress,
        'remaining_work':['Нужен согласованный режим перестройки произвольного титульника: частичная замена реквизитов пока не универсальна.',
            'Белые перекрытия и сложные плавающие объекты сохраняются; требуется предварительный просмотр перед их удалением.',
            'Старый DOC необходимо конвертировать в DOCX.',
            'Для очень больших рисунков нужна ручная компоновка; имеющиеся номера и ссылки автоматически не перенумеровываются.',
            'Успешный запуск не подтверждает визуальную идентичность Wordcraft и Microsoft Word.']}
    out=root/'corpus-report';out.mkdir(exist_ok=True)
    (out/'technical.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[]
    for item in inventory:
        runs=[r for r in final if r['sha256']==item['sha256']]
        cells=[]
        for scenario in ('check','format','metadata'):
            r=next(r for r in runs if r['scenario']==scenario)
            value=r['status']
            if r.get('error'):value+=': '+r['error']
            if r.get('unapplied_fields'):value+=f"; не заменено полей: {len(r['unapplied_fields'])}"
            cells.append('<td>'+html.escape(value)+'</td>')
        rows.append('<tr><td>'+html.escape(item['path'])+'</td>'+''.join(cells)+'</tr>')
    text='''<!doctype html><meta charset="utf-8"><title>Отладка корпуса</title>
<style>body{font:16px/1.5 system-ui;margin:30px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:8px;text-align:left}pre{white-space:pre-wrap}</style>
<h1>Технический прогон Word-корпуса</h1><p>Это результаты отладки скрипта, не заключение о соответствии работ нормоконтролю. Копии с одинаковым SHA-256 проверялись одним набором прогонов.</p>'''
    text+=f'<p>Файлов: {len(inventory)}. Уникальных: {summary["unique"]}. Итоговых запусков: {len(final)}.</p>'
    text+='<h2>Что остаётся исправить</h2><ul>'+''.join('<li>'+html.escape(s)+'</li>' for s in summary['remaining_work'])+'</ul>'
    text+='<h2>Все файлы</h2><table><tr><th>Файл</th><th>Проверка</th><th>Оформление</th><th>Замена реквизитов</th></tr>'+''.join(rows)+'</table>'
    text+='<h2>Стресс-сценарии и агрегаты</h2><pre>'+html.escape(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>'
    (out/'index.html').write_text(text,encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ('files','unique','runs','final','baseline')},ensure_ascii=False))
    print('METADATA NOT UNIVERSAL',len(remaining))


if __name__=='__main__':
    import sys
    build(sys.argv[1])
