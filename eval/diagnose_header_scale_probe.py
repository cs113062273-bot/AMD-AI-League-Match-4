"""Inspect table-header scaling through authored CPU HTTP, without a model.

The reader computes only from the requested row and its visible column label.
This probes an unsupported derivation, not a competition question or score.
"""
import argparse
import asyncio
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.types import Settings


async def diagnose():
    html='';calls=[];mode='derived'
    async def source(request):return web.Response(text=html,content_type='text/html')
    def evidence(data):
        for p in data.get('passages',[]):
            if 'Hall: Elm Hall' not in p['text']:continue
            found=re.search(r'Chairs(?: \((thousands|millions)\))?: ([0-9]+(?:\.[0-9]+)?)(?: \||$)',p['text'])
            if found:
                scale={'thousands':1000,'millions':1000000}.get(found[1],1)
                value=Decimal(found[2])*scale
                return p,found[2],str(int(value)) if value==value.to_integral_value() else ''
        return None,'',''
    async def reader(request):
        data=await request.json();calls.append({'path':request.path,'data':data})
        p,coefficient,derived=evidence(data)
        if request.path=='/verify':return web.json_response({'supported':bool(derived) and data.get('proposed')==derived})
        return web.json_response({'passage':p['id'] if p else -1,'answer':coefficient if mode=='coefficient' else derived})
    app=web.Application();app.router.add_get('/source',source);app.router.add_post('/{tail:.*}',reader)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);rows=[]
    try:
        for name,label,coefficient,mode in [('derived-million','Chairs (millions)','4.2','derived'),
                                           ('raw-million','Chairs (millions)','4.2','coefficient'),
                                           ('derived-thousand','Chairs (thousands)','4.2','derived'),
                                           ('ordinary-literal','Chairs','4','derived')]:
            html='<h1>Hall inventory</h1><table><tr><th>Hall</th><th>'+label+'</th></tr><tr><td>Oak Hall</td><td>4</td></tr><tr><td>Elm Hall</td><td>'+coefficient+'</td></tr></table>'
            calls=[]
            result=await Engine(Settings(model_url=base,allow_private=True,search=False,browser=False,max_depth=0,budget=4)).run(
                'How many chairs does Elm Hall have?',base+'/source')
            requests=[c['data'] for c in calls if c['path']=='/select'];p,raw,expected=evidence(requests[0]) if requests else (None,'','')
            rows.append({'id':name,'source_html':html,'source_sha256':hashlib.sha256(html.encode()).hexdigest(),
                         'expected_from_visible_header':expected,'coefficient':raw,'complete_row_and_header_sent':bool(p),
                         'result':result.internal(),'calls':list(calls)})
        return {'scope':__doc__,'rows':rows,'torch_imported':'torch' in sys.modules,
                'unsupported_header_scaling_reproduced':all(r['complete_row_and_header_sent'] and not r['result']['answer']
                    and bool(r['expected_from_visible_header']) for r in rows if r['id'].startswith('derived-')),
                'production_sha256':{p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path('agent').glob('*.py'))},
                'diagnostic_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    finally:await runner.cleanup()


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    report=asyncio.run(diagnose());target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'unsupported_header_scaling_reproduced':report['unsupported_header_scaling_reproduced'],
                      'rows':[{'id':r['id'],'expected':r['expected_from_visible_header'],'actual':r['result']['answer'],
                               'reason':r['result']['reason'],'complete_evidence':r['complete_row_and_header_sent']} for r in report['rows']],
                      'torch_imported':report['torch_imported']}))
