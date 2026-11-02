"""Remove only provably invisible shapes; preserve overlays and semantic objects."""


def process(model,changes,issues,check_only=False):
    from normokontrol import paragraphs,add_issue
    from text_edits import replace
    count=0
    for _,p in paragraphs(model['body']):
        objects=p.get('objects',[])
        markers=[i for i,c in enumerate(p.get('text','')) if c=='\ufffc']
        if len(markers)!=len(objects):
            continue
        for index in range(len(objects)-1,-1,-1):
            obj=objects[index]
            if obj.get('type')!='shape' or obj.get('story') is not None:
                continue
            floating=obj.get('float') or {}
            if obj.get('fill') is None and obj.get('stroke') is None and not obj.get('extra'):
                if check_only:
                    add_issue(issues,'invisible-artifact','Найдена невидимая пустая фигура; режим оформления может безопасно удалить её.')
                elif replace(p,markers[index],markers[index]+1,'',allow_marker=True):
                    del objects[index]
                    count+=1
            elif floating and obj.get('fill')==[255,255,255] and obj.get('stroke') in (None,[255,255,255]):
                add_issue(issues,'legacy-overlay-review','Найдена пустая белая плавающая фигура. Она может быть старой вёрсткой или закрывать данные: автоматически не удаляется.')
    if count:
        changes.append(f'Удалено невидимых пустых фигур: {count}; содержательные объекты и белые перекрытия сохранены.')
