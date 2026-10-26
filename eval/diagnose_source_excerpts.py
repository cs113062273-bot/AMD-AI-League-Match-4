"""Paired, authored CPU HTTP evidence-fidelity controls; no LLM or accuracy claim."""
import argparse
import asyncio
import importlib
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent import selector
from agent.engine import Engine
from agent.cardinals import count_value
from agent.planner import plan_query
from agent.types import Candidate,Page,Passage,Settings,Deadline
from revision_engine import load_engine


async def diagnose(engine,selection):
    prefix='Oak Hall has 4 chairs. '
    target='Elm Hall has '
    padding='x'*(1099-len(prefix)-len(target)-1)+' '
    boundary=prefix+padding+target+'4 million chairs.'
    cases=[('tail-magnitude','Elm',boundary,'4000000'),
           ('earlier-literal','Oak',boundary,'4'),
           ('ordinary','Elm','Elm Hall has 4 million chairs.','4000000'),
           ('conflict','Elm','Elm Hall has 4 million chairs. Elm Hall has 5 million chairs.',''),
           ('tail-conflict','Elm',prefix+padding+target+'4 million chairs. Elm Hall has 5 million chairs.',''),
           ('word-magnitude','Elm',prefix+padding+target+'four million chairs.','4000000'),
           ('decimal-magnitude','Elm',prefix+padding+target+'1.25 million chairs.','1250000')]
    forced=None;calls=[];html='';entity='Elm'
    async def source(request):return web.Response(text=html,content_type='text/html')
    async def reader(request):
        data=await request.json();calls.append({'path':request.path,'data':data})
        if forced is not None:return web.json_response(forced)
        found=[]
        for p in data.get('passages',[]):
            for m in re.finditer(entity+r' Hall has (four million|[0-9.]+(?: million)?)(?: chairs\.|$)',p['text']):
                found.append((p,m[1]))
        values={str(count_value(raw)) if count_value(raw) is not None else raw for p,raw in found}
        if request.path=='/verify':return web.json_response({'supported':len(values)==1 and data.get('proposed') in values})
        p,raw=found[0] if len(values)==1 else (None,'')
        return web.json_response({'passage':p['id'] if p else -1,'answer':raw})
    app=web.Application();app.router.add_get('/source',source);app.router.add_post('/{tail:.*}',reader)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);rows=[]
    try:
        for name,entity,text,expected in cases:
            html='<h1>'+entity+' Hall</h1><p>'+text+'</p>';calls=[]
            result=await engine(Settings(model_url=base,allow_private=True,search=False,browser=False,max_depth=0,budget=4)).run(
                'How many chairs does '+entity+' Hall have?',base+'/source')
            rows.append({'id':name,'passed':result.answer==expected,'answer':result.answer,'expected':expected,'reason':result.reason,
                         'source_text':text,'source_sha256':hashlib.sha256(html.encode()).hexdigest(),'calls':list(calls)})
            rows.append({'id':name+'-bounds','passed':bool(calls) and all(len(c['data']['passages'])<=8
                         and all(len(p['text'])<=1100 for p in c['data']['passages']) for c in calls)})
            selects=[c['data'] for c in calls if c['path']=='/select'];verifies=[c['data'] for c in calls if c['path']=='/verify']
            key=lambda p:(p['source'],p.get('locator'),p['text'])
            same=bool(selects and verifies) and set(map(key,selects[0]['passages']))==set(map(key,verifies[0]['passages']))
            rows.append({'id':name+'-same-context','passed':same or not expected and not verifies})
        # A literal elsewhere in the source must not authorize an unsent answer.
        plan=plan_query('What is the code for Elm Hall?')
        text='Hidden code: Z9. '+('padding '*155)+'Elm Hall code: R8.'
        passage=Passage(text,locator='p:1');page=Page(base+'/source',passages=[passage])
        sent=selection.payload(plan,[],[(page,passage,1)])['passages'][0]
        rows.append({'id':'source-slice','passed':sent['text'] in text})
        rows.append({'id':'target-retained','passed':'Elm Hall code: R8.' in sent['text']})
        rows.append({'id':'word-boundaries','passed':not sent['text'].startswith('adding') and not sent['text'].endswith('padd')})
        forced={'passage':0,'answer':'Z9'}
        chosen,state=await selection.select(plan,[],[(page,passage,1)],Settings(model_url=base),Deadline(4))
        rows.append({'id':'unsent-literal-rejected','passed':chosen is None and state=='invalid_selection'})
        forced={'supported':True};calls=[]
        fake=Candidate('Z9','Z9',page.url,'Invented code: Z9.',signals={'locator':'fake'})
        valid,state=await selection.verify_selection(plan,fake,[(page,passage,1)],Settings(model_url=base),Deadline(4))
        rows.append({'id':'unbound-evidence-rejected','passed':not valid and not calls})
        # Multi-member mechanical checks must use the same shifted slice.
        member_plan=plan_query('Which two teams played in the Cedar Cup?')
        member_text='Other event preview. '+('padding '*150)+'The Cedar Cup featured Maple United against Cedar FC.'
        member_passage=Passage(member_text,locator='p:3');member_page=Page(base+'/members',passages=[member_passage])
        forced={'passage':0,'answers':['Maple United','Cedar FC']}
        chosen,state=await selection.select(member_plan,[],[(member_page,member_passage,1)],Settings(model_url=base),Deadline(4))
        mechanical=importlib.import_module(selection.__package__+'.candidates').verify
        rows.append({'id':'late-members-mechanical','passed':bool(chosen) and mechanical(chosen,member_plan,[member_page])})
        # Full-field projection remains restricted to what the reader saw.
        license_plan=plan_query('What is the license of River?')
        license_text='Other package notes. '+('padding '*150)+'River license: MIT OR Apache-2.0'
        license_passage=Passage(license_text,label='license',value='MIT OR Apache-2.0',kind='json',locator='license')
        license_page=Page(base+'/license',passages=[license_passage])
        forced={'passage':0,'answer':'MIT'}
        chosen,state=await selection.select(license_plan,[],[(license_page,license_passage,1)],Settings(model_url=base),Deadline(4))
        rows.append({'id':'late-license-projection','passed':bool(chosen) and chosen.answer=='MIT OR Apache-2.0'
                     and mechanical(chosen,license_plan,[license_page])})
        parent=Passage('name: River; license: MIT OR Apache-2.0',label='name',value='River',kind='json',locator='record.name')
        field=Passage('license: MIT OR Apache-2.0',label='license',value='MIT OR Apache-2.0',kind='json',locator='record.license')
        extras=[Passage('Other source note '+str(i),locator='p:'+str(i)) for i in range(6)]
        conflict=Passage('River license: ISC',locator='p:conflict')
        projection_page=Page(base+'/projection',passages=[parent,field,*extras,conflict])
        ranked=[(projection_page,p,1) for p in [parent,*extras,conflict]]
        chosen,state=await selection.select(license_plan,[],ranked,Settings(model_url=base),Deadline(4))
        sent=selection.payload(license_plan,[],ranked)['passages']
        forced={'supported':True};calls=[]
        if chosen:await selection.verify_selection(license_plan,chosen,ranked,Settings(model_url=base),Deadline(4))
        key=lambda p:(p['source'],p.get('locator'),p['text'])
        rows.append({'id':'projection-retains-all-contexts','passed':bool(calls)
                     and set(map(key,sent))==set(map(key,calls[-1]['data']['passages']))})
        author_plan=plan_query('Who is the first author of the Birch report?')
        author=Passage('Authors: Vale, Mira; Finch, Rowan.',label='authors',locator='authors')
        first=Passage('first author: Mira Vale',label='first author',value='Mira Vale',kind='field',locator='first-author')
        author_page=Page(base+'/authors',passages=[author,first,*extras,conflict])
        ranked=[(author_page,p,1) for p in [author,*extras,conflict]]
        forced={'passage':0,'answer':'Vale, Mira'}
        chosen,state=await selection.select(author_plan,[],ranked,Settings(model_url=base),Deadline(4))
        rows.append({'id':'canonical-author-preserved','passed':bool(chosen) and chosen.answer=='Mira Vale'
                     and mechanical(chosen,author_plan,[author_page])})
        sent=selection.payload(author_plan,[],ranked)['passages'];forced={'supported':True};calls=[]
        if chosen:await selection.verify_selection(author_plan,chosen,ranked,Settings(model_url=base),Deadline(4))
        rows.append({'id':'canonical-author-retains-contexts','passed':bool(calls)
                     and set(map(key,sent))==set(map(key,calls[-1]['data']['passages']))})
        forced=None
        # Duplicate source text on different URLs/locators is distinct context.
        short=Passage('Elm Hall has 4 chairs.',locator='p:2');page=Page(base+'/source',passages=[short]);p2=Page(base+'/other',passages=[short])
        chosen,state=await selection.select(plan_query('How many chairs does Elm Hall have?'),[],[(page,short,1),(p2,short,1)],Settings(model_url=base),Deadline(4))
        if chosen:
            calls=[];await selection.verify_selection(plan_query('How many chairs does Elm Hall have?'),chosen,[(page,short,1),(p2,short,1)],Settings(model_url=base),Deadline(4))
            rows.append({'id':'distinct-sources-retained','passed':len(calls[-1]['data']['passages'])==2})
        else:rows.append({'id':'distinct-sources-retained','passed':False})
        # Different names, ordinary padding, shifts and unsupported quantities:
        # the entire requested assertion must survive, including its qualifier.
        query=plan_query('How many seats does Birch Theatre have?')
        for offset in [1080,1099,1100,1120]:
            for raw in ['7 million','1.25 million','four hundred and five','4 to 6 million',
                        'at least 7 million','about four million','not 7 million']:
                assertion='Birch Theatre has '+raw+' seats.'
                prefix='Other rooms have 7 seats. '
                pad=('ordinary notes '*100)[:offset-len(prefix)-len('Birch Theatre has ')]+' '
                text=prefix+pad+assertion;passage=Passage(text)
                visible=selection.payload(query,[],[(page,passage,1)])['passages'][0]
                rows.append({'id':'shift-'+str(offset)+'-'+raw,'passed':assertion in visible['text']
                             and visible['text'] in text and len(visible['text'])<=1100})
        return rows
    finally:await runner.cleanup()


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();out=Path(args.out)
    if out.exists():raise FileExistsError(out)
    old,revision,hashes=load_engine('c02cacf');old_selector=importlib.import_module(old.__module__.rsplit('.',1)[0]+'.selector')
    before=asyncio.run(diagnose(old,old_selector));after=asyncio.run(diagnose(Engine,selector))
    report={'scope':__doc__,'baseline':revision,'baseline_hashes':hashes,'before':before,'after':after,'torch_imported':'torch' in sys.modules,
            'before_passed':sum(r['passed'] for r in before),'after_passed':sum(r['passed'] for r in after),'total':len(after)}
    assert [r['id'] for r in before]==[r['id'] for r in after]
    report.update(diagnostic_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path('agent').glob('*.py'))},
                  wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
                  losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']])
    out.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','torch_imported']}))
    print(json.dumps([r for r in after if not r['passed']]))
    if not all(r['passed'] for r in after):sys.exit(1)
