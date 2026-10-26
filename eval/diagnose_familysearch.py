"""Authored CPU HTTP source/collection checks plus one frozen exposed-source replay.

No model or external request. Canonical official URLs are mapped to loopback
fixtures by the diagnostic transport only. Not a new question-only assessment.
"""
import argparse
import asyncio
import base64
from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from revision_engine import load_engine

PID='ABCD-123';PARTNER='EFGH-456'
FRONT='https://ancestors.familysearch.org/en/'+PID+'/birch-vale-1800-1880'
API='https://www.familysearch.org/service/tree/tree-data/published/persons/'+PID


def document(count=4):
    return {'version':'1.2','localizedData':{'en':{'lifeSummary':'Birch Vale married Rowan Cedar. Their family is described here.'}},
        'person':{'@type':'Person','@context':'http://schema.org','identifier':PID,'name':'Birch Vale','url':FRONT,
                  'birthDate':'+1800-01-01','deathDate':'+1880-01-01',
                  'spouse':[{'@type':'Person','identifier':PARTNER,'name':'Rowan Cedar','gender':'Female','published':True}],
                  'children':[{'@type':'Person','identifier':'JKLM-'+str(i).zfill(3),'otherParentId':PARTNER,
                               'name':'Child '+str(i),'gender':'Male' if i%2 else 'Female','published':i%2==0} for i in range(count)]}}


def guards(engine):
    core=engine.__module__.rsplit('.',1)[0];network=importlib.import_module(core+'.network')
    parse=importlib.import_module(core+'.parser').parse_response;proofs=importlib.import_module(core+'.proofs')
    planner=importlib.import_module(core+'.planner');rows=[]
    q=planner.plan_query('How many children did Birch Vale have with his wife, Rowan?',FRONT)
    def page(data=None,**kwargs):
        return parse(network.Response(API,body=json.dumps(data if data is not None else document()).encode(),
                                      status=200,content_type='application/json',**kwargs))
    p=page();proof,needed=proofs.propose(q,[p])
    def check(name,actual,expected):rows.append({'id':'guard-'+name,'passed':actual==expected,'actual':actual,'expected':expected})
    check('valid-source',bool(proof) and needed and proofs.validate(proof,q,[p]),True)
    check('source-not-flooded',not p.truncated and len(p.passages)<=8,True)
    for name,modify in [
        ('forged-source',lambda a:replace(a,source='https://other.example/api')),
        ('forged-locator',lambda a:replace(a,locator='person.fake')),
        ('forged-evidence',lambda a:replace(a,span=a.span+' invented')),
        ('forged-key',lambda a:replace(a,key='not-the-source')),
        ('forged-count',lambda a:replace(a,value='4')),
        ('wrong-role',lambda a:replace(a,role='children')),
    ]:
        if proof:
            fake=replace(proof,atoms=(modify(proof.atoms[0]),*proof.atoms[1:]))
            actual=proofs.validate(fake,q,[p])
        else:actual=False
        check(name,actual,False)
    for name,atoms in [('missing-partner',tuple(a for a in proof.atoms if a.role!='partner') if proof else ()),
                       ('missing-collection',tuple(a for a in proof.atoms if a.role!='children') if proof else ()),
                       ('reversed',tuple(reversed(proof.atoms)) if proof else ())]:
        check(name,proofs.validate(replace(proof,atoms=atoms),q,[p]) if proof else False,False)
    for name,changed in [('missing-field',replace(p,passages=[x for x in p.passages if x.locator!='person'])),
                          ('truncated',replace(p,truncated=True)),('error',replace(p,error='http_403')),
                          ('relabeled-url',replace(p,url='https://other.example/profile'))]:
        candidate,required=proofs.propose(q,[changed]);check(name,bool(candidate),False)
    different=page(document(3));candidate,required=proofs.propose(q,[p,different])
    check('conflicting-records',bool(candidate),False);check('conflicting-count-blocks-fallback',required,True)
    same=page(document());candidate,required=proofs.propose(q,[p,same]);check('same-records-retained',bool(candidate),True)
    for name,data in [('wrong-context',dict(document(),person={**document()['person'],'@context':{}})),
                      ('root-array',[]),('root-null',None),('invalid-version',dict(document(),version={})),
                      ('malformed-child',dict(document(),person={**document()['person'],'children':[{}]}))]:
        try:
            content=json.dumps(data).encode();bad=parse(network.Response(API,body=content,status=200,content_type='application/json'))
            candidate,required=proofs.propose(q,[bad]);safe=not candidate
        except Exception:safe=False
        check(name,safe,True)
    duplicate=b'{"person":{},"person":{},"version":"1.2"}'
    bad=parse(network.Response(API,body=duplicate,status=200,content_type='application/json'))
    check('duplicate-json-keys',bool(bad.error),True)
    # Exercise the actual Runtime.infer packing branch with an authored string
    # counter. No tokenizer/model/torch is loaded or generation invoked.
    runtime_module=importlib.import_module(core+'.model_server')
    class StringCounter:
        def apply_chat_template(self,messages,**kwargs):return json.dumps(messages)
        def encode(self,text):return range(len(text))
    runtime=runtime_module.Runtime.__new__(runtime_module.Runtime)
    runtime.torch=object();runtime.tokenizer=StringCounter();runtime.context_limit=10
    request={'mode':'verify','question':'How many children?','passages':[{'id':i,'text':'complete source evidence '+str(i)} for i in range(5)],
             'proof':{'operation':'count_relationships','collection_passages':[2,3]},'candidates':[]}
    original=deepcopy(request)
    result=runtime.infer(request)
    check('oversized-proof-context-limit',result.get('error'),'context_limit')
    check('oversized-proof-not-pruned',request,original)
    # Exact source relation values must remain visible in the model request.
    if proof:
        check('no-derived-count-as-literal',all(a.value!='4' for a in proof.atoms),True)
        check('returned-unpublished-records-counted',proof.answer,'4')
    else:
        check('no-derived-count-as-literal',False,True);check('returned-unpublished-records-counted','','4')
    return rows


