"""Group repeated findings while retaining every message and page."""
from collections import defaultdict
import html

ERRORS = {'structure','stamp-code','frame-missing','table-layout','figure-layout','toc-convergence'}
REVIEW = {'bibliography-review','caption-review','caption-placeholder','heading-ambiguous','toc-auto-review','media'}


def severity(code):
    return 'error' if code in ERRORS else 'review' if code in REVIEW else 'warning'


def render(issues):
    if not issues:
        return '<p>В выполненных автоматических проверках замечаний не найдено.</p>'
    groups=defaultdict(list)
    for issue in issues:
        groups[(issue.get('severity',severity(issue['code'])),issue['code'])].append(issue)
    result=[]
    for kind,label in [('error','Ошибки'),('warning','Предупреждения'),('review','Ручная проверка')]:
        selected=[(code,items) for (level,code),items in groups.items() if level==kind]
        if not selected:
            continue
        result.append('<h3>'+label+'</h3>')
        for code,items in selected:
            title=html.escape(items[0]['message'])
            rows=''.join('<li>'+html.escape(i['message'])+(f' (стр. {int(i["page"])})' if i.get('page') else '')+'</li>' for i in items)
            result.append(f'<details><summary>{title} <strong>({len(items)})</strong></summary><ul>{rows}</ul></details>')
    return ''.join(result)
