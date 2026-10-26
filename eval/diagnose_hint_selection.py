"""CPU/loopback HTTP checks of concise-hint choice and existing recovery gates.

Recorded public GETs are replayed, never interpreted as answer evidence.
No model, GPU or browser launch; not an answer-accuracy assessment.
"""
import argparse
import asyncio
import base64
from dataclasses import replace
import hashlib
import importlib
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs,urlsplit,urlencode

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.network import Fetcher,Response
from agent.planner import plan_query
from agent.search import concise_query,search
from agent.types import Settings,Deadline
from revision_engine import load_engine
from probe_hint_selection import links_from_response


CASES=[
    ('later-specific','When did Boreal Instruments announce its optics division?',
        ['optics division announcement','boreal instruments optics division'],'boreal instruments optics division'),
    ('first-specific','When did Boreal Instruments announce its optics division?',
        ['boreal instruments optics division','optics division announcement'],'boreal instruments optics division'),
    ('tie-order','Who founded Boreal Instruments?',
        ['boreal instruments founder','boreal instruments biography'],'boreal instruments founder'),
    ('tie-reversed','Who founded Boreal Instruments?',
        ['boreal instruments biography','boreal instruments founder'],'boreal instruments biography'),
    ('more-specific-person','What is the full name of Canadian swimmer Mira Vale?',
        ['mira vale full name','canadian swimmer mira vale'],'canadian swimmer mira vale'),
    ('duplicate-tokens','Who founded Boreal Instruments?',
        ['boreal boreal founder','boreal instruments founder'],'boreal instruments founder'),
    ('unicode','Who founded Fj\u00e4ll Optik?',
        ['optik founder','fj\u00e4ll optik founder'],'fj\u00e4ll optik founder'),
    ('whitespace','Who founded Boreal Instruments?',
        ['  boreal instruments founder  '],'boreal instruments founder'),
    ('unrelated','Who founded Boreal Instruments?',
        ['cedar optical founder'],''),
    ('url-not-query','Who founded Boreal Instruments?',
        ['https://example.org/boreal-instruments','boreal instruments founder'],'boreal instruments founder'),
    ('model-year-denied','Who founded Boreal Instruments?',
        ['boreal instruments founded 1997','boreal instruments founder'],'boreal instruments founder'),
    ('multiline-denied','Who founded Boreal Instruments?',
        ['boreal instruments\nfounder','boreal instruments founder'],'boreal instruments founder'),
    ('long-hint-denied','Who founded Boreal Instruments?',
        ['boreal instruments founder '+ 'another '*20,'boreal instruments founder'],'boreal instruments founder'),
    ('word-limit','Who founded Boreal Instruments?',
        ['boreal instruments founder one two three four five six','boreal instruments founder'],'boreal instruments founder'),
    ('schema-denied','Who founded Boreal Instruments?',
        [None,{},'boreal instruments founder'],'boreal instruments founder'),
    ('quoted-fallback','What two teams were mentioned in the lawsuit against "Amber Journal"?',
        [],'"Amber Journal" lawsuit against'),
    ('no-entity','What is the name?',[],''),
]


def direct(chooser):
    return [dict(id=name,passed=(actual:=chooser(plan_query(q),hints))==expected,actual=actual,expected=expected)
            for name,q,hints,expected in CASES]


async def http(searcher):
    rows=[];mode='';hits=[];base=''
    question='When did Boreal Instruments announce its optics division?'
    short='boreal instruments optics division';hints=['optics division announcement',short]
    async def handler(request):
        query=request.query.get('q','');hits.append((request.path,query))
        if request.path=='/wiki':return web.json_response({'query':{'search':[]}})
        if request.path=='/rss':return web.Response(text='<rss><channel/></rss>',content_type='text/xml')
        useful=mode=='initial-usable' or request.path=='/lite' and query==short
        if useful:
            return web.Response(text='<li class="b_algo"><h2><a class="result-link" href="'+base+'/company">Boreal Instruments optics division</a></h2></li>',content_type='text/html')
        return web.Response(text='<title>No results</title>',content_type='text/html')
    app=web.Application();app.router.add_get('/{tail:.*}',handler);runner=web.AppRunner(app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    try:
        for mode,budget in [('fallback',12),('initial-usable',12),('low-budget',6)]:
            hits.clear();deadline=Deadline(budget)
            async with Fetcher(Settings(allow_private=True),deadline) as transport:
                class Mapping:
                    events=[]
                    async def fetch(self,url,**kwargs):
                        parsed=urlsplit(url);params=parse_qs(parsed.query)
                        path='/wiki' if parsed.hostname=='en.wikipedia.org' else '/rss' if params.get('format')==['rss'] else '/lite' if parsed.hostname=='lite.duckduckgo.com' else '/empty'
                        q=(params.get('q') or params.get('srsearch') or [''])[0]
                        response=await transport.fetch(base+path+'?'+urlencode({'q':q}),**kwargs)
                        self.events.append({'url':url,'error':response.error});return replace(response,url=url)
                mapped=Mapping();mapped.deadline=deadline
                actual=await searcher(plan_query(question),mapped,hints=hints)
            short_calls=sum(path=='/lite' and query==short for path,query in hits)
            expected=[] if mode=='low-budget' else [(base+'/company','Boreal Instruments optics division')]
            passed=actual==expected and short_calls==(1 if mode=='fallback' else 0)
            rows.append(dict(id='http-'+mode,passed=passed,short_calls=short_calls,requests=list(hits),actual=actual))
    finally:await runner.cleanup()
    return rows


async def recorded(old_chooser):
    probe_path=ROOT/'benchmarks/hint-selection-20261023-probe.json'
    probe=json.loads(probe_path.read_text(encoding='utf-8'));rows=[];replays=[]
    for r in probe['rows']:
        plan=plan_query(r['question']);before=old_chooser(plan,r['hints']);after=concise_query(plan,r['hints'])
        rows.append(dict(id=r['id'],before=before,after=after,matched_measured_proposal=after==r['max_overlap']))
    for row in probe['live']:
        for v in row['variants']:
            path=ROOT/v['capture_path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==v['capture_sha256']
            data=json.loads(path.read_text(encoding='utf-8'));data['body']=base64.b64decode(data.pop('body_base64'))
            plan=plan_query(next(r['question'] for r in probe['rows'] if r['id']==row['id']))
            links=await links_from_response(plan,Response(**data))
            replays.append(dict(id=row['id'],query=v['query'],capture_sha256=v['capture_sha256'],
                                identical_candidates=links==[tuple(pair) for pair in v['links']],links=links))
    return dict(probe_sha256=hashlib.sha256(probe_path.read_bytes()).hexdigest(),choices=rows,
                changed=sum(r['before']!=r['after'] for r in rows),replays=replays)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('50fcaa1');old_search=importlib.import_module(old.__module__.rsplit('.',1)[0]+'.search')
    before=direct(old_search.concise_query)+asyncio.run(http(old_search.search))
    after=direct(concise_query)+asyncio.run(http(search));captures=asyncio.run(recorded(old_search.concise_query))
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,before=before,after=after,recorded=captures,
                before_passed=sum(r['passed'] for r in before),after_passed=sum(r['passed'] for r in after),total=len(after),
                wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
                losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
                search_sha256=hashlib.sha256((ROOT/'agent/search.py').read_bytes()).hexdigest())
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    print(json.dumps({'recorded_sets':len(captures['choices']),'changed':captures['changed'],'capture_replays':len(captures['replays'])}))
    if not all(r['passed'] for r in after) or not all(r['identical_candidates'] for r in captures['replays']):sys.exit(1)
