"""Source-bound English cardinal count controls, CPU/loopback HTTP only.

Authored related controls plus one immutable exposed source. Not a model or
unseen-question score. No public requests or model/tokenizer loads.
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
    g=engine.run.__globals__;rows=[]
    cases=[('zero', '0'),('four','4'),('nineteen','19'),('twenty-one','21'),
           ('thirty two','32'),('one hundred','100'),('one hundred and five','105'),
           ('two thousand three hundred and forty-one','2341'),
           ('one million two hundred thousand','1200000'),('a hundred','100'),
           ('Twenty-One','21'),('twenty\u2011one','21'),('one thousand, two hundred and three','1203'),
           ('one billion and two million','1002000000'),
           ('nine hundred and ninety-nine trillion nine hundred and ninety-nine billion '
            'nine hundred and ninety-nine million nine hundred and ninety-nine thousand '
            'nine hundred and ninety-nine','999999999999999')]
    for raw,answer in cases:
        plan=g['plan_query']('How many chairs does Elm Hall have?')
        page=g['parse_response'](Response('https://example.org/elm',
            ('<h1>Elm Hall</h1><p>Elm Hall has '+raw+' chairs.</p>').encode(),'text/html','utf-8',200))
        passage=next(p for p in page.passages if raw in p.text)
        c=Candidate(raw,answer,page.url,passage.text,kind='number',score=20)
        extracted=g['extract'](plan,page)
        rows.append({'id':'bound-'+raw,'passed':g['verify'](c,plan,[page])
                     and any(x.raw==raw and x.answer==answer for x in extracted),
                     'verified':g['verify'](c,plan,[page]),'candidates':[(x.raw,x.answer) for x in extracted]})
    negatives=[('four','5','Elm Hall has four chairs.'),
               ('one','1','Elm Hall has one hundred chairs.'),
               ('hundred','100','Elm Hall has one hundred chairs.'),
               ('twenty','20','Elm Hall has twenty-one chairs.'),
               ('four','4','Elm Hall has about four chairs.'),
               ('four','4','Elm Hall has at least four chairs.'),
               ('four','4','Elm Hall has four to six chairs.'),
               ('four','4','Elm Hall has between four and six chairs.'),
               ('four','4','Elm Hall has four and a half chairs.'),
               ('four','4','Elm Hall has four point five chairs.'),
               ('five','5','Elm Hall has four point five chairs.'),
               ('four','4','An elm is a four-year-old tree.'),
               ('one','1','Elm Hall won its one hundredth award.'),
               ('four','4','Elm Hall has 2 hundred four chairs.'),
               ('four','4','Elm Hall has four\u2013six chairs.'),
               ('six','6','Elm Hall has four\u2013six chairs.'),
               ('six','6','Elm Hall has four to six chairs.'),
               ('four','4','Elm Hall has four or six chairs.'),
               ('six','6','Elm Hall has four or six chairs.'),
               ('three','3','Elm Hall has three quarters of its chairs.'),
               ('four','4','Elm Hall has four dozen chairs.'),
               ('one','1','Elm Hall has one million chairs.'),
               ('hundred','100','Elm Hall has a hundred chairs.'),
               ('four','04','Elm Hall has four chairs.'),
               ('one','1','Elm Hall has one quadrillion chairs.'),
               ('one','1','Elm Hall has one lakh chairs.'),
               ('three','3','Elm Hall has three fifths of its chairs.'),
               ('four','4','Elm Hall has four hundredths of its chairs.'),
               ('four','4','Elm Hall has < four chairs.'),
               ('four','4','Elm Hall has four/five of its chairs.'),
               ('five','5','Elm Hall has four/five of its chairs.'),
               ('four','4','Elm Hall has four plus one chairs.'),
               ('one','1','Elm Hall has four plus one chairs.')]
    for i,(raw,answer,text) in enumerate(negatives):
        plan=g['plan_query']('How many chairs does Elm Hall have?')
        page=g['parse_response'](Response('https://example.org/elm',('<p>'+text+'</p>').encode(),'text/html','utf-8',200))
        p=next(p for p in page.passages if raw in p.text)
        c=Candidate(raw,answer,page.url,p.text,kind='number',score=20,
                    signals={'number_projection':{'value':answer,'source_span':raw}})
        rows.append({'id':'reject-'+str(i),'passed':not g['verify'](c,plan,[page]),'raw':raw,'text':text})
    plan=g['plan_query']('What was the population of Maple Harbour at the 2004 census?')
    text='At the 2004 census, its population was six hundred and seventeen, in four families. In 2014 its population was eight hundred and thirty-nine.'
    page=g['parse_response'](Response('https://example.org/population',('<p>'+text+'</p>').encode(),'text/html','utf-8',200))
    p=next(p for p in page.passages if 'families' in p.text)
    for raw,answer,expected in [('six hundred and seventeen','617',True),('four','4',False),('eight hundred and thirty-nine','839',False)]:
        actual=g['verify'](Candidate(raw,answer,page.url,p.text,kind='number',score=20),plan,[page])
        rows.append({'id':'population-'+raw,'passed':actual==expected,'expected':expected,'actual':actual})
    for raw in ['hundred','one hundred hundred','one thousand million','twenty eleven','one and two',
                'one trillion trillion','two, one','one thousand,','one million and','one point two',
                'one-hundred','two thousand two hundred and zero']:
        plan=g['plan_query']('How many chairs does Elm Hall have?')
        page=g['parse_response'](Response('https://example.org/elm',
            ('<p>Elm Hall has '+raw+' chairs.</p>').encode(),'text/html','utf-8',200))
        p=page.passages[0]
        c=Candidate(raw,'1',page.url,p.text,kind='number',score=20)
        rows.append({'id':'unsupported-grammar-'+raw,'passed':not g['verify'](c,plan,[page])})
    for content_type,prefix in [('text/html','<p>'),('text/plain','')]:
        width=1600 if prefix else 2000
        padding='x '*(width//2-3)
        content=prefix+padding+'one hundred and five chairs.'+('</p>' if prefix else '')
        page=g['parse_response'](Response('https://example.org/long',content.encode(),content_type,'utf-8',200))
        plan=g['plan_query']('How many chairs does Elm Hall have?')
        clipped=next(p for p in page.passages if p.text.endswith('one'))
        full=next(p for p in page.passages if 'one hundred and five' in p.text)
        wrong=g['verify'](Candidate('one','1',page.url,clipped.text,kind='number',score=20),plan,[page])
        right=g['verify'](Candidate('one hundred and five','105',page.url,full.text,kind='number',score=20),plan,[page])
        rows.append({'id':'clipped-'+content_type,'passed':not wrong and right,'partial_accepted':wrong,'full_accepted':right})
    page=g['parse_response'](Response('https://example.org/data',b'{"chairs":"four","name":"Elm Hall"}',
                                    'application/json','utf-8',200))
    plan=g['plan_query']('How many chairs does Elm Hall have?')
    for label,expected in [('chairs',True),('name',False)]:
        p=next(p for p in page.passages if p.label==label)
        actual=g['verify'](Candidate('four','4',page.url,p.text,p.label,p.section,kind='number',score=20),plan,[page])
        rows.append({'id':'json-own-value-'+label,'passed':actual==expected,'actual':actual})
    scalar='x '*897+'one hundred and five chairs.'
    page=g['parse_response'](Response('https://example.org/long-data',json.dumps({'description':scalar}).encode(),
                                    'application/json','utf-8',200))
    p=next(p for p in page.passages if p.label=='description')
    actual=g['verify'](Candidate('one','1',page.url,p.text,p.label,p.section,kind='number',score=20),plan,[page])
    rows.append({'id':'json-clipped-value','passed':not actual,'actual':actual})
    return rows


async def transport(engine):
    mode='';text='';selected='';expected='';calls=[];rows=[]
    async def source(request):
        return web.Response(text='<h1>Elm Hall</h1><p>'+text+'</p>',content_type='text/html')
    async def model(request):
        data=await request.json();calls.append({'path':request.path,'data':data})
        if request.path=='/verify':
            if mode=='unavailable':return web.json_response({'error':'RuntimeError'},status=503)
            return web.json_response({'supported':mode!='semantic-reject' and data.get('proposed')==expected})
        p=next((p for p in data.get('passages',[]) if 'Elm Hall has' in p['text']),None)
        return web.json_response({'passage':p['id'] if p else -1,'answer':selected if p else ''})
    app=web.Application();app.router.add_get('/source',source);app.router.add_post('/{tail:.*}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    cases=[('word','four','four','4'),('digits','four','4','4'),
           ('hyphen','twenty-one','21','21'),('large','one thousand and five','1005','1005'),
           ('zero','zero','0','0'),('semantic-reject','four','four',''),
           ('fragment','one hundred','one',''),('wrong-value','four','5',''),
           ('approximation','about four','four',''),('range','four to six','4',''),
           ('fraction','four and a half','4',''),('ambiguous-binding','four chairs and four','4',''),
           ('unavailable','four','four',''),('text-copy','four','four','four'),
           ('version-copy','four','four','four'),('count-field','four','four',''),
           ('word-unit','four','four chairs','4'),('digit-unit','four','4 chairs','4'),
           ('grouped-unit','10,000','10,000 chairs','10,000'),('wrong-unit','four','4 doors','')]
    try:
        for mode,phrase,selected,expected in cases:
            calls.clear();text='Elm Hall has '+phrase+' chairs.'
            question={'text-copy':'What is the displayed text?', 'version-copy':'What is the version?',
                      'count-field':'What is the count field?'}.get(mode,'How many chairs does Elm Hall have?')
            result=await engine(Settings(model_url=base,search=False,browser=False,allow_private=True,
                max_depth=0,budget=4)).run(question,base+'/source')
            verification=[c['data'] for c in calls if c['path']=='/verify']
            rows.append({'id':'http-'+mode,'passed':result.answer==expected
                         and result.sources==([base+'/source'] if expected else [])
                         and (not expected or bool(verification) and verification[0]['proposed']==expected)
                         and (mode not in {'word','digits','hyphen','large','zero','word-unit','digit-unit'}
                              or bool(verification) and verification[0].get('number_normalization',{}).get('integer')==expected)
                         and (mode!='semantic-reject' or bool(verification)),
                         'actual':result.answer,'expected':expected,'reason':result.reason,
                         'calls':[c['path'] for c in calls], 'selection':result.diagnostics.get('model_selections')})
    finally:await runner.cleanup()
    return rows


def protocol(engine):
    namespace=engine.__module__.rsplit('.',1)[0]
    validate=importlib.import_module(namespace+'.model_protocol').validate_reply
    rows=[]
    for answer,text,expected in [('4','Count: four.','four'),('four','Count: four.','four'),
                                 ('one','Count: one hundred.',''),('1','Count: one hundred.',''),
                                 ('4','Count: four, with four reserves.',''),
                                 ('4','Count: 4.','4'),
                                 ('four chairs','Count: four chairs.','four'),
                                 ('4 chairs','Count: four chairs.','four'),
                                 ('4 chairs','Count: four doors.',''),
                                 ('4 doors','Count: four doors.',''),
                                 ('10,000 chairs','Count: 10,000 chairs.','10,000')]:
        data={'question':'How many chairs are there?','constraints':{'kind':'number','operation':'single'},
              'candidates':[],'passages':[{'id':0,'text':text}]}
        result=validate({'passage':0,'answer':answer},data)
        rows.append({'id':'protocol-'+str(len(rows)), 'passed':result.get('answer','')==expected,
                     'reply':result,'expected':expected})
    request={'question':'How many chairs does Hundred Hall have?',
             'constraints':{'kind':'number','operation':'single'},'candidates':[],
             'passages':[{'id':0,'text':'It has one hundred chairs.'}]}
    result=validate({'passage':0,'answer':'one hundred'},request)
    rows.append({'id':'protocol-cardinal-is-not-unit','passed':result.get('answer')=='one hundred','reply':result})
    return rows


def recorded(engine):
    path=ROOT/'research/external-disjoint12b-20261023/simpleqa-2811.json';raw=path.read_bytes()
    capture_hash='19c95b414ecb9031239aa913a93304b9d4b3d680bca355087b5f4034ace9c062'
    if hashlib.sha256(raw).hexdigest()!=capture_hash:raise ValueError('Capture changed')
    e=dict(json.loads(raw)['https://www.laytonlegacy.ca/jack']);e['body']=base64.b64decode(e.pop('body_base64'),validate=True)
    g=engine.run.__globals__;page=g['parse_response'](Response(**e))
    p=next(p for p in page.passages if 'first of four children' in p.text)
    plan=g['plan_query']('How many children were in the family in which Jack Layton grew up?')
    actual=g['verify'](Candidate('four','4',page.url,p.text,kind='number',score=20),plan,[page])
    return {'id':'saved-literal-count','passed':actual,'capture_sha256':capture_hash,
            'body_sha256':hashlib.sha256(e['body']).hexdigest(),'literal':p.text,
            'scope':'Authored development count query on an already exposed source; not the original city question or model correctness'}


async def diagnose(engine):return direct(engine)+protocol(engine)+await transport(engine)+[recorded(engine)]


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--baseline');args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    engine=Engine;hashes={}
    if args.baseline:engine,_,hashes=load_engine(args.baseline)
    rows=asyncio.run(diagnose(engine))
    current={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in [
        'agent/cardinals.py','agent/candidates.py','agent/selector.py','agent/model_protocol.py',
        'agent/population.py','agent/model_server.py','agent/parser.py']}
    report={'scope':__doc__,'baseline':args.baseline,'diagnostic_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'source_hashes':hashes if args.baseline else current,'rows':rows,'passed':sum(r['passed'] for r in rows),'total':len(rows),
            'torch_imported':'torch' in sys.modules}
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'total':report['total'],'failures':[r['id'] for r in rows if not r['passed']]}))
