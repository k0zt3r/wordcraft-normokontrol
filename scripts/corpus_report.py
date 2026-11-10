"""Produce a technical corpus summary without embedding private documents."""
from collections import Counter
import html
import json
from pathlib import Path
from urllib.parse import quote


def build_batch(root):
    """One entry point to the actual agent-generated results of any corpus."""
    root=Path(root).resolve()
    inventory=json.loads((root/'inventory.json').read_text(encoding='utf-8'))
    results=json.loads((root/'summary.json').read_text(encoding='utf-8'))
    supporting=json.loads((root/'supporting-results.json').read_text(encoding='utf-8'))
    rows=[]
    def link(path,label):
        target=Path(path).resolve().relative_to(root).as_posix()
        return f'<a href="{quote(target)}">{html.escape(label)}</a>'
    for item in inventory:
        runs=[r for r in results if r['sha256']==item['sha256']]
        cells=[]
        for scenario in ('check','format'):
            run=next((r for r in runs if r['scenario']==scenario),None)
            if not run:
                cells.append('<td>Не запускалось</td>')
            elif run['status']!='ok':
                cells.append('<td>Ошибка: '+html.escape(run.get('error',run['status']))+'</td>')
            else:
                files=run['artifacts']
                value=' · '.join(link(files[k],label) for k,label in
                                 [('report_html','Отчёт'),('docx','DOCX'),('pdf','PDF')])
                title=('; учебный титульник найден на первой странице' if run.get('institutional_title') else '; учебный титульник не подтверждён') if scenario=='format' else ''
                cells.append(f'<td>{value}<br>{run["pages"]} стр.; замечаний: {sum(run["issues"].values())}{title}</td>')
        rows.append('<tr><td>'+html.escape(item['path'])+'</td>'+''.join(cells)+'</tr>')
    extras=''.join('<li>'+html.escape(item['path'])+' — '+html.escape(item['status'])+
                   (f', {item["pages"]} стр.' if 'pages' in item else '')+'</li>' for item in supporting)
    text='''<!doctype html><html lang="ru"><meta charset="utf-8"><title>Пакетная проверка документов</title>
<style>body{font:16px/1.5 system-ui;max-width:1400px;margin:30px auto;padding:0 20px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd3dc;padding:12px;text-align:left;overflow-wrap:anywhere}a{color:#1257a4}</style>
<h1>Пакетная проверка штатным скриптом</h1>
<p>Все Word-документы обработаны через общий агентный API: отдельно проверка и отдельно оформление. Исходники и прежние результаты не изменены; контрольные суммы сверены. Техническое завершение не подтверждает отсутствие замечаний.</p>
<p>Недостающие реквизиты не выдумываются. Исходные вводные абзацы и собственные титулы служебных документов сохраняются после нового учебного титульника. В PDF и схемах выполнена проверка чтения; нормоконтроль этой программы принимает DOCX.</p>
<table><tr><th>Исходник</th><th>Проверить</th><th>Оформить</th></tr>'''
    (root/'index.html').write_text(text+''.join(rows)+'</table><h2>Дополнительные файлы</h2><ul>'+extras+'</ul></html>',encoding='utf-8')


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
