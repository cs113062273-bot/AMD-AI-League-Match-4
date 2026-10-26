"""Actual local HTTP mapping of standard providers to isolate bounded concise recovery.

Provider bodies and endpoints are controlled, with no public network or LLM.
"""
import argparse
import asyncio
from dataclasses import replace
import hashlib
import importlib
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs,urlsplit,urlencode

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.network import Fetcher
from agent.planner import plan_query
from agent.search import search,concise_query
from agent.types import Settings,Deadline
from revision_engine import load_engine


async def diagnose(searcher):
    base='';mode='';short='';label='';sent=[]
    async def provider(request):
        q=request.query.get('q','')
        if request.path=='/rss':return web.Response(text='<rss><channel/></rss>',content_type='text/xml')
        if request.path=='/wiki':return web.json_response({'query':{'search':[]}})
        matched=mode=='initial-usable' or request.path=='/lite' and q==short and mode!='unrelated-short'
        if matched:
            css='result-link' if request.path=='/lite' else ''
            text='<li class="b_algo"><h2><a class="'+css+'" href="'+base+'/answer">'+label+'</a></h2></li>'
        elif mode=='unrelated-short' and request.path=='/lite' and q==short:
            text='<a class="result-link" href="'+base+'/spam">Kitchen gadgets</a>'
        else:text='<html><title>No results</title></html>'
        return web.Response(text=text,content_type='text/html')
    app=web.Application();app.router.add_get('/{tail:.*}',provider)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);rows=[]
    try:
        for mode,question,hints,short,label,expected,budget in [
            ('safe-hint','What is the first and last name of the partner of Orin Vale?',['orin vale spouse'],'orin vale spouse','Orin Vale biography',True,12),
            ('quoted','What two teams were mentioned in the lawsuit against "Amber Journal"?',[],'"Amber Journal" lawsuit against','Amber Journal lawsuit',True,12),
            ('unrelated-hint','What is the partner of Orin Vale?',['mira chen spouse'],'','Orin Vale biography',False,12),
            ('generic-hint','What is the first and last name of the partner of Orin Vale?',['first last name'],'','Orin Vale biography',False,12),
            ('digit-hint','What is the partner of Orin Vale?',['orin vale 1998 spouse'],'','Orin Vale biography',False,12),
            ('url-hint','What is the partner of Orin Vale?',['https://example.org/orin-vale'],'','Orin Vale biography',False,12),
            ('initial-usable','What is the partner of Orin Vale?',['orin vale spouse'],'orin vale spouse','Orin Vale biography',True,12),
            ('low-budget','What is the partner of Orin Vale?',['orin vale spouse'],'orin vale spouse','Orin Vale biography',False,6),
            ('unrelated-short','What is the partner of Orin Vale?',['orin vale spouse'],'orin vale spouse','Orin Vale biography',False,12),
        ]:
            sent.clear();deadline=Deadline(budget)
            async with Fetcher(Settings(allow_private=True),deadline) as http:
                class Mapping:
                    events=[]
                    async def fetch(self,url,**kwargs):
                        sent.append(url);parts=urlsplit(url);params=parse_qs(parts.query)
                        path='/wiki' if parts.hostname=='en.wikipedia.org' else '/rss' if params.get('format')==['rss'] else '/lite' if parts.hostname=='lite.duckduckgo.com' else '/empty'
                        q=(params.get('q') or params.get('srsearch') or [''])[0]
                        reply=await http.fetch(base+path+'?'+urlencode({'q':q}),**kwargs)
                        self.events.append({'url':url,'error':reply.error})
                        return replace(reply,url=url)
                mapped=Mapping();mapped.deadline=deadline
                actual=await searcher(plan_query(question),mapped,hints=hints)
            concise_calls=[url for url in sent if urlsplit(url).hostname=='lite.duckduckgo.com' and parse_qs(urlsplit(url).query).get('q')==[short]] if short else []
            passed=actual==([(base+'/answer',label)] if expected else [])
            if mode in {'initial-usable','low-budget'}:passed=passed and not concise_calls
            if mode in {'safe-hint','quoted'}:passed=passed and len(concise_calls)==1
            if mode in {'unrelated-hint','generic-hint','digit-hint','url-hint'}:
                passed=passed and all(parse_qs(urlsplit(url).query).get('q')!=[hint]
                    for hint in hints for url in sent if urlsplit(url).hostname=='lite.duckduckgo.com')
            rows.append(dict(id=mode,passed=passed,actual=actual,requests=list(sent),concise_calls=len(concise_calls)))
    finally:await runner.cleanup()
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('d346a1c');old_search=importlib.import_module(old.__module__.rsplit('.',1)[0]+'.search').search
    before=asyncio.run(diagnose(old_search));after=asyncio.run(diagnose(search))
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,before=before,after=after,
        before_passed=sum(r['passed'] for r in before),after_passed=sum(r['passed'] for r in after),total=len(after),
        wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
        losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
        search_sha256=hashlib.sha256((ROOT/'agent/search.py').read_bytes()).hexdigest())
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    if not all(r['passed'] for r in after):sys.exit(1)
