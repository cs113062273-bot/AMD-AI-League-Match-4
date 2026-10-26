"""Dated-event literal witnesses, including actual unsupported selection and HTTP.

The HTTP semantic service always supports a chosen literal, isolating the guard.
This is development source-binding evidence, not model or public-web accuracy.
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
from agent.network import Response
from agent.parser import parse_response
from agent.types import Page,Passage,Candidate,Settings
from revision_engine import load_engine

QUERY='What is the first and last name of the person whom Orin Vale married in 1998?'
CASES=[
    ('dated',QUERY,'Orin Vale married Mira Chen in 1998.','','prose',True),
    ('undated',QUERY,'Orin Vale is married to Mira Chen.','','prose',False),
    ('period-question',QUERY[:-1]+'.','Orin Vale is married to Mira Chen.','','prose',False),
    ('period-heading',QUERY,'Orin Vale | Mira Chen','Marriages > 1998.','record',True),
    ('wrong-year',QUERY,'Orin Vale married Mira Chen in 2001.','','prose',False),
    ('unrelated-date',QUERY,'Orin Vale married Mira Chen. Orin published a book in 1998.','','prose',False),
    ('other-person',QUERY,'Orin Vale married Mira Chen. Marin Shaw married Dana Wood in 1998.','','prose',False),
    ('semicolon',QUERY,'Orin Vale married Mira Chen; a book was published in 1998.','','prose',False),
    ('same-clause-other-event',QUERY,'Orin Vale married Mira Chen in 2001, and published a book in 1998.','','prose',False),
    ('year-before',QUERY,'In 1998, Orin Vale married Mira Chen.','','prose',True),
    ('birth-year',QUERY,'Mira Chen was born in 1998 and later married Orin Vale.','','prose',False),
    ('separate-birth',QUERY,'Mira Chen was born in 1970. Orin Vale married Mira Chen in 1998.','','prose',True),
    ('two-events',QUERY,'Mira Chen was born in 1970 and married Orin Vale in 1998.','','prose',True),
    ('adjacent-coreference',QUERY,'Orin Vale married Mira Chen. Their wedding took place in 1998.','','prose',True),
    ('wrong-coreference-year',QUERY,'Orin Vale married Mira Chen. Their wedding took place in 2001.','','prose',False),
    ('distant-year',QUERY,'Orin Vale married Mira Chen. They lived abroad. Their wedding took place in 1998.','','prose',False),
    ('heading-year',QUERY,'Orin Vale | Mira Chen','Marriages > 1998','record',True),
    ('wrong-heading',QUERY,'Orin Vale | Mira Chen','Marriages > 2001','record',False),
    ('record-year',QUERY,'1998 | Orin Vale | Mira Chen','Marriages','record',True),
    ('generic-year',QUERY,'1998 | Orin Vale | Mira Chen','Directory','record',False),
    ('birth-query','Who was born in 1998?','Mira Chen was born in 1998.','','prose',True),
    ('birth-undated','Who was born in 1998?','Mira Chen is a researcher.','','prose',False),
    ('award-query','Who won the Cedar Prize in 1998?','Mira Chen won the Cedar Prize in 1998.','','prose',True),
    ('award-undated','Who won the Cedar Prize in 1998?','Mira Chen won the Cedar Prize.','','prose',False),
    ('release-query','Who published River Notes in 1998?','Mira Chen published River Notes in 1998.','','prose',True),
    ('release-wrong-event','Who published River Notes in 1998?','Mira Chen published River Notes and died in 1998.','','prose',False),
    ('foundation-query','Who founded Ridge Works in 1998?','Mira Chen founded Ridge Works in 1998.','','prose',True),
    ('ordinary-person','Who is Orin Vale married to?','Orin Vale is married to Mira Chen.','','prose',True),
    ('timeless-field','Who is the author of River Notes?','Mira Chen is the author of River Notes.','','prose',True),
    # These are deliberately outside this guard's single-year/single-event
    # scope; independent semantics must decide whether they are supported.
    ('multiple-events','Who was born in 1998 and married in 2001?','Mira Chen is a researcher.','','prose',True),
]


def direct(engine):
    g=engine.run.__globals__;rows=[]
    for name,query,text,section,kind,expected in CASES:
        p=Passage(text,section=section,kind=kind);page=Page('https://example.org/'+name,title='Biography',passages=[p]);plan=g['plan_query'](query,page.url)
        chosen=Candidate('Mira Chen','Mira Chen',page.url,p.text,section=section,kind=plan.kind,score=8)
        actual=g['verify'](chosen,plan,[page])
        rows.append(dict(id=name,passed=actual==expected,expected=expected,actual=actual))
    report=json.loads((ROOT/'benchmarks/expansion-20261023-live.json').read_text(encoding='utf-8'))
    row=next(row for row in report['rows'] if row['id']=='simpleqa-37');capture=ROOT/row['capture_path']
    assert hashlib.sha256(capture.read_bytes()).hexdigest()==row['capture_sha256']
    selection=Candidate(**row['result']['diagnostics']['model_selections'][0]);data=dict(json.loads(capture.read_text(encoding='utf-8'))[selection.source])
    data['body']=base64.b64decode(data.pop('body_base64'));page=parse_response(Response(**data))
    plan=g['plan_query'](row['result']['diagnostics']['plan']['question'],page.url)
    actual=g['verify'](selection,plan,[page])
    rows.append(dict(id='actual-missing-marriage-year',passed=not actual,actual=actual,capture_sha256=row['capture_sha256']))
    calendar=g['verify'].__globals__['calendar_years']
    for name,text,expected in [('sentence-year','Mira married in 1998.',['1998']),
        ('version','version 1998.2',[]),('version-label','release 1998.beta',[]),
        ('document-id','PEP 1998 and RFC 1999',[]),('two-years','Born in 1970, married in 1998.',['1970','1998'])]:
        actual=calendar(text);rows.append(dict(id='calendar-'+name,passed=actual==expected,actual=actual,expected=expected))
    return rows


async def http(engine):
    chosen='';calls=[];cases={row[0]:row for row in CASES if row[0] in {'dated','undated','unrelated-date','adjacent-coreference','heading-year','birth-year'}}
    async def source(request):
        name,q,text,section,kind,expected=cases[request.match_info['name']]
        return web.Response(text='<title>Orin Vale biography</title>'+('<h2>'+section+'</h2>' if section else '')+'<p>'+text+'</p>',content_type='text/html')
    async def model(request):
        data=await request.json();calls.append(request.path)
        if request.path=='/verify':return web.json_response({'supported':True})
        passage=next((p for p in data.get('passages',[]) if 'Mira Chen' in p['text']),None)
        return web.json_response({'passage':passage['id'] if passage else -1,'answer':'Mira Chen' if passage else ''})
    app=web.Application();app.router.add_get('/{name}',source);app.router.add_post('/{tail:.*}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);rows=[]
    try:
        for chosen,case in cases.items():
            calls.clear();name,q,text,section,kind,supported=case
            # The heading-year record control is covered directly; its HTML
            # source needs an actual compact record rather than ordinary p.
            if kind=='record':continue
            result=await engine(Settings(model_url=base,search=False,allow_private=True,max_depth=0,budget=5)).run(q,base+'/'+name)
            expected='Mira Chen' if supported else ''
            rows.append(dict(id='http-'+name,passed=result.answer==expected and result.sources==([base+'/'+name] if expected else []),model_calls=list(calls),result=result.internal()))
    finally:await runner.cleanup()
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('f6b7d0b');before=direct(old)+asyncio.run(http(old));after=direct(Engine)+asyncio.run(http(Engine))
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,before=before,after=after,
        before_passed=sum(r['passed'] for r in before),after_passed=sum(r['passed'] for r in after),total=len(after),
        wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
        losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
        production_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'agent').glob('*.py')})
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    if not all(r['passed'] for r in after):sys.exit(1)
