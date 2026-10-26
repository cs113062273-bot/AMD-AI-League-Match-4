"""Official-case identity, readable HTML-in-JSON and discovered-URL HTTP controls.

The captured real response is replayed offline; no paid or third-party endpoint.
Controlled semantic replies test integration, not actual model accuracy.
"""
import argparse
import asyncio
import base64
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict,replace
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.network import Fetcher,Response
from agent.oyez import case_key,parse_case
from agent.types import Settings
from benchmarks.fakeweb import FakeWeb
from revision_engine import load_engine

FRONT='https://www.oyez.org/cases/1966/37'
API='https://api.oyez.org/cases/1966/37?labels=true'
KEY=('1966','37')


def captured():
    metadata=json.loads((ROOT/'benchmarks/browser-budget-20261023-api-probe.json').read_text(encoding='utf-8'))
    path=ROOT/metadata['capture_path']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==metadata['capture_sha256']
    data=json.loads(path.read_text(encoding='utf-8'));data['body']=base64.b64decode(data.pop('body_base64'))
    return Response(**data),metadata['capture_sha256']


def controls():
    response,sha=captured();data=json.loads(response.text);rows=[]
    page=parse_case(response,KEY)
    rows.append(dict(id='real-facts',passed=not page.error and page.url==API and len(page.passages)<25
        and any('University of Georgia' in p.text and 'University of Alabama' in p.text and '<em>' not in p.text for p in page.passages),
        passage_count=len(page.passages),capture_sha256=sha))
    for name,change in [('wrong-term',{'term':'1965'}),('wrong-docket',{'docket_number':'38'}),
        ('wrong-href',{'href':'https://api.oyez.org/cases/1966/38'}),
        ('foreign-href',{'href':'https://api.oyez.org.evil.test/cases/1966/37'}),
        ('credential-href',{'href':'https://user@api.oyez.org/cases/1966/37'}),
        ('missing-name',{'name':None})]:
        changed=replace(response,body=json.dumps({**data,**change}).encode())
        result=parse_case(changed,KEY);rows.append(dict(id=name,passed=bool(result.error) and not result.passages,error=result.error))
    for name,changed in [('bad-json',replace(response,body=b'{')),
        ('wrong-final',replace(response,url='https://api.oyez.org/cases/1966/38')),
        ('foreign-final',replace(response,url='https://other.test/cases/1966/37')),
        ('limited',replace(response,status=429,error='http_429')),
        ('truncated',replace(response,truncated=True))]:
        result=parse_case(changed,KEY);rows.append(dict(id=name,passed=bool(result.error) and not result.passages,error=result.error))
    hidden={**data,'facts_of_the_case':'<p>Visible facts.</p><p hidden>Secret Name</p><script>Injected Name</script>',
            'question':None,'conclusion':None,'description':None}
    result=parse_case(replace(response,body=json.dumps(hidden).encode()),KEY)
    texts=' '.join(p.text for p in result.passages)
    rows.append(dict(id='hidden-content',passed='Visible facts.' in texts and 'Secret Name' not in texts and 'Injected Name' not in texts))
    hidden['facts_of_the_case']='<p>Opening facts.</p>'+''.join('<p>Later fact '+str(i)+'.</p>' for i in range(300))
    result=parse_case(replace(response,body=json.dumps(hidden).encode()),KEY)
    rows.append(dict(id='bounded',passed=result.truncated and len(result.passages)<=96))
    hidden['facts_of_the_case']=''.join('<p>Fact '+str(i)+'.</p>' for i in range(95))
    result=parse_case(replace(response,body=json.dumps(hidden).encode()),KEY)
    rows.append(dict(id='bounded-with-scalar-fields',passed=result.truncated and len(result.passages)<=96))
    for name,url,expected in [('front',FRONT,KEY),('api',API,KEY),('no-www',FRONT.replace('www.',''),KEY),
        ('lookalike',FRONT.replace('oyez.org','oyez.org.evil.test'),None),
        ('suffix',FRONT+'/other',None),('credentials',FRONT.replace('www.','user@www.'),None),
        ('wrong-port',FRONT.replace('oyez.org','oyez.org:8080'),None),
        ('encoded-path',FRONT.replace('/1966/','/%31%39%36%36/'),None),
        ('list','https://api.oyez.org/cases?per_page=10',None)]:
        actual=case_key(url);rows.append(dict(id='route-'+name,passed=actual==expected,actual=actual))
    return rows


@contextmanager
def replay_transport(engines,base):
    """Actual loopback HTTP, with logical source URLs retained at the fetch boundary.

    Does not test public DNS/TLS; no other production transport behavior changes.
    """
    originals={e.run.__globals__['Fetcher']:e.run.__globals__['Fetcher'].fetch for e in engines}
    contexts=[]
    try:
        for cls,original in originals.items():
            async def fetch(fetcher,url,_original=original,**kwargs):
                route='/api' if urlsplit(url).hostname=='api.oyez.org' else '/front' if case_key(url) else '/landing'
                response=await _original(fetcher,base+route,**kwargs)
                return replace(response,url=url)
            ctx=patch.object(cls,'fetch',fetch);ctx.__enter__();contexts.append(ctx)
        yield
    finally:
        for ctx in reversed(contexts):ctx.__exit__(None,None,None)


async def integration(engines):
    mode='';events=[]
    async def model(request):
        data=await request.json();events.append(request.path)
        if request.path=='/verify':return web.json_response({'supported':True})
        p=next((p for p in data['passages'] if 'George Burnett' in p['text']),None)
        return web.json_response({'passage':p['id'] if p else -1,'answer':'George Burnett' if p else ''})
    app=web.Application();app.router.add_post('/{tail:.*}',model);runner=web.AppRunner(app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start();model_url='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    response,sha=captured();good=response.body;data=json.loads(response.text);wrong=json.dumps({**data,'docket_number':'38'})
    rows={stage:[] for stage in engines}
    try:
        for mode,body in [('direct',good),('discovered',good),('wrong-identity',wrong),('api-url',good)]:
            routes={'/front':(200,'text/html','<div id="app"></div>'),'/api':(200,'application/json',body),
                '/landing':(200,'text/html','<a href="'+FRONT+'">Curtis Publishing v Butts case facts</a>')}
            with FakeWeb(routes) as server,replay_transport(list(engines.values()),server.base):
                for stage,engine in engines.items():
                    events.clear();start='https://example.org/landing' if mode=='discovered' else API if mode=='api-url' else FRONT
                    result=await engine(Settings(model_url=model_url,allow_private=True,search=False,max_depth=1,budget=5)).run(
                        'Who was the source of the article in Curtis Publishing v. Butts?',start)
                    expected='' if mode=='wrong-identity' else 'George Burnett'
                    rows[stage].append(dict(id=mode,passed=result.answer==expected and result.sources==([API] if expected and mode!='api-url' else [start] if expected else []),
                        model_calls=list(events),result=result.internal()))
    finally:await runner.cleanup()
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('4141065');rows=controls();paired=asyncio.run(integration({'before':old,'after':Engine}))
    report=dict(scope=__doc__,baseline=revision,controls=rows,**paired,
        controls_passed=sum(r['passed'] for r in rows),controls_total=len(rows),
        before_passed=sum(r['passed'] for r in paired['before']),after_passed=sum(r['passed'] for r in paired['after']),total=len(paired['after']))
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['controls_passed','controls_total','before_passed','after_passed','total']}))
    if not all(r['passed'] for r in rows+paired['after']):sys.exit(1)
