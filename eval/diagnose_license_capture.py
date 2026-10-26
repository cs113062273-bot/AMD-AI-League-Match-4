"""Replay the saved official itoa body with partial CPU selections, no public requests.

Development source-compatibility evidence, not real-model or held-out accuracy.
"""
import argparse
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.network import Response
from agent.types import Settings
from revision_engine import load_engine


async def diagnose():
    receipt=json.loads((ROOT/'benchmarks/crates-history-20261023-live-v1.json').read_text(encoding='utf-8'))
    capture=receipt['captures'][0];raw=(ROOT/capture['capture_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=capture['capture_sha256']:raise ValueError('Capture changed')
    envelope=json.loads(raw);body=base64.b64decode(envelope['body_base64'],validate=True)
    if hashlib.sha256(body).hexdigest()!=capture['body_sha256']:raise ValueError('Body changed')
    mode='';calls=[];payloads=[];rows=[];requests=[]
    async def replay(self,url,limit,request_timeout):
        requests.append(url)
        if url!=envelope['url']:raise ValueError('Uncaptured source requested')
        return Response(url,body,envelope['content_type'],envelope['charset'],envelope['status'])
    async def model(request):
        data=await request.json();calls.append(request.path);payloads.append(data)
        if request.path=='/verify':
            if mode=='unavailable':return web.json_response({'error':'unavailable'},status=503)
            return web.json_response({'supported':mode!='reject'})
        if mode=='abstain':return web.json_response({'passage':-1,'answer':''})
        answer='Apache-2.0' if mode=='other-branch' else 'MIT OR Apache-2.0' if mode=='full' else 'MIT'
        for p in data.get('passages',[]):
            if p['locator'].endswith('.license') and 'MIT OR Apache-2.0' in p['text']:
                return web.json_response({'passage':p['id'],'answer':answer})
        return web.json_response({'passage':-1,'answer':''})
    app=web.Application();app.router.add_post('/{path}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    endpoint='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    before,revision,hashes=load_engine('8e264c6')
    try:
        for stage,engine in [('baseline',before),('after',Engine)]:
            for mode in ['partial','other-branch','full','option','reject','unavailable','abstain','no-model']:
                calls.clear();payloads.clear();requests.clear()
                query='What was the license of the crates.io crate itoa as of 2020-01-31?'
                if mode=='option':query='Which license option other than Apache-2.0 was offered for the crates.io crate itoa as of 2020-01-31?'
                with patch.object(engine.run.__globals__['Fetcher'],'_fetch',replay):
                    result=await engine(Settings(model_url='' if mode=='no-model' else endpoint,search=False,browser=False,budget=12)).run(query)
                if mode in {'reject','unavailable','abstain'}:expected=''
                elif mode=='option':expected='MIT'
                elif stage=='baseline' and mode in {'partial','other-branch'}:expected='MIT' if mode=='partial' else 'Apache-2.0'
                else:expected='MIT OR Apache-2.0'
                passed=result.answer==expected and (result.sources==[envelope['url']] if expected else not result.sources)
                if expected and mode!='no-model':
                    checks=[p for p,c in zip(payloads,calls) if c=='/verify']
                    passed &= bool(checks) and checks[-1]['proposed']==expected
                if mode=='no-model':passed &= not calls
                rows.append(dict(id=stage+'-'+mode,passed=bool(passed),expected_behavior=expected,actual=result.answer,
                    replayed_requests=list(requests),cpu_stub_calls=list(calls),cpu_stub_payloads=list(payloads),result=result.internal()))
    finally:await runner.cleanup()
    return dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,capture=capture,
        passed=sum(r['passed'] for r in rows),total=len(rows),rows=rows,
        note='Baseline partial results describe the reproduced field loss. The assertion total checks replay behavior, not answer correctness.',
        production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('app.py'),*sorted(Path('agent').glob('*.py'))]})


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    report=asyncio.run(diagnose());target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['passed','total']}))
    if report['passed']!=report['total']:sys.exit(1)
