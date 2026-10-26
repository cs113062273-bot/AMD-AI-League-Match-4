"""Real Chromium case citation from frozen official responses; optional paired full4B.

No public network in the pair. Logical URLs are served through actual loopback HTTP.
The DOM must contain matching primary case blocks before it can supply a citation.
"""
import argparse
import asyncio
import base64
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.network import Response
from agent.oyez import rendered_case_supported,unrendered_passages
from agent.types import Settings,Page,Passage
from benchmarks.fakeweb import FakeWeb
from diagnose_gpu_recovery import memory
from diagnose_oyez import FRONT,API,KEY,captured
from revision_engine import load_engine

QUESTION='What two football teams were mentioned in the libel case against "The Saturday Evening Post" in 1963?'
ANSWER='University of Georgia and University of Alabama'
CASES=[
    dict(id='real-teams',query=QUESTION,answer=ANSWER,source=FRONT,mode='real'),
    dict(id='real-informant',query='Who was the source of the article in Curtis Publishing v. Butts?',answer='George Burnett',source=FRONT,mode='real'),
    dict(id='api-only-docket',query='What is the docket number of Curtis Publishing Company v. Butts?',answer='37',source=API,mode='real'),
    dict(id='direct-api',query=QUESTION,answer=ANSWER,source=API,mode='api'),
    dict(id='wrong-title',query=QUESTION,answer=ANSWER,source=API,mode='wrong-title'),
    dict(id='shell-only',query=QUESTION,answer=ANSWER,source=API,mode='shell'),
    dict(id='browser-off',query=QUESTION,answer=ANSWER,source=API,mode='off'),
    dict(id='partial-content',query=QUESTION,answer=ANSWER,source=API,mode='partial'),
    dict(id='reading-reserve',query=QUESTION,answer=ANSWER,source=API,mode='real',budget=8)]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshots():
    metadata=json.loads((ROOT/'benchmarks/oyez-render-20261023-probe.json').read_text(encoding='utf-8'))
    path=ROOT/metadata['capture_path'];assert sha(path)==metadata['capture_sha256']
    return json.loads(path.read_text(encoding='utf-8')),metadata['capture_sha256']


def direct():
    from agent.oyez import parse_case
    api_response,_=captured();api=parse_case(api_response,KEY)
    d=json.loads((ROOT/'research/oyez-render-20261023/live-page.json').read_text(encoding='utf-8'))
    d['passages']=[Passage(**p) for p in d['passages']];page=Page(**d)
    rows=[]
    for name,changed,expected in [
        ('real-dom',page,True),('wrong-url',replace(page,url=FRONT[:-2]+'38'),False),
        ('foreign-host',replace(page,url=FRONT.replace('oyez.org','oyez.org.evil.test')),False),
        ('api-url-is-not-frontend',replace(page,url=API),False),
        ('wrong-title',replace(page,title='Wrong case',passages=[p for p in page.passages if p.label!='og:title']),False),
        ('metadata-only',replace(page,passages=[p for p in page.passages if p.kind=='meta']),False),
        ('partial-case',replace(page,passages=[p for p in page.passages if p.section!='Conclusion']),False),
        ('error',replace(page,error='http_403'),False),('truncated',replace(page,truncated=True),False),
        ('no-page',None,False)]:
        actual=rendered_case_supported(api,changed);rows.append(dict(id=name,passed=actual==expected,actual=actual))
    # A first visible paragraph alone must not replace the full API case.
    fact=next(p for p in api.passages if p.kind=='prose')
    partial=Page(FRONT,title=api.title+' | Oyez',passages=[fact])
    rows.append(dict(id='single-block-insufficient',passed=not rendered_case_supported(api,partial)))
    extra=unrendered_passages(api,page)
    rows.append(dict(id='api-only-fields-retained',passed=any(p.label=='docket number' and p.value=='37' for p in extra)
        and not any(p.section in {'facts of the case','question','conclusion'} for p in extra)))
    nested=replace(api,passages=[replace(p,section=p.section+' > Details') if p.section=='facts of the case' else p for p in api.passages])
    missing=replace(page,passages=[p for p in page.passages if p.kind!='prose' or not p.text.startswith(('In New York Times Co.', 'prevent federal marshals'))])
    rows.append(dict(id='nested-headings-full',passed=rendered_case_supported(nested,page)))
    rows.append(dict(id='nested-heading-missing-facts',passed=not rendered_case_supported(nested,missing)))
    return rows


