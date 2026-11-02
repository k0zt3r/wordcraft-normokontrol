"""Local debugging corpus. Original documents and reports never enter Git."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
from zipfile import ZipFile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent.parent


def describe(path):
    result={'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'size':path.stat().st_size}
    if path.suffix.lower()!='.docx':
        result['format']='unsupported'
        return result
    with ZipFile(path) as archive:
        xml=ET.fromstring(archive.read('word/document.xml'))
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
            'wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
            'm':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
        result['xml_counts']={name:len(xml.findall(xpath,ns)) for name,xpath in {
            'paragraphs':'.//w:p','tables':'.//w:tbl','sections':'.//w:sectPr',
            'floating_drawings':'.//wp:anchor','inline_drawings':'.//wp:inline',
            'textboxes':'.//w:txbxContent','math':'.//m:oMath','revisions':'.//w:ins'}.items()}
    return result


def worker(source, folder, scenario):
    import normokontrol as nk
    folder=Path(folder)
    result={'scenario':scenario,'source':str(source)}
    start=time.perf_counter()
    try:
        options={'check_only':scenario=='check'}
        if scenario=='metadata':
            options['metadata']={'author':'Иванов И.И.','group':'ТЕСТ.1-26-1','supervisor':'Петров П.П.',
                'supervisor_title':'доцент','title':'Проверка замены реквизитов','discipline':'Тестовая дисциплина',
                'city':'Иркутск','year':'2026','code':'КР.420200.10.03.01.ПЗ'}
        report=nk.process(source,folder/'result',progress=lambda _:None,**options)
        result.update(status='ok',pages=report['pages'],issues=Counter(i['code'] for i in report['issues']),
                      changes=len(report['changes']))
        if scenario=='metadata':
            result['unapplied_fields']=[i['message'] for i in report['issues'] if i['code']=='metadata-unapplied']
    except Exception as error:
        result.update(status='error',error=str(error),traceback=traceback.format_exc())
    result['seconds']=round(time.perf_counter()-start,3)
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'outcome.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


def run_one(source, folder, scenario, timeout):
    folder.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--worker',str(source),str(folder),scenario]
    proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        stdout,stderr=proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if sys.platform=='win32':
            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        else:
            proc.kill()
        proc.communicate()
        return {'scenario':scenario,'status':'timeout','seconds':timeout}
    outcome=folder/'outcome.json'
    if outcome.exists():
        return json.loads(outcome.read_text(encoding='utf-8'))
    return {'scenario':scenario,'status':'worker-error','error':stderr.decode('utf-8',errors='replace')[-3000:]}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--worker',nargs=3)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--scenarios',nargs='+',default=['check','format'])
    parser.add_argument('--jobs',type=int,default=2)
    parser.add_argument('--timeout',type=int,default=120)
    args=parser.parse_args()
    if args.worker:
        worker(Path(args.worker[0]),Path(args.worker[1]),args.worker[2]);return
    if not args.out:
        parser.error('--out is required')
    args.out.mkdir(parents=True,exist_ok=False)
    paths=sorted(p for name in ('2 курс 1 сем','2 курс 2 сем') for p in (ROOT/name).rglob('*')
                 if p.is_file() and p.suffix.lower() in {'.docx','.doc','.docm','.dotx'} and not p.name.startswith('~$'))
    inventory=[describe(p) for p in paths]
    groups={}
    for path,item in zip(paths,inventory):
        groups.setdefault(item['sha256'],[]).append((path,item))
    (args.out/'inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
    results=[]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures={pool.submit(run_one,items[0][0],args.out/digest[:12]/scenario,scenario,args.timeout):(digest,scenario)
                 for digest,items in groups.items() for scenario in args.scenarios}
        for future in as_completed(futures):
            digest,scenario=futures[future]
            outcome=future.result()
            outcome['files']=[item['path'] for _,item in groups[digest]]
            outcome['sha256']=digest
            results.append(outcome)
            (args.out/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            print(f"{len(results)}/{len(futures)} {scenario} {outcome['status']} {outcome.get('error','')[:140]}",flush=True)
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256'] for p,item in zip(paths,inventory))
    print('Original hashes verified. Unique files:',len(groups),flush=True)


if __name__=='__main__':
    main()
