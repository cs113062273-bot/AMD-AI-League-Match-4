"""Complete scaled-count source atoms, authored CPU and loopback HTTP controls.

No model, browser, public API, gold changes or independent accuracy claim.
"""
import argparse
import asyncio
import base64
import hashlib
import importlib
import json
from pathlib import Path
import sys

from aiohttp import web

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.engine import Engine
from agent.network import Response
from agent.types import Candidate,Settings
from revision_engine import load_engine


def direct(engine):
    g=engine.run.__globals__;literal=g['verify'].__globals__['literal_span'];rows=[]
    negatives=[('4','Count: 4 million'),('4.5','Count: 4.5 million'),('4','Count: 4 hundred'),
               ('1,234','Count: 1,234 thousand'),('4 million','Count: 4 million and 200 thousand'),
               ('200 thousand','Count: 4 million and 200 thousand'),('$4','Cost: $4 million')]
    for kind in ['number','price','measurement','duration','percentage','year','time']:
        for i,(raw,text) in enumerate(negatives):
            actual=literal(raw,text,kind)
            rows.append({'id':'literal-'+kind+'-'+str(i),'passed':not actual,'raw':raw,'text':text})
    for raw,text in [('4 million','Count: 4 million'),('4','Count: 4 million. Reserve: 4'),
                     ('4.5 million','Count: 4.5 million'),('$4 million','Cost: $4 million'),
                     ('4','Score: 5\u20134'),('2014','March 1,2014'),('4','Count: 4 chairs')]:
        rows.append({'id':'full-or-later-'+str(len(rows)),'passed':literal(raw,text,'number'),'raw':raw,'text':text})
    for kind in ['text','version']:
        rows.append({'id':'non-numeric-'+kind,'passed':literal('4','Count: 4 million',kind)})
    positives=[('4 hundred','400'),('4 million','4000000'),('1.25 million','1250000'),
               ('1,234 thousand','1234000'),('0.5 thousand','500'),('4million','4000000'),
               ('4 million and 200 thousand','4200000'),('4 hundred and five','405'),
               ('four million 200 thousand','4200000'),('.5 million','500000'),
               ('1.2e3 thousand','1200000'),('.5e2 thousand','50000'),
               ('4 hundred twenty thousand','420000'),('4.123456 million','4123456')]
    plan=g['plan_query']('How many chairs does Elm Hall have?')
    for raw,answer in positives:
        page=g['parse_response'](Response('https://example.org/elm',
            ('<p>Elm Hall has '+raw+' chairs.</p>').encode(),'text/html','utf-8',200))
        p=page.passages[0]
        actual=g['verify'](Candidate(raw,answer,page.url,p.text,kind='number',score=20),plan,[page])
        rows.append({'id':'canonical-'+raw,'passed':actual,'actual':actual})
    for raw,answer,text in [('4','4','Elm Hall has 4 million chairs.'),
                            ('4 million','4','Elm Hall has 4 million chairs.'),
                            ('4 million','4000001','Elm Hall has 4 million chairs.'),
                            ('4 million','4000000','Elm Hall has about 4 million chairs.'),
                            ('4 million','4000000','Elm Hall has 4 million to 6 million chairs.')]:
        page=g['parse_response'](Response('https://example.org/elm',('<p>'+text+'</p>').encode(),'text/html','utf-8',200));p=page.passages[0]
        actual=g['verify'](Candidate(raw,answer,page.url,p.text,kind='number',score=20),plan,[page])
        rows.append({'id':'reject-'+str(len(rows)),'passed':not actual,'actual':actual,'raw':raw,'text':text})
    for raw,answer in [('4.0000000000000000000000000000001 million','4000000'),
                       ('4 thousand million','4000000000'),('1,23 million','1230000'),
                       ('1e999 million','1000000'),('4 million and 2000 thousand','6000000'),
                       ('4 million and','4000000')]:
        page=g['parse_response'](Response('https://example.org/elm',
            ('<p>Elm Hall has '+raw+' chairs.</p>').encode(),'text/html','utf-8',200));p=page.passages[0]
        actual=g['verify'](Candidate(raw,answer,page.url,p.text,kind='number',score=20),plan,[page])
        # An unsupported literal may remain copyable under existing number
        # rules, but it cannot gain a fabricated normalized integer answer.
        selected=next((c for c in g['extract'](plan,page) if c.raw==raw and c.answer==answer),None)
        rows.append({'id':'no-rounded-derivation-'+raw,'passed':not selected and not actual,
                     'mechanical_acceptance':actual,'normalized_candidate':bool(selected)})
    for raw,text in [('a million','Elm Hall has half a million chairs.'),
                     ('4 million','Elm Hall has half of 4 million chairs.')]:
        page=g['parse_response'](Response('https://example.org/elm',('<p>'+text+'</p>').encode(),'text/html','utf-8',200));p=page.passages[0]
        actual=g['verify'](Candidate(raw,str(1000000 if raw=='a million' else 4000000),page.url,p.text,kind='number',score=20),plan,[page])
        rows.append({'id':'fraction-prefix-'+raw,'passed':not actual})
    for raw,text in [('4','Count: 4 hundredths'),('4','Count: 4 millionth'),('4','Count: 4 millions')]:
        rows.append({'id':'unsupported-scale-boundary-'+str(len(rows)),'passed':not literal(raw,text,'number')})
    page=g['parse_response'](Response('https://example.org/long',
        ('<p>'+'x '*798+'4 million chairs.</p>').encode(),'text/html','utf-8',200))
    clipped=next(p for p in page.passages if p.text.endswith('4'))
    full=next(p for p in page.passages if '4 million' in p.text)
    wrong=g['verify'](Candidate('4','4',page.url,clipped.text,kind='number',score=20),plan,[page])
    right=g['verify'](Candidate('4 million','4000000',page.url,full.text,kind='number',score=20),plan,[page])
    rows.append({'id':'clipped-scalar-prefix','passed':not wrong and right,'partial_accepted':wrong,'full_accepted':right})
    # Existing literal ranges remain literal ranges, not a derived scalar.
    page=g['parse_response'](Response('https://example.org/range',b'<p>Elm Hall has 4 to 6 million chairs.</p>','text/html','utf-8',200))
    p=page.passages[0]
    rows.append({'id':'full-range-retained','passed':g['verify'](Candidate('4 to 6 million','4 to 6 million',page.url,p.text,kind='number',score=20),plan,[page])})
    plan=g['plan_query']('What was the population of Maple Harbour at the 2004 census?')
    text='At the 2004 census its population was 4 million, in 2 hundred households. In 2014 its population was 6 million.'
    page=g['parse_response'](Response('https://example.org/population',('<p>'+text+'</p>').encode(),'text/html','utf-8',200));p=page.passages[0]
    for raw,answer,expected in [('4 million','4000000',True),('2 hundred','200',False),('6 million','6000000',False)]:
        actual=g['verify'](Candidate(raw,answer,page.url,p.text,kind='number',score=20),plan,[page])
        rows.append({'id':'population-'+raw,'passed':actual==expected,'actual':actual,'expected':expected})
    return rows