@contextmanager
def replay(engines,source,records):
    contexts=[]
    try:
        for cls in {e.run.__globals__['Fetcher'] for e in engines}:
            original=cls.fetch
            async def fetch(fetcher,url,_original=original,**kwargs):
                if url not in records:return Response(url,status=404,error='not_captured')
                response=await _original(fetcher,source+'/r/'+hashlib.sha256(url.encode()).hexdigest(),**kwargs)
                return replace(response,url=records[url]['url'])
            ctx=patch.object(cls,'fetch',fetch);ctx.__enter__();contexts.append(ctx)
        yield
    finally:
        for ctx in reversed(contexts):ctx.__exit__(None,None,None)


async def paired(engines,model_url,runtime=None):
    records,capture_sha=snapshots();api_response,_=captured()
    rows=[]
    for i,case in enumerate(CASES):
        selected={u:dict(r) for u,r in records.items()}
        if case['mode'] in {'wrong-title','shell','partial'}:
            html='<title>Wrong case</title><p>'+('Wrong case content. '*8)+'</p>' if case['mode']=='wrong-title' else '<title>Oyez</title><div>Loading</div>'
            if case['mode']=='partial':
                data=json.loads(api_response.text)
                html='<title>'+data['name']+' | Oyez</title>'+data['facts_of_the_case']
            selected[FRONT]={**selected[FRONT],'body_base64':base64.b64encode(html.encode()).decode('ascii')}
        routes={'/r/'+hashlib.sha256(u.encode()).hexdigest():(r['status'],r['content_type'],base64.b64decode(r['body_base64']),r.get('headers',{}))
            for u,r in selected.items() if r['status'] and not r.get('error')}
        pair={}
        with FakeWeb(routes) as source,replay(list(engines.values()),source.base,selected):
            for stage in (['before','after'] if i%2==0 else ['after','before']):
                if runtime and memory()['used_mib']>11800:raise RuntimeError('Dedicated memory guard')
                settings=Settings(model_url=model_url,search=False,allow_private=True,max_depth=0,budget=case.get('budget',16),browser=case['mode']!='off')
                started=time.monotonic();result=await engines[stage](settings).run(case['query'],API if case['mode']=='api' else FRONT)
                pair[stage]=dict(result=result.internal(),seconds=time.monotonic()-started,
                    passed=result.answer==case['answer'] and result.sources==[case['source']])
                print(json.dumps(dict(id=case['id'],stage=stage,passed=pair[stage]['passed'],answer=result.answer,sources=result.sources,reason=result.reason)),flush=True)
                if runtime:
                    end=time.monotonic()+2
                    while runtime.active is not None and time.monotonic()<end:await asyncio.sleep(.02)
                    if runtime.active is not None:raise RuntimeError('Worker did not release')
        rows.append(dict(id=case['id'],**pair))
    return rows,capture_sha


