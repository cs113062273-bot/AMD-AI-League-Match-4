"""CPU population/year role controls; authored variants and local HTTP, not accuracy."""
import argparse
import asyncio
from dataclasses import asdict
import hashlib
from html import escape
import json
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.network import Response
from agent.types import Candidate,Settings
from revision_engine import load_engine

QUERY='What was the population of Maple Harbour at the 2004 census?'
TEXT='At the 2004 census, its population was 617, in 142 families. In 2014 its population was 839.'


def direct(engine):
    g=engine.run.__globals__;rows=[]
    plans=[('census',QUERY,'number','2004'),
        ('ordinary-year','What was the population of Maple Harbour in 2004?','number','2004'),
        ('inhabitants','How many inhabitants lived in Maple Harbour at the 2004 census?','number','2004'),
        ('multiple-censuses','What was the population at the 2004 census or at the 2014 census?','number',''),
        ('negated-census','What was the population, not at the 2004 census?','number',''),
        ('density','What was the population density of Maple Harbour in 2004?','text','2004'),
        ('growth','What was the population growth rate of Maple Harbour in 2004?','text','2004'),
        ('percentage','What was the population percentage in Maple Harbour?','percentage',''),
        ('label','What is the population label of this chart?','text',''),
        ('population-type','What population of cells produced the response in 2004?','text','2004'),
        ('contraction',"What's the population of Maple Harbour in 2004?",'number','2004'),
        ('curly-contraction','What\u2019s the population of Maple Harbour in 2004?','number','2004'),
        ('not-a-calendar-year','What was the population at the 2004.2 census?','number',''),
        ('url-not-a-census-year','What was the population? https://example.org/at-the-2004-census','number',''),
        ('who','Who counted the population in 2004?','text','2004')]
    for name,query,kind,year in plans:
        plan=g['plan_query'](query)
        rows.append(dict(id='plan-'+name,passed=(plan.kind,plan.year)==(kind,year),
            expected=[kind,year],actual=[plan.kind,plan.year]))

    def check(name,text,values,query=QUERY):
        url='https://example.org/population'
        html='<h1>Maple Harbour</h1><p>'+escape(text)+'</p>'
        page=g['parse_response'](Response(url,html.encode(),'text/html',status=200))
        passage=next(p for p in page.passages if p.kind=='prose' and text in p.text)
        plan=g['plan_query'](query,url)
        for value,expected in values:
            candidate=Candidate(value,value,url,passage.text,passage.label,passage.section,plan.kind,10)
            actual=g['verify'](candidate,plan,[page])
            rows.append(dict(id=name+'-'+value,passed=actual==expected,expected=expected,actual=actual))

    check('main',TEXT,[('617',True),('142',False),('2004',False),('839',False),('2014',False)])
    check('subject','In 2004, the population of Maple Harbour was 617, in 142 families.',
        [('617',True),('142',False),('2004',False)])
    check('year-after','The population of Maple Harbour was 617 in 2004.',[('617',True),('2004',False)])
    check('coordinated','In 2004 its population was 617, and in 2014 its population was 839.',
        [('617',True),('839',False)])
    check('updated-year','In 2014 its population was 839. The page was updated in 2004.',[('839',False)])
    check('residents','There were 617 residents and 142 households in 2004.',
        [('617',True),('142',False),('2004',False)])
    check('label-years','Population (2004): 617; Population (2014): 839.',
        [('617',True),('839',False),('2004',False),('2014',False)])
    check('same-number-two-roles','At the 2004 census, its population was 617, in 617 families.',[('617',True)])
    check('population-is-year-like','At the 2004 census, its population was 2004, in 142 families.',
        [('2004',True),('142',False)])
    check('four-digit-families','At the 2004 census, its population was 7617, in 1423 families.',
        [('7617',True),('1423',False),('2004',False)])
    check('comma-grouping','At the 2004 census, its population was 1,234, in 1,111 families.',
        [('1,234',True),('1,111',False)])
    check('no-population','At the 2004 census, the population was unknown, in 142 families.',
        [('142',False),('2004',False)])
    check('unknown-wording','The 2004 census counted 617 locals.',[('617',True)])
    # Do not promote a limited role parser into a universal positive witness.
    # Unclassified literals and unresolved multi-year clauses retain semantics.
    check('unclassified','At the 2004 census, the area was 64 square kilometres.',[('64',True)])
    check('unresolved-years','In 2004 and 2014 the population was 617 and 839 respectively.',
        [('617',True),('839',True)])
    check('non-population-question',TEXT,[('142',True)],
        'What was the household count of Maple Harbour in 2004?')
    check('density-not-count',TEXT,[('142',True)],
        'What was the population density of Maple Harbour in 2004?')
    check('irrelevant-url-year',TEXT,[('142',False),('617',True)],
        QUERY+' See https://example.org/archive/2014')
    # Authored metamorphic substitutions: no new factual questions or gold.
    rng=random.Random(940222)
    for i in range(8):
        year,later=sorted(rng.sample(range(1940,2025),2))
        population,families,other=rng.sample(range(100,950),3)
        query=f'What was the population of Cedar Village {i} at the {year} census?'
        text=f'At the {year} census, its population was {population}, in {families} families. In {later} its population was {other}.'
        check('substitution-'+str(i),text,[(str(population),True),(str(families),False),
            (str(other),False),(str(year),False)],query)
    return rows


async def transport(engine):
    rows=[];selected='';calls=[]
    async def source(request):
        return web.Response(text='<h1>Maple Harbour</h1><p>'+TEXT+'</p>',content_type='text/html')
    async def model(request):
        data=await request.json();calls.append(request.path)
        if request.path=='/verify':return web.json_response({'supported':True})
        passage=next((p for p in data.get('passages',[]) if selected in p['text']),None)
        return web.json_response({'passage':passage['id'] if passage else -1,'answer':selected if passage else ''})
    app=web.Application();app.router.add_get('/population',source);app.router.add_post('/{tail:.*}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    try:
        for selected in ['617','142','2004','839']:
            calls.clear();expected=selected if selected=='617' else ''
            result=await engine(Settings(model_url=base,search=False,allow_private=True,max_depth=0,budget=4)).run(QUERY,base+'/population')
            rows.append(dict(id='http-stub-'+selected,passed=result.answer==expected
                and result.sources==([base+'/population'] if expected else []),
                expected=expected,actual=result.answer,calls=list(calls),result=result.internal()))
        calls.clear()
        result=await engine(Settings(model_url='',search=False,allow_private=True,max_depth=0,budget=4)).run(QUERY,base+'/population')
        rows.append(dict(id='http-no-model',passed=result.answer=='617'
            and result.sources==[base+'/population'] and not calls,
            expected='617',actual=result.answer,calls=list(calls),result=result.internal()))
    finally:await runner.cleanup()
    return rows


async def diagnose(engine):return direct(engine)+await transport(engine)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--baseline');ap.add_argument('--out',required=True)
    args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    engine=Engine;revision='working-tree';hashes={}
    if args.baseline:engine,revision,hashes=load_engine(args.baseline)
    rows=asyncio.run(diagnose(engine))
    report=dict(scope=__doc__,revision=revision,baseline_source_sha256=hashes,
        diagnostic_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path('app.py'),*sorted(Path('agent').glob('*.py'))]},
        passed=sum(r['passed'] for r in rows),total=len(rows),rows=rows)
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'],total=report['total'],failures=[r['id'] for r in rows if not r['passed']])))
    if report['passed']!=report['total']:sys.exit(1)
