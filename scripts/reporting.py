"""Group repeated findings while retaining every message and page."""
from collections import defaultdict
import html
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent.parent


def references_for(message):
    """Attach only stated citations and known operations, not guessed normative claims."""
    refs=re.findall(r'§\s*(\d+(?:\.\d+)+)',message)
    low=message.lower()
    if 'интервал' in low and 'заголов' in low:
        refs+=['7.1.3','Приложение Е']
    if 'содержани' in low:
        refs+=['6.4']
    if 'учебный шифр' in low:
        refs+=['6.2']
    if 'шрифт и интервалы текста' in low:
        refs+=['7.1.3','7.1.4','7.2.9','7.6.7','Приложение Е']
    if 'рамк' in low and ('штамп' in low or 'основн' in low):
        refs+=['7.1.2','Приложение И']
    if 'приложени' in low:
        refs+=['Приложение '+m.upper() for m in re.findall(r'приложени[еяю]\s+([А-Я])',message,re.I) if m.upper() in 'БГДЕИК']
    return list(dict.fromkeys(refs))


def change_details(changes):
    result=[]
    for i,text in enumerate(changes,1):
        refs=references_for(text)
        result.append({'number':i,'text':text,'references':refs,
                       'basis':'Применение указанного пункта; технические величины не являются цитатой нормы.' if refs else 'Техническое изменение; прямой пункт положения не установлен.'})
    return result


def anchor(ref):
    return 'norm-'+ref.replace('.','-').replace(' ','-')


def reference_links(refs):
    return ' · '.join(f'<a href="#{html.escape(anchor(ref),quote=True)}">{html.escape(ref if ref.startswith("Приложение") else "§"+ref)}</a>' for ref in refs)


def render_changes(changes):
    rows=[]
    for item in change_details(changes):
        links=reference_links(item['references'])
        note=links or 'Техническое изменение; прямой пункт положения не установлен.'
        rows.append(f'<li id="change-{item["number"]}">{html.escape(item["text"])}<br><small>{note}</small></li>')
    return '<ol>'+''.join(rows)+'</ol>' if rows else '<p>Оформление не изменялось.</p>'


def render_sources(messages):
    refs=list(dict.fromkeys(ref for message in messages for ref in references_for(message)))
    if not refs:
        return ''
    clauses={}
    for clause in json.loads((ROOT/'references/norm-source/clauses.json').read_text(encoding='utf-8')):
        if clause['page']>5:
            clauses.setdefault(clause['clause'],clause)
    # Reports need page text, not the much larger font/geometry extraction.
    full_text=(ROOT/'references/norm-source/full-text.md').read_text(encoding='utf-8')
    headings=list(re.finditer(r'(?m)^## Страница PDF (\d+)$',full_text))
    pages={int(match[1]):full_text[match.end():headings[i+1].start() if i+1<len(headings) else len(full_text)].strip()
           for i,match in enumerate(headings)}
    appendix_pages={'Б':33,'Г':36,'Д':37,'Е':39,'И':44,'К':46}
    result=[]
    for ref in refs:
        if ref.startswith('Приложение '):
            number=appendix_pages.get(ref[-1])
            text=pages.get(number)
        else:
            clause=clauses.get(ref)
            number=clause['page'] if clause else None
            text=clause['text'] if clause else None
        if text:
            link=(ROOT/'Normokontrol.pdf').as_uri()+f'#page={number}'
            result.append(f'<article id="{html.escape(anchor(ref),quote=True)}"><h3>{html.escape(ref)}</h3><p><a href="{html.escape(link,quote=True)}">Оригинал PDF, страница {number}</a></p><pre>{html.escape(text)}</pre><p><a href="#changes">К изменениям</a></p></article>')
        else:
            result.append(f'<article id="{html.escape(anchor(ref),quote=True)}"><h3>{html.escape(ref)}</h3><p>Сверьте полный текст положения: отдельный фрагмент не найден в индексе.</p></article>')
    return '<h2>Пункты положения</h2>'+''.join(result) if result else ''

ERRORS = {'structure','stamp-code','frame-missing','table-layout','figure-layout','toc-convergence'}
REVIEW = {'bibliography-review','caption-review','caption-placeholder','heading-ambiguous','toc-auto-review','media',
          'list-case-review','list-italic-review','list-punctuation-review','list-structure-review','cover-discipline-review',
          'heading-reference-review','bibliography-format-review','legacy-overlay-review','cover-approval','toc-manual-review'}


def severity(code):
    return 'error' if code in ERRORS else 'review' if code in REVIEW else 'warning'


def render(issues):
    if not issues:
        return '<p>В выполненных автоматических проверках замечаний не найдено.</p>'
    groups=defaultdict(list)
    for issue in issues:
        groups[(issue.get('severity',severity(issue['code'])),issue['code'])].append(issue)
    result=['<ol>']
    for kind,label in [('error','Ошибки'),('warning','Предупреждения'),('review','Ручная проверка')]:
        selected=[(code,items) for (level,code),items in groups.items() if level==kind]
        if not selected:
            continue
        for code,items in selected:
            title=html.escape(items[0]['message'])
            rows=''.join('<li>'+html.escape(i['message'])+(f' (стр. {int(i["page"])})' if i.get('page') else '')+' '+reference_links(references_for(i['message']))+'</li>' for i in items)
            result.append(f'<li><details><summary>{label}: {title} <strong>({len(items)})</strong></summary><ul>{rows}</ul></details></li>')
    return ''.join(result)+'</ol>'
