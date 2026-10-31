"""Offline directory and numbering rules; names and codes have separate provenance."""
import re

UNIVERSITY_FULL = 'Федеральное государственное бюджетное образовательное учреждение высшего образования «Иркутский государственный университет путей сообщения»'
UNIVERSITY_NAME = 'Иркутский государственный университет путей сообщения'
UNIVERSITY_SHORT = 'ФГБОУ ВО ИрГУПС'
WORK_TYPES = {
    'КР':'КУРСОВАЯ РАБОТА', 'КП':'КУРСОВОЙ ПРОЕКТ', 'ДП':'ДИПЛОМНЫЙ ПРОЕКТ',
    'ДР':'ДИПЛОМНАЯ РАБОТА', 'МД':'МАГИСТЕРСКАЯ ДИССЕРТАЦИЯ',
    'УП':'ОТЧЁТ ПО УЧЕБНОЙ ПРАКТИКЕ', 'ПП':'ОТЧЁТ ПО ПРОИЗВОДСТВЕННОЙ ПРАКТИКЕ',
    'ОП':'ОТЧЁТ ПО ПРЕДДИПЛОМНОЙ ПРАКТИКЕ', 'РГР':'РАСЧЁТНО-ГРАФИЧЕСКАЯ РАБОТА',
    'К':'КОНТРОЛЬНАЯ РАБОТА', 'ЛР':'ОТЧЁТ ПО ЛАБОРАТОРНОЙ РАБОТЕ', 'Р':'РЕФЕРАТ',
    'ОН':'ОТЧЁТ ПО НАУЧНО-ИССЛЕДОВАТЕЛЬСКОЙ РАБОТЕ', 'ОМ':'ОТЧЁТ ПО НАУЧНО-МЕТОДИЧЕСКОЙ РАБОТЕ'}
DOCUMENT_CODES = {'ПЗ':'Пояснительная записка', 'СБ':'Сборочный чертёж', 'ВО':'Чертёж общего вида',
                  'ГЧ':'Габаритный чертёж', 'МЭ':'Электромонтажный чертёж', 'МЧ':'Монтажный чертёж', 'ТУ':'Технические условия'}
REG_NUMBER_RE = re.compile(r'(?:ДП|ДР|МД|КП|КР|УП|ПП|ОП|РГР|К|ЛР|Р|ОН|ОМ)\.\d{6}\.\d{2}\.\d{2}\.\d{2}(?:\.\d+)?(?:-\d{4})?\.(?:ПЗ|СБ|ВО|ГЧ|МЭ|МЧ|ТУ)')
# Official structure, checked 2026-10-31. Head university, not branch departments.
DIRECTORY_URL = 'https://www.irgups.ru/org/strukt/univer/ifk/'
DIRECTORY = {
 'Транспортные системы': [('Транспортное машиностроение',None),('Физика, механика и приборостроение','410300'),('Автоматизация производственных процессов','410400')],
 'Управление на транспорте и информационные технологии': [('Управление эксплуатационной работой','420100'),('Информационные системы и защита информации','420200'),('Математика','420300')],
 'Строительство железных дорог': [('Путь и путевое хозяйство','430100'),('Строительство железных дорог, мостов и тоннелей','430200'),('Техносферная безопасность','430300')],
 'Системы обеспечения транспорта': [('Электроэнергетика транспорта','440100'),('Автоматика, телемеханика и связь','440200'),('Управление качеством и инженерная графика','440300')],
 'Экономика и управление': [('Экономика и управление на железнодорожном транспорте','450100'),('Таможенное дело и правоведение','460200'),('Финансовый и стратегический менеджмент',None),('Философия и социально-гуманитарные науки','460300'),('Физическая культура',None),('Иностранные языки',None)]}
# Codes above are historical codes from Appendix A, PDF pp.31–32, not from the current web page.
# Unknown/renamed/merged units intentionally have no inferred code.


def unit_code(department):
    return next((code for rows in DIRECTORY.values() for name,code in rows if name==department), None)


def generate_number(work, division, specialty, document='ПЗ', account='', year='', include_year=False):
    work, division, specialty, document = (str(v).strip().upper() for v in (work,division,specialty,document))
    if work not in WORK_TYPES:
        raise ValueError('Выберите вид работы из §6.2.')
    if work in {'ОН','ОМ'}:
        raise ValueError('Для ОН/ОМ §6.2 требует код разновидности темы и государственной регистрации. Учебная формула к ним не применяется; введите согласованный шифр вручную.')
    if not re.fullmatch(r'\d{6}',division):
        raise ValueError('Код подразделения — шесть цифр по приложению А, например 420200.')
    if not re.fullmatch(r'\d{2}\.\d{2}\.\d{2}',specialty):
        raise ValueError('Направление / специальность: формат 10.03.01.')
    if document not in DOCUMENT_CODES:
        raise ValueError('Выберите шифр документа из §6.2.')
    base=f'{work}.{division}.{specialty}'
    if work in {'ДП','ДР','МД'}:
        # Appendix B.1 uses 001; §6.2 does not prescribe a universal digit count.
        if not re.fullmatch(r'\d+',str(account).strip()):
            raise ValueError('Для ВКР введите учётный номер, выданный выпускающей кафедрой. Скрипт его не присваивает.')
        base += '.' + str(account).strip()
        include_year=True
    elif account:
        raise ValueError('В учебном шифре по §6.2 учётный номер не используется.')
    if include_year:
        if not re.fullmatch(r'\d{4}',str(year).strip()):
            raise ValueError('Введите год четырьмя цифрами.')
        base += '-' + str(year).strip()
    return base + '.' + document


def prepare_metadata(metadata):
    result={k:v for k,v in (metadata or {}).items() if v}
    # Institution is fixed. Override obsolete command-line values as well.
    result['university']=UNIVERSITY_NAME
    result['university_short']=UNIVERSITY_SHORT
    if result.get('generate_code'):
        kind=(result.get('work_code') or next((code for code,title in WORK_TYPES.items() if title==result.get('work_type','').upper()), '')).strip().upper()
        division=result.get('division_code') or unit_code(result.get('department','')) or ''
        result['code']=generate_number(kind,division,result.get('specialty',''),result.get('document_code') or 'ПЗ',
                                       result.get('account',''),result.get('year',''),result.get('include_year',False))
        result['work_type']=WORK_TYPES[kind]
    return result
