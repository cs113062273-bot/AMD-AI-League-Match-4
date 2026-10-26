"""CPU-only concise-hint proposal over recorded expansions and bounded public GETs.

No LLM, GPU or browser. Hints and search titles are discovery only, never
answer evidence. Public responses are dynamic; this is not answer accuracy.
"""
import argparse
import asyncio
import base64
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote_plus

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.network import Fetcher,Response
from agent.planner import plan_query,tokens,STOP
from agent.search import concise_query,search
from agent.types import Settings,Deadline

REPORTS=[
    'benchmarks/external-disjoint12b-20261023-repeat.json',
    'benchmarks/external-disjoint12b-20261023-first.json',
    'benchmarks/concise-discovery-20261023-live.json',
    'benchmarks/case-citation-20261023-final.json',
]
GENERIC={'first','last','given','family','name','day','month','year','line','field','value'}


def proposal(plan,hints,keep_field=True):
    original=set(plan.entity_terms)-GENERIC
    focus=set(tokens(plan.focus))-STOP
    if not original:return ''
    valid=[]
    for hint in hints:
        if not isinstance(hint,str) or not 1<len(hint)<=80 or re.search(r'https?://|\d|[\r\n]',hint):continue
        words=set(tokens(hint));retained=len(original.intersection(words))
        if 2<=len(hint.split())<=8 and retained>=min(2,len(original)):
            valid.append(((len(focus.intersection(words)) if keep_field else 0,retained),hint.strip()))
    return max(valid,key=lambda item:item[0])[1] if valid else concise_query(plan,hints)


def offline():
    rows=[];seen=set();hashes={}
    for filename in REPORTS:
        path=ROOT/filename;hashes[filename]=hashlib.sha256(path.read_bytes()).hexdigest()
        data=json.loads(path.read_text(encoding='utf-8'));records=data.get('rows',[])
        if isinstance(records,dict):records=[r for rs in records.values() for r in rs]
        records=records+data.get('live_rows',[])
        for record in records:
            diag=record.get('result',{}).get('diagnostics',{})
            question=diag.get('plan',{}).get('question','');hints=diag.get('search_hints',[])
            if not question or not hints or (question,tuple(hints)) in seen:continue
            seen.add((question,tuple(hints)));plan=plan_query(question)
            rows.append(dict(id=record['id'],question=question,hints=hints,before=concise_query(plan,hints),
                             max_overlap=proposal(plan,hints,False),field_then_overlap=proposal(plan,hints)))
    return rows,hashes


async def links_from_response(plan,response):
    class Replay:
        deadline=Deadline(4);events=[]
        async def fetch(self,url,**kwargs):
            if 'w/api.php' in url:return Response(url,error='offline_missing')
            return response
    return await search(plan,Replay(),[('https://lite.duckduckgo.com/lite/?q=','duckduckgo_lite')])


async def live(rows,capture_dir):
    output=[]
    for row in rows:
        if row['before']==row['max_overlap']==row['field_then_overlap']:continue
        queries=list(dict.fromkeys([row['before'],row['max_overlap'],row['field_then_overlap']]))
        plan=plan_query(row['question'])
        async with Fetcher(Settings(concurrency=2),Deadline(12)) as fetcher:
            responses=await asyncio.gather(*(fetcher.fetch('https://lite.duckduckgo.com/lite/?q='+quote_plus(q),
                                                timeout=5,max_bytes=400000) for q in queries))
        variants=[]
        for i,(query,response) in enumerate(zip(queries,responses)):
            target=capture_dir/(row['id']+'-'+str(i)+'.json')
            if target.exists():raise FileExistsError(target)
            data=asdict(response);data['body_base64']=base64.b64encode(data.pop('body')).decode('ascii')
            target.write_text(json.dumps(data,indent=2),encoding='utf-8')
            links=await links_from_response(plan,response)
            variants.append(dict(query=query,status=response.status,error=response.error,bytes=len(response.body),
                                 capture_path=target.relative_to(ROOT).as_posix(),
                                 capture_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),links=links))
        output.append(dict(id=row['id'],variants=variants))
        print(json.dumps({'id':row['id'],'variants':[dict(query=v['query'],status=v['status'],links=len(v['links'])) for v in variants]}),flush=True)
    return output


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--capture-dir');args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    rows,hashes=offline();report=dict(scope=__doc__,rows=rows,input_sha256=hashes,
        production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('agent').glob('*.py')})
    if args.capture_dir:
        capture=ROOT/args.capture_dir;capture.mkdir(exist_ok=False,parents=True)
        report['live']=asyncio.run(live(rows,capture))
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'recorded_sets':len(rows),'max_overlap_changes':sum(r['before']!=r['max_overlap'] for r in rows),
                      'field_then_overlap_changes':sum(r['before']!=r['field_then_overlap'] for r in rows)}))
