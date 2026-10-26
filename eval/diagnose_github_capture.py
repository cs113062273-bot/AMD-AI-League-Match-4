"""Offline replay of two saved official responses, with explicit CPU semantic stubs.

This checks captured API compatibility and provenance, not model accuracy.
No source response is downloaded by this script.
"""
import argparse
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.network import Fetcher, Response
from agent.types import Settings


async def diagnose():
    receipt=json.loads((ROOT/'benchmarks/github-history-20261023-api-probe.json').read_text(encoding='utf-8'))
    bodies={}
    for row in receipt['rows']:
        raw=(ROOT/row['capture_path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Capture changed')
        envelope=json.loads(raw)
        if envelope['url']!=row['url'] or envelope['status']!=200:raise ValueError('Unexpected capture envelope')
        bodies[row['url']]=(envelope,base64.b64decode(envelope['body_base64'],validate=True))
    calls=[];payloads=[];requests=[];rows=[];mode=''
    async def replay(self,url,limit,request_timeout):
        requests.append(url)
        if url not in bodies:raise ValueError('Uncaptured source requested')
        envelope,body=bodies[url]
        return Response(url,body,envelope['content_type'],envelope['charset'],envelope['status'],
            redirects=envelope['redirects'],headers=envelope['headers'])
    async def model(request):
        data=await request.json();calls.append(request.path);payloads.append(data)
        if request.path=='/verify':return web.json_response({'supported':mode!='reject'})
        for passage in data.get('passages',[]):
            match=re.search(r'Licensed under the ([^(]+)',passage['text'])
            if match:return web.json_response({'passage':passage['id'],'answer':match[1].strip()})
        return web.json_response({'passage':-1,'answer':''})
    app=web.Application();app.router.add_post('/{path}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    endpoint='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    try:
        for mode in ['supported','reject','no-model']:
            calls.clear();payloads.clear();requests.clear()
            with patch.object(Fetcher,'_fetch',replay):
                result=await Engine(Settings(model_url='' if mode=='no-model' else endpoint,
                    search=False,browser=False,max_depth=2,budget=12)).run(
                        'What was the license of the GitHub repository psf/requests as of 2020-01-31?')
            expected='Apache License, Version 2.0' if mode=='supported' else ''
            passed=result.answer==expected and (result.sources==list(bodies) if expected else not result.sources)
            if expected:
                proof=result.diagnostics.get('proposed_proof',{})
                atoms=proof.get('atoms',[])
                passed &= len(atoms)==2 and atoms[0]['value']=='2020-01-25T23:19:22Z'
                passed &= len(atoms)==2 and atoms[1]['locator'].startswith('content/base64/')
                passed &= calls==['/select','/verify']
            if mode=='no-model':passed &= not calls
            rows.append(dict(id=mode,passed=bool(passed),expected=expected,actual=result.answer,
                replayed_requests=list(requests),cpu_stub_calls=list(calls),cpu_stub_payloads=list(payloads),result=result.internal()))
    finally:await runner.cleanup()
    return dict(scope=__doc__,capture_receipt=receipt,body_sha256={u:hashlib.sha256(b).hexdigest() for u,(e,b) in bodies.items()},
        passed=sum(r['passed'] for r in rows),total=len(rows),rows=rows,
        production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('app.py'),*sorted(Path('agent').glob('*.py'))]})


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    report=asyncio.run(diagnose());target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['passed','total']}))
    if report['passed']!=report['total']:sys.exit(1)
