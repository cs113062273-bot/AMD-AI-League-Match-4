"""Actual HTTP check of record scope/conflict guards with a deliberately permissive semantic service.

The service selects an actual first year span, preferring compact records, and
always verifies it. This isolates independent source-binding checks, not LLM accuracy.
"""
import argparse
import asyncio
from dataclasses import replace
import hashlib
import inspect
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.types import Settings
from agent.parser import parse_response
from agent.network import Response
from agent.planner import plan_query
from agent.candidates import extract,rank
from revision_engine import load_engine


async def diagnose(engine):
    hits=[];calls=[]
    def record(year,name='Elin Voss',tag='article',cell='div'):
        return '<'+tag+' data-year="'+year+'"><'+cell+'>'+year+'</'+cell+'><'+cell+'>'+name+'</'+cell+'><'+cell+'>Biochemist</'+cell+'></'+tag+'>'
    positive='<h2>Cedar Prize recipients</h2><h1>Honorees</h1>'+record('1987')
    variants=[
        ('valid-banner',positive,'1987'),
        ('valid-subsection','<h1>Honorees</h1><h2>Cedar Prize recipients</h2>'+record('1987'),'1987'),
        ('wrong-award','<h2>Merit Medal recipients</h2><h1>Honorees</h1>'+record('1987'),''),
        ('wrong-award-paragraph','<h2>Merit Medal recipients</h2><h1>Honorees</h1>'+record('1987',cell='p'),''),
        ('wrong-award-aria','<h2>Merit Medal recipients</h2><h1>Honorees</h1>'+record('1987',tag='div role="row"',cell='span').replace('</div role="row">','</div>'),''),
        ('wrong-award-aria-paragraph','<h2>Merit Medal recipients</h2><h1>Honorees</h1>'+record('1987',tag='p role="row"',cell='span').replace('</p role="row">','</p>'),''),
        ('sibling-scope','<h1>Honorees</h1><h2>Merit Medal recipients</h2>'+record('1987')+'<h2>Cedar Prize recipients</h2>'+record('1994'),'1994'),
        ('conflicting-records',positive+record('1994'),''),
        ('different-people',positive+record('1994','Marin Shaw'),'1987'),
        ('api-signature','<article><h2>API</h2><dl><dt class="sig">connect(timeout=30)</dt></dl></article>','30'),
    ]
    async def source(request):
        hits.append(request.path)
        return web.Response(text='<title>Ridge Council records</title>'+dict((name,body) for name,body,answer in variants)[request.match_info['name']],content_type='text/html')
    async def model(request):
        data=await request.json();calls.append(request.path)
        if request.path=='/verify':return web.json_response({'supported':True})
        passages=sorted(data.get('passages',[]),key=lambda p:not p.get('locator','').startswith('record['))
        for passage in passages:
            match=re.search(r'(?<!\d)\d{4}(?!\d)',passage['text'])
            if match:return web.json_response({'passage':passage['id'],'answer':match[0]})
        return web.json_response({'passage':-1,'answer':''})
    app=web.Application();app.router.add_get('/{name}',source);app.router.add_post('/{tail:.*}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);rows=[]
    try:
        for name,body,expected in variants:
            query='What is the default value of timeout parameter in connect?' if name=='api-signature' else 'In what year did Elin Voss receive the Cedar Prize?'
            calls.clear()
            result=await engine(Settings(model_url=base,allow_private=True,search=False,max_depth=0,budget=5)).run(query,base+'/'+name)
            passed=result.answer==expected and result.sources==([base+'/'+name] if expected else [])
            rows.append({'id':name,'passed':passed,'model_calls':list(calls),'result':result.internal()})
    finally:await runner.cleanup()
    # A low lexical score or unrelated higher metadata must not hide a conflict
    # in the actually selected record. Probe the current production guard directly.
    page=parse_response(Response('https://example.com/records',('<title>Records</title>'+positive+record('1994')).encode(),'text/html',status=200))
    plan=plan_query('In what year did Elin Voss receive the Cedar Prize?',page.url)
    candidates=rank(extract(plan,page),plan)
    low=[replace(candidate,score=1) for candidate in candidates]
    chosen=next(c for c in low if c.signals.get('structure')=='record')
    ambiguous=engine._ambiguous(low,plan,[page],chosen) if 'chosen' in inspect.signature(engine._ambiguous).parameters else engine._ambiguous(low,plan,[page])
    rows.append({'id':'selected-low-score-conflict','passed':ambiguous})
    return {'scope':__doc__,'passed':sum(row['passed'] for row in rows),'total':len(rows),'rows':rows}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--baseline');ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    engine=Engine;revision='working-tree';hashes={}
    if args.baseline:engine,revision,hashes=load_engine(args.baseline)
    report=asyncio.run(diagnose(engine));report.update(revision=revision,baseline_source_sha256=hashes,
        diagnostic_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'total':report['total'],'failures':[row['id'] for row in report['rows'] if not row['passed']]}))
