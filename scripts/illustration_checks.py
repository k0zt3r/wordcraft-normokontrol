"""Check duplicate and out-of-order caption numbers without renumbering links."""
import re


def check(model,issues):
    from normokontrol import norm,add_issue
    from captions import caption_paragraphs
    seen=set()
    last={}
    for _,p in caption_paragraphs(model):
        text=norm(p.get('text',''))
        match=re.match(r'^(рисунок|таблица)\s+((?:[а-яa-z]\.)?\d+(?:\.\d+)*)(?:\s|[–—-]|$)',text)
        if not match:
            continue
        kind,number=match.groups()
        key=(kind,number)
        if key in seen:
            add_issue(issues,'caption-number-duplicate',f'Повтор номера подписи: {kind} {number}. Ссылки автоматически не перенумеровываются.')
        seen.add(key)
        parts=number.split('.')
        sequence=(kind,tuple(parts[:-1]))
        current=int(parts[-1])
        previous=last.get(sequence,0)
        if current!=previous+1:
            add_issue(issues,'caption-number-order',f'Проверьте последовательность подписей: {kind} {number}; предыдущий номер в этой группе — {previous}.')
        last[sequence]=current
