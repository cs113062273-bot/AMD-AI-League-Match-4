"""CPU-only year/field binding over authored HTML tables and adversarial HTTP stubs.

These are structural regression and metamorphic checks, not unseen accuracy.
No real assessment rows, model weights, browser or public network are used.
"""
import argparse
import asyncio
import hashlib
from html import escape
import json
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.network import Response
from agent.types import Candidate,Settings
from revision_engine import load_engine


def table(headers,rows,title='Maple Harbour records'):
    return '<h1>'+escape(title)+'</h1><table><tr>'+''.join('<th>'+escape(x)+'</th>' for x in headers)+\
        '</tr>'+''.join('<tr>'+''.join('<td>'+escape(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</table>'


def direct(engine):
    g=engine.run.__globals__;checks=[]

    def check(name,html,query,answer,expected,cell_value=None):
        url='https://example.org/table-year-check'
        page=g['parse_response'](Response(url,html.encode(),'text/html',status=200))
        plan=g['plan_query'](query,url)
        passages=[p for p in page.passages if p.kind=='table' and answer in p.text]
        if cell_value is not None:
            passages=[p for p in page.passages if p.kind=='cell' and p.value==cell_value]
        assert passages,(name,answer)
        outcomes=[]
        for passage in passages:
            if answer not in passage.text:continue
            c=Candidate(answer,answer,url,passage.text,passage.label,passage.section,plan.kind,10)
            outcomes.append(g['verify'](c,plan,[page]))
        actual=any(outcomes)
        checks.append(dict(id=name,passed=actual==expected,expected=expected,actual=actual,
            kind=plan.kind,year=plan.year,answer=answer))

    # Relabel entities, years, quantities and column order without changing
    # the structural requirement. This is authored metamorphic coverage.
    rng=random.Random(20261023)
    fields=[('Population','617','839'),('Enrollment','52','68'),
        ('Director','Mira Vale','Orin North'),('Email','alpha@example.org','beta@example.org')]
    for i,(field,good,bad) in enumerate(fields):
        first,second=sorted(rng.sample(range(1950,2025),2))
        query=f'What was the {field.lower()} of Maple Harbour in {first}?'
        for reverse in [False,True]:
            labels=[field+' '+str(first),field+' '+str(second)]
            values=[good,bad]
            if reverse:labels.reverse();values.reverse()
            html=table(['Town',*labels],[['Maple Harbour',*values]],f'{first} and {second} records')
            for value,expected in [(good,True),(bad,False)]:
                check(f'wide-{i}-{reverse}-{expected}',html,query,value,expected)
            # A cell's context includes its entire row; its neighbor's year
            # must not authorize the value selected from the other column.
            check(f'wide-cell-{i}-{reverse}',html,query,bad,False,cell_value=bad)
        for year_label in ['Year','Census year','Observation year','Reporting year','Calendar year']:
            html=table([year_label,'Town',field],[[str(first),'Maple Harbour',good],
                [str(second),'Maple Harbour',bad]],f'{first} and {second} records')
            check(f'row-{i}-{year_label}-right',html,query,good,True)
            check(f'row-{i}-{year_label}-wrong',html,query,bad,False)

    query='What was the population of Maple Harbour in 2004?'
    for bad in ['unknown','2004 / 2014','2014']:
        html=table(['Year','Population'],[[bad,'839']],'Population in 2004 and 2014')
        check('row-unproven-'+bad,html,query,'839',False)
    html=table(['Town','Population 2004 / 2014'],[['Maple Harbour','839']])
    check('combined-year-column',html,query,'839',False)
    html=table(['Town','2004','2014'],[['Maple Harbour','617','839']])
    check('bare-year-right',html,query,'617',True)
    check('bare-year-wrong',html,query,'839',False)
    html=table(['Town','Population 2004','Population 2014'],[['Maple Harbour','617','617']])
    check('same-value-is-supported',html,query,'617',True)
    html=table(['Town','Population 2004','Families 2014'],[['Maple Harbour','617','142']])
    check('other-field-year-does-not-veto',html,query,'617',True)
    check('other-field-still-rejected',html,query,'142',False)
    for label in ['Birth year','Update year','Year established','Fiscal year']:
        html=table(['Town',label,'Population'],[['Maple Harbour','2014','617']],
            'Population in 2004')
        check('other-year-meaning-'+label,html,query,'617',True)
    # An exact year in the question does not turn a title into row evidence.
    html=table(['Year','Town','Population'],[['2014','Maple Harbour','839']],
        'Population in 2004')
    check('wrong-year-under-right-heading',html,query,'839',False)
    html=table(['Year','Town','Population','Population 2014'],
        [['2004','Maple Harbour','617','839']],'Population records')
    check('row-year-binds-undated-column',html,query,'617',True)
    check('column-year-overrides-row-for-that-field',html,query,'839',False)
    # Preserve semantic handling for questions outside a single point year.
    html=table(['Town','Population 2004','Population 2014'],[['Maple Harbour','617','839']])
    for name,question in [('timeless','What is the population of Maple Harbour?'),
        ('comparison','What was the population of Maple Harbour in 2004 and 2014?'),
        ('asof','What was the population of Maple Harbour as of 2014?')]:
        check('outside-'+name,html,question,'617',True)
    return checks


async def transport(engine):
    rows=[];calls=[];selected='';base=''
    body=table(['Town','Population 2014','Population 2004'],[['Maple Harbour','839','617']],
        'Population in 2004 and 2014')
    row_body=table(['Year','Town','Population'],[['2014','Maple Harbour','839'],
        ['2004','Maple Harbour','617']],'Population in 2004 and 2014')

    async def source(request):
        return web.Response(text=row_body if request.path=='/row-table' else body,content_type='text/html')
    async def model(request):
        data=await request.json();calls.append(request.path)
        if request.path=='/verify':return web.json_response({'supported':True})
        passage=next((p for p in data.get('passages',[]) if selected in p['text']),None)
        return web.json_response({'passage':passage['id'] if passage else -1,
            'answer':selected if passage else ''})

    app=web.Application();app.router.add_get('/table',source);app.router.add_get('/row-table',source)
    app.router.add_post('/{tail:.*}',model)
    runner=web.AppRunner(app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    try:
        for selected,expected in [('617','617'),('839','')]:
            calls.clear()
            result=await engine(Settings(model_url=base,search=False,allow_private=True,
                max_depth=0,budget=4)).run('What was the population of Maple Harbour in 2004?',base+'/table')
            rows.append(dict(id='http-selected-'+selected,passed=result.answer==expected
                and result.sources==([base+'/table'] if expected else []),
                expected=expected,actual=result.answer,model_stub_calls=list(calls),result=result.internal()))
        calls.clear()
        result=await engine(Settings(model_url='',search=False,allow_private=True,
            max_depth=0,budget=4)).run('What was the population of Maple Harbour in 2004?',base+'/row-table')
        rows.append(dict(id='http-deterministic-row-year',passed=result.answer=='617'
            and result.sources==[base+'/row-table'] and not calls,
            expected='617',actual=result.answer,model_stub_calls=list(calls),result=result.internal()))
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
    print(json.dumps(dict(passed=report['passed'],total=report['total'],
        failures=[r['id'] for r in rows if not r['passed']])))
    if report['passed']!=report['total']:sys.exit(1)
