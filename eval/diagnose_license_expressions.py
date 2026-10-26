"""Whole license field recovery: authored loopback HTTP with explicit CPU semantic stubs.

Related controls, not independent held-out questions or real-model accuracy.
"""
import argparse
import asyncio
import hashlib
import html
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
    rows=[];mode='';expression='';selected='';form='';query='';calls=[];payloads=[]
    async def source(request):
        if form=='nested':return web.json_response({'name':'River','version':{'license':expression}})
        if form=='declared':return web.json_response({'name':'River','licenseDeclared':expression})
        if form=='concluded':return web.json_response({'name':'River','licenseConcluded':expression})
        if form=='json':return web.json_response({'name':'River','license':expression})
        if form=='dl':body='<dl><dt>License</dt><dd>'+html.escape(expression)+'</dd></dl>'
        elif form=='inline':body='<p><strong>License:</strong> '+html.escape(expression)+'</p>'
        elif form=='table':body='<table><tr><th>Package</th><th>License</th></tr><tr><td>River</td><td>'+html.escape(expression)+'</td></tr></table>'
        elif form=='duplicate':body='<table><tr><th>Package</th><th>License</th><th>License</th></tr><tr><td>River</td><td>'+html.escape(expression)+'</td><td>ISC OR BSD-2-Clause</td></tr></table>'
        elif form=='prose':body='<p>River is offered under '+html.escape(expression)+'.</p>'
        else:raise ValueError(form)
        return web.Response(text='<title>River metadata</title>'+body,content_type='text/html')
    async def model(request):
        data=await request.json();calls.append(request.path);payloads.append(data)
        if request.path=='/verify':
            if mode=='unavailable':return web.json_response({'error':'unavailable'},status=503)
            return web.json_response({'supported':mode!='reject'})
        if mode=='abstain':return web.json_response({'passage':-1,'answer':''})
        passages=data.get('passages',[])
        if form in {'table','duplicate'}:passages=sorted(passages,key=lambda p:'/cell[' in p['locator'],reverse=mode=='duplicate-cell')
        for p in passages:
            if expression in p['text'] and selected in p['text']:
                return web.json_response({'passage':p['id'],'answer':selected})
        return web.json_response({'passage':-1,'answer':''})
    app=web.Application();app.router.add_get('/source',source);app.router.add_post('/{path}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    whole='What is the license of River?'
    checks=[
        ('or','MIT OR Apache-2.0','MIT','json',whole,'MIT OR Apache-2.0'),
        ('and','BSD-3-Clause AND ISC','ISC','json',whole,'BSD-3-Clause AND ISC'),
        ('with','GPL-2.0-only WITH Classpath-exception-2.0','GPL-2.0-only','json',whole,'GPL-2.0-only WITH Classpath-exception-2.0'),
        ('plus','GPL-2.0+','GPL-2.0','json',whole,'GPL-2.0+'),
        ('nested','MIT AND (Apache-2.0 OR BSD-2-Clause)','Apache-2.0','nested',whole,'MIT AND (Apache-2.0 OR BSD-2-Clause)'),
        ('custom','LicenseRef-River OR LicenseRef-Pine','LicenseRef-River','json',whole,'LicenseRef-River OR LicenseRef-Pine'),
        ('document','DocumentRef-Local:LicenseRef-River AND MIT','MIT','json',whole,'DocumentRef-Local:LicenseRef-River AND MIT'),
        ('declared','MIT OR Apache-2.0','MIT','declared',whole,'MIT OR Apache-2.0'),
        ('concluded','MIT OR Apache-2.0','MIT','concluded',whole,'MIT OR Apache-2.0'),
        ('definition-list','MIT OR Apache-2.0','MIT','dl',whole,'MIT OR Apache-2.0'),
        ('inline-field','MIT OR Apache-2.0','MIT','inline',whole,'MIT OR Apache-2.0'),
        ('table-row','MIT OR Apache-2.0','MIT','table',whole,'MIT OR Apache-2.0'),
        ('complete-selected','MIT OR Apache-2.0','MIT OR Apache-2.0','json',whole,'MIT OR Apache-2.0'),
        ('single','MIT','MIT','json',whole,'MIT'),
        ('component','MIT OR Apache-2.0','MIT','json','Which license option other than Apache-2.0 is offered for River?','MIT'),
        ('exception','GPL-2.0-only WITH Classpath-exception-2.0','Classpath-exception-2.0','json','Which license exception is named for River?','Classpath-exception-2.0'),
        ('prose','MIT OR Apache-2.0','MIT','prose','Which license option other than Apache-2.0 is offered for River?','MIT'),
        ('reject','MIT OR Apache-2.0','MIT','json',whole,''),
        ('unavailable','MIT OR Apache-2.0','MIT','json',whole,''),
        ('abstain','MIT OR Apache-2.0','MIT','json',whole,''),
        ('no-model','MIT OR Apache-2.0','MIT','json',whole,'MIT OR Apache-2.0'),
        ('parenthesized','(MIT)','MIT','json',whole,'(MIT)'),
        ('bracket-spacing','(MIT)OR(Apache-2.0)','MIT','json',whole,'(MIT)OR(Apache-2.0)'),
        ('subexpression','MIT OR (BSD-2-Clause AND Apache-2.0)','BSD-2-Clause AND Apache-2.0','json',whole,'MIT OR (BSD-2-Clause AND Apache-2.0)'),
        ('spdx-question','MIT OR Apache-2.0','MIT','json','What is the SPDX expression of River?','MIT OR Apache-2.0'),
        ('duplicate-row','MIT OR Apache-2.0','MIT','duplicate',whole,''),
        ('duplicate-cell','MIT OR Apache-2.0','MIT','duplicate',whole,''),
        ('operator-only','MIT OR Apache-2.0','OR','json',whole,''),
        ('family-fragment','BSD-3-Clause OR MIT','BSD','json',whole,'BSD-3-Clause OR MIT'),
        ('single-id-suffix','GPL-2.0-only','GPL-2.0','json',whole,'GPL-2.0-only'),
        ('single-id-family','BSD-3-Clause','BSD','json',whole,'BSD-3-Clause'),
    ]
    try:
        for mode,expression,selected,form,query,expected in checks:
            calls.clear();payloads.clear()
            result=await engine(Settings(model_url='' if mode=='no-model' else base,search=False,browser=False,
                allow_private=True,max_depth=0,budget=12)).run(query,base+'/source')
            passed=result.answer==expected and (result.sources==[base+'/source'] if expected else not result.sources)
            if expected and mode!='no-model':
                verifications=[p for p,c in zip(payloads,calls) if c=='/verify']
                passed &= bool(verifications) and verifications[-1].get('proposed')==expected
            if mode=='no-model':passed &= not calls
            rows.append(dict(id=mode,passed=bool(passed),query=query,source_field=expression,stub_selection=selected,
                expected=expected,actual=result.answer,cpu_stub_calls=list(calls),cpu_stub_payloads=list(payloads),result=result.internal()))
    finally:await runner.cleanup()
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--baseline');ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    engine=Engine;revision='working-tree';hashes={}
    if args.baseline:engine,revision,hashes=load_engine(args.baseline)
    rows=asyncio.run(diagnose(engine))
    report=dict(scope=__doc__,revision=revision,baseline_source_sha256=hashes,
        diagnostic_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('app.py'),*sorted(Path('agent').glob('*.py'))]},
        passed=sum(r['passed'] for r in rows),total=len(rows),rows=rows)
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'],total=report['total'],failures=[r['id'] for r in rows if not r['passed']])))
    if report['passed']!=report['total']:sys.exit(1)