async def controlled(engines):
    async def model(request):
        data=await request.json()
        if request.path=='/verify':return web.json_response({'supported':True})
        if 'docket number' in data['question']:
            passage=next((p for p in data['passages'] if 'docket number: 37' in p['text']),None);answer='37'
        else:
            passage=next((p for p in data['passages'] if 'University of Georgia' in p['text'] and 'University of Alabama' in p['text']),None)
            answer='George Burnett' if data['question'].startswith('Who') else ANSWER
        if not passage:return web.json_response({'passage':-1,'answer':''})
        if data['constraints'].get('member_count'):return web.json_response({'passage':passage['id'],'answers':['University of Georgia','University of Alabama']})
        return web.json_response({'passage':passage['id'],'answer':answer})
    app=web.Application();app.router.add_post('/{tail:.*}',model);runner=web.AppRunner(app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    try:return await paired(engines,'http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]))
    finally:await runner.cleanup()


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--model',action='store_true')
    ap.add_argument('--manifest',default='benchmarks/case-citation-20261023-freeze-final.json')
    ap.add_argument('--live-check',action='store_true');args=ap.parse_args();target=Path(args.out)
    if args.live_check and not args.model:ap.error('--live-check requires --model')
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('587ca65');engines={'before':old,'after':Engine}
    production={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'agent').glob('*.py')}
    report=dict(scope=__doc__,model=args.model,baseline=revision,baseline_source_sha256=hashes,
        production_sha256=production,controls=direct(),cases=CASES,rows=[])
    server=None;thread=None
    try:
        if args.model:
            manifest_path=ROOT/args.manifest
            manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
            assert manifest['production_sha256']==production and manifest['runner_sha256']==sha(Path(__file__))
            assert json.loads((ROOT/'benchmarks/case-citation-20261023-cases.json').read_text(encoding='utf-8'))==CASES
            assert manifest['cases_sha256']==sha(ROOT/'benchmarks/case-citation-20261023-cases.json')
            assert manifest['capture_sha256']==snapshots()[1]
            report['freeze_sha256']=sha(manifest_path)
            try:
                with socket.create_connection(('127.0.0.1',8765),timeout=.3):raise RuntimeError('Existing model service')
            except (ConnectionRefusedError,TimeoutError):pass
            initial=memory();report['memory_before']=initial
            if initial['used_mib']>2000:raise RuntimeError('Insufficient GPU headroom')
            os.environ.update(APERTURE_MODEL=str(ROOT/'models/qwen'),APERTURE_VERIFY_MODEL='0',APERTURE_CONTEXT_TOKENS='1536',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
            from agent.model_server import Runtime,make_server
            print(json.dumps({'stage':'loading_owned_full4b','pid':os.getpid(),'memory':initial}),flush=True)
            runtime=Runtime();report['health_before']=runtime.health()
            if memory()['used_mib']>11800:raise RuntimeError('Dedicated memory guard after load')
            server=make_server(runtime,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            report['rows'],report['capture_sha256']=asyncio.run(paired(engines,'http://127.0.0.1:'+str(server.server_port),runtime))
            if args.live_check:
                from diagnose_reader import run as live_run
                cases_path=ROOT/'benchmarks/expansion-20261023-live-cases.json'
                report['live_cases_sha256']=sha(cases_path)
                live_cases=json.loads(cases_path.read_text(encoding='utf-8'))
                capture_dir=ROOT/'research/case-citation-20261023-live3';capture_dir.mkdir(exist_ok=True)
                for case in live_cases:
                    if (capture_dir/(case['id']+'.json')).exists():raise FileExistsError(case['id'])
                report['live_rows']=[]
                settings=Settings(model_url='http://127.0.0.1:'+str(server.server_port),budget=24,max_depth=2,search=True,browser=True)
                asyncio.run(live_run(live_cases,settings,'',stage='actual_web',live_web=True,capture_dir=capture_dir,rows=report['live_rows']))
                report['live_summary']={'exact_answer':sum(r['answer_ok'] for r in report['live_rows']),
                    'strict_joint':sum(r['joint_ok'] for r in report['live_rows']),'total':len(report['live_rows']),
                    'scope':'Same3 exposed originalgold/liveHTTP/search/browser; dynamic evidence, not causal/holdout/newwhole12 score.'}
            report['health_after']=runtime.health()
        else:report['rows'],report['capture_sha256']=asyncio.run(controlled(engines))
    except Exception as exc:report['error']=type(exc).__name__+': '+str(exc)
    finally:
        if server:server.shutdown();server.server_close();thread.join(timeout=2)
        report['production_changed_during_run']=production!={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'agent').glob('*.py')}
        report['comparison']=dict(before_passed=sum(r['before']['passed'] for r in report['rows']),after_passed=sum(r['after']['passed'] for r in report['rows']),total=len(report['rows']),
            wins=[r['id'] for r in report['rows'] if r['after']['passed'] and not r['before']['passed']],losses=[r['id'] for r in report['rows'] if r['before']['passed'] and not r['after']['passed']])
        target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'comparison':report['comparison'],'guards_passed':sum(r['passed'] for r in report['controls']),'guards_total':len(report['controls']),'error':report.get('error')}),flush=True)
    if report.get('error') or report['comparison']['losses'] or not all(r['passed'] for r in report['controls']):sys.exit(1)
