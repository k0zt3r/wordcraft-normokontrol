"""Group repeated findings while retaining every message and page."""
from collections import defaultdict
import html
import json
from pathlib import Path
import re
from urllib.parse import quote
import base64

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


def locate_findings(issues, model, wordcraft):
    """Resolve explicit positions or unique excerpts in the final saved model.

    Findings without a known excerpt keep their page or remain document-wide.
    Cache positions so repeated checks of one paragraph cost one layout request.
    """
    from normokontrol import paragraphs, norm
    candidates = [(path, para, norm(para.get('text', '')))
                  for path, para in paragraphs(model['body'])]
    by_path = {tuple(path): (path, para) for path, para, _ in candidates}
    cache = {}
    for issue in issues:
        position = issue.get('location', {})
        explicit = by_path.get(tuple(position.get('path', [])))
        if explicit:
            matches = [explicit]
        else:
            excerpt = issue['message'].rsplit(': ', 1)[-1].strip()
            if excerpt == issue['message'] or len(excerpt) < 12:
                continue
            excerpt = norm(excerpt)
            matches = [(path, para) for path, para, text in candidates if excerpt in text]
        if len(matches) != 1:
            continue
        path, para = matches[0]
        key = tuple(path)
        if key not in cache:
            from runtime import PositionUnavailable
            try:
                cache[key] = wordcraft.locate(path)
            except PositionUnavailable:
                cache[key] = None
        pos = cache[key]
        if pos is None:
            issue['location_status'] = 'unavailable'
            continue
        issue['page'] = pos['page']
        issue['location'] = dict(story='body', path=path, off=0,
                                 x=pos['x'], y=pos['y'], text=para.get('text', ''))


def finding_link(issue, pdf_name):
    page = issue.get('page')
    if not pdf_name or not isinstance(page, int) or isinstance(page, bool) or page < 1:
        return f' (стр. {int(page)})' if page else ''
    fragment = f'page={page}'
    location = issue.get('location', {})
    if isinstance(location.get('x'), (int, float)) and isinstance(location.get('y'), (int, float)):
        fragment += f'&zoom=125,{max(0, location["x"] - 20):.0f},{max(0, location["y"] - 40):.0f}'
    href = quote(pdf_name, safe='') + '#' + fragment
    return f' <a href="{html.escape(href, quote=True)}">Открыть страницу PDF · стр. {page}</a>'


def highlighted_places(pdf_path, issues):
    """Embed cropped PDF context with a highlighted first line, without saving
    annotations to the deliverable PDF. Reuse one image for repeated findings.
    Never invent a location for document-wide or unresolvable findings.
    """
    try:
        import pymupdf
    except ImportError:
        return {}, ''
    if not Path(pdf_path).is_file():
        return {}, ''
    links, sections, cached = {}, [], {}
    with pymupdf.open(pdf_path) as pdf:
        for issue in issues:
            location = issue.get('location', {})
            number, text = issue.get('page'), location.get('text', '')
            x, y = location.get('x'), location.get('y')
            if (not isinstance(number, int) or not 1 <= number <= len(pdf) or not text
                    or not isinstance(x, (int, float)) or not isinstance(y, (int, float))):
                continue
            key = (number, tuple(location.get('path', [])), x, y, text)
            if key in cached:
                links[id(issue)] = cached[key]
                continue
            page = pdf[number - 1]
            hits = page.search_for(text.replace('\ufffc', '').strip())
            if not hits:
                hits = page.search_for(' '.join(text.replace('\ufffc', '').split()[:8]))
            if not hits:
                continue
            first = min(hits, key=lambda r: abs(r.y0 - y) + .2 * abs(r.x0 - x))
            if abs(first.y0 - y) > max(40, first.height * 2):
                continue  # A distant duplicate is not the reported location.
            clip = pymupdf.Rect(page.rect.x0, max(page.rect.y0, first.y0 - 30),
                                page.rect.x1, min(page.rect.y1, first.y1 + 85))
            annotation = page.add_highlight_annot(first)
            try:
                annotation.set_colors(stroke=(1, .8, 0))
                annotation.set_opacity(.45)
                annotation.update()
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4), clip=clip, annots=True)
                image_data = base64.b64encode(pixmap.tobytes('png')).decode('ascii')
            finally:
                page.delete_annot(annotation)
            anchor_id = f'place-{len(sections) + 1}'
            cached[key] = links[id(issue)] = anchor_id
            excerpt = text[:300] + ('…' if len(text) > 300 else '')
            sections.append(f'<article class="place" id="{anchor_id}"><h3>Начало абзаца · страница {number}</h3>'
                            f'<blockquote>{html.escape(excerpt)}</blockquote>'
                            f'<img loading="lazy" width="{pixmap.width}" height="{pixmap.height}" alt="Начало абзаца выделено жёлтым на странице {number}" '
                            f'src="data:image/png;base64,{image_data}">'
                            f'<p>{finding_link(issue, Path(pdf_path).name)} · <a href="#findings">К замечаниям</a></p></article>')
    heading = ('<h2>Места замечаний</h2><p>Жёлтым выделена первая строка найденного абзаца. '
               'Это указатель места; замечание может относиться к другой части этого абзаца. '
               'Выделения показаны только в отчёте, DOCX и PDF не помечены.</p>')
    return links, heading + ''.join(sections) if sections else ''


def render(issues, pdf_name=None, places=None):
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
            def row(issue):
                place = (places or {}).get(id(issue))
                link = (f' <a class="place-link" href="#{place}">Показать место с выделением · стр. {issue["page"]}</a>'
                        if place else finding_link(issue, pdf_name))
                if issue.get('location_status') == 'unavailable':
                    link += ' <small>Wordcraft не предоставил точные координаты этого абзаца.</small>'
                return '<li>'+html.escape(issue['message'])+link+' '+reference_links(references_for(issue['message']))+'</li>'
            rows=''.join(row(i) for i in items)
            result.append(f'<li><details><summary>{label}: {title} <strong>({len(items)})</strong></summary><ul>{rows}</ul></details></li>')
    return ''.join(result)+'</ol>'
