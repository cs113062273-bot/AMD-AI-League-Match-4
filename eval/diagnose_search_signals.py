"""Ranking-only URL text and clue lookup isolation with actual local HTTP.

Recorded public result pages are replayed unchanged; no model or accuracy claim.
The numeric-year query proposal is measured separately and is not promoted.
"""
import argparse
import asyncio
import base64
import hashlib
import importlib
import json
from pathlib import Path
import sys
from urllib.parse import quote_plus

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine,link_score
from agent.network import Fetcher
from agent.planner import plan_query
from agent.search import search
from agent.types import Settings,Deadline
from agent.urls import relevance_url,answer_lookup_url,canonical_url
from revision_engine import load_engine


async def controlled(searcher):
    mode='';hits=[];base=''
    async def provider(request):
        hits.append(request.path)
        q='Boreal Instruments support phone'
        if mode=='lookup':
            items=[('https://www.wordplays.com/crossword-solver/'+q.replace(' ','-'),q),
                   (base+'/answer','Boreal Instruments contact')]
        elif mode=='puzzle':items=[('https://www.wordplays.com/crossword-solver/cedar-tree','Cedar tree crossword clue')]
        elif mode=='identity':items=[(base+'/resource?id=Boreal-Instruments','Reference')]
        elif mode=='label':items=[(base+'/resource?q=Boreal+Instruments','Boreal Instruments contact')]
        elif mode=='encoded':items=[(base+'/unrelated?%73%65='+q.replace(' ','-'),'Ministry of Interior')]
        elif mode=='fallback' and request.path=='/good':items=[(base+'/answer','Boreal Instruments contact')]
        elif mode=='mixed':items=[(base+'/unrelated?SE='+q.replace(' ','-'),'Ministry of Interior'),(base+'/answer','Boreal Instruments contact')]
        elif mode=='identifier':items=[(base+'/unrelated?query=render_mode','Reference')]
        else:items=[(base+'/unrelated?SE='+q.replace(' ','-'),'Ministry of Interior')]
        html=''.join('<li class="b_algo"><h2><a class="result-link" href="'+u+'">'+label+'</a></h2></li>' for u,label in items)
        return web.Response(text=html,content_type='text/html')
    app=web.Application();app.router.add_get('/{tail:.*}',provider)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);rows=[]
    try:
        for mode in ['query-only','encoded','identifier','mixed','fallback','lookup','puzzle','identity','label']:
            hits.clear();puzzle=mode=='puzzle'
            q='What is the answer to the Cedar tree crossword clue?' if puzzle else 'What is the value of `render_mode`?' if mode=='identifier' else 'What is the support phone of Boreal Instruments?'
            providers=[(base+'/good?q=','bing'),(base+'/bad?q=','bing')] if mode=='fallback' else [(base+'/bad?q=','bing')]
            async with Fetcher(Settings(allow_private=True),Deadline(12 if mode=='fallback' else 3.8)) as fetcher:
                actual=await searcher(plan_query(q),fetcher,providers)
            targets=[u for u,label in actual]
            if mode in {'query-only','encoded','identifier'}:passed=not actual
            elif mode=='mixed':passed=bool(targets) and targets[0]==base+'/answer'
            elif mode=='fallback':passed=base+'/answer' in targets and '/good' in hits
            elif mode=='lookup':passed=targets==[base+'/answer']
            elif mode=='puzzle':passed=bool(targets) and 'wordplays.com/crossword-solver/' in targets[0]
            else:passed=len(actual)==1
            rows.append(dict(id=mode,passed=passed,targets=targets,hits=list(hits)))
    finally:await runner.cleanup()
    return rows


