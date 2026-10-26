"""CPU-only location discovery and creator-prose ranking on actual captures.

No model/GPU/browser. Complete evidence in a payload and a literal selector
stub are not actual model answers or a new strict joint benchmark score.
"""
import argparse
import asyncio
import importlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.candidates import passage_score,verify
from agent.engine import rank_passages
from agent.parser import parse_response
from agent.planner import plan_query
from agent.search import concise_query,location_hint,search
from agent.selector import payload,select
from agent.types import Deadline,Settings,Page,Passage
from diagnose_source_title import Replay,read_capture
from revision_engine import load_engine


def location_controls():
    rows=[]
    for name,q,hint,expected in [
        ('missing-place','Which sculptor created Ceres in the River Castle Garden?',
            'ceres sculptor created','ceres sculptor created River Castle Garden'),
        ('partial-place','Which sculptor created Ceres in the River Castle Garden?',
            'ceres sculpture river','ceres sculpture river Castle Garden'),
        ('already-anchored','Which sculptor created Ceres in River Castle Garden?',
            'river castle garden ceres','river castle garden ceres'),
        ('multiple-places','Which sculptor created Ceres in River Castle and in Harbor Garden?',
            'ceres sculpture','ceres sculpture'),
        ('quoted-place','Which sculptor created "Ceres in River Castle"?',
            'ceres sculpture','ceres sculpture'),
        ('negated-place','Which sculptor created Ceres, not in River Castle?',
            'ceres sculpture','ceres sculpture'),
        ('single-word','Which sculptor created Ceres in York?',
            'ceres sculpture','ceres sculpture'),
        ('overflow','Which sculptor created Ceres in River Castle Garden?',
            'ceres statue sculpture creator artist description catalogue history',
            'ceres statue sculpture creator artist description catalogue history'),
    ]:
        actual=location_hint(plan_query(q),hint)
        rows.append(dict(id=name,passed=actual==expected,actual=actual,expected=expected))
    return rows


def relation_controls(old_score):
    rows=[];page=Page('https://example.org/art',title='River statue')
    for name,q,text,kind,boost in [
        ('sculptor','What is the name of the sculptor who created the statue?',
            'The statue was created by Elin Voss.','prose',True),
        ('architect','Which architect designed the bridge?',
            'The bridge was designed by Elin Voss.','prose',True),
        ('painter','Which painter painted the canvas?',
            'The canvas was painted by Elin Voss.','prose',True),
        ('author','Who wrote the book?',
            'The book was written by Elin Voss.','prose',True),
        ('wrong-relation','Which architect designed the bridge?',
            'The article was written by Elin Voss.','prose',False),
        ('different-output','What material was used by the sculptor who created the statue?',
            'The statue was created by Elin Voss.','prose',False),
        ('negation','Who created the statue?',
            'The statue was not originally created by Elin Voss.','prose',False),
        ('json-parent','Who created the statue?',
            'latitude: 42 | parent statue created by Elin Voss.','jsonld',False),
    ]:
        plan=plan_query(q);p=Passage(text,kind=kind)
        before=old_score(plan,page,p);after=passage_score(plan,page,p)
        rows.append(dict(id=name,passed=abs(after-before-(6 if boost else 0))<1e-9,before=before,after=after))
    return rows


async def replay(searcher,plan,hints,captures):
    f=Replay(captures,plan.url);links=await searcher(plan,f,hints=hints)
    pages=[parse_response(await f.fetch(u)) for u,a in links[:4]]
    pages=[p for p in pages if not p.error]
    return dict(links=links,requests=f.events,missing_captures=f.misses,
        creator_found=any('Caius Gabriel Cibber' in p.text and '1680' in p.text and 'Ceres' in p.text
            for pg in pages for p in pg.passages)),pages


async def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out);assert not target.exists()
    original=json.loads((ROOT/'benchmarks/external-disjoint12b-20261023-repeat.json').read_text(encoding='utf-8'))
    row=next(r for r in original['rows'] if r['id']=='simpleqa-2010');diag=row['result']['diagnostics']
    live=json.loads((ROOT/'benchmarks/location-hints-20261023-live.json').read_text(encoding='utf-8'))
    current=read_capture(live['capture_path'],live['sha256'])
    captures={**read_capture(row['capture_path'],row['capture_sha256']),**current}
    plan=plan_query(diag['plan']['question'],diag['plan']['url'])
    old,revision,hashes=load_engine('3f3a4b9');prefix=old.__module__.rsplit('.',1)[0]
    old_search=importlib.import_module(prefix+'.search');old_score=importlib.import_module(prefix+'.candidates').passage_score
    before,_=await replay(old_search.search,plan,diag['search_hints'],captures)
    after,pages=await replay(search,plan,diag['search_hints'],captures)
    old_ranked=old.run.__globals__['rank_passages'](plan,pages);ranked=rank_passages(plan,pages)
    before_ranks=[i+1 for i,(pg,p,s) in enumerate(old_ranked) if 'Caius Gabriel Cibber' in p.text]
    after_ranks=[i+1 for i,(pg,p,s) in enumerate(ranked) if 'Caius Gabriel Cibber' in p.text]
    sent=payload(plan,[],ranked)
    idx=next(i for i,p in enumerate(sent['passages']) if 'Caius Gabriel Cibber' in p['text'])
    async def reply(*args,**kwargs):return {'passage':idx,'answer':'Caius Gabriel Cibber'},'ok'
    with patch('agent.selector.request_model',reply):
        chosen,state=await select(plan,[],ranked,Settings(),Deadline(4))
    checks=location_controls()+relation_controls(old_score)
    probe=json.loads((ROOT/'benchmarks/hint-selection-20261023-probe.json').read_text(encoding='utf-8'))
    choices=[dict(id=r['id'],before=old_search.concise_query(plan_query(r['question']),r['hints']),
        after=concise_query(plan_query(r['question']),r['hints'])) for r in probe['rows']]
    changed=[r['id'] for r in choices if r['before']!=r['after']]
    valid=bool(chosen and verify(chosen,plan,pages))
    all_passed=(not before['creator_found'] and after['creator_found'] and before_ranks==[28]
        and after_ranks==[1] and not before['missing_captures'] and not after['missing_captures']
        and all(r['passed'] for r in checks) and valid and changed==['simpleqa-2010'])
    result=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,
        input_sha256={row['capture_path']:row['capture_sha256'],live['capture_path']:live['sha256']},
        before=before,after=after,before_creator_ranks=before_ranks,after_creator_ranks=after_ranks,
        controls=checks,recorded_choices=choices,changed=changed,payload=sent,
        stub_protocol=dict(state=state,literal_verified=valid,source=chosen.source if chosen else ''),all_passed=all_passed)
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(all_passed=all_passed,before_found=before['creator_found'],after_found=after['creator_found'],
        before_ranks=before_ranks,after_ranks=after_ranks,before_misses=before['missing_captures'],after_misses=after['missing_captures'],
        controls=sum(r['passed'] for r in checks),total=len(checks),changed=changed,literal_verified=valid,
        failures=[r['id'] for r in checks if not r['passed']])))
    if not all_passed:sys.exit(1)


if __name__=='__main__':asyncio.run(main())