async def http(engine):
    phrase='';selected='';expected='';mode='';calls=[];rows=[]
    async def source(request):return web.Response(text='<h1>Elm Hall</h1><p>Elm Hall has '+phrase+' chairs.</p>',content_type='text/html')
    async def model(request):
        data=await request.json();calls.append({'path':request.path,'data':data})
        if request.path=='/verify':return web.json_response({'supported':mode!='reject'})
        p=next((p for p in data.get('passages',[]) if 'Elm Hall has' in p['text']),None)
        return web.json_response({'passage':p['id'] if p else -1,'answer':selected if p else ''})
    app=web.Application();app.router.add_get('/source',source);app.router.add_post('/{tail:.*}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    cases=[('prefix','4 million','4',''),('word-scale','4 million','4 million','4000000'),
           ('decimal-scale','1.25 million','1250000','1250000'),('hundred','4 hundred','4 hundred','400'),
           ('reject','4 million','4 million',''),('ambiguous','4 million chairs and 4 million','4000000',''),
           ('range','4 million to 6 million','4',''),('qualified','about 4 million','4000000',''),
           ('sum','4 million and 200 thousand','4200000','4200000')]
    try:
        for mode,phrase,selected,expected in cases:
            calls.clear()
            result=await engine(Settings(model_url=base,search=False,browser=False,allow_private=True,
                max_depth=0,budget=4)).run('How many chairs does Elm Hall have?',base+'/source')
            paths=[c['path'] for c in calls]
            rows.append({'id':'http-'+mode,'passed':result.answer==expected
                         and result.sources==([base+'/source'] if expected else [])
                         and (not expected or '/verify' in paths)
                         and (mode!='reject' or '/verify' in paths),
                         'actual':result.answer,'expected':expected,'paths':paths,
                         'selections':result.diagnostics.get('model_selections')})
    finally:await runner.cleanup()
    return rows


def recorded(engine):
    audit=json.loads((ROOT/'benchmarks/magnitude-counts-20261024-saved-source-audit.json').read_text())
    record=next(r for r in audit['rows'] if 'census.gov' in r['url'])
    first=json.loads((ROOT/'benchmarks/external-disjoint12-20261023-first.json').read_text(encoding='utf-8'))
    frozen=next(r for r in first['rows'] if r['id']=='simpleqa-3207')
    if record['capture_sha256']!=frozen['capture_sha256']:raise ValueError('Capture differs from first assessment')
    capture=(ROOT/record['capture_path']).read_bytes()
    if hashlib.sha256(capture).hexdigest()!=record['capture_sha256']:raise ValueError('Capture changed')
    responses=json.loads(capture)
    envelope=next(dict(e) for e in responses.values() if e['url']==record['url'] and
        hashlib.sha256(base64.b64decode(e['body_base64'])).hexdigest()==record['body_sha256'])
    envelope['body']=base64.b64decode(envelope.pop('body_base64'),validate=True)
    g=engine.run.__globals__;page=g['parse_response'](Response(**envelope))
    passage=next(p for p in page.passages if 'approximately 19 million housing units' in p.text)
    literal=g['verify'].__globals__['literal_span']
    return {'id':'actual-census-prefix','passed':not literal('19',passage.text,'number')
            and literal('19 million',passage.text,'number'),
            'capture_path':record['capture_path'],'capture_sha256':record['capture_sha256'],
            'body_sha256':record['body_sha256'],'source':page.url,'locator':passage.locator,
            'scope':'Already exposed actual fetched source; qualified national sampling count is not the original city answer. Boundary check only, no new score.'}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--baseline');args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    engine=Engine;hashes={}
    if args.baseline:engine,_,hashes=load_engine(args.baseline)
    async def run():return direct(engine)+await http(engine)+[recorded(engine)]
    rows=asyncio.run(run())
    source_hashes=hashes if args.baseline else {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [ROOT/'agent'/name for name in ['number_atoms.py','magnitudes.py','normalize.py','cardinals.py',
            'candidates.py','selector.py','population.py','model_server.py']]}
    report={'scope':__doc__,'baseline':args.baseline,'source_hashes':source_hashes,
            'diagnostic_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'passed':sum(r['passed'] for r in rows),'total':len(rows),'rows':rows,'torch_imported':'torch' in sys.modules}
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'total':len(rows),'failures':[r['id'] for r in rows if not r['passed']]}))
