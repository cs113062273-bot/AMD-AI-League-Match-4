"""Reproduce count information lost at the reader's 1,100-character cut.

Authored CPU HTTP reader and verifier, no model or public web. A probe of
visible evidence fidelity, not model accuracy or a new competition score.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import re
import sys

from aiohttp import web

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.engine import Engine
from agent.cardinals import count_value
from agent.types import Settings


async def probe():
    prefix='Oak Hall has 4 chairs. '
    target='Elm Hall has '
    padding='x'*(1099-len(prefix)-len(target)-1)+' '
    paragraph=prefix+padding+target+'4 million chairs.'
    assert paragraph[:1100].endswith('Elm Hall has 4')
    html='<h1>Elm Hall</h1><p>'+paragraph+'</p>'
    calls=[]
    async def source(request):return web.Response(text=html,content_type='text/html')
    def visible_count(data):
        for p in data.get('passages',[]):
            match=re.search(r'Elm Hall has (4 million|4)(?: chairs\.|$)',p['text'])
            if match:return p,match[1]
        return None,''
    async def reader(request):
        data=await request.json();calls.append({'path':request.path,'data':data})
        p,raw=visible_count(data)
        if request.path=='/verify':
            value=count_value(raw)
            expected=str(value) if value is not None else raw
            return web.json_response({'supported':bool(raw) and data.get('proposed')==expected})
        return web.json_response({'passage':p['id'] if p else -1,'answer':raw})
    app=web.Application();app.router.add_get('/source',source);app.router.add_post('/{tail:.*}',reader)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    try:
        result=await Engine(Settings(model_url=base,allow_private=True,search=False,browser=False,
            max_depth=0,budget=4)).run('How many chairs does Elm Hall have?',base+'/source')
        return {'scope':__doc__,'input_sha256':hashlib.sha256(html.encode()).hexdigest(),
                'paragraph_length':len(paragraph),'actual_target_phrase':'Elm Hall has 4 million chairs.',
                'result':result.internal(),'calls':calls,
                'defect_reproduced':result.answer=='4'
                    and any(p['text'].endswith('Elm Hall has 4') for c in calls for p in c['data'].get('passages',[])),
                'torch_imported':'torch' in sys.modules,
                'source_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in [ROOT/'agent/selector.py',ROOT/'agent/candidates.py']}}
    finally:await runner.cleanup()


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    report=asyncio.run(probe());target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'defect_reproduced':report['defect_reproduced'],'answer':report['result']['answer'],
                      'reason':report['result']['reason'],'calls':[c['path'] for c in report['calls']]}))
