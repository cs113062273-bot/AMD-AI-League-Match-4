"""Small live-source availability probe from exposed historical failures.

Runs actual production HTTP/search parsing, without model inference or gold
answers in production requests. This reports retrieval, not answer accuracy.
"""
import argparse
import asyncio
import base64
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent.network import Fetcher
from agent.parser import parse_response
from agent.planner import plan_query
from agent.search import search
from agent.types import Settings,Deadline
from agent.urls import discovery_url


async def diagnose(cases,capture_dir=None,reuse_hints=False,baseline_search=None):
    rows=[]
    for case in cases:
        settings=Settings(request_timeout=3,model_url='')
        deadline=Deadline(16)
        diagnostic=case.get('result',case)['diagnostics']
        plan=plan_query(diagnostic['plan']['question'],diagnostic['plan']['url'])
        hints=diagnostic.get('search_hints',[]) if reuse_hints else []
        async with Fetcher(settings,deadline) as fetcher:
            start=await fetcher.fetch(plan.url,timeout=3)
            baseline_candidates=None
            if baseline_search:
                # Both algorithms see the same initial failed-host evidence.
                # Common URL responses are fetched once and reused; retain the
                # union of requests so offline replay is complete for both.
                view=SimpleNamespace(deadline=deadline,events=list(fetcher.events),fetch=fetcher.fetch)
                baseline_candidates=await baseline_search(plan,view,hints=hints)
                candidates=await search(plan,view,hints=hints)
            else:candidates=await search(plan,fetcher,hints=hints)
            responses=await asyncio.gather(*(fetcher.fetch(url,timeout=3) for url,label in candidates[:4])) if deadline.remaining>1 else []
            pages=[parse_response(response) for response in responses]
            rows.append({'id':case['id'],'query':plan.question,'starting_url':plan.url,
                'starting_status':start.status,'starting_error':start.error,'candidates':candidates,
                'search_hints':hints,
                'pages':[{'url':page.url,'title':page.title,'error':page.error,'passages':len(page.passages)} for page in pages],
                'events':fetcher.events,'seconds':16-deadline.remaining})
            if baseline_search:
                rows[-1]['baseline_candidates']=baseline_candidates
                rows[-1]['comparison_scope']='Shared initial events and cached common responses; union captured for deterministic offline replay. Shared timeline, not a latency comparison.'
            if capture_dir:
                snapshots={}
                for url,response in fetcher.cache.items():
                    if not discovery_url(url):continue
                    data=asdict(response);data['body_base64']=base64.b64encode(data.pop('body')).decode('ascii')
                    snapshots[url]=data
                target=capture_dir/(case['id']+'.json')
                if target.exists():raise FileExistsError(target)
                target.write_text(json.dumps(snapshots,ensure_ascii=True,indent=2),encoding='utf-8')
                rows[-1].update(search_snapshot_path=str(target.relative_to(ROOT)),search_snapshot_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        print(json.dumps({'id':case['id'],'candidates':len(candidates),'readable_pages':sum(not p.error and bool(p.passages) for p in pages)},ensure_ascii=True),flush=True)
    return {'scope':__doc__,'captured_utc':datetime.now(timezone.utc).isoformat(),'rows':rows,
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['agent/search.py','agent/urls.py','agent/network.py','agent/planner.py']}}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--report',default='benchmarks/external-transfer100-retest-20261021.json')
    ap.add_argument('--ids',nargs='+',required=True);ap.add_argument('--out',required=True)
    ap.add_argument('--capture-dir')
    ap.add_argument('--reuse-hints',action='store_true',help='Reuse saved unverified model hints from the input trace; no inference')
    ap.add_argument('--compare-baseline',help='Run historical search then current with shared initial events and cached common HTTP responses')
    args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    report=json.loads((ROOT/args.report).read_text(encoding='utf-8'))
    cases=[case for case in report['rows'] if case['id'] in args.ids]
    if {case['id'] for case in cases}!=set(args.ids):raise ValueError('Unrecognized case ID')
    capture_dir=ROOT/args.capture_dir if args.capture_dir else None
    if capture_dir:capture_dir.mkdir(parents=True,exist_ok=True)
    baseline=None;revision=None
    if args.compare_baseline:
        from revision_engine import load_engine
        engine,revision,hashes=load_engine(args.compare_baseline)
        baseline=importlib.import_module(engine.__module__.rsplit('.',1)[0]+'.search').search
    result=asyncio.run(diagnose(cases,capture_dir,reuse_hints=args.reuse_hints,baseline_search=baseline));result['input_report']=args.report
    result['reused_trace_hints']=args.reuse_hints
    if baseline:result.update(baseline_revision=revision,baseline_source_sha256=hashes)
    target.write_text(json.dumps(result,ensure_ascii=True,indent=2),encoding='utf-8')
