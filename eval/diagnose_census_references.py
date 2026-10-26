"""CPU census-reference planning and HTTP binding; authored controls, not accuracy."""
import argparse
import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.types import Settings
from revision_engine import load_engine

FORMS=['In the {year} census,','During the {year} census,','As of the {year} Census,',
    'As of {year} Census,','According to the {year} national census,']


def direct(engine):
    plan_query=engine.run.__globals__['plan_query'];rows=[]
    def check(name,query,year='',asof=''):
        plan=plan_query(query)
        actual=[plan.year,plan.as_of,plan.latest]
        expected=[year,asof,bool(asof)]
        rows.append(dict(id=name,passed=actual==expected,query=query,expected=expected,actual=actual))
    for year in ['1973','2004','2020']:
        for i,form in enumerate(FORMS):
            check('census-'+year+'-'+str(i),form.format(year=year)+' what was the population of Maple Harbour?',year)
        for i,prep in enumerate(['in the','during the','as of the','according to the']):
            check('trailing-'+year+'-'+str(i),f'What was the population of Maple Harbour {prep} {year} census?',year)
        check('generic-cutoff-'+year,f'As of {year}, what was the population of Maple Harbour?',asof=year+'-12-31')
        check('generic-year-'+year,f'What was the population of Maple Harbour in {year}?',year)
    check('calendar-cutoff','As of 2020-02-29, what was the population of Maple Harbour?',asof='2020-02-29')
    check('household-census','How many households were there in Maple Harbour, as of the 2000 census?','2000')
    check('separate-cutoff','As of 2020, what was the population according to the 2020 census?',asof='2020-12-31')
    for i,prep in enumerate(['not in the','excluding during the','not as of the','except according to the']):
        check('negated-'+str(i),f'What was the population of Maple Harbour, {prep} 2020 census?')
    check('multi-census','What was the population in the 2004 census or in the 2020 census?')
    check('version-not-year','What was the population in the 2020.2 census?')
    check('url-not-constraint','What was the population? See https://example.org/in-the-2020-census')
    check('quoted-title','What is the title of the book "In the 2020 census"?')
    check('backtick-title','What is the title of the book `In the 2020 census`?')
    check('quoted-unrelated-year','What was the population in the 2020 census? Ignore the title "City of 2004".')
    # The last case stays unplanned: multiple supplied calendar years are
    # outside this census helper. The full question remains available.
    return rows


async def transport(engine):
    rows=[];base='';selected='';calls=[]
    body='<h1>Maple Harbour population in 2004 and 2020</h1><table><tr><th>Year</th><th>Town</th><th>Population</th></tr>'\
        '<tr><td>2004</td><td>Maple Harbour</td><td>361</td></tr>'\
        '<tr><td>2020</td><td>Maple Harbour</td><td>617</td></tr></table>'
    async def source(request):
        content=body.replace('population','households').replace('Population','Households').replace('2004','1990').replace('2020','2000') if request.path=='/households' else body
        return web.Response(text=content,content_type='text/html')
    async def model(request):
        data=await request.json();calls.append(request.path)
        if request.path=='/verify':return web.json_response({'supported':True})
        passage=next((p for p in data.get('passages',[]) if selected in p['text']),None)
        return web.json_response({'passage':passage['id'] if passage else -1,'answer':selected if passage else ''})
    app=web.Application();app.router.add_get('/population',source);app.router.add_get('/households',source)
    app.router.add_post('/{tail:.*}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    try:
        for i,form in enumerate(FORMS[:4]):
            query=form.format(year='2020')+' what was the population of Maple Harbour?'
            for selected,expected in [('617','617'),('361','')]:
                calls.clear()
                result=await engine(Settings(model_url=base,search=False,allow_private=True,max_depth=0,budget=4)).run(query,base+'/population')
                rows.append(dict(id=f'http-stub-{i}-{selected}',passed=result.answer==expected
                    and result.sources==([base+'/population'] if expected else []),
                    expected=expected,actual=result.answer,calls=list(calls),result=result.internal()))
            calls.clear()
            result=await engine(Settings(model_url='',search=False,allow_private=True,max_depth=0,budget=4)).run(query,base+'/population')
            rows.append(dict(id=f'http-no-model-{i}',passed=result.answer=='617'
                and result.sources==[base+'/population'] and not calls,
                expected='617',actual=result.answer,calls=list(calls),result=result.internal()))
        calls.clear()
        result=await engine(Settings(model_url='',search=False,allow_private=True,max_depth=0,budget=4)).run(
            'How many households were there in Maple Harbour, as of the 2000 census?',base+'/households')
        rows.append(dict(id='http-no-model-households',passed=result.answer=='617'
            and result.sources==[base+'/households'] and not calls,
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
