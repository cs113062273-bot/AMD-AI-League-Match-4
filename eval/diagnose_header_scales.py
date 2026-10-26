"""Paired authored CPU HTTP tests of same-column count-scale proofs, not ML accuracy."""
import argparse
import asyncio
from decimal import Decimal,InvalidOperation
import hashlib
import html
import importlib
import inspect
from dataclasses import asdict,replace
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.types import Settings
from revision_engine import load_engine


def table(headers,rows):
    return '<table><tr>'+''.join('<th>'+html.escape(h)+'</th>' for h in headers)+'</tr>'+''.join(
        '<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</table>'


async def diagnose(engine):
    mode='';body='';calls=[];question='';other=''
    async def source(request):
        text=other if request.path=='/other' else body
        return web.Response(text='<h1>Hall inventory</h1>'+text,content_type='text/html')
    def visible(data):
        found=[]
        for p in data.get('passages',[]):
            if not re.search(r'(?:^| \| )Hall: Elm Hall(?: \||$)',p['text']):continue
            if '2020' in question and 'Year:' in p['text'] and 'Year: 2020' not in p['text']:continue
            if 'version 3' in question and 'Version:' in p['text'] and 'Version: 3' not in p['text']:continue
            pattern=r'(?:^| \| )Chairs(?: 2020)?(?: \((?:in )?(thousands?|millions?|billions?|trillions?)\)| in (thousands?|millions?|billions?|trillions?))?: ([^|]+)'
            for match in re.finditer(pattern,p['text'],re.I):
                raw=match[3].strip();unit=(match[1] or match[2] or '').lower().rstrip('s')
                factor={'thousand':1000,'million':10**6,'billion':10**9,'trillion':10**12}.get(unit,1)
                if 'in millions' in question:factor=1
                try:
                    value=Decimal(raw.replace(',',''))*factor
                    full=str(int(value)) if value.is_finite() and value==value.to_integral_value() else raw if factor==1 and 'in millions' in question else ''
                except (InvalidOperation,ValueError,OverflowError):full=''
                found.append((p,raw,full))
        if data.get('proof',{}).get('operation')=='scale_table_count':
            atoms={a['role']:a for a in data['proof']['premises']}
            label=atoms['column_header']['value'];raw=atoms['coefficient']['value'];name=atoms['row_identity']['value']
            match=re.fullmatch(r'Chairs(?: 2020)?(?: \((?:in )?(thousands?|millions?|billions?|trillions?)\)| in (thousands?|millions?|billions?|trillions?))',label,re.I)
            if match and name in question:
                unit=(match[1] or match[2]).lower().rstrip('s')
                full=str(int(Decimal(raw.replace(',',''))*{'thousand':1000,'million':10**6,'billion':10**9,'trillion':10**12}[unit]))
                found.append(({'id':atoms['coefficient']['passage']},raw,full))
        return found
    async def reader(request):
        data=await request.json();calls.append({'path':request.path,'data':data})
        found=visible(data);values={value for p,raw,value in found if value}
        if request.path=='/verify':
            if mode=='unavailable':return web.json_response({'error':'unavailable'},status=503)
            if mode=='invalid':return web.json_response({'supported':'yes'})
            return web.json_response({'supported':mode=='positive' or mode!='reject' and len(values)==1 and data.get('proposed') in values})
        if not found:return web.json_response({'passage':-1,'answer':''})
        p,raw,value=found[0]
        if mode=='positive':
            match=re.search(r'[-+]?[0-9][0-9.,eE+-]*',raw);value=match[0] if match else raw
        return web.json_response({'passage':p['id'],'answer':value if len(values)==1 or mode=='positive' else ''})
    app=web.Application();app.router.add_get('/source',source);app.router.add_get('/other',source);app.router.add_post('/{tail:.*}',reader)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    q='How many chairs does Elm Hall have?';cases=[]
    def add(name,headers,rows,expected,query=q,reader_mode='honest',extra=''):
        cases.append((name,table(headers,rows),expected,query,reader_mode,extra))
    for unit,raw,expected in [('millions','4.2','4200000'),('thousands','4.2','4200'),('billions','0.0042','4200000'),
                              ('trillions','0.0000042','4200000'),('millions','0','0'),('millions','1,200','1200000000')]:
        add(unit+'-'+raw,['Hall','Chairs ('+unit+')'],[['Oak Hall','4'],['Elm Hall',raw]],expected)
    for label in ['Chairs (in millions)','Chairs in millions','Chairs (million)']:
        add(label,['Hall',label],[['Elm Hall','4.2']],'4200000')
    add('ordinary-literal',['Hall','Chairs'],[['Oak Hall','9'],['Elm Hall','4']],'4')
    add('reordered-columns',['Chairs (millions)','Hall'],[['4.2','Elm Hall'],['9','Oak Hall']],'4200000')
    add('wrong-column-number',['Hall','Doors (millions)','Chairs (thousands)'],[['Elm Hall','9','4.2']],'4200')
    add('equivalent-duplicate-columns',['Hall','Chairs (millions)','Chairs (millions)'],[['Elm Hall','4.2','4.2']],'4200000')
    add('equivalent-mixed-columns',['Hall','Chairs','Chairs (millions)'],[['Elm Hall','4200000','4.2']],'4200000')
    add('multiple-row-constraints',['Region','Hall','Chairs (millions)'],[['Cedar District','Oak Hall','9'],['Cedar District','Elm Hall','4.2']],
        '4200000','How many chairs does Elm Hall in Cedar District have?')
    add('multiple-subjects-equal-counts',['Hall','Chairs (millions)'],[['Oak Hall','4.2'],['Elm Hall','4.2']],
        '','How many chairs do Elm Hall and Oak Hall have combined?',reader_mode='positive')
    add('observation-year',['Hall','Year','Chairs (millions)'],[['Elm Hall','2021','9'],['Elm Hall','2020','4.2']],
        '4200000','How many chairs did Elm Hall have in 2020?')
    add('dated-column',['Hall','Chairs 2021 (millions)','Chairs 2020 (millions)'],[['Elm Hall','9','4.2']],
        '4200000','How many chairs did Elm Hall have in 2020?')
    add('version',['Hall','Version','Chairs (millions)'],[['Elm Hall','2','9'],['Elm Hall','3','4.2']],
        '4200000','How many chairs does Elm Hall have in version 3?')
    add('requested-scale-output',['Hall','Chairs (millions)'],[['Elm Hall','4.2']],
        '4.2','How many chairs does Elm Hall have, in millions?')
    for name,headers,rows in [
        ('duplicate-headers',['Hall','Chairs (millions)','Chairs (millions)'],[['Elm Hall','4.2','5.2']]),
        ('conflicting-rows',['Hall','Chairs (millions)'],[['Elm Hall','4.2'],['Elm Hall','5.2']]),
        ('plain-scaled-conflict',['Hall','Chairs','Chairs (millions)'],[['Elm Hall','4','4.2']]),
        ('missing-cell',['Hall','Chairs (millions)'],[['Elm Hall']]),
        ('range',['Hall','Chairs (millions)'],[['Elm Hall','4.2 to 5.2']]),
        ('approximate',['Hall','Chairs (millions)'],[['Elm Hall','about 4.2']]),
        ('negative',['Hall','Chairs (millions)'],[['Elm Hall','-4.2']]),
        ('nonintegral',['Hall','Chairs (millions)'],[['Elm Hall','0.0000001']]),
        ('overflow',['Hall','Chairs (millions)'],[['Elm Hall','1000000000000000']]),
        ('ambiguous-comma',['Hall','Chairs (millions)'],[['Elm Hall','1,25']]),
        ('mixed-scales',['Hall','Chairs (millions or billions)'],[['Elm Hall','4.2']]),
        ('footnote',['Hall','Chairs (millions)'],[['Elm Hall','4.2*']]),
    ]:add(name,headers,rows,'',reader_mode='positive')
    for name in ['reject','unavailable','invalid','disabled']:
        add(name,['Hall','Chairs (millions)'],[['Elm Hall','4.2']],'',reader_mode=name)
    # Two tables in the same source must agree after scale normalization.
    extra=table(['Hall','Chairs'],[['Elm Hall','4']])
    cases.append(('other-table-conflict',table(['Hall','Chairs (millions)'],[['Elm Hall','4.2']])+extra,'',q,'positive',''))
    cases.append(('equivalent-other-table',table(['Hall','Chairs (millions)'],[['Elm Hall','4.2']])+
                  table(['Hall','Chairs'],[['Elm Hall','4200000']]),'4200000',q,'honest',''))
    # Proof validation must see another fetched source; semantic checking must
    # retain relevant prose too, rather than looking only at chosen premises.
    for name,extra in [('appended-inventory-conflict',table(['Hall','Chairs'],[['Elm Hall','4']])),
                       ('prose-context','<p>Elm Hall does not have 4200000 chairs. The inventory is disputed.</p>')]:
        cases.append((name,table(['Hall','Chairs (millions)'],[['Elm Hall','4.2']])+'<a href="/other">Full inventory details</a>',
                      '',q,'positive' if name=='appended-inventory-conflict' else 'reject',extra))
    for name,caption,expected in [('same-caption','All figures are shown in millions','4200000'),
                                   ('conflicting-caption','All figures are shown in thousands',''),
                                   ('long-caption','Notes '*70+'All figures in thousands',''),
                                   ('long-valid-caption','Notes '*70+'All figures in millions','4200000'),
                                   ('over-budget-caption','Notes '*190+'All figures in millions','')]:
        markup=table(['Hall','Chairs (millions)'],[['Elm Hall','4.2']]).replace('<table>','<table><caption>'+caption+'</caption>')
        cases.append((name,markup,expected,q,'positive',''))
    cases.append(('global-section-conflict','<h2>All figures in thousands</h2>'+table(['Hall','Chairs (millions)'],[['Elm Hall','4.2']]),'',q,'positive',''))
    for name,headers,record in [
        ('long-prefix',['Notes','Hall','Chairs (millions)'],['ordinary notes '*90,'Elm Hall','4.2']),
        ('long-suffix',['Hall','Chairs (millions)','Notes'],['Elm Hall','4.2','ordinary notes '*90]),
        ('separated-fields',['Hall','Notes','Chairs (millions)'],['Elm Hall','ordinary notes '*90,'4.2'])]:
        cases.append((name,table(headers,[record]),'4200000',q,'honest',''))
    rows=[]
    try:
        for name,body,expected,question,mode,other in cases:
            calls=[]
            # Both inventories are retrieved in this first response. Direct
            # controls below separately bind actual distinct source pages.
            if other:body+=other
            result=await engine(Settings(model_url='' if mode=='disabled' else base,allow_private=True,
                search=False,browser=False,max_depth=0,budget=4)).run(question,base+'/source')
            passed=result.answer==expected and (bool(result.sources) if expected else not result.sources)
            verification=[c['data'] for c in calls if c['path']=='/verify']
            if name in {'reject','unavailable','invalid'}:passed &= bool(verification)
            if name=='prose-context' and verification:
                passed &= any('inventory is disputed' in p['text'] for p in verification[-1]['passages'])
            for sent in verification:
                passed &= len(sent['passages'])<=8 and all(len(p['text'])<=1100 for p in sent['passages'])
                if sent.get('proof',{}).get('operation')=='scale_table_count':
                    passages={p['id']:p for p in sent['passages']}
                    passed &= all(a.get('passage') in passages and a['value'] in html.unescape(body)
                                  and a['source']==passages[a['passage']]['source'] and 'span' not in a
                                  for a in sent['proof']['premises'])
                    if name=='same-caption':passed &= any(p['text']=='All figures are shown in millions' for p in sent.get('table_captions',[]))
                    if name=='multiple-row-constraints':passed &= {'Elm Hall','Cedar District'}.issubset(
                        {item['value'] for item in sent['proof']['row_identifiers']})
            rows.append({'id':name,'passed':bool(passed),'expected':expected,'actual':result.answer,'reason':result.reason,
                         'source_html':body,'question':question,'calls':list(calls)})
        return rows
    finally:await runner.cleanup()


def guards(engine):
    prefix=engine.__module__.rsplit('.',1)[0]
    proofmod=importlib.import_module(prefix+'.proofs')
    parse=importlib.import_module(prefix+'.parser').parse_response
    response=importlib.import_module(prefix+'.network').Response
    plan_query=importlib.import_module(prefix+'.planner').plan_query
    def page(markup,url='https://inventory.example/source',**kwargs):
        return parse(response(url=url,body=('<h1>Inventory</h1>'+markup).encode(),content_type='text/html',**kwargs))
    query='How many chairs does Elm Hall have?';plan=plan_query(query)
    source=page(table(['Hall','Chairs (millions)'],[['Oak Hall','5.2'],['Elm Hall','4.2']]))
    row=next(p for p in source.passages if p.kind=='table' and p.qualifiers['cells'][0]=='Elm Hall')
    other=next(p for p in source.passages if p.kind=='table' and p.qualifiers['cells'][0]=='Oak Hall')
    atoms=(proofmod.Atom(source.url,row.locator,row.text,'Chairs (millions)','column_header',key='1'),
           proofmod.Atom(source.url,row.locator,row.text,'4.2','coefficient',key='1'),
           proofmod.Atom(source.url,row.locator,row.text,'Elm Hall','row_identity',key='0'))
    proof=proofmod.Proof('scale_table_count',atoms);rows=[]
    def check(name,actual,expected):rows.append({'id':'guard-'+name,'passed':actual==expected,'actual':actual,'expected':expected})
    check('valid-proof',proofmod.validate(proof,plan,[source]),True)
    for name,bad in [('wrong-column',replace(atoms[1],key='0')),('wrong-source',replace(atoms[1],source=source.url+'/other')),
                     ('wrong-locator',replace(atoms[1],locator=other.locator)),
                     ('wrong-row',replace(atoms[1],locator=other.locator,span=other.text,value='5.2')),
                     ('forged-value',replace(atoms[1],value='4200000')),('forged-header',replace(atoms[0],value='Chairs (thousands)')),
                     ('forged-span',replace(atoms[1],span='Hall: Elm Hall | Chairs (millions): 4.2 invented')),
                     ('wrong-role',replace(atoms[1],role='column_header'))]:
        changed=(bad,atoms[1],atoms[2]) if name=='forged-header' else (atoms[0],bad,atoms[2])
        check(name,proofmod.validate(replace(proof,atoms=changed),plan,[source]),False)
    check('reversed-premises',proofmod.validate(replace(proof,atoms=tuple(reversed(atoms))),plan,[source]),False)
    check('missing-premise',proofmod.validate(replace(proof,atoms=atoms[:1]),plan,[source]),False)
    check('wrong-entity',proofmod.validate(proof,plan_query('How many chairs does Oak Hall have?'),[source]),False)
    check('wrong-field',proofmod.validate(proof,plan_query('How many doors does Elm Hall have?'),[source]),False)
    check('different-page-conflict',proofmod.validate(proof,plan,[source,page(table(['Hall','Chairs'],[['Elm Hall','4']]),source.url+'/other')]),False)
    check('equivalent-page',proofmod.validate(proof,plan,[source,page(table(['Hall','Chairs'],[['Elm Hall','4200000']]),source.url+'/other')]),True)
    check('truncated-source',proofmod.validate(proof,plan,[replace(source,truncated=True)]),False)
    check('failed-source',proofmod.validate(proof,plan,[replace(source,error='truncated')]),False)
    for name,bad in [('forged-identity',replace(atoms[2],value='Oak Hall')),('identity-column',replace(atoms[2],key='1')),
                     ('identity-outside-row',replace(atoms[2],key='99'))]:
        check(name,proofmod.validate(replace(proof,atoms=(*atoms[:2],bad)),plan,[source]),False)
    altered=replace(source,passages=[replace(p,qualifiers={k:v for k,v in p.qualifiers.items() if k!='column'}) for p in source.passages])
    # Row proofs derive their own actual column; cell selection hints are not needed.
    check('no-cell-hints-needed',proofmod.validate(proof,plan,[altered]),True)
    for name,key,value in [('missing-row','row',None),('missing-table','table',None),('bad-columns','columns',[]),
                            ('missing-value','cells',['Elm Hall']),('source-continues','source_continues',True)]:
        altered=replace(source,passages=[replace(p,qualifiers={**p.qualifiers,key:value}) for p in source.passages])
        check(name,proofmod.validate(proof,plan,[altered]),False)
    for name,headers,record,q,expected in [
        ('same-noun-identity',['Company','Trees (millions)'],['Forest Trees','4.2'],'How many trees does Forest Trees own?','4200000'),
        ('scale-word-in-name',['Name','Chairs (millions)'],['Million Oaks','4.2'],'How many chairs does Million Oaks have?','4200000'),
        ('population-synonym',['Town','Population (millions)'],['Birch Town','4.2'],'How many inhabitants does Birch Town have?','4200000'),
        ('number-of-form',['Name','Items (thousands)'],['Cedar Store','4.2'],'What is the number of items in Cedar Store?','4200'),
        ('count-of-form',['Name','Seats (thousands)'],['Pine Theatre','4.2'],'What is the count of seats for Pine Theatre?','4200')]:
        target=page(table(headers,[record]));candidate,required=proofmod.propose(plan_query(q),[target])
        check(name,candidate.answer if candidate and required and proofmod.validate(candidate,plan_query(q),[target]) else '',expected)
    # More than 64 matching ordinary rows cannot hide a later scaled conflict.
    lots=page(table(['Hall','Chairs'],[['Elm Hall','4'] for _ in range(70)])+
              table(['Hall','Chairs (millions)'],[['Elm Hall','4.2']]))
    candidate,required=proofmod.propose(plan,[lots])
    check('many-rows-conflict',bool(candidate),False);check('many-rows-derivation-required',required,True)
    lots=page(table(['Hall','Chairs'],[['Elm Hall','4200000'] for _ in range(70)])+
              table(['Hall','Chairs (millions)'],[['Elm Hall','4.2']]))
    candidate,required=proofmod.propose(plan,[lots])
    check('many-agreeing-rows',candidate.answer if candidate and required else '', '4200000')
    return rows


async def verification_guards(engine):
    prefix=engine.__module__.rsplit('.',1)[0]
    mod=importlib.import_module(prefix+'.proofs');selection=importlib.import_module(prefix+'.selector')
    parse=importlib.import_module(prefix+'.parser').parse_response
    Response=importlib.import_module(prefix+'.network').Response
    types=importlib.import_module(prefix+'.types');planner=importlib.import_module(prefix+'.planner')
    source=parse(Response(url='https://inventory.example/source',content_type='text/html',
                         body=table(['Hall','Chairs (millions)'],[['Elm Hall','4.2']]).encode()))
    passage=next(p for p in source.passages if p.kind=='table')
    proof=mod.Proof('scale_table_count',(
        mod.Atom(source.url,passage.locator,passage.text,'Chairs (millions)','column_header',key='1'),
        mod.Atom(source.url,passage.locator,passage.text,'4.2','coefficient',key='1'),
        mod.Atom(source.url,passage.locator,passage.text,'Elm Hall','row_identity',key='0')))
    others=[types.Page('https://inventory.example/note'+str(i),passages=[types.Passage('Unrelated note '+str(i),locator='p:1')]) for i in range(6)]
    disputed=types.Page('https://inventory.example/dispute',passages=[types.Passage('Elm Hall actually has 8 chairs. Inventory sources disagree.',locator='p:1')])
    pages=[source,*others,disputed]
    context=[(source,passage,10)]+[(p,p.passages[0],1) for p in [*others,disputed]]
    plan=planner.plan_query('How many chairs does Elm Hall have?');calls=[];reject_conflict=False
    async def verifier(request):
        data=await request.json();calls.append(data)
        conflict=any('Inventory sources disagree.' in p['text'] for p in data['passages'])
        return web.json_response({'supported':not (reject_conflict and conflict)})
    app=web.Application();app.router.add_post('/verify',verifier)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);rows=[]
    try:
        for name,candidate,ctx,conflict,expected,expected_call in [
            ('valid-request',proof,context,False,True,True),
            ('invalid-source',replace(proof,atoms=(replace(proof.atoms[0],source=source.url+'/fake'),*proof.atoms[1:])),context,False,False,False),
            ('missing-context',proof,[],False,False,False),
            ('missing-witness',proof,context[1:],False,False,False),
            ('eighth-context-conflict',proof,context,True,False,True)]:
            calls=[];reject_conflict=conflict
            args=[plan,candidate,pages,types.Settings(model_url=base),types.Deadline(4)]
            if 'context' in inspect.signature(selection.verify_proof).parameters:args.append(ctx)
            try:supported,state=await selection.verify_proof(*args)
            except (ValueError,IndexError) as exc:
                if 'context' in inspect.signature(selection.verify_proof).parameters:raise
                # Historical proof serialization only supports two premises;
                # record its actual exception for this new operation.
                supported=False;state='unsupported_operation_'+type(exc).__name__
            passed=supported==expected and bool(calls)==expected_call
            if name=='eighth-context-conflict' and calls:
                sent=calls[-1]['passages']
                passed &= len(sent)==8 and any(p['source']==disputed.url for p in sent)
            rows.append({'id':'verify-'+name,'passed':bool(passed),'state':state,'supported':supported,'calls':list(calls)})
        return rows
    finally:await runner.cleanup()


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();out=Path(args.out)
    if out.exists():raise FileExistsError(out)
    old,revision,hashes=load_engine('40dd82c')
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