async def verification_guards(engine):
    core=engine.__module__.rsplit('.',1)[0];types=importlib.import_module(core+'.types')
    net=importlib.import_module(core+'.network');parse=importlib.import_module(core+'.parser').parse_response
    mod=importlib.import_module(core+'.proofs');selection=importlib.import_module(core+'.selector')
    plan=importlib.import_module(core+'.planner').plan_query('How many children did Birch Vale have with his wife, Rowan?',FRONT)
    p=parse(net.Response(API,body=json.dumps(document()).encode(),status=200,content_type='application/json'))
    proof,needed=mod.propose(plan,[p]);calls=[];reject=False
    if proof is None:
        # The historical engine has no such operation. Return fixed controls as
        # unsupported, rather than inventing a pre-existing source-count path.
        return [{'id':'verify-'+name,'passed':False,'state':'operation_absent'} for name in
                ['all-fields-visible','missing-context','missing-collection','forged-proof','eighth-conflict']]
    others=[types.Page('https://example.org/note'+str(i),passages=[types.Passage('Other family note '+str(i),locator='p:1')])
            for i in range(8-len(p.passages))]
    others[-1].passages[0].text='Birch Vale had exactly 77 children. This contradicts the source list.'
    pages=[p,*others];context=[(p,x,10) for x in p.passages]+[(x,x.passages[0],1) for x in others]
    async def endpoint(request):
        data=await request.json();calls.append(data)
        conflict=any('contradicts the source list' in x['text'] for x in data['passages'])
        return web.json_response({'supported':not (reject and conflict)})
    app=web.Application();app.router.add_post('/verify',endpoint)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);rows=[]
    try:
        fake=replace(proof,atoms=(replace(proof.atoms[0],source=API+'/fake'),*proof.atoms[1:]))
        missing=[x for x in context if x[1].qualifiers.get('familysearch_role')!='children']
        for name,candidate,ctx,conflicting,expected,called in [
            ('all-fields-visible',proof,context,False,True,True),('missing-context',proof,[],False,False,False),
            ('missing-collection',proof,missing,False,False,False),('forged-proof',fake,context,False,False,False),
            ('eighth-conflict',proof,context,True,False,True)]:
            calls=[];reject=conflicting
            supported,state=await selection.verify_proof(plan,candidate,pages,types.Settings(model_url=base),types.Deadline(4),ctx)
            passed=supported==expected and bool(calls)==called
            if name=='eighth-conflict':passed &= bool(calls) and len(calls[-1]['passages'])==8 and calls[-1]['passages'][-1]['source']==others[-1].url
            if calls:
                data=calls[-1];sent={x['id']:x for x in data['passages']}
                passed &= all(i in sent and len(sent[i]['text'])<=1100 for i in data['proof']['collection_passages'])
                passed &= data['proof']['subject'] in json.dumps(data['passages']) and data['proof']['partner'] in json.dumps(data['passages'])
            rows.append({'id':'verify-'+name,'passed':bool(passed),'supported':supported,'state':state,'calls':list(calls)})
        return rows
    finally:await runner.cleanup()


