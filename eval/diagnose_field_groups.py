"""CPU and controlled HTTP field-group scope checks plus recorded real HTML.

The semantic endpoint is a permissive literal-copying stub, not a model.
No GPU, browser, public request or new answer-accuracy measurement.
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
from agent.selector import payload
from agent.types import Candidate,Settings
from revision_engine import load_engine

QUESTION='What is the full name of the researcher Mira Vale, born in 1998?'
FIELDS=[('Full Name','Mira Vale'),('Date of Birth','1998-03-04'),('Last Updated','2026-01-01')]


def group(fields=FIELDS):
    return '<div>'+''.join('<div><span>'+label+'</span><span>'+value+'</span></div>' for label,value in fields)+'</div>'


def cases():
    valid=group();plain=[('Name','Mira Vale'),('Nationality','Canada'),('DOB','1998-03-04')]
    variants=[
        ('full-name',valid,1,True),('name',group(plain),1,True),
        ('trailing-colon',group([(k+':',v) for k,v in FIELDS]),1,True),
        ('inline-format',group([('Full Name','Mira <em>Vale</em>'),*FIELDS[1:]]),1,True),
        ('comments',valid.replace('<div><span>','<div><!-- row --> \n<span>'),1,True),
        ('wrong-date-update',group([('Full Name','Mira Vale'),('Date of Birth','1970-03-04'),('Last Updated','1998-01-01')]),1,False),
        ('no-date-update',group([('Full Name','Mira Vale'),('Country of Birth','Canada'),('Last Updated','1998')]),1,False),
        ('unknown-date',group([('Full Name','Mira Vale'),('Date of Birth','unknown'),('Last Updated','1998')]),1,False),
        ('conflicting-dates',group([*FIELDS,('Birth Year','1970')]),1,False),
        ('other-profile-date',group([('Full Name','Mira Vale'),('Country of Birth','Canada'),('Last Updated','1998')])+
             group([('Full Name','Rowan North'),('Date of Birth','1998-03-04'),('Last Updated','2026')]),2,False),
        ('sibling-profile',valid+group([('Full Name','Rowan North'),('Date of Birth','1970-03-04'),('Last Updated','1998')]),2,True),
        ('three-cards','<div>'+valid+group([('Full Name','Rowan North'),('Date of Birth','1970-03-04'),('Last Updated','1998')])+group([('Full Name','Dana Wood'),('Date of Birth','1960-01-01'),('Last Updated','1998')])+'</div>',3,True),
        ('duplicate-label',group([*FIELDS,('full_name','Other Person')]),0,False),
        ('two-name-fields',group([*FIELDS,('Name','Rowan North')]),0,False),
        ('no-name',group([('Role','Researcher'),*FIELDS[1:]]),0,False),
        ('two-rows',group(FIELDS[:2]),1,True),
        ('one-row',group(FIELDS[:1]),0,False),
        ('reordered-rows',group([FIELDS[1],FIELDS[2],FIELDS[0]]),1,True),
        ('swapped-columns',group([(value,label) for label,value in FIELDS]),0,False),
        ('too-many-rows',group(FIELDS+[(f'Extra {i}','value') for i in range(10)]),0,False),
        ('long-value',group([*FIELDS,('Biography','x'*221)]),0,False),
        ('long-context',group([*FIELDS]+[(f'Extra {i}','x'*200) for i in range(5)]),0,False),
        ('loose-group-text',valid.replace('<div>','<div>Profile ',1),0,False),
        ('loose-row-text',valid.replace('<div><span>','<div>Unlabelled <span>',1),0,False),
        ('three-cells',valid.replace('</span></div>','</span><span>Other</span></div>',1),0,False),
        ('block-value',valid.replace('Mira Vale','<div>Mira Vale</div>'),0,False),
        ('line-break-value',valid.replace('Mira Vale','Mira<br>Vale'),0,False),
        ('interactive',valid.replace('Mira Vale','<button>Mira Vale</button>'),0,False),
        ('hidden-group','<div hidden>'+valid+'</div>',0,False),
        ('hidden-date',valid.replace('<span>Date of Birth</span><span>1998-03-04</span>','<span>Date of Birth</span><span hidden>1998-03-04</span>'),0,False),
        ('hidden-update-proof',group([('Full Name','Mira Vale'),('Country of Birth','Canada'),('Last Updated','1998')])+ '<div hidden>'+group()+'</div>',1,False),
        ('biography-fallback',group([('Full Name','Mira Vale'),('Biography','Mira Vale was born in 1998.'),('Nationality','Canada')]),1,False),
        ('truncated',valid,0,False),
    ]
    return variants


def parse_checks(engine):
    g=engine.run.__globals__;rows=[]
    for name,html,expected_groups,supported in cases():
        page=g['parse_response'](Response('https://example.org/'+name,('<title>Researcher profiles</title>'+html).encode(),'text/html',status=200,truncated=name=='truncated'))
        fields=[p for p in page.passages if p.locator.startswith('fieldgroup[')]
        groups={p.locator.split('/')[0] for p in fields}
        targets=[p for p in fields if p.value=='Mira Vale' and p.label.rstrip(':') in {'Name','Full Name'}]
        plan=g['plan_query'](QUESTION,page.url)
        accepted=any(g['verify'](Candidate('Mira Vale','Mira Vale',page.url,p.text,p.label,p.section,kind=plan.kind,score=10),plan,[page]) for p in targets)
        passed=not page.error and len(groups)==expected_groups and accepted==supported
        for p in fields:
            # Bindings must be exactly the visible local group, never another card.
            passed=passed and p.value in p.text and len(p.text)<=1000 and len(p.qualifiers['identity'])==1
            passed=passed and all(str(value) in p.text for value in p.qualifiers['bindings'].values())
            if p.value=='Mira Vale':passed=passed and 'Rowan North' not in p.text and 'Dana Wood' not in p.text
        if name=='biography-fallback':
            dated=payload(plan,[],g['rank_passages'](plan,[page]))
            timeless_plan=g['plan_query']('What is the full name of Mira Vale?',page.url)
            timeless=payload(timeless_plan,[],g['rank_passages'](timeless_plan,[page]))
            passed=passed and not any(p['locator'].startswith('fieldgroup[') for p in dated['passages'])
            passed=passed and any(p['locator'].startswith('fieldgroup[') for p in timeless['passages'])
        rows.append(dict(id=name,passed=passed,groups=len(groups),expected_groups=expected_groups,
                         accepted=accepted,expected_supported=supported))
    return rows


async def http(engine):
    mode='';calls=[];requests=[];rows=[]
    variants={name:(html,supported) for name,html,count,supported in cases() if name in
        {'full-name','wrong-date-update','no-date-update','unknown-date','conflicting-dates','other-profile-date','sibling-profile','biography-fallback'}}
    variants['biography-fallback']=(variants['biography-fallback'][0],True)
    async def source(request):
        requests.append(request.path)
        return web.Response(text='<title>Researcher profiles</title>'+variants[mode][0],content_type='text/html')
    async def model(request):
        data=await request.json();calls.append((request.path,data))
        if request.path=='/verify':return web.json_response({'supported':True})
        # Prefer complete source groups. Copy only a name already present.
        passages=sorted(data.get('passages',[]),key=lambda p:not p['locator'].startswith('fieldgroup['))
        selected=next((p for p in passages if 'Mira Vale' in p['text']),None)
        return web.json_response({'passage':selected['id'] if selected else -1,'answer':'Mira Vale' if selected else ''})
    app=web.Application();app.router.add_get('/source',source);app.router.add_post('/{tail:.*}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    try:
        for mode,(html,supported) in variants.items():
            calls.clear();requests.clear()
            result=await engine(Settings(model_url=base,search=False,allow_private=True,max_depth=0,budget=5)).run(QUESTION,base+'/source')
            expected='Mira Vale' if supported else ''
            passed=result.answer==expected and result.sources==([base+'/source'] if expected else [])
            methods=[p for p,data in calls]
            passed=passed and requests==['/source'] and methods==(['/select','/verify'] if supported else ['/select'])
            if supported:passed=passed and calls[1][1]['question']==QUESTION
            rows.append(dict(id='http-'+mode,passed=passed,model_paths=methods,result=result.internal()))
    finally:await runner.cleanup()
    return rows


def recorded(engine):
    report=json.loads((ROOT/'benchmarks/external-disjoint12b-20261023-repeat.json').read_text(encoding='utf-8'))
    row=next(r for r in report['rows'] if r['id']=='simpleqa-3120')
    source=ROOT/row['capture_path'];assert hashlib.sha256(source.read_bytes()).hexdigest()==row['capture_sha256']
    responses=json.loads(source.read_text(encoding='utf-8'));g=engine.run.__globals__;pages=[]
    case=next(c for c in json.loads((ROOT/'benchmarks/external-disjoint12b-20261023.json').read_text(encoding='utf-8')) if c['id']==row['id'])
    plan=g['plan_query'](case['query'],case['url'])
    for url in ['https://www.soccerstats247.com/players/juan-pablo-guzman-perdomo-134947/',
                'https://en.soccerwiki.org/player.php?pid=85733',
                'https://www.footballdatabase.eu/en/player/details/204458-juan-guzman']:
        data=dict(responses[url]);data['body']=base64.b64decode(data.pop('body_base64'))
        pages.append(g['parse_response'](Response(**data)))
    candidates=g['rank']([c for page in pages for c in g['extract'](plan,page)],plan)
    ranked=g['rank_passages'](plan,pages,candidates);data=payload(plan,candidates,ranked)
    groups=[(i+1,page,p) for i,(page,p,score) in enumerate(ranked) if p.locator.startswith('fieldgroup[') and p.label=='Full Name']
    # Derive the literal from the captured DOM field, never a benchmark alias.
    p=groups[0][2] if groups else next(p for page in pages for p in page.passages if p.label=='Full Name')
    candidate=Candidate(p.value,p.value,(groups[0][1].url if groups else next(page.url for page in pages if p in page.passages)),
                        p.text,p.label,p.section,kind=plan.kind,score=10)
    accepted=g['verify'](candidate,plan,pages)
    visible=any(v['locator'].startswith('fieldgroup[') and p.value in v['text'] and '31/08/1988' in v['text'] for v in data['passages'])
    return dict(id='recorded-profile',passed=bool(groups) and accepted and visible,position=groups[0][0] if groups else None,
                literal_value=p.value,literal_guard_accepted=accepted,complete_group_in_payload=visible,
                source_capture_sha256=row['capture_sha256'],passages=data['passages'],
                scope='Recorded content and literal guard only; no model, unchanged gold, not a new correct answer.')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('26ad9fb')
    before=parse_checks(old)+asyncio.run(http(old))+[recorded(old)]
    after=parse_checks(Engine)+asyncio.run(http(Engine))+[recorded(Engine)]
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,before=before,after=after,
                before_passed=sum(r['passed'] for r in before),after_passed=sum(r['passed'] for r in after),total=len(after),
                wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
                losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
                production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('agent').glob('*.py')})
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    if not all(r['passed'] for r in after):sys.exit(1)
