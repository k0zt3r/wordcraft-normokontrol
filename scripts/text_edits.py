"""Edit a visible span while retaining run formatting and bookmark markers."""
import copy


def replace(para, start, end, value, allow_marker=False):
    text=para.get('text','')
    data=text.encode('utf-8')
    runs=para.get('runs',[])
    if sum(r.get('len',0) for r in runs)!=len(data) or ('\ufffc' in text[start:end] and not allow_marker):
        return False
    lo=len(text[:start].encode('utf-8'))
    hi=len(text[:end].encode('utf-8'))
    added=value.encode('utf-8')
    output=[]
    offset=0
    inserted=False
    for run in runs:
        stop=offset+run['len']
        left=max(0,min(stop,lo)-offset)
        right=max(0,stop-max(offset,hi))
        if left:
            item=copy.deepcopy(run);item['len']=left;output.append(item)
        if not inserted and stop>=lo:
            if added:
                item=copy.deepcopy(run);item['len']=len(added);output.append(item)
            inserted=True
        if right:
            item=copy.deepcopy(run);item['len']=right;output.append(item)
        offset=stop
    if not inserted:
        return False
    para['text']=text[:start]+value+text[end:]
    para['runs']=output
    delta=len(added)-(hi-lo)
    for obj in para.get('objects',[]):
        if isinstance(obj.get('off'),int) and obj['off']>=hi:
            obj['off']+=delta
    return True
