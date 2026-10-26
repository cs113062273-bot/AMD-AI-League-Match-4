"""Actual local HTTP recovery after one search-result origin begins returning 403.

No public requests or actual model; authored CPU semantic stubs and page/depth caps.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.types import Settings
from revision_engine import load_engine


async def diagnose(engine):
    mode='';hits=[];calls=[];rows=[];origin_a='';origin_b='';phone='+1 800 555 0176'
    async def content(request):
        origin='a' if request.host==origin_a.split('//')[1] else 'b'
        hits.append((origin,request.path))
        if request.path=='/answer':
            return web.Response(text='<title>Boreal Instruments</title><p>Support phone: '+phone+'</p>',content_type='text/html')
        return web.Response(status=404 if mode=='resource-404' else 403)
    async def root(request):
        hits.append(('root',request.path))
        if request.path=='/provider':
            targets=[origin_a+'/blocked/'+str(i) for i in range(8)]
            if mode=='one-denied':
                targets=[origin_a+'/blocked/0']+[base+'/empty/'+str(i) for i in range(1,4)]+[
                    origin_a+'/answer']+[base+'/empty/'+str(i) for i in range(4,7)]
                if not request.query.get('q','').startswith('site:'):targets=targets[:4]+[origin_b+'/empty/0']
            elif mode=='same-origin-answer':targets[4]=origin_a+'/answer'
            elif mode=='resource-404':targets[4]=origin_a+'/answer'
            elif mode!='no-alternative' and not request.query.get('q','').startswith('site:'):
                # A second query contributes the alternative. One provider
                # response is deliberately capped at eight links by search.
                targets=targets[:4]+[origin_b+'/answer']
            links=''.join('<li class="b_algo"><h2><a href="'+u+'">Boreal Instruments support phone</a></h2></li>' for u in targets)
            return web.Response(text=links,content_type='text/html')
        return web.Response(text='<h1>Boreal Instruments</h1><p>Support information is available elsewhere.</p>',content_type='text/html')
    async def model(request):
        data=await request.json();calls.append(request.path)
        if request.path=='/expand':return web.json_response({'terms':[]})
        if request.path=='/verify':return web.json_response({'supported':mode!='reject' and data.get('proposed')==phone})
        if not data.get('question','').startswith('Choose the best available page link'):
            for p in data.get('passages',[]):
                if phone in p['text']:return web.json_response({'passage':p['id'],'answer':phone})
        return web.json_response({'passage':-1,'answer':''})
    runners=[]
    async def start(handler,post=False):
        app=web.Application();app.router.add_get('/{tail:.*}',handler)
        if post:app.router.add_post('/{tail:.*}',model)
        runner=web.AppRunner(app);await runner.setup();runners.append(runner)
        site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
        return 'http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    try:
        origin_a=await start(content);origin_b=await start(content);base=await start(root,True)
        checks=[('late-denial',9,2,phone),('same-origin-answer',9,2,phone),('one-denied',9,2,phone),('resource-404',9,2,phone),
            ('no-alternative',9,2,''),('page-cap',5,2,''),('depth-cap',9,1,''),('reject',9,2,'')]
        for mode,max_pages,max_depth,expected in checks:
            hits.clear();calls.clear()
            result=await engine(Settings(model_url=base,search=True,browser=False,allow_private=True,
                search_providers=[(base+'/provider?q=','bing')],budget=12,max_pages=max_pages,max_depth=max_depth)).run(
                    'What is the support phone of Boreal Instruments?',base+'/root')
            expected_source=origin_a+'/answer' if mode in {'same-origin-answer','resource-404','one-denied'} else origin_b+'/answer'
            passed=result.answer==expected and (result.sources==[expected_source] if expected else not result.sources)
            content_hits=[(o,p) for o,p in hits if p!='/provider']
            passed &= len(content_hits)<=max_pages and len(content_hits)==len(set(content_hits))
            if mode in {'page-cap','depth-cap'}:passed &= not any(p=='/answer' for o,p in content_hits)
            if mode=='late-denial':passed &= ('b','/answer') in content_hits
            if mode=='resource-404':passed &= not result.diagnostics.get('origin_recovery')
            rows.append(dict(id=mode,passed=bool(passed),expected=expected,actual=result.answer,
                content_hits=content_hits,cpu_stub_calls=list(calls),result=result.internal()))
    finally:
        for runner in runners:await runner.cleanup()
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--baseline');ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    engine=Engine;revision='working-tree';hashes={}
    if args.baseline:engine,revision,hashes=load_engine(args.baseline)
    rows=asyncio.run(diagnose(engine));report=dict(scope=__doc__,revision=revision,baseline_source_sha256=hashes,
        diagnostic_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('app.py'),*sorted(Path('agent').glob('*.py'))]},
        passed=sum(r['passed'] for r in rows),total=len(rows),rows=rows)
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'],total=report['total'],failures=[r['id'] for r in rows if not r['passed']])))
    if report['passed']!=report['total']:sys.exit(1)
