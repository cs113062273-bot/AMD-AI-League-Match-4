"""CPU-only paired discovery replay over hash-verified actual public bodies.

No model/browser or synthetic answer. The replay measures recovered retrieval
and source text in the reader payload, not answer accuracy or source gold.
"""
import argparse
import asyncio
import base64
import hashlib
import importlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.engine import rank_passages
from agent.network import Response
from agent.parser import parse_response
from agent.planner import plan_query
from agent.search import search,source_title_query
from agent.selector import payload
from agent.types import Deadline
from agent.urls import canonical_url
from revision_engine import load_engine


def read_capture(path,digest):
    path=ROOT/path;assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    captures={}
    for u,raw in json.loads(path.read_text(encoding='utf-8')).items():
        data=dict(raw);data['body']=base64.b64decode(data.pop('body_base64'))
        captures[u]=Response(**data)
    return captures


class Replay:
    def __init__(self,captures,start,failed=True):
        self.responses=captures;self.deadline=Deadline(30);self.misses=[]
        self.events=[dict(url=start,error='http_403')] if failed else []
    async def fetch(self,url,**kwargs):
        key=canonical_url(url)
        response=self.responses.get(key)
        if response is None:
            self.misses.append(url);response=Response(url,error='not_captured')
        self.events.append(dict(url=url,error=response.error))
        return response


async def replay(searcher,plan,hints,captures,failed=True):
    fetcher=Replay(captures,plan.url,failed)
    links=await searcher(plan,fetcher,hints=hints)
    pages=[parse_response(await fetcher.fetch(u)) for u,a in links[:4]]
    pages=[p for p in pages if not p.error]
    sent=payload(plan,[],rank_passages(plan,pages))
    witnesses=[p for p in sent['passages'] if 'Hermogenes' in p['text'] and 'Horse' in p['text']
        and 'eight' in p['text'] and '81' in p['text'] and '89' in p['text']]
    return dict(links=links,requests=fetcher.events,missing_captures=fetcher.misses,
        reader_passages=sent['passages'],complete_witness_in_payload=bool(witnesses),
        witness_source=witnesses[0]['source'] if witnesses else '')


def guards():
    question='Who won eight Olympic races?'
    base='https://en.wikipedia.org/wiki/Oriole_of_Ridge'
    rows=[]
    cases=[('unmentioned-title',question,base,'"Oriole of Ridge"'),
        ('already-anchored','When did Oriole win?',base,''),
        ('ordinary-company','What month did Activision Blizzard launch its division?',
            'https://en.wikipedia.org/wiki/Activision_Blizzard',''),
        ('mobile-language',question,'https://fr.m.wikipedia.org/wiki/Oriole_de_Ridge','"Oriole de Ridge"')]
    for name,url in [('other-site','https://example.org/wiki/Oriole_of_Ridge'),
        ('lookalike','https://en.wikipedia.org.example.org/wiki/Oriole_of_Ridge'),
        ('credentials','https://x@en.wikipedia.org/wiki/Oriole_of_Ridge'),
        ('non-http','ftp://en.wikipedia.org/wiki/Oriole_of_Ridge'),
        ('odd-port','https://en.wikipedia.org:8443/wiki/Oriole_of_Ridge'),
        ('namespace','https://en.wikipedia.org/wiki/Special:Search'),
        ('encoded-control','https://en.wikipedia.org/wiki/Oriole%0Aof_Ridge'),
        ('malformed','https://['),('invalid-utf8','https://en.wikipedia.org/wiki/%FF'),
        ('not-article','https://en.wikipedia.org/w/index.php?title=Oriole'),
        ('too-long','https://en.wikipedia.org/wiki/'+'X'*121)]:
        cases.append((name,question,url,''))
    for name,q,u,expected in cases:
        actual=source_title_query(plan_query(q,u))
        rows.append(dict(id=name,passed=actual==expected,actual=actual,expected=expected))
    return rows


async def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out);assert not target.exists()
    report=json.loads((ROOT/'benchmarks/external-disjoint12b-20261023-repeat.json').read_text(encoding='utf-8'))
    row=next(r for r in report['rows'] if r['id']=='simpleqa-2215');diag=row['result']['diagnostics']
    original=read_capture(row['capture_path'],row['capture_sha256'])
    live=json.loads((ROOT/'benchmarks/source-title-20261023-live.json').read_text(encoding='utf-8'))
    captures={**original,**read_capture(live['capture_path'],live['sha256'])}
    plan=plan_query(diag['plan']['question'],diag['plan']['url'])
    old,revision,hashes=load_engine('ee623ca')
    old_search=importlib.import_module(old.__module__.rsplit('.',1)[0]+'.search').search
    before=await replay(old_search,plan,diag['search_hints'],captures)
    after=await replay(search,plan,diag['search_hints'],captures)
    # A reachable starting source must not activate this fallback.
    unchanged_before=await replay(old_search,plan,diag['search_hints'],captures,False)
    unchanged_after=await replay(search,plan,diag['search_hints'],captures,False)
    checks=guards()
    all_passed=(not before['complete_witness_in_payload'] and after['complete_witness_in_payload']
        and unchanged_before==unchanged_after and all(r['passed'] for r in checks)
        and not before['missing_captures'] and not after['missing_captures'])
    result=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,
        input_sha256={row['capture_path']:row['capture_sha256'],live['capture_path']:live['sha256']},
        before=before,after=after,guards=checks,reachable_source_unchanged=unchanged_before==unchanged_after,
        all_passed=all_passed)
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(all_passed=all_passed,guards_passed=sum(r['passed'] for r in checks),
        guards_total=len(checks),before_witness=before['complete_witness_in_payload'],after_witness=after['complete_witness_in_payload'],
        before_misses=before['missing_captures'],after_misses=after['missing_captures'],
        reachable_source_unchanged=result['reachable_source_unchanged'])))
    if not all_passed:sys.exit(1)


if __name__=='__main__':asyncio.run(main())
