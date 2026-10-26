"""Same saved source for exposed failure 911, original selected span, CPU stubs only.

Source-assisted development replay; not a new sample or actual model assessment.
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
from eval.run import score
from revision_engine import load_engine


async def diagnose():
    first_path=ROOT/'benchmarks/external-disjoint12b-20261023-first.json'
    cases_path=ROOT/'benchmarks/external-disjoint12b-20261023.json'
    first=json.loads(first_path.read_text(encoding='utf-8'))
    row=next(r for r in first['rows'] if r['id']=='simpleqa-911')
    case=next(c for c in json.loads(cases_path.read_text(encoding='utf-8')) if c['id']==row['id'])
    capture_path=ROOT/row['capture_path'];raw=capture_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=row['capture_sha256']:raise ValueError('Saved source changed')
    capture=json.loads(raw);selected=row['result']['answer'];calls=[];payloads=[];requests=[];rows=[];mode=''
    async def replay(self,url,limit,request_timeout):
        requests.append(url)
        if url not in capture:raise ValueError('Uncaptured request')
        e=capture[url]
        return Response(e['url'],base64.b64decode(e['body_base64']),e['content_type'],e['charset'],e['status'],
            redirects=e['redirects'],headers=e['headers'])
    async def model(request):
        data=await request.json();calls.append(request.path);payloads.append(data)
        if request.path=='/verify':
            if mode=='unavailable':return web.json_response({'error':'unavailable'},status=503)
            return web.json_response({'supported':mode!='reject'})
        if mode=='abstain':return web.json_response({'passage':-1,'answer':''})
        for p in data.get('passages',[]):
            if selected in p['text']:return web.json_response({'passage':p['id'],'answer':selected})
        return web.json_response({'passage':-1,'answer':''})
    app=web.Application();app.router.add_post('/{path}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    endpoint='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    before,revision,hashes=load_engine('c77246d')
    try:
        for stage,engine in [('baseline',before),('after',Engine)]:
            for mode in ['supported','reject','unavailable','abstain']:
                calls.clear();payloads.clear();requests.clear()
                with patch.object(engine.run.__globals__['Fetcher'],'_fetch',replay):
                    result=await engine(Settings(model_url=endpoint,search=False,browser=False,max_depth=0,budget=12)).run(case['query'],case['url'])
                answer_ok,source_ok,expected_source,joint,category=score(result.answer,result.sources,case)
                if mode=='supported':passed=(result.answer==selected if stage=='baseline' else joint) and result.sources==[case['url']]
                else:passed=not result.answer and not result.sources
                if mode=='supported' and stage=='after':
                    checks=[p for p,c in zip(payloads,calls) if c=='/verify']
                    passed &= bool(checks) and checks[-1]['proposed']==result.answer
                    passed &= bool(result.diagnostics.get('selection',{}).get('signals',{}).get('name_boundary'))
                rows.append(dict(id=stage+'-'+mode,passed=bool(passed),actual=result.answer,
                    answer_ok=answer_ok,source_ok=source_ok,joint_ok=joint,failure_category=category,
                    replayed_requests=list(requests),cpu_stub_calls=list(calls),cpu_stub_payloads=list(payloads),result=result.internal()))
    finally:await runner.cleanup()
    return dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,
        cases_sha256=hashlib.sha256(cases_path.read_bytes()).hexdigest(),first_assessment_sha256=hashlib.sha256(first_path.read_bytes()).hexdigest(),
        capture_path=row['capture_path'],capture_sha256=row['capture_sha256'],original_model_selection=selected,
        passed=sum(r['passed'] for r in rows),total=len(rows),rows=rows,
        note='Assertions describe both baseline failure and updated CPU replay behavior; not eight correct answers or actual-model assessment accuracy.',
        production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('app.py'),*sorted(Path('agent').glob('*.py'))]})


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    report=asyncio.run(diagnose());target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'],total=report['total'],supported=[
        {k:r[k] for k in ['id','actual','answer_ok','source_ok','joint_ok']} for r in report['rows'] if r['id'].endswith('-supported')])))
    if report['passed']!=report['total']:sys.exit(1)
