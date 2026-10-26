"""CPU-only frozen actual retrieval replay for empty-hint historical questions.

No GPU, model or browser. A selector stub tests literal protocol only; it is
not an actual model answer, unseen accuracy or a strict joint-score result.
"""
import argparse
import asyncio
import importlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.candidates import verify
from agent.engine import rank_passages
from agent.normalize import literal_span
from agent.parser import parse_response
from agent.planner import plan_query
from agent.search import concise_query,search
from agent.selector import payload,select
from agent.types import Deadline,Settings
from diagnose_source_title import read_capture,Replay
from revision_engine import load_engine


def controls(chooser):
    cases=[
        ('empty-hints','How many goals did River Academy score against Harbor School in 1992?',[],
            'River Academy Harbor School 1992'),
        ('invalid-hint','How many goals did River Academy score against Harbor School in 1992?',
            ['unrelated query'],'River Academy Harbor School 1992'),
        ('existing-hint','How many goals did River Academy score against Harbor School in 1992?',
            ['river academy goals'],'river academy goals'),
        ('quoted-first','Who from River Academy won "Pine Award" in 1992?',[],
            '"Pine Award" river academy'),
        ('no-year','How many goals did River Academy score against Harbor School?',[],''),
        ('two-years','Compare River Academy and Harbor School in 1992 and 1993.',[],''),
        ('one-name','How many goals did River Academy score in 1992?',[],''),
        ('duplicate-name','Did River Academy defeat River Academy in 1992?',[],''),
        ('all-lowercase','how many goals did river academy score against harbor school in 1992?',[],''),
        ('url-year','How many goals did River Academy score against Harbor School? https://example.org/1992',[],''),
        ('identifier-year','Did River Academy and Harbor School implement RFC 1992?',[],''),
        ('version-year','Did River Academy and Harbor School use version 1992.3?',[],''),
    ]
    rows=[]
    for name,q,hints,expected in cases:
        actual=chooser(plan_query(q),hints)
        rows.append(dict(id=name,passed=actual==expected,actual=actual,expected=expected))
    return rows


async def replay(searcher,plan,hints,captures):
    f=Replay(captures,plan.url)
    f.events[0]['error']=captures[plan.url].error
    links=await searcher(plan,f,hints=hints)
    pages=[parse_response(await f.fetch(u)) for u,a in links[:4]]
    pages=[p for p in pages if not p.error]
    ranked=rank_passages(plan,pages);sent=payload(plan,[],ranked)
    witness=[p for p in sent['passages'] if 'Game 2' in p['text'] and '5\u20134' in p['text']
        and 'Selkirk' in p['text'] and '1920' in p['text']]
    return dict(links=links,missing_captures=f.misses,requests=f.events,complete_witness=bool(witness),
        payload=sent),ranked,pages


async def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out);assert not target.exists()
    report=json.loads((ROOT/'benchmarks/external-disjoint12b-20261023-repeat.json').read_text(encoding='utf-8'))
    row=next(r for r in report['rows'] if r['id']=='simpleqa-1076');diag=row['result']['diagnostics']
    live=json.loads((ROOT/'benchmarks/named-year-20261023-live-v1.json').read_text(encoding='utf-8'))
    captures={**read_capture(row['capture_path'],row['capture_sha256']),
        **read_capture(live['capture_path'],live['sha256'])}
    plan=plan_query(diag['plan']['question'],diag['plan']['url'])
    old,revision,hashes=load_engine('f95c617')
    old_search=importlib.import_module(old.__module__.rsplit('.',1)[0]+'.search')
    before,_,_=await replay(old_search.search,plan,diag['search_hints'],captures)
    after,ranked,pages=await replay(search,plan,diag['search_hints'],captures)
    idx=next(i for i,p in enumerate(after['payload']['passages']) if 'Game 2' in p['text'] and '5\u20134' in p['text'])
    async def reply(*args,**kwargs):return {'passage':idx,'answer':'4'},'ok'
    with patch('agent.selector.request_model',reply):
        chosen,state=await select(plan,[],ranked,Settings(),Deadline(4))
    # The literal check must use the score, not the matching [4] citation.
    score_literal=literal_span('4','Game 2 concluded 5\u20134 on March 25.','number')
    stub=dict(state=state,raw=chosen.raw if chosen else '',source=chosen.source if chosen else '',
        literal_verified=bool(chosen and verify(chosen,plan,pages)),score_without_footnote_literal=score_literal)
    before_controls=controls(old_search.concise_query);after_controls=controls(concise_query)
    all_passed=(not before['complete_witness'] and after['complete_witness']
        and not before['missing_captures'] and not after['missing_captures']
        and all(r['passed'] for r in after_controls) and stub['literal_verified'] and score_literal)
    result=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,
        input_sha256={row['capture_path']:row['capture_sha256'],live['capture_path']:live['sha256']},
        before=before,after=after,before_controls=before_controls,after_controls=after_controls,
        stub_protocol=stub,all_passed=all_passed)
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(all_passed=all_passed,before_witness=before['complete_witness'],after_witness=after['complete_witness'],
        before_misses=before['missing_captures'],after_misses=after['missing_captures'],
        controls_passed=sum(r['passed'] for r in after_controls),controls_total=len(after_controls),stub=stub)))
    if not all_passed:sys.exit(1)


if __name__=='__main__':asyncio.run(main())
