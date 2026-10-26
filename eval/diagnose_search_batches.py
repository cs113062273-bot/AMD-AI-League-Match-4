"""Controlled HTTP probe: reject unrelated provider batches, retain generic links in relevant batches."""
import argparse
import asyncio
import importlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.network import Fetcher
from agent.planner import plan_query
from agent.search import search
from agent.types import Settings,Deadline
from revision_engine import load_engine


async def diagnose(searcher):
    base='';hits=[]
    async def provider(request):
        hits.append((request.path,request.query.get('q','')))
        relevant=request.path=='/mixed' or request.path=='/rewrite' and not request.query.get('q','').startswith('site:')
        items=[('/contact','Boreal Instruments support'),('/reference','More details')] if relevant else [('/spam','Kitchen gadgets')]
        html=''.join('<li class="b_algo"><h2><a href="'+base+url+'">'+label+'</a></h2></li>' for url,label in items)
        return web.Response(text=html,content_type='text/html')
    app=web.Application();app.router.add_get('/{tail:.*}',provider)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);rows=[]
    try:
        for name,providers,expected in [
            ('unrelated-batch',[(base+'/unused?q=','bing'),(base+'/bad?q=','bing'),(base+'/mixed?q=','bing')],['/contact','/reference']),
            ('unrelated-query',[(base+'/rewrite?q=','bing')],['/contact','/reference']),
            ('unrelated-only-refused',[(base+'/bad?q=','bing')],[]),
        ]:
            hits.clear()
            # Under four seconds avoids a public Wikipedia fallback in the
            # intentionally all-weak case. All provider traffic is actual local HTTP.
            async with Fetcher(Settings(allow_private=True),Deadline(3.8)) as fetcher:
                actual=await searcher(plan_query('What is the support phone of Boreal Instruments?',base+'/root'),fetcher,providers)
            rows.append({'id':name,'passed':actual==[(base+url,dict((('/contact','Boreal Instruments support'),('/reference','More details'),('/spam','Kitchen gadgets')))[url]) for url in expected],
                'actual':actual,'hits':list(hits)})
    finally:await runner.cleanup()
    return {'scope':__doc__,'passed':sum(row['passed'] for row in rows),'total':len(rows),'rows':rows}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--baseline');ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    searcher=search;revision='working-tree';hashes={}
    if args.baseline:
        engine,revision,hashes=load_engine(args.baseline)
        searcher=importlib.import_module(engine.__module__.rsplit('.',1)[0]+'.search').search
    result=asyncio.run(diagnose(searcher));result.update(revision=revision,source_sha256=hashes)
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'passed':result['passed'],'total':result['total'],'failures':[row['id'] for row in result['rows'] if not row['passed']]}))
