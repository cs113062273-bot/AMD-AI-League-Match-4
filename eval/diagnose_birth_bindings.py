"""CPU/HTTP checks of birth-year bindings from actual parsed structured fields.

A controlled semantic endpoint copies an existing name and says supported,
isolating the literal guard. No GPU/model weights/browser or accuracy claim.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.network import Response
from agent.types import Candidate,Settings
from revision_engine import load_engine


CASES=[
    ('camel-date',{'name':'Mira Vale','birthDate':'1998-03-04','lastUpdated':'2026-01-01'},True),
    ('underscore-date',{'name':'Mira Vale','date_of_birth':'04/03/1998'},True),
    ('spaced-date',{'name':'Mira Vale','Date of Birth':'March 4, 1998'},True),
    ('upper-key',{'name':'Mira Vale','BIRTHDATE':'1998-03-04'},True),
    ('year-field',{'name':'Mira Vale','birthYear':'1998','lastUpdated':'2026'},True),
    ('year-of-birth',{'name':'Mira Vale','yearOfBirth':'1998'},True),
    ('dob',{'name':'Mira Vale','DOB':'1998-03-04'},True),
    ('explicit-born',{'name':'Mira Vale','Born':'1998','lastUpdated':'2026'},True),
    ('wrong-born-update',{'name':'Mira Vale','Born':'1970','lastUpdated':'1998'},False),
    ('wrong-date-update',{'name':'Mira Vale','birthDate':'1970-03-04','lastUpdated':'1998-01-01'},False),
    ('wrong-year-field',{'name':'Mira Vale','birthYear':'1970','lastUpdated':'1998'},False),
    ('missing-birth-field',{'name':'Mira Vale','lastUpdated':'1998'},False),
    ('empty-date',{'name':'Mira Vale','birthDate':'','lastUpdated':'1998'},False),
    ('unknown-date',{'name':'Mira Vale','birthDate':'unknown','lastUpdated':'1998'},False),
    ('conflicting-date-fields',{'name':'Mira Vale','Born':'1998','birthDate':'1970-03-04'},False),
    ('matching-date-fields',{'name':'Mira Vale','Born':'1998','birthDate':'1998-03-04'},True),
    ('date-range',{'name':'Mira Vale','birthDate':'1970 or 1998'},False),
    ('version-not-year',{'name':'Mira Vale','birthDate':'1998.2'},False),
    ('other-entity',{'name':'Mira Vale','lastUpdated':'1998','child':{'name':'Rowan North','birthDate':'1998-03-04'}},False),
    ('child-no-inheritance',{'name':'Rowan North','Born':'1998','child':{'name':'Mira Vale','lastUpdated':'1998'}},False),
    ('local-biography',{'name':'Mira Vale','biography':'Mira Vale was born in 1998.'},True),
    ('long-local-biography',{'name':'Mira Vale','biography':'Mira Vale was born in 1998. '+'She writes about nature. '*12},True),
]


def direct(engine):
    g=engine.run.__globals__;rows=[]
    for name,data,expected in CASES:
        for content_type in ['application/json','text/html']:
            body=json.dumps(data)
            if content_type=='text/html':body='<script type="application/ld+json">'+body+'</script>'
            page=g['parse_response'](Response('https://example.org/'+name,body.encode(),content_type,status=200))
            passage=next(p for p in page.passages if p.label=='biography') if name=='long-local-biography' else next(p for p in page.passages if p.value=='Mira Vale' and p.label.split('.')[-1]=='name')
            query='What is the full name of the writer born in 1998?' if name=='long-local-biography' else 'Who was born in 1998?'
            plan=g['plan_query'](query,page.url)
            candidate=Candidate('Mira Vale','Mira Vale',page.url,passage.text,passage.label,passage.section,kind=plan.kind,score=10)
            actual=g['verify'](candidate,plan,[page])
            rows.append(dict(id=name+('-jsonld' if content_type=='text/html' else '-json'),passed=actual==expected,
                             expected=expected,actual=actual,evidence=passage.text,bindings=passage.qualifiers.get('bindings')))
    # Out-of-band qualifiers cannot supply a date absent from the chosen text.
    page=g['parse_response'](Response('https://example.org/visible',json.dumps({'name':'Mira Vale','birthDate':'1998-03-04'}).encode(),'application/json',status=200))
    p=next(p for p in page.passages if p.label=='name');p.text='name: Mira Vale'
    plan=g['plan_query']('Who was born in 1998?',page.url)
    candidate=Candidate('Mira Vale','Mira Vale',page.url,p.text,p.label,p.section,kind=plan.kind,score=10)
    rows.append(dict(id='date-must-be-in-literal-passage',passed=not g['verify'](candidate,plan,[page])))
    # Timeless name questions still need no birth witness.
    plan=g['plan_query']('Who is Mira Vale?',page.url)
    rows.append(dict(id='timeless-unchanged',passed=g['verify'](candidate,plan,[page])))
    return rows


async def http(engine):
    mode='';calls=[];rows=[]
    variants={name:(data,expected) for name,data,expected in CASES if name in {'camel-date','explicit-born','wrong-born-update','conflicting-date-fields','other-entity'}}
    async def source(request):return web.json_response(variants[mode][0])
    async def model(request):
        data=await request.json();calls.append(request.path)
        if request.path=='/verify':return web.json_response({'supported':True})
        p=next((p for p in data['passages'] if p['text'].startswith('name: Mira Vale')),None)
        return web.json_response({'passage':p['id'] if p else -1,'answer':'Mira Vale' if p else ''})
    app=web.Application();app.router.add_get('/source',source);app.router.add_post('/{tail:.*}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    try:
        for mode,(data,expected) in variants.items():
            calls.clear();result=await engine(Settings(model_url=base,search=False,allow_private=True,max_depth=0,budget=5)).run('Who was born in 1998?',base+'/source')
            passed=result.answer==('Mira Vale' if expected else '') and result.sources==([base+'/source'] if expected else [])
            if expected:passed=passed and calls==['/select','/verify']
            else:passed=passed and '/verify' not in calls
            rows.append(dict(id='http-'+mode,passed=passed,calls=list(calls),result=result.internal()))
    finally:await runner.cleanup()
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('a85ec14')
    before=direct(old)+asyncio.run(http(old));after=direct(Engine)+asyncio.run(http(Engine))
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,before=before,after=after,
                before_passed=sum(r['passed'] for r in before),after_passed=sum(r['passed'] for r in after),total=len(after),
                wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
                losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
                evidence_sha256=hashlib.sha256((ROOT/'agent/evidence.py').read_bytes()).hexdigest())
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    if not all(r['passed'] for r in after):sys.exit(1)
