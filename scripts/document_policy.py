"""Work-type labels and the common structural requirements of the regulation."""
import re


def kind(model):
    from normokontrol import body_start, paragraphs, norm
    start=body_start(model)
    text=' '.join(norm(p.get('text','')) for _,p in paragraphs(model['body'][:start or 30]))
    if re.search(r'лабораторн(?:ая|ой|ую|ые|ых)',text):
        return 'lab'
    if re.search(r'дипломн|магистерская диссертация',text):
        return 'vkr'
    if re.search(r'курсов(?:ая|ой|ую)',text):
        return 'course'
    if re.search(r'отч[её]т.{0,100}практик',text):
        return 'practice'
    if 'реферат' in text:
        return 'essay'
    return 'generic'


def required(model):
    # §6.1 has no blanket laboratory exemption. A task-specific waiver needs
    # independent evidence; inferred work type cannot silently waive the PDF.
    return ('введение','заключение','список использованных источников')
