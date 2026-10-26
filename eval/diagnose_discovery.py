"""Controlled HTTP provider/navigation diagnosis; not real-web or LLM accuracy.

The semantic service extracts only an actual phone span and abstains on link
selection. Search providers and pages are local HTTP fixtures, without network
interception or a public provider dependency.
"""
import argparse
import asyncio
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.planner import plan_query,tokens
from agent.search import rewrites
from agent.types import Settings


async def diagnose():
    queries=[];hits=[];base=''
    phone='+1 800 555 0129'
    async def get(request):
        hits.append(request.path)
        path=request.path
        if path.startswith('/provider/'):
            query=request.query.get('q','');queries.append(query)
            target='/spam' if path.endswith('bad') else '/contact'
            label='Kitchen gadgets' if path.endswith('bad') else 'Boreal Instruments support contact'
            return web.Response(text='<li class="b_algo"><h2><a href="'+base+target+'">'+label+'</a></h2></li>',content_type='text/html')
        bodies={
            '/root-search':'<h1>Boreal Instruments</h1>',
            '/contact':'<title>Boreal Instruments support</title><h1>Boreal Instruments support</h1><p>Support phone: '+phone+'</p>',
            '/spam':'<h1>Kitchen gadgets</h1><p>Discounts and promotional offers.</p>',
            '/one':'<h1>Boreal Instruments</h1><a href="/leaf">More</a>',
            '/two':'<h1>Boreal Instruments</h1><a href="/leaf">More</a><a href="/spam">Overview</a>',
            '/foreign':'<h1>Boreal Instruments</h1><a href="https://unrelated.invalid/">More</a>',
            '/leaf':'<title>Boreal Instruments support</title><h1>Boreal Instruments support</h1><p>Support phone: '+phone+'</p>',
        }
        return web.Response(text=bodies.get(path,'Not found'),content_type='text/html',status=200 if path in bodies else 404)

    async def model(request):
        data=await request.json()
        if request.path=='/verify':
            return web.json_response({'supported':any(data.get('proposed') in p['text'] for p in data.get('passages',[]))})
        if not data.get('question','').startswith('Choose the best available page link'):
            for passage in data.get('passages',[]):
                found=re.search(r'\+1 800 555 \d{4}',passage['text'])
                if found:return web.json_response({'passage':passage['id'],'answer':found[0]})
        return web.json_response({'passage':-1,'answer':''})

    app=web.Application();app.router.add_get('/{path:.*}',get)
    app.router.add_post('/{path:.*}',model)
    runner=web.AppRunner(app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    rows=[]
    try:
        for name,path,search,expected in [('weak-provider','/root-search',True,phone),
                ('one-weak-link','/one',False,phone),('two-weak-links','/two',False,phone),
                ('foreign-weak-link','/foreign',False,'')]:
            hits.clear();queries.clear()
            settings=Settings(model_url=base,allow_private=True,search=search,budget=12,max_depth=2,
                search_providers=[(base+'/provider/good?q=','bing'),(base+'/provider/bad?q=','bing')])
            result=await Engine(settings).run('What is the support phone of Boreal Instruments?',base+path)
            source='/contact' if search else '/leaf'
            passed=result.answer==expected and (result.sources==[base+source] if expected else not result.sources)
            if not expected:passed=passed and not any('unrelated.invalid' in event['url'] for event in result.diagnostics.get('fetches',[]))
            rows.append({'id':name,'passed':passed,'hits':list(hits),'queries':list(queries),'result':result.internal()})
    finally:await runner.cleanup()

    for question,anchors,hints in [
        ('What is the support phone of Boreal Instruments?',['boreal','instruments'],['contact','telephone']),
        ('What is the default of `async_pool` in FlintDB?',['flintdb','async_pool'],['configuration','client']),
        ('What is the title of PEP 750?',['pep','750'],['python','interpolation']),
    ]:
        actual=rewrites(plan_query(question),hints)
        rows.append({'id':'query-anchors-'+anchors[0],'passed':all(set(anchors).issubset(tokens(q)) for q in actual),
                     'queries':actual,'anchors':anchors})
    return {'scope':__doc__,'passed':sum(r['passed'] for r in rows),'total':len(rows),'rows':rows}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    report=asyncio.run(diagnose())
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'total':report['total'],'failures':[r['id'] for r in report['rows'] if not r['passed']]}))
