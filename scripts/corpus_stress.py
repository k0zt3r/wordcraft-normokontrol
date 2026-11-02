"""Anonymous boundary scenarios independent of private corpus documents."""
import json
from pathlib import Path
import tempfile
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
import normokontrol as nk


def run(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    results=[]
    with tempfile.TemporaryDirectory() as tmp:
        source=Path(tmp)/'synthetic.docx'
        doc=Document()
        doc.add_paragraph('Отчёт по лабораторной работе')
        doc.add_paragraph('Иркутск 2026')
        for title in ('Теоретическая часть','Практическая часть'):
            p=doc.add_paragraph(title);p.alignment=WD_ALIGN_PARAGRAPH.CENTER
            doc.add_paragraph('Обезличенный тестовый текст.')
        doc.save(source)
        cases=[('lab-no-bibliography',{}),('templates-empty',{'toc_template':True,'bibliography_template':True}),
               ('templates-one',{'toc_entries':['Теоретическая часть'],'bibliography_entries':['Тестовый источник.']}),
               ('templates-large',{'toc_entries':['Теоретическая часть','Практическая часть']+['Неизвестный раздел '+str(i) for i in range(98)],
                                    'bibliography_entries':['Тестовый источник '+str(i)+'.' for i in range(100)]}),
               ('metadata-long',{'metadata':{'title':'Длинная тема '*500,'author':'Автор '*100,'discipline':'Тест'}})]
        for name,options in cases:
            try:
                report=(nk.create_document(out/name,progress=lambda _:None,**options) if name=='metadata-long'
                        else nk.process(source,out/name,progress=lambda _:None,**options))
                results.append({'scenario':name,'status':'ok','pages':report['pages'],
                                'issues':sorted({i['code'] for i in report['issues']})})
            except Exception as error:
                results.append({'scenario':name,'status':'error','error':str(error)})
    (out/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    return results


if __name__=='__main__':
    import sys
    print(json.dumps(run(sys.argv[1]),ensure_ascii=False,indent=2))
