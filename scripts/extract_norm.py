"""Lossless text/layout extraction of the bundled public regulation."""
import hashlib
import json
from pathlib import Path
import pymupdf

ROOT=Path(__file__).resolve().parent.parent


def extract():
    source=ROOT/'Normokontrol.pdf'
    target=ROOT/'references/norm-source'
    images=target/'images';vectors=target/'vectors'
    images.mkdir(parents=True,exist_ok=True);vectors.mkdir(exist_ok=True)
    pages=[];assets=[];seen=set()
    with pymupdf.open(source) as pdf:
        for i,page in enumerate(pdf):
            blocks=page.get_text('dict')
            text=page.get_text(sort=False)
            pages.append({'page':i+1,'width':page.rect.width,'height':page.rect.height,'text':text,
                          'text_blocks':[b for b in blocks['blocks'] if b['type']==0]})
            for item in page.get_images(full=True):
                xref=item[0]
                data=pdf.extract_image(xref)
                name=f'image-{xref}.{data["ext"]}'
                if xref not in seen:
                    (images/name).write_bytes(data['image']);seen.add(xref)
                assets.append({'page':i+1,'xref':xref,'file':'images/'+name,
                               'rectangles':[list(r) for r in page.get_image_rects(xref)]})
            # Store vector originals, not raster screenshots. Geometry remains inspectable.
            if i+1>=33:
                name=f'page-{i+1:02}.svg'
                (vectors/name).write_text(page.get_svg_image(text_as_path=False),encoding='utf-8')
                assets.append({'page':i+1,'file':'vectors/'+name,'type':'page-vector-original'})
    manifest={'source':'../../Normokontrol.pdf','sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
              'pages':pages,'assets':assets,'limitations':'Текстовый слой извлечён полностью. Текст, встроенный в растровые рисунки, не объявляется распознанным. SVG сохраняет векторную геометрию.'}
    (target/'source.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    md=['# П.440300.05.4.092-2017 — полный извлечённый текст',
        'Источник: `../../Normokontrol.pdf`. SHA-256: `'+manifest['sha256']+'`.',
        'Ниже сохранены все страницы, включая повторы колонтитулов. Это извлечение, не пересказ. Рисунки перечислены в assets.json.']
    for p in pages:
        md.extend([f'\n## Страница PDF {p["page"]}\n',p['text']])
    (target/'full-text.md').write_text('\n\n'.join(md),encoding='utf-8')
    (target/'assets.json').write_text(json.dumps(assets,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Extracted {len(pages)} pages, {len(seen)} images, {len(assets)} asset references.')


if __name__=='__main__':extract()
