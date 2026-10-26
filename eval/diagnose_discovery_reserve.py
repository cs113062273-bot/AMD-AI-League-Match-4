"""CPU-only real-capture replay and HTTP checks for navigation starving discovery.

Model endpoints are explicit stubs. This tests engine scheduling and literal
evidence flow, not actual model answers, unseen accuracy or source-gold gains.
"""
import argparse
import asyncio
import base64
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.network import Response
from agent.types import Settings
from agent.urls import canonical_url,discovery_url
from diagnose_source_title import read_capture
from revision_engine import load_engine


def actual_captures():
    report=json.loads((ROOT/'benchmarks/external-disjoint12b-20261023-repeat.json').read_text(encoding='utf-8'))
    row=next(r for r in report['rows'] if r['id']=='simpleqa-1232')
    captures=read_capture(row['capture_path'],row['capture_sha256'])
    live=json.loads((ROOT/'benchmarks/village-20261023-discovery.json').read_text(encoding='utf-8'))
    captures.update(read_capture(live['capture_path'],live['sha256']))
    probe=json.loads((ROOT/'benchmarks/village-20261023-probe.json').read_text(encoding='utf-8'))
    hashes={row['capture_path']:row['capture_sha256'],live['capture_path']:live['sha256']}
    for record in probe['rows']:
        path=ROOT/record['capture_path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
        data=json.loads(path.read_text(encoding='utf-8'));data['body']=base64.b64decode(data.pop('body_base64'))
        captures[record['url']]=Response(**data);hashes[record['capture_path']]=record['sha256']
    return row['result']['diagnostics']['plan'],captures,hashes


async def actual(engine,plan,captures):
    missing=[];sent=[]
    class CapturedFetcher:
        def __init__(self,settings,deadline):
            self.settings=settings;self.deadline=deadline;self.events=[];self.cache={}
        async def __aenter__(self):return self
        async def __aexit__(self,*exc):pass
        async def fetch(self,url,**kwargs):
            url=canonical_url(url);response=captures.get(url)
            if response is None:
                missing.append(url);response=Response(url,error='not_captured')
            self.cache[url]=response
            self.events.append(dict(url=url,final=response.url,status=response.status,bytes=len(response.body),
                error=response.error,redirects=response.redirects,truncated=response.truncated,truncation_reason=response.truncation_reason))
            return response
    async def model(settings,deadline,path,data,**kwargs):
        if path=='/expand':return {'terms':['konaruiyeh census data']},'ok'
        if path=='/verify':
            return {'supported':data.get('proposed')=='219' and any('2006 census' in p['text'] and 'population was 219' in p['text'] for p in data['passages'])},'ok'
        if data['question'].startswith('Choose the best available page link'):
            url='https://irandataportal.syr.edu/2006-census'
            p=next((p for p in data['passages'] if url in p['text']),None)
            return ({'passage':p['id'],'answer':url} if p else {'passage':-1,'answer':''}),'ok'
        sent.append(data)
        p=next((p for p in data['passages'] if '2006 census' in p['text'] and 'population was 219' in p['text']),None)
        return ({'passage':p['id'],'answer':'219'} if p else {'passage':-1,'answer':''}),'ok'
    prefix=engine.__module__.rsplit('.',1)[0]
    selector=importlib.import_module(prefix+'.selector');navigation=importlib.import_module(prefix+'.navigation')
    with patch.dict(engine.run.__globals__,Fetcher=CapturedFetcher),patch.object(selector,'request_model',model),patch.object(navigation,'request_model',model):
        result=await engine(Settings(model_url='http://cpu-stub.invalid',browser=False,search=True,
            max_pages=10,max_depth=2,budget=24)).run(plan['question'],plan['url'])
    content=[e['url'] for e in result.diagnostics.get('fetches',[]) if not discovery_url(e['url'])]
    return dict(result=result.internal(),missing_captures=missing,content_requests=content,
        unique_content_requests=len(set(content)),sent_payloads=sent)


async def controlled(engine):
    base='';mode='';hits=[];phone='+1 202-555-0186'
    def anchors(items):return ''.join('<li class="b_algo"><h2><a href="'+base+p+'">'+label+'</a></h2></li>' for p,label in items)
    async def source(request):
        hits.append(request.path)
        if request.path=='/provider':
            first=[('/archive','Boreal Instruments support')]+[('/blocked/'+str(i),'Boreal Instruments support') for i in range(3)]
            pending=[] if mode=='no-pending' else [('/blocked/4','Boreal Instruments support'),('/answer','Boreal Instruments support')]
            if mode=='one-pending':pending=[('/answer','Boreal Instruments support')]
            return web.Response(text=anchors(first+pending),content_type='text/html')
        if request.path=='/archive':
            links=[('/old/'+str(i),'Boreal Instruments support phone') for i in range(4)]
            return web.Response(text='<h1>Boreal Instruments</h1><p>Choose a support archive.</p>'+anchors(links),content_type='text/html')
        if request.path=='/start':
            return web.Response(text='<h1>Boreal Instruments</h1><p>No contact details on this page.</p>',content_type='text/html')
        if request.path=='/answer' and mode!='navigation-answer' or mode in {'navigation-answer','no-pending'} and request.path=='/old/0':
            return web.Response(text='<h1>Boreal Instruments support</h1><p>Support phone: '+phone+'</p>',content_type='text/html')
        if request.path.startswith('/old/'):return web.Response(text='<h1>Boreal Instruments archive</h1><p>Service notices.</p>',content_type='text/html')
        return web.Response(status=403)
    async def model(request):
        data=await request.json()
        if request.path=='/expand':return web.json_response({'terms':[]})
        if request.path=='/verify':return web.json_response({'supported':data.get('proposed')==phone})
        if data['question'].startswith('Choose the best available page link'):
            target=base+'/old/0';p=next((p for p in data['passages'] if target in p['text']),None)
            return web.json_response({'passage':p['id'],'answer':target} if p else {'passage':-1,'answer':''})
        p=next((p for p in data['passages'] if phone in p['text']),None)
        return web.json_response({'passage':p['id'],'answer':phone} if p else {'passage':-1,'answer':''})
    app=web.Application();app.router.add_get('/{tail:.*}',source);app.router.add_post('/{tail:.*}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);rows=[]
    try:
        for mode,pages,depth,expected in [('crowded-navigation',10,2,phone),('navigation-answer',10,2,phone),
            ('no-pending',10,2,phone),('one-pending',10,2,phone),('no-url',10,1,phone),
            ('page-cap',5,2,''),('depth-cap',10,1,'')]:
            hits.clear()
            result=await engine(Settings(model_url=base,search=True,browser=False,allow_private=True,
                max_pages=pages,max_depth=depth,budget=10,search_providers=[(base+'/provider?q=','bing')])).run(
                    'What is the support phone of Boreal Instruments?','' if mode=='no-url' else base+'/start')
            content=[p for p in hits if p!='/provider']
            passed=result.answer==expected and len(content)<=pages and len(content)==len(set(content))
            if mode in {'crowded-navigation','navigation-answer','no-pending'}:passed &= '/old/0' in hits
            if mode in {'page-cap','depth-cap'}:passed &= '/answer' not in hits
            if mode=='no-pending':passed &= not result.diagnostics.get('discovery_reserve')
            initial=content[:4] if mode=='no-url' else content[1:5]
            passed &= set(initial)=={'/archive','/blocked/0','/blocked/1','/blocked/2'} and len(initial)==4
            if mode!='no-url':passed &= content[0]=='/start'
            rows.append(dict(id=mode,passed=bool(passed),hits=list(hits),result=result.internal()))
    finally:await runner.cleanup()
    return rows


async def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out);assert not target.exists()
    old,revision,hashes=load_engine('ed6436c');plan,captures,inputs=actual_captures()
    before=await actual(old,plan,captures);after=await actual(Engine,plan,captures)
    before_controls=await controlled(old);after_controls=await controlled(Engine)
    all_passed=(before['result']['answer']=='' and after['result']['answer']=='219'
        and after['result']['sources']==['https://alchetron.com/Konaruiyeh']
        and not before['missing_captures'] and not after['missing_captures']
        and after['unique_content_requests']<=10 and all(r['passed'] for r in after_controls))
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,input_sha256=inputs,
        before=before,after=after,before_controls=before_controls,after_controls=after_controls,all_passed=all_passed)
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(all_passed=all_passed,before_answer=before['result']['answer'],after_answer=after['result']['answer'],
        before_misses=before['missing_captures'],after_misses=after['missing_captures'],
        before_controls=sum(r['passed'] for r in before_controls),after_controls=sum(r['passed'] for r in after_controls),
        total_controls=len(after_controls),failures=[r['id'] for r in after_controls if not r['passed']],
        reserves=after['result']['diagnostics'].get('discovery_reserve'))))
    if not all_passed:sys.exit(1)


if __name__=='__main__':asyncio.run(main())
