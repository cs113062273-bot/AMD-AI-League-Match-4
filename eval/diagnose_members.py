"""Literal-member protocol and end-to-end HTTP guards; semantic replies are controlled.

This isolates mechanical source binding. It is not real-model accuracy evidence.
"""
import argparse
import asyncio
from copy import deepcopy
from dataclasses import replace
import importlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.model_protocol import validate_reply
from agent.planner import plan_query
from agent.selector import payload,select
from agent.types import Candidate,Deadline,Page,Passage,Settings
from agent.candidates import verify
from revision_engine import load_engine

QUESTION='Which two football teams played in the Cedar Cup?'
TEXT='The Cedar Cup featured Maple United, coached by Mira Chen, against Cedar FC, coached by Orin Vale.'
VALUES=['Maple United','Cedar FC']


def protocol(check):
    passage=Passage(TEXT);page=Page('https://example.org/cup',passages=[passage])
    request=payload(plan_query(QUESTION),[],[(page,passage,8)])
    valid={'passage':0,'answers':VALUES};rows=[]
    controls=[('valid',valid,True),('missing',{'passage':0,'answers':['Maple United']},False),
        ('invented',{'passage':0,'answers':['Maple United','Birch FC']},False),
        ('duplicate',{'passage':0,'answers':['Maple United','Maple United']},False),
        ('containment',{'passage':0,'answers':['Maple United','United']},False),
        ('unsent-id',{'passage':8,'answers':VALUES},False),
        ('bool-id',{'passage':False,'answers':VALUES},False),
        ('candidate-mixed',{'candidate':0,'passage':0,'answers':VALUES},False),
        ('bool-candidate',{'candidate':False,'passage':0,'answers':VALUES},False),
        ('wrong-string',{'passage':0,'answers':VALUES,'answer':'Other'},False),
        ('non-string',{'passage':0,'answers':VALUES,'answer':[]},False),
        ('bad-member',{'passage':0,'answers':['Maple United',False]},False),
        ('changed-case',{'passage':0,'answers':['maple United','Cedar FC']},False),
        ('single-span',{'passage':0,'answer':'Maple United'},False),
        ('empty-member-abstain',{'passage':-1,'answers':[]},True),
        ('empty-with-answer',{'passage':-1,'answers':[],'answer':'Maple United'},False),
        ('abstain',{'passage':-1,'answer':''},True)]
    for name,reply,expected in controls:
        actual=check(reply,request)
        rows.append(dict(id=name,passed=('error' not in actual)==expected,reply=actual))
    for name,changed in [('singular',{'question':'Which football team played?'}),
                         ('date',{'constraints':dict(request['constraints'],kind='date')}),
                         ('compose-fields',{'constraints':dict(request['constraints'],operation='compose_fields')}),
                         ('forged-count',{'constraints':dict(request['constraints'],member_count=3)})]:
        changed={**request,**changed};actual=check(valid,changed)
        rows.append(dict(id=name,passed='error' in actual,reply=actual))
    long=deepcopy(request);long['passages'][0]['text']=TEXT+' x'*600+' Birch FC'
    # What was not sent to the selector cannot become evidence in its response.
    long['passages'][0]['text']=long['passages'][0]['text'][:1100]
    actual=check({'passage':0,'answers':['Maple United','Birch FC']},long)
    rows.append(dict(id='unsent-suffix',passed='error' in actual,reply=actual))
    split=deepcopy(request);split['passages']=[{'id':0,'text':'Maple United played.'},{'id':1,'text':'Cedar FC played.'}]
    actual=check(valid,split);rows.append(dict(id='different-passages',passed='error' in actual,reply=actual))
    four=deepcopy(request);four['question']='Which four cities hosted the festival?'
    four['constraints'].update(member_count=4,cardinality=4)
    four['passages']=[{'id':0,'text':'Oslo hosted in spring. Lima hosted in summer. Kyoto hosted in autumn. Bern hosted in winter.'}]
    actual=check({'passage':0,'answers':['Oslo','Lima','Kyoto','Bern']},four)
    rows.append(dict(id='four-members',passed=actual.get('answer')=='Oslo, Lima, Kyoto and Bern',reply=actual))
    return rows