async def diagnose(engine):
    core=engine.__module__.rsplit('.',1)[0];network=importlib.import_module(core+'.network');types=importlib.import_module(core+'.types')
    mode='';active={};source_calls=[];model_calls=[];original=network.Fetcher.fetch
    async def source(request):
        source_calls.append(request.path)
        if request.path=='/front':return web.Response(text='<title>Birch Vale</title><div id="app"></div><script src="/app.js"></script>',content_type='text/html')
        if request.path=='/landing':return web.Response(text='<a href="'+active.get('front',FRONT)+'">Birch Vale family children profile</a>',content_type='text/html')
        return web.Response(text=active.get('raw') or json.dumps(active['data']),content_type='application/json',status=active.get('status',200))
    async def reader(request):
        data=await request.json();model_calls.append({'path':request.path,'data':data})
        if request.path=='/verify':
            if mode=='unavailable':return web.json_response({'error':'unavailable'},status=503)
            if mode=='invalid':return web.json_response({'supported':'yes'})
            proof=data.get('proof',{})
            if proof.get('operation')=='count_relationships':
                records=[row for p in data['passages'] if p['id'] in proof['collection_passages']
                         for row in json.loads(p['text'])['children']]
                ids=[r['identifier'] for r in records if not proof.get('partner') or r.get('otherParentId')==proof['partner']]
                supported=len(ids)==len(set(ids)) and data.get('proposed')==str(len(ids))
                if mode=='conflict' and any('exactly 77 children' in p['text'] for p in data['passages']):supported=False
                return web.json_response({'supported':supported and mode!='reject'})
            return web.json_response({'supported':mode=='malicious'})
        # Intentionally unhelpful selection: the new path must derive a source
        # collection, not rely on a model to invent an expanded count.
        if mode=='malicious':
            for p in data.get('passages',[]):
                if '77' in p['text']:return web.json_response({'passage':p['id'],'answer':'77'})
        return web.json_response({'passage':-1,'answer':''})
    app=web.Application();app.router.add_get('/front',source);app.router.add_get('/api',source);app.router.add_get('/landing',source)
    app.router.add_post('/{tail:.*}',reader);runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    async def transport(self,url,*args,**kwargs):
        front=active.get('front',FRONT);api=active.get('api',API)
        route='/front' if url==front else '/api' if url==api else '/landing' if url=='https://example.org/family' else None
        if route is None:raise AssertionError('Unexpected external fetch: '+url)
        r=await original(self,base+route,*args,**kwargs)
        r=replace(r,url=active.get('final',api) if route=='/api' else url,
                  truncated=active.get('truncated',False) if route=='/api' else r.truncated,
                  redirects=active.get('redirects',[]) if route=='/api' else [])
        self.cache[url]=r
        return r
    network.Fetcher.fetch=transport
    q='How many children did Birch Vale have with his wife, Rowan?';cases=[]
    def add(name,data=None,expected='',query=q,**kw):cases.append({'id':name,'data':data if data is not None else document(),'expected':expected,'query':query,**kw})
    add('four-records',expected='4');add('zero-records',document(0),'0');add('one-record',document(1),'1')
    add('total-children',expected='4',query='How many children did Birch Vale have?')
    add('direct-api',expected='4',start=API);add('discovered-profile',expected='4',start='https://example.org/family',depth=1)
    add('one-page-cap',pages=1);add('two-page-cap',expected='4',pages=2)
    d=document();d['person']['spouse'].append({'@type':'Person','identifier':'MNOP-789','name':'Willow Ash','gender':'Female'})
    d['person']['children'][0]['otherParentId']='MNOP-789';add('other-partner-filter',d,'3')
    add('no-named-spouse-with-two',d,query='How many children did Birch Vale have with his wife?')
    add('different-requested-spouse',query='How many children did Birch Vale have with his wife, Willow?')
    for name,mutate in [
        ('duplicate-child',lambda d:d['person']['children'].append(deepcopy(d['person']['children'][0]))),
        ('missing-child-id',lambda d:d['person']['children'][0].pop('identifier')),
        ('missing-other-parent',lambda d:d['person']['children'][0].pop('otherParentId')),
        ('unknown-other-parent',lambda d:d['person']['children'][0].update(otherParentId=None)),
        ('wrong-person',lambda d:d['person'].update(identifier='WXYZ-987')),
        ('wrong-profile-link',lambda d:d['person'].update(url=FRONT.replace(PID,'WXYZ-987'))),
        ('wrong-type',lambda d:d['person'].update({'@type':'Organization'})),
        ('partial-snapshot',lambda d:d.update(partial=True)),
        ('paged-snapshot',lambda d:d.update(nextPage='/more')),
        ('private-snapshot',lambda d:d['person'].update(private=True)),
        ('removed-person',lambda d:d.update(removed=True)),
        ('missing-children',lambda d:d['person'].pop('children')),
        ('children-not-array',lambda d:d['person'].update(children={'total':4})),
        ('ambiguous-spouses',lambda d:d['person']['spouse'].append({'@type':'Person','identifier':'MNOP-789','name':'Rowan Ash','gender':'Female'})),
    ]:
        d=document();mutate(d);d['localizedData']['en']['lifeSummary']+=' A nearby unrelated record has 77 entries.'
        add(name,d,mode='malicious')
    add('truncated-response',truncated=True);add('error-status',status=403)
    add('wrong-api-final-url',final=API.replace(PID,'WXYZ-987'))
    add('cross-origin-final-url',final=API.replace('www.familysearch.org','other.example'))
    add('cross-origin-redirect',redirects=['https://other.example/mirror'])
    for mode_name in ['reject','unavailable','invalid','disabled']:add(mode_name,mode=mode_name)
    # Locale metadata may be large; it must never displace the primary record.
    d=document();d['localizedData']={str(i):{'lifeSummary':'Birch Vale reference '+str(i),'metadata':{str(k):str(k) for k in range(100)}} for i in range(45)}
    d['localizedData']['en']={'lifeSummary':'Birch Vale married Rowan Cedar.'};add('translation-flood',d,'4')
    for name,mutate in [
        ('private-child',lambda d:d['person']['children'][0].update(private=True)),
        ('private-spouse',lambda d:d['person']['spouse'][0].update(private=True)),
        ('duplicate-spouse-id',lambda d:d['person']['spouse'].append(deepcopy(d['person']['spouse'][0]))),
        ('subject-is-child',lambda d:d['person']['children'][0].update(identifier=PID)),
        ('spouse-is-child',lambda d:d['person']['children'][0].update(identifier=PARTNER)),
        ('array-over-cap',lambda d:d.update(person=document(129)['person'])),
        ('wrong-api-version',lambda d:d.update(version='2.0')),
        ('missing-api-version',lambda d:d.pop('version')),
        ('count-contradiction',lambda d:d['person'].update(childrenCount=9)),
        ('nested-page-info',lambda d:d['person'].update(childrenPage={'hasMore':True})),
        ('root-count-contradiction',lambda d:d.update(totalChildren=9)),
        ('spouse-page-info',lambda d:d['person'].update(spousePage={'hasMore':True})),
        ('wrong-child-url',lambda d:d['person']['children'][0].update(url=FRONT)),
        ('wrong-spouse-url',lambda d:d['person']['spouse'][0].update(url=FRONT)),
        ('sons-filter',lambda d:None),('wives-filter',lambda d:None),('qualified-children',lambda d:None),
    ]:
        d=document();mutate(d)
        query={'sons-filter':'How many male children did Birch Vale have?',
               'wives-filter':'How many children did Birch Vale have with his first wife, Rowan?',
               'qualified-children':'How many adopted children did Birch Vale have?'}.get(name,q)
        add(name,d,query=query,mode='malicious')
    add('complete-large-collection',document(60),'60')
    d=document();d['person']['children'][0].pop('otherParentId')
    add('total-missing-other-parent',d,'4',query='How many children did Birch Vale have?')
    d=document();d['person']['spouse'][0]['gender']='Male';add('husband-only-as-wife',d)
    d=document();d['person']['spouse'][0]['gender']='Male'
    add('husband-question',d,'4',query='How many children did Birch Vale have with her husband, Rowan?')
    d=document();d['person'].update(childrenCount=4,spouseCount=1);add('matching-declared-counts',d,'4')
    d=document();d['person']['children'][0]['otherParentId']='WXYZ-987';add('unlisted-partner-record',d,'3')
    d=document();d['localizedData']['en']['lifeSummary']='Birch Vale and Rowan Cedar had exactly 77 children.'
    add('conflicting-summary',d,mode='conflict')
    # This is an already exposed actual source, not a synthetic answer fixture.
    receipt=json.loads((ROOT/'benchmarks/family-published-20261024-probe-v1.json').read_text(encoding='utf-8'))
    raw=(ROOT/receipt['capture_path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==receipt['capture_sha256']
    envelope=json.loads(raw);body=base64.b64decode(envelope['body_base64']);assert hashlib.sha256(body).hexdigest()==receipt['body_sha256']
    actual=json.loads(body);person=actual['person'];partner=person['spouse'][0]['identifier']
    expected=str(len({c['identifier'] for c in person['children'] if c['otherParentId']==partner}))
    add('actual-saved-source',actual,expected,query='How many children did Swiss painter Johann Caspar F\u00fcssli have with his wife, Elisabeth?',
        front=person['url'],api=receipt['url'],raw=body.decode('utf-8'))
    actual_case=cases[-1]
    actual_case['capture_sha256']=receipt['capture_sha256'];actual_case['body_sha256']=receipt['body_sha256']
    rows=[]
    try:
        for active in cases:
            source_calls=[];model_calls=[];mode=active.get('mode','honest')
            result=await engine(types.Settings(model_url='' if mode=='disabled' else base,search=False,browser=False,allow_private=True,
                max_depth=active.get('depth',0),max_pages=active.get('pages',10),budget=5)).run(active['query'],active.get('start',active.get('front',FRONT)))
            expected=active['expected'];passed=result.answer==expected and result.sources==([active.get('api',API)] if expected else [])
            if expected:passed &= '/api' in source_calls and any(c['path']=='/verify' for c in model_calls)
            if active['id']=='one-page-cap':passed &= '/api' not in source_calls
            if active['id'] in {'reject','unavailable','invalid'}:passed &= any(c['path']=='/verify' for c in model_calls)
            if active['id']=='actual-saved-source':
                passed &= result.reason=='proof_verified'
                passed &= any('at least 7 sons and 11 daughters' in p['text'] for c in model_calls
                              if c['path']=='/verify' for p in c['data']['passages'])
            if active['id']=='conflicting-summary':passed &= any(c['path']=='/verify' and any('exactly 77 children' in p['text'] for p in c['data']['passages']) for c in model_calls)
            rows.append({'id':active['id'],'passed':bool(passed),'expected':expected,'actual':result.answer,'reason':result.reason,
                         'source_calls':list(source_calls),'model_calls':list(model_calls),'sources':result.sources,
                         **({k:active[k] for k in ['capture_sha256','body_sha256']} if active['id']=='actual-saved-source' else {})})
        return rows
    finally:network.Fetcher.fetch=original;await runner.cleanup()


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();out=Path(args.out)
    if out.exists():raise FileExistsError(out)
    old,revision,hashes=load_engine('53217fc')
    before=asyncio.run(diagnose(old))+guards(old)+asyncio.run(verification_guards(old))
    after=asyncio.run(diagnose(Engine))+guards(Engine)+asyncio.run(verification_guards(Engine))
    assert [r['id'] for r in before]==[r['id'] for r in after]
    report={'scope':__doc__,'baseline':revision,'baseline_hashes':hashes,'before':before,'after':after,
            'before_passed':sum(r['passed'] for r in before),'after_passed':sum(r['passed'] for r in after),'total':len(after),
            'wins':[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
            'losses':[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
            'torch_imported':'torch' in sys.modules,'diagnostic_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'production_sha256':{p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path('agent').glob('*.py'))}}
    out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','torch_imported']}))
    print(json.dumps([r['id'] for r in after if not r['passed']]))
    if not all(r['passed'] for r in after):sys.exit(1)
