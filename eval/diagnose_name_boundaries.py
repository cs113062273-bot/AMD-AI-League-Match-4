"""Facility-name/status boundaries: authored local HTTP, explicit CPU semantic stubs.

Related controls, not independent held-out questions or actual-model accuracy.
"""
import argparse
import asyncio
import hashlib
import html
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.types import Settings
from revision_engine import load_engine


async def diagnose(engine):
    mode='';source_text='';selected='';form='';calls=[];payloads=[];rows=[]
    async def source(request):
        if form=='json':return web.json_response({'name':source_text})
        if form=='field':body='<dl><dt>Name</dt><dd>'+html.escape(source_text)+'</dd></dl>'
        else:body='<p>'+html.escape(source_text)+'</p>'
        return web.Response(text='<title>River archive</title>'+body,content_type='text/html')
    async def model(request):
        data=await request.json();calls.append(request.path);payloads.append(data)
        if request.path=='/verify':
            if mode=='unavailable':return web.json_response({'error':'unavailable'},status=503)
            return web.json_response({'supported':mode!='reject'})
        if mode=='abstain':return web.json_response({'passage':-1,'answer':''})
        for p in data.get('passages',[]):
            if selected in p['text']:return web.json_response({'passage':p['id'],'answer':selected})
        return web.json_response({'passage':-1,'answer':''})
    app=web.Application();app.router.add_get('/source',source);app.router.add_post('/{path}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    question='What is the name of the school where the River Project first planted a tree?'
    checks=[
        ('former','The first planting took place at the former Pine Elementary School.','former Pine Elementary School','prose',question,'Pine Elementary School'),
        ('article-status','The first planting took place at the former Pine Elementary School.','the former Pine Elementary School','prose',question,'Pine Elementary School'),
        ('current','The event took place at the current Cedar High School.','current Cedar High School','prose',question,'Cedar High School'),
        ('previous','They met at the previous River Secondary School.','previous River Secondary School','prose',question,'River Secondary School'),
        ('already-short','They met at the former Pine Elementary School.','Pine Elementary School','prose',question,'Pine Elementary School'),
        ('capitalized','They met at Former Pine Elementary School.','Former Pine Elementary School','prose',question,'Former Pine Elementary School'),
        ('official-json','former Pine Elementary School','former Pine Elementary School','json',question,'former Pine Elementary School'),
        ('official-field','former Pine Elementary School','former Pine Elementary School','field',question,'former Pine Elementary School'),
        ('quoted','The school is named "former Pine Elementary School".','former Pine Elementary School','prose',question,'former Pine Elementary School'),
        ('smart-quotes','The school is named \u201cformer Pine Elementary School\u201d.','former Pine Elementary School','prose',question,'former Pine Elementary School'),
        ('named','They attended a school named former Pine Elementary School.','former Pine Elementary School','prose',question,'former Pine Elementary School'),
        ('name-label','Official name: former Pine Elementary School.','former Pine Elementary School','prose',question,'former Pine Elementary School'),
        ('not-name-question','The description is former Pine Elementary School.','former Pine Elementary School','prose','What is the description of the site?','former Pine Elementary School'),
        ('status-question','The site is described as former Pine Elementary School.','former Pine Elementary School','prose','What is the designation including status of the school?','former Pine Elementary School'),
        ('lowercase','The first planting took place at the former pine elementary school.','former pine elementary school','prose',question,'former pine elementary school'),
        ('generic-head','The first planting took place at the former School.','former School','prose',question,'former School'),
        ('wrong-type','The first planting took place at the former Pine Hospital.','former Pine Hospital','prose',question,'former Pine Hospital'),
        ('old-is-name','They met at the Old Pine Elementary School.','Old Pine Elementary School','prose',question,'Old Pine Elementary School'),
        ('reject','The first planting took place at the former Pine Elementary School.','former Pine Elementary School','prose',question,''),
        ('unavailable','The first planting took place at the former Pine Elementary School.','former Pine Elementary School','prose',question,''),
        ('abstain','The first planting took place at the former Pine Elementary School.','former Pine Elementary School','prose',question,''),
    ]
    try:
        for mode,source_text,selected,form,query,expected in checks:
            calls.clear();payloads.clear()
            result=await engine(Settings(model_url=base,search=False,browser=False,allow_private=True,max_depth=0,budget=12)).run(query,base+'/source')
            passed=result.answer==expected and (result.sources==[base+'/source'] if expected else not result.sources)
            checks_sent=[p for p,c in zip(payloads,calls) if c=='/verify']
            if expected:passed &= bool(checks_sent) and checks_sent[-1]['proposed']==expected
            rows.append(dict(id=mode,passed=bool(passed),source=source_text,query=query,stub_selection=selected,
                expected=expected,actual=result.answer,cpu_stub_calls=list(calls),cpu_stub_payloads=list(payloads),result=result.internal()))
    finally:await runner.cleanup()
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
