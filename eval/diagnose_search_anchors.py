"""Controlled HTTP search-topic probes, including weak lexical overlap and empty discovery.

Provider responses are controlled; this is retrieval behavior, not public-web accuracy.
"""
import argparse
import asyncio
import hashlib
import importlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.network import Fetcher
from agent.planner import plan_query
from agent.search import search
from agent.types import Settings,Deadline
from revision_engine import load_engine


async def diagnose(searcher):
    base='';hits=[];mode=''
    questions={
        'first':'What is the first and last name of the partner of Orin Vale?',
        'two':'What two teams played the Cedar Cup final?',
        'day':'What day was the Pine Harbor festival opened?',
        'unrelated-only':'What day was the Pine Harbor festival opened?',
        'singleton':'What is the license of httpx?',
        'identifier':'What is the value of the `render_mode` field?',
    }
    async def provider(request):
        hits.append((request.path,request.query.get('q','')))
        if mode=='unrelated-only':items=[('/dictionary','Day definition')]
        elif mode in {'singleton','identifier'}:
            items=[('/answer','httpx')] if mode=='singleton' else [('/answer','render_mode')]
        elif request.path=='/weak':items=[('/dictionary',mode+' definition')]
        else:
            label={'first':'Orin Vale biography','two':'Cedar Cup final teams','day':'Pine Harbor festival opening'}[mode]
            items=[('/answer',label),('/details','More details')]
        html=''.join('<li class="b_algo"><h2><a href="'+base+u+'">'+label+'</a></h2></li>' for u,label in items)
        return web.Response(text=html,content_type='text/html')
    app=web.Application();app.router.add_get('/{tail:.*}',provider)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);rows=[]
    try:
        for mode,question in questions.items():
            hits.clear();plan=plan_query(question,'')
            providers=[(base+'/unused?q=','bing'),(base+'/weak?q=','bing'),(base+'/relevant?q=','bing')]
            hints=[]
            async with Fetcher(Settings(allow_private=True),Deadline(3.8)) as fetcher:
                actual=await searcher(plan,fetcher,providers,hints=hints)
            paths=[u.removeprefix(base) for u,label in actual]
            expected=[] if mode=='unrelated-only' else ['/answer'] if mode in {'singleton','identifier'} else ['/answer','/details']
            rows.append(dict(id=mode,passed=paths==expected,actual=actual,requests=list(hits)))
    finally:await runner.cleanup()
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    engine,revision,hashes=load_engine('c052c78')
    before=asyncio.run(diagnose(importlib.import_module(engine.__module__.rsplit('.',1)[0]+'.search').search))
    after=asyncio.run(diagnose(search))
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,before=before,after=after,
        before_passed=sum(r['passed'] for r in before),after_passed=sum(r['passed'] for r in after),total=len(after),
        wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
        losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
        search_sha256=hashlib.sha256((ROOT/'agent/search.py').read_bytes()).hexdigest(),
        diagnostic_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    if not all(r['passed'] for r in after):sys.exit(1)
