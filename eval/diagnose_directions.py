"""Independent geographic-boundary guard checks and actual HTTP integration.

The controlled semantic endpoint always supports a literal selection. These
checks isolate source guards, not LLM or public-web accuracy.
"""
import argparse
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.types import Candidate,Page,Passage,Settings
from agent.planner import plan_query
from agent.network import Response
from agent.parser import parse_response
from revision_engine import load_engine

QUERY='What river borders the west of Briarton?'
PARALLEL='Briarton is bounded on the west by Pine River and on the south by Cedar River.'
CASES=[
    ('nearby',QUERY,'Pine River is near Briarton.','','Pine River',False),
    ('direct-west',QUERY,'Pine River forms the western boundary of Briarton.','','Pine River',True),
    ('opposite',QUERY,'Pine River forms the southern boundary of Briarton.','','Pine River',False),
    ('parallel-good',QUERY,PARALLEL,'','Pine River',True),
    ('parallel-wrong',QUERY,PARALLEL,'','Cedar River',False),
    ('other-sentence',QUERY,'Pine River is near Briarton. Cedar River forms the western boundary.','','Pine River',False),
    ('other-clause',QUERY,'Pine River is near Briarton; Cedar River forms the western boundary.','','Pine River',False),
    ('comma-with',QUERY,'Pine River is near Briarton, with Cedar River forming its western boundary.','','Pine River',False),
    ('proper-name',QUERY,'West River is near Briarton.','','West River',False),
    ('proper-name-positive',QUERY,'West River forms the western boundary of Briarton.','','West River',True),
    ('heading',QUERY,'Pine River','Geography > Western boundary','Pine River',True),
    ('heading-opposite',QUERY,'Pine River forms the southern boundary.','Geography > Western boundary','Pine River',False),
    ('heading-proper-name',QUERY,'Pine River','West River parks','Pine River',False),
    ('north','Which river forms the northern boundary of Briarton?','Pine River forms the northerly boundary of Briarton.','','Pine River',True),
    ('east','Which river forms the eastern boundary of Briarton?','Pine River forms the easterly boundary of Briarton.','','Pine River',True),
    ('south','What river borders the south of Briarton?','Pine River forms the southern boundary of Briarton.','','Pine River',True),
    ('repeated-conflict',QUERY,'Pine River forms the western boundary. Pine River forms the southern boundary.','','Pine River',False),
    ('relative-clause',QUERY,'Pine River, which forms the western boundary of Briarton, is navigable.','','Pine River',True),
    # Out-of-scope means the boundary guard must defer to semantic verification;
    # True here is not a claim that the passage answers these questions.
    ('proper-location-query','What river borders the West Bank?','Pine River is near the West Bank.','','Pine River',True),
    ('non-boundary-query','What river flows west of Briarton?','Pine River is near Briarton.','','Pine River',True),
    ('multiple-directions','Which rivers form the north and west boundaries of Briarton?','Pine River is near Briarton.','','Pine River',True),
]


def direct_checks(engine):
    verify=engine.run.__globals__['verify'];planner=engine.run.__globals__['plan_query'];rows=[]
    for name,query,text,section,answer,expected in CASES:
        url='https://example.org/'+name;passage=Passage(text,section=section)
        page=Page(url,title='Briarton geography',passages=[passage]);plan=planner(query,url)
        chosen=Candidate(answer,answer,url,text,section=section,kind=plan.kind,score=8)
        actual=verify(chosen,plan,[page])
        rows.append(dict(id=name,passed=actual==expected,expected=expected,actual=actual))
    report=json.loads((ROOT/'benchmarks/external-disjoint12-20261023-first.json').read_text(encoding='utf-8'))
    row=next(row for row in report['rows'] if row['id']=='simpleqa-779')
    path=ROOT/row['capture_path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==row['capture_sha256']
    snapshot=json.loads(path.read_text(encoding='utf-8'))
    selected=Candidate(**row['result']['diagnostics']['model_selections'][0])
    response=dict(snapshot[selected.source]);response['body']=base64.b64decode(response.pop('body_base64'))
    page=parse_response(Response(**response));plan=planner(row['result']['diagnostics']['plan']['question'],selected.source)
    actual=verify(selected,plan,[page])
    rows.append(dict(id='actual-goldsboro-selection',passed=not actual,expected=False,actual=actual,capture_sha256=row['capture_sha256']))
    return rows


async def http_checks(engine):
    selected='';calls=[]
    cases={row[0]:row for row in CASES if row[0] in {'nearby','direct-west','opposite','parallel-wrong','heading','proper-name'}}
    async def source(request):
        name,query,text,section,answer,expected=cases[request.match_info['name']]
        return web.Response(text='<title>Briarton geography</title>'+('<h2>'+section+'</h2>' if section else '')+'<p>'+text+'</p>',content_type='text/html')
    async def model(request):
        data=await request.json();calls.append(request.path)
        if request.path=='/verify':return web.json_response({'supported':True})
        answer=cases[selected][4]
        passage=next((p for p in data.get('passages',[]) if answer in p['text']),None)
        return web.json_response({'passage':passage['id'] if passage else -1,'answer':answer if passage else ''})
    app=web.Application();app.router.add_get('/{name}',source);app.router.add_post('/{tail:.*}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);rows=[]
    try:
        for selected,case in cases.items():
            calls.clear();name,query,text,section,answer,supported=case
            result=await engine(Settings(model_url=base,allow_private=True,search=False,max_depth=0,budget=5)).run(query,base+'/'+name)
            expected=answer if supported else ''
            passed=result.answer==expected and result.sources==([base+'/'+name] if expected else [])
            rows.append(dict(id='http-'+name,passed=passed,model_calls=list(calls),result=result.internal()))
    finally:await runner.cleanup()
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('1285dc8')
    before=direct_checks(old)+asyncio.run(http_checks(old));after=direct_checks(Engine)+asyncio.run(http_checks(Engine))
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,before=before,after=after,
        before_passed=sum(r['passed'] for r in before),after_passed=sum(r['passed'] for r in after),total=len(after),
        wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
        losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
        production_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'agent').glob('*.py')})
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    if not all(r['passed'] for r in after):sys.exit(1)
