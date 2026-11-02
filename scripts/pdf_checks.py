"""Inspect the main page area independently of frame and stamp text."""


def empty_body(page):
    import pymupdf
    mm = 72 / 25.4
    spans = [s for b in page.get_text('dict')['blocks'] for line in b.get('lines',[]) for s in line['spans']]
    stamp = any(s['text'].strip() == 'Изм.' and s['bbox'][1] > page.rect.height-45*mm for s in spans)
    if stamp:
        big = any(s['text'].strip() == 'Литера' and s['bbox'][1] > page.rect.height-45*mm for s in spans)
        region = pymupdf.Rect(20*mm+.5,5*mm+.5,page.rect.width-5*mm-.5,page.rect.height-(45 if big else 20)*mm-.5)
    else:
        region = page.rect
    if page.get_text(clip=region).strip():
        return False
    if any(rect.intersects(region) for image in page.get_images() for rect in page.get_image_rects(image[0])):
        return False
    # A vector-only diagram is content too; the page frame does not fit inside region.
    return not any(region.contains(d['rect']) and not d['rect'].is_empty for d in page.get_drawings())
