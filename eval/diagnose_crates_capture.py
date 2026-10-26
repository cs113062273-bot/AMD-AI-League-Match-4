"""Same saved public crates.io response, historical baseline/current CPU replay.

Development API compatibility evidence, no new download or held-out score.
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
from agent.engine import Engine
from agent.network import Response
from agent.types import Settings
from revision_engine import load_engine


async def diagnose():
    receipt=json.loads((ROOT/'benchmarks/crates-history-20261023-live-v1.json').read_text(encoding='utf-8'))
    record=receipt['captures'][0];raw=(ROOT/record['capture_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=record['capture_sha256']:raise ValueError('Capture changed')
    envelope=json.loads(raw);body=base64.b64decode(envelope['body_base64'],validate=True)
    if hashlib.sha256(body).hexdigest()!=record['body_sha256']:raise ValueError('Body changed')
    data=json.loads(body)
    observed=[v for v in data['versions'] if v['num']=='0.4.5']
    if len(observed)!=1 or observed[0]['license']!='MIT OR Apache-2.0' or not observed[0]['created_at'].startswith('2020-01-24T'):
        raise ValueError('Unexpected saved development premise')
    before,revision,hashes=load_engine('74e3f48');requests=[];rows=[]
    async def replay(self,url,limit,request_timeout):
        requests.append(url)
        if url!=envelope['url']:raise ValueError('Uncaptured request')
        return Response(url,body,envelope['content_type'],envelope['charset'],envelope['status'],
            redirects=envelope['redirects'],headers=envelope['headers'])
    for name,engine,expected in [('baseline',before,''),('after',Engine,'MIT OR Apache-2.0')]:
        requests.clear()
        with patch.object(engine.run.__globals__['Fetcher'],'_fetch',replay):
            result=await engine(Settings(model_url='',search=False,browser=False,budget=12)).run(
                'What was the license of the crates.io crate itoa as of 2020-01-31?')
        passed=result.answer==expected and (result.sources==[envelope['url']] if expected else not result.sources)
        if expected:
            scope=result.diagnostics.get('selection',{}).get('signals',{}).get('qualifiers',{}).get('registry_release',{})
            passed &= scope=={'version':'0.4.5','date':'2020-01-24','name':'itoa'}
        rows.append(dict(id=name,passed=bool(passed),expected=expected,actual=result.answer,replayed_requests=list(requests),result=result.internal()))
    return dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,capture=record,
        declared_record=observed[0],passed=sum(r['passed'] for r in rows),total=len(rows),rows=rows,
        production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('app.py'),*sorted(Path('agent').glob('*.py'))]})


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    report=asyncio.run(diagnose());target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['passed','total']}))
    if report['passed']!=report['total']:sys.exit(1)