def source_guards():
    p=Passage(TEXT,locator='p[0]');page=Page('https://example.org/cup',passages=[p]);plan=plan_query(QUESTION)
    c=Candidate('Maple United and Cedar FC','Maple United and Cedar FC',page.url,p.text,
                signals={'literal_spans':VALUES,'locator':p.locator})
    rows=[]
    for name,candidate,pages,expected in [('bound',c,[page],True),
        ('wrong-source',replace(c,source='https://example.org/other'),[page],False),
        ('fabricated-evidence',replace(c,evidence=TEXT+' Invented text'),[page],False),
        ('altered-output',replace(c,answer='Maple United and Birch FC'),[page],False),
        ('empty-spans',replace(c,signals={'literal_spans':[]}),[page],False)]:
        actual=verify(candidate,plan,pages);rows.append(dict(id=name,passed=actual==expected,actual=actual))
    q='Which two authors won the Cedar Prize in 1998?'
    for name,text,expected in [('both-dated','Mira Chen won the Cedar Prize in 1998. Orin Vale won the Cedar Prize in 1998.',True),
        ('one-undated','Mira Chen won the Cedar Prize in 1998. Orin Vale won another award.',False),
        ('wrong-date','Mira Chen won the Cedar Prize in 1998. Orin Vale won the Cedar Prize in 2001.',False)]:
        p=Passage(text);page=Page(c.source,passages=[p]);c2=replace(c,raw='Mira Chen and Orin Vale',answer='Mira Chen and Orin Vale',
            evidence=text,signals={'literal_spans':['Mira Chen','Orin Vale']})
        actual=verify(c2,plan_query(q),[page]);rows.append(dict(id=name,passed=actual==expected,actual=actual))
    q='Which two rivers form the northern boundary of Cedar District?'
    text='The northern boundary is Linden River. The southern boundary is Birch River.'
    page=Page(c.source,passages=[Passage(text)])
    c2=replace(c,raw='Linden River and Birch River',answer='Linden River and Birch River',evidence=text,
        signals={'literal_spans':['Linden River','Birch River']})
    rows.append(dict(id='one-wrong-direction',passed=not verify(c2,plan_query(q),[page])))
    for question,expected in [(QUESTION,2),('Which four cities hosted the festival?',4),('How many teams played?',1)]:
        actual=plan_query(question).cardinality
        rows.append(dict(id='cardinality-'+str(expected)+'-'+str(len(rows)),passed=actual==expected,actual=actual))
    return rows


async def http(engine):
    mode='';calls=[]
    async def source(request):return web.Response(text='<title>Cedar Cup</title><p>'+TEXT+'</p>',content_type='text/html')
    async def model(request):
        data=await request.json();calls.append((request.path,data))
        if request.path=='/verify':return web.json_response({'supported':mode!='wrong-type'})
        if mode=='unsent-id':return web.json_response({'passage':8,'answers':VALUES})
        values=['Mira Chen','Orin Vale'] if mode=='wrong-type' else ['Maple United','Birch FC'] if mode=='invented' else VALUES
        p=next(p for p in data['passages'] if 'Maple United' in p['text'])
        return web.json_response({'passage':p['id'],'answers':values})
    app=web.Application();app.router.add_get('/cup',source);app.router.add_post('/{tail:.*}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);rows=[]
    try:
        for mode in ['valid','invented','unsent-id','wrong-type']:
            calls.clear();result=await engine(Settings(model_url=base,allow_private=True,search=False,max_depth=0,budget=5)).run(QUESTION,base+'/cup')
            expected='Maple United and Cedar FC' if mode=='valid' else ''
            passed=result.answer==expected and result.sources==([base+'/cup'] if expected else [])
            if expected:passed=passed and [p for p,d in calls]==['/select','/verify']
            rows.append(dict(id='http-'+mode,passed=passed,calls=[p for p,d in calls],result=result.internal()))
    finally:await runner.cleanup()
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('4141065');old_protocol=importlib.import_module(old.__module__.rsplit('.',1)[0]+'.model_protocol').validate_reply
    before=protocol(old_protocol)+asyncio.run(http(old));after=protocol(validate_reply)+asyncio.run(http(Engine))
    guards=source_guards()
    report=dict(scope=__doc__,baseline=revision,before=before,after=after,source_guards=guards,
        before_passed=sum(r['passed'] for r in before),after_passed=sum(r['passed'] for r in after),total=len(after),
        wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
        losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']])
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    print(json.dumps({'guards_passed':sum(r['passed'] for r in guards),'guards_total':len(guards)}))
    if not all(r['passed'] for r in after+guards):sys.exit(1)