def direct(old_score):
    rows=[];plan=plan_query('What is the support phone of Boreal Instruments?')
    base='https://example.org/'
    for name,url,label,expected in [
        ('query-echo',base+'contact?SE=Boreal+Instruments+support+phone','Contact',base+'contact'),
        ('encoded-key',base+'contact?%71=Boreal+Instruments','Contact',base+'contact'),
        ('identity',base+'resource?package=Boreal+Instruments&id=8','Reference',base+'resource?package=Boreal+Instruments&id=8'),
        ('signed',base+'file?q=Boreal+Instruments&sig=abc&expires=99','Download',base+'file?sig=abc&expires=99'),
    ]:
        actual=relevance_url(url);rows.append(dict(id=name,passed=actual==expected and canonical_url(url)==url,actual=actual))
    for name,url,expected in [('lookup','https://www.wordplays.com/crossword-solver/cedar',True),
        ('subdomain','https://m.wordplays.com/crossword-solver/cedar',True),
        ('lookalike','https://wordplays.com.example.org/crossword-solver/cedar',False),
        ('editorial','https://www.wordplays.com/blog/cedar',False),
        ('path-boundary','https://www.wordplays.com/crossword-solver-guide',False)]:
        rows.append(dict(id=name,passed=answer_lookup_url(url)==expected))
    echo=base+'z?SE='+'-'.join(plan.terms);good=base+'a'
    old=(old_score(plan,base,echo,'Details'),old_score(plan,base,good,'Boreal Instruments'))
    new=(link_score(plan,base,echo,'Details'),link_score(plan,base,good,'Boreal Instruments'))
    rows.append(dict(id='navigation-echo',passed=old[0]>old[1] and new[0]<new[1],before=old,after=new))
    clue='https://www.wordplays.com/crossword-solver/Boreal-Instruments-support-phone'
    rows.append(dict(id='navigation-lookup',passed=link_score(plan,base,clue,plan.question)<0))
    puzzle=plan_query('What is the answer to the Cedar tree crossword clue?')
    rows.append(dict(id='navigation-puzzle-retained',passed=link_score(puzzle,base,clue,'Cedar tree crossword clue')>1))
    return rows


async def recorded(old_search):
    report=json.loads((ROOT/'benchmarks/query-years-20261023-probe.json').read_text(encoding='utf-8'))
    cases=json.loads((ROOT/'benchmarks/expansion-20261023-live-cases.json').read_text(encoding='utf-8'));rows=[]
    body=''
    async def provider(request):return web.Response(text=body,content_type='text/html')
    app=web.Application();app.router.add_get('/p',provider);runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    try:
        for row in report['rows']:
            c=next(c for c in cases if c['id']==row['id'])
            for stage in ['before','after']:
                evidence=row[stage];path=ROOT/evidence['capture_path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==evidence['capture_sha256']
                response=json.loads(path.read_text(encoding='utf-8'));body=base64.b64decode(response['body_base64']).decode('utf-8','replace')
                pair={}
                for version,searcher in [('before',old_search),('after',search)]:
                    async with Fetcher(Settings(allow_private=True),Deadline(3.8)) as fetcher:
                        pair[version]=await searcher(plan_query(c['query']),fetcher,[(base+'/p?q=','duckduckgo_lite')])
                rows.append(dict(id=row['id']+'-'+stage+'-query',query=evidence['query'],capture_sha256=evidence['capture_sha256'],**pair,
                    removed=[item for item in pair['before'] if item not in pair['after']],
                    added=[item for item in pair['after'] if item not in pair['before']]))
    finally:await runner.cleanup()
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('5629aaf');old_search=importlib.import_module(old.__module__.rsplit('.',1)[0]+'.search').search
    before=asyncio.run(controlled(old_search));after=asyncio.run(controlled(search));guards=direct(old.run.__globals__['link_score'])
    report=dict(scope=__doc__,baseline=revision,before=before,after=after,guards=guards,recorded=asyncio.run(recorded(old_search)),
        before_passed=sum(r['passed'] for r in before),after_passed=sum(r['passed'] for r in after),total=len(after),
        wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
        production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('agent').glob('*.py')})
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    print(json.dumps({'guard_passed':sum(r['passed'] for r in guards),'guard_total':len(guards),
        'recorded':[{'id':r['id'],'removed':len(r['removed']),'added':len(r['added'])} for r in report['recorded']]}))
    if not all(r['passed'] for r in after+guards):sys.exit(1)
