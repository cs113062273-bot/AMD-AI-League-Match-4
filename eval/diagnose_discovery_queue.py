"""Controlled HTTP replay of discovery starvation, duplicates and retrieval bounds.

Motivated by external-transfer100's blocked top-four source failures; these are
new development scenarios, not a real-web/LLM accuracy measurement.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.types import Settings
from revision_engine import load_engine


async def diagnose(engine):
    base='';mode='';hits=[];calls=[]
    phone='+1 800 555 0187'

    def anchors(items):
        return ''.join('<li class="b_algo"><h2><a href="'+base+url+'">'+label+'</a></h2></li>' for url,label in items)

    async def source(request):
        hits.append(request.path)
        if request.path=='/provider':
            targets=['/empty']*4 if mode=='provider-duplicates' else ['/blocked/'+str(i) for i in range(4)] if mode.startswith('blocked') else ['/empty/'+str(i) for i in range(4)]
            items=[(url,'Boreal Instruments support phone '+str(i)) for i,url in enumerate(targets)]
            items.append(('/answer','Boreal Instruments support'))
            return web.Response(text=anchors(items),content_type='text/html')
        if request.path.startswith('/blocked'):
            return web.Response(status=403)
        if request.path=='/answer':
            return web.Response(text='<title>Boreal Instruments support</title><p>Support phone: '+phone+'</p>',content_type='text/html')
        if request.path=='/navigation':
            items=[('/empty','Boreal Instruments support phone '+str(i)) for i in range(4)]+[('/answer','Boreal Instruments support')]
            return web.Response(text='<h1>Boreal Instruments</h1>'+anchors(items),content_type='text/html')
        return web.Response(text='<h1>Boreal Instruments</h1><p>Our documentation is being updated.</p>',content_type='text/html')

    async def model(request):
        data=await request.json();calls.append(request.path)
        if request.path=='/verify':
            return web.json_response({'supported':any(data.get('proposed','') in p['text'] for p in data.get('passages',[]))})
        if not data.get('question','').startswith('Choose the best available page link'):
            for passage in data.get('passages',[]):
                match=re.search(r'\+1 800 555 \d{4}',passage['text'])
                if match:return web.json_response({'passage':passage['id'],'answer':match[0]})
        return web.json_response({'passage':-1,'answer':''})

    app=web.Application();app.router.add_get('/{tail:.*}',source);app.router.add_post('/{tail:.*}',model)
    runner=web.AppRunner(app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    rows=[]
    try:
        for mode,max_pages,depth,expected in [
            ('provider-duplicates',10,2,phone),('blocked-first-four',10,2,phone),
            ('answerless-first-four',10,2,phone),('blocked-page-cap',5,2,''),
            ('blocked-depth-cap',10,1,''),('navigation-duplicates',10,1,phone),
        ]:
            hits.clear();calls.clear();navigation=mode.startswith('navigation')
            settings=Settings(model_url=base,search=not navigation,allow_private=True,budget=12,
                max_pages=max_pages,max_depth=depth,search_providers=[(base+'/provider?q=','bing')])
            result=await engine(settings).run('What is the support phone of Boreal Instruments?',base+('/navigation' if navigation else '/root'))
            content_hits=[hit for hit in hits if hit!='/provider']
            passed=result.answer==expected and result.sources==([base+'/answer'] if expected else [])
            passed=passed and len(content_hits)<=max_pages and len(content_hits)==len(set(content_hits))
            if not expected:passed=passed and '/answer' not in hits
            rows.append({'id':mode,'passed':passed,'hits':list(hits),'model_calls':list(calls),'result':result.internal()})
    finally:await runner.cleanup()
    return {'scope':__doc__,'passed':sum(row['passed'] for row in rows),'total':len(rows),'rows':rows}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--baseline');args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    engine=Engine;revision='working-tree';hashes={}
    if args.baseline:engine,revision,hashes=load_engine(args.baseline)
    report=asyncio.run(diagnose(engine))
    if not args.baseline:
        hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['agent/engine.py','agent/search.py','agent/urls.py']}
    report.update(revision=revision,source_sha256=hashes,diagnostic_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    target.write_text(json.dumps(report,ensure_ascii=True,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'total':report['total'],'failures':[row['id'] for row in report['rows'] if not row['passed']]}))
