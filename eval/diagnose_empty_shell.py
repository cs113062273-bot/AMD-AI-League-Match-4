"""CPU-only captured-source routing check; render is a spy, never a browser.

This verifies a missed JS-shell fallback, not a recovered model answer.
"""
import argparse
import asyncio
import base64
from dataclasses import asdict
import hashlib
import importlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.network import Response
from agent.parser import parse_response
from agent.types import Settings
from agent.urls import discovery_url
from revision_engine import load_engine


def captures():
    seen=set();rows=[]
    for name in ['first','repeat']:
        report=json.loads((ROOT/f'benchmarks/external-disjoint12b-20261023-{name}.json').read_text(encoding='utf-8'))
        for record in report['rows']:
            path=ROOT/record['capture_path']
            assert hashlib.sha256(path.read_bytes()).hexdigest()==record['capture_sha256']
            assert not record['capture_omitted']
            for url,raw in json.loads(path.read_text(encoding='utf-8')).items():
                if raw['error'] or 'html' not in raw['content_type'].lower() or discovery_url(url):continue
                data=dict(raw);data['body']=base64.b64decode(data.pop('body_base64'))
                key=(url,hashlib.sha256(data['body']).hexdigest())
                if key in seen:continue
                seen.add(key);rows.append((record['id'],Response(**data),key[1]))
    return rows


async def routing(engine,response):
    calls=[]
    async def serve(request):return web.Response(body=response.body,content_type='text/html')
    async def render(url,*args,**kwargs):
        calls.append(url)
        return None,{'state':'spy_no_browser_launch'}
    app=web.Application();app.router.add_get('/source',serve)
    runner=web.AppRunner(app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    url='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])+'/source'
    browser=importlib.import_module(engine.__module__.rsplit('.',1)[0]+'.browser')
    rows=[]
    try:
        with patch.object(browser,'render',render):
            for enabled in [True,False]:
                calls.clear()
                result=await engine(Settings(model_url='',browser=enabled,search=False,
                    max_depth=0,allow_private=True,budget=4)).run('How many children did this painter have?',url)
                rows.append(dict(browser_enabled=enabled,render_spy_calls=len(calls),
                    passed=len(calls)==int(enabled),answer=result.answer,reason=result.reason))
    finally:await runner.cleanup()
    return rows


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out);assert not target.exists()
    old,revision,hashes=load_engine('a4f3460');before_parser=old.run.__globals__['parse_response']
    saved=captures();audit=[];actual=None
    for case_id,response,digest in saved:
        before,after=before_parser(response),parse_response(response)
        expected_change='ancestors.familysearch.org/en/9MF8-T95/' in response.url
        b,a=asdict(before),asdict(after);b.pop('dynamic');a.pop('dynamic')
        passed=b==a and (before.dynamic==after.dynamic or expected_change and not before.dynamic and after.dynamic)
        audit.append(dict(case_id=case_id,url=response.url,body_sha256=digest,passed=passed,
            before_dynamic=before.dynamic,after_dynamic=after.dynamic))
        if expected_change:actual=response
    assert actual is not None
    notice='<noscript>'+'Enable JavaScript to use this application. '*15+'</noscript>'
    head='<html><head><meta name="description" content="Directory"><script src="/app.js"></script></head><body>'
    fixtures=[('empty-cleaned-body',head+notice+'<div id="root"></div></body></html>',True,False),
        ('readable-body',head+notice+'<article><h1>A source</h1><p>'+'Readable source facts. '*20+'</p></article></body></html>',False,False),
        ('embedded-data',head+notice+'<script type="application/json">{"name":"A source","count":8}</script></body></html>',False,False),
        ('truncated',head+notice+'</body></html>',False,True),
        ('no-active-script',head.replace('<script src="/app.js"></script>','')+notice+'</body></html>',False,False)]
    controls=[]
    for name,html,expected,truncated in fixtures:
        page=parse_response(Response('https://example.org/source',html.encode(),'text/html',truncated=truncated))
        controls.append(dict(id=name,passed=page.dynamic==expected,dynamic=page.dynamic))
    before_routing=asyncio.run(routing(old,actual));after_routing=asyncio.run(routing(Engine,actual))
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,
        audit=audit,controls=controls,before_routing=before_routing,after_routing=after_routing,
        changed=[r for r in audit if r['before_dynamic']!=r['after_dynamic']],
        all_passed=all(r['passed'] for r in audit+controls+after_routing))
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(all_passed=report['all_passed'],audited=len(audit),changed=report['changed'],
        controls=controls,before_routing=before_routing,after_routing=after_routing)))
    if not report['all_passed']:sys.exit(1)


if __name__=='__main__':main()
