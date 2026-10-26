"""CPU exact cutoff parsing and actual local HTTP; invented histories, not accuracy."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.types import Settings
from revision_engine import load_engine

CASES=[
    ('2020','2020-12-31',''),('2020-02-29','2020-02-29',''),
    ('2020-02','2020-02-29',''),('2019-02','2019-02-28',''),
    ('2020-2-9','2020-02-09',''),('2020/02/29','2020-02-29',''),
    ('March 2020','2020-03-31',''),('Mar. 2020','2020-03-31',''),
    ('March 3, 2020','2020-03-03',''),('3rd March 2020','2020-03-03',''),
    ('the year 2020','2020-12-31',''),('the 2020-02-29','2020-02-29',''),
    ('29/02/2020','2020-02-29',''),('02/29/2020','2020-02-29',''),
    ('2020.2','','unresolved_cutoff'),('2020-99-99','','invalid_cutoff'),
    ('2019-02-29','','invalid_cutoff'),('2020-02-30','','invalid_cutoff'),
    ('2020-00','','invalid_cutoff'),('0000','','invalid_cutoff'),
    ('March 32, 2020','','invalid_cutoff'),('03/04/2020','','ambiguous_cutoff'),
    ('2020-2021','','unresolved_cutoff'),('2020 to 2021','','ambiguous_cutoff'),
    ('2020 or as of 2021','','ambiguous_cutoff'),('next summer','','unresolved_cutoff'),
    ('2020-02-29T12:00Z','','unresolved_cutoff'),('now','',''),('today','',''),
    ('2020 - 2021','','ambiguous_cutoff'),('2020, or 2021','','ambiguous_cutoff'),
    ('March 2020 through April 2020','','ambiguous_cutoff'),
    ('2020-02-29 12:00Z','','unresolved_cutoff'),
    ('2020-02-29 at 12:00','','unresolved_cutoff'),
    ('now or 2020','','ambiguous_cutoff'),('2020 or now','','ambiguous_cutoff'),
]


def direct(engine):
    planner=engine.run.__globals__['plan_query'];rows=[]
    for raw,value,issue in CASES:
        plan=planner('What was the latest version of River Sample as of '+raw+'?')
        actual=[plan.as_of,getattr(plan,'temporal_issue','')]
        passed=actual==[value,issue]
        if issue:passed &= bool(getattr(plan,'temporal_raw',[]))
        rows.append(dict(id='plan-'+raw,passed=passed,expected=[value,issue],actual=actual))
    for name,query,value in [
        ('negated','What is the latest version, not as of 2020?',''),
        ('quoted','What is the title of "As of 2020"?',''),
        ('url','What is the latest version? See https://example.org/as-of-2020',''),
        ('repeat','What was the latest version as of 2020, again as of 2020?','2020-12-31')]:
        plan=planner(query)
        rows.append(dict(id=name,passed=plan.as_of==value and not getattr(plan,'temporal_issue',''),
            expected=value,actual=plan.as_of))
    return rows


async def transport(engine):
    rows=[];hits=[];model_calls=[];logical=[]
    body='<h1>River Sample release history</h1><table><tr><th>Version</th><th>Release date</th></tr>'\
        '<tr><td>1.0</td><td>2020-01-01</td></tr><tr><td>1.1</td><td>2020-02-29</td></tr>'\
        '<tr><td>1.2</td><td>2020-03-03</td></tr><tr><td>2.0</td><td>2020-11-01</td></tr></table>'
    async def source(request):
        hits.append(request.path)
        if request.path=='/pypi/river-sample/json':
            return web.json_response({'info':{'name':'river-sample','version':'9.0'},'releases':{}})
        content=body
        if request.path=='/sparse':
            content=content.replace('<tr><td>1.1</td><td>2020-02-29</td></tr>','').replace('<tr><td>1.2</td><td>2020-03-03</td></tr>','')
        return web.Response(text=content,content_type='text/html')
    async def model(request):
        model_calls.append(request.path)
        return web.json_response({'passage':-1,'answer':''})
    app=web.Application();app.router.add_post('/{tail:.*}',model);app.router.add_get('/{tail:.*}',source)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    try:
        for raw,expected in [('2020','2.0'),('2020-02','1.1'),('March 2020','1.2'),
            ('2020-02-29','1.1'),('2020.2',''),('2020-99-99',''),('03/04/2020','')]:
            hits.clear();model_calls.clear()
            result=await engine(Settings(model_url='',search=False,allow_private=True,max_depth=0,budget=4)).run(
                'What was the latest version of River Sample as of '+raw+'?',base+'/history')
            passed=result.answer==expected and result.sources==([base+'/history'] if expected else [])
            if not expected:passed &= not hits and not model_calls
            rows.append(dict(id='http-history-'+raw,passed=bool(passed),expected=expected,actual=result.answer,
                hits=list(hits),model_calls=list(model_calls),result=result.internal()))
        hits.clear()
        result=await engine(Settings(model_url='',search=False,allow_private=True,max_depth=0,budget=4)).run(
            'What was the latest version of River Sample as of 2020-02?',base+'/sparse')
        rows.append(dict(id='http-sparse-month',passed=result.answer=='1.0' and result.sources==[base+'/sparse'],
            expected='1.0',actual=result.answer,hits=list(hits),result=result.internal()))
        # Controlled registry transport: only local HTTP is contacted. Public
        # URLs are logical adapter identities, not fetched primary sources.
        fetcher=engine.run.__globals__['Fetcher'];original=fetcher.fetch
        async def replay(self,url,**kwargs):
            logical.append(url)
            response=await original(self,base+urlsplit(url).path,**kwargs)
            response.url=url
            return response
        for raw,expected in [('now','9.0'),('the year 2020',''),('next summer',''),('2020.2','')]:
            hits.clear();logical.clear();model_calls.clear()
            with patch.object(fetcher,'fetch',replay):
                result=await engine(Settings(model_url=base,search=False,allow_private=True,max_depth=0,budget=4)).run(
                    'What was the latest version of the PyPI package river-sample as of '+raw+'?')
            passed=result.answer==expected and (bool(result.sources) if expected else not result.sources)
            if raw in {'next summer','2020.2'}:passed &= not hits and not logical and not model_calls
            rows.append(dict(id='http-registry-'+raw,passed=bool(passed),expected=expected,actual=result.answer,
                local_hits=list(hits),logical_requests=list(logical),model_calls=list(model_calls),result=result.internal()))
    finally:await runner.cleanup()
    return rows


async def diagnose(engine):return direct(engine)+await transport(engine)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--baseline');ap.add_argument('--out',required=True)
    args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    engine=Engine;revision='working-tree';hashes={}
    if args.baseline:engine,revision,hashes=load_engine(args.baseline)
    rows=asyncio.run(diagnose(engine))
    report=dict(scope=__doc__,revision=revision,baseline_source_sha256=hashes,
        diagnostic_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path('app.py'),*sorted(Path('agent').glob('*.py'))]},
        passed=sum(r['passed'] for r in rows),total=len(rows),rows=rows)
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'],total=report['total'],failures=[r['id'] for r in rows if not r['passed']])))
    if report['passed']!=report['total']:sys.exit(1)
