"""CPU-only month-request precision and actual captured announcement protocol.

Selector responses are stubs. This tests source-backed projection, not model
accuracy, discovery success, or the immutable benchmark's exact-string score.
"""
import argparse
import asyncio
import base64
import hashlib
import importlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.engine import Engine
from agent.network import Response
from agent.parser import parse_response
from agent.planner import plan_query
from agent.types import Settings,Deadline
from revision_engine import load_engine


def checks(planner,question):
    positive=[question,'Specify the month and year of the announcement.',
        'State the year, and month of the announcement.',
        'Give the month and year of the announcement.',
        'Provide the year and month of the announcement.',
        'Tell me the month, and year of the announcement.',
        'What month and year was it announced?',
        'Which year, and month was it announced?']
    negative=['What day, month, and year was it announced?',
        'Specify the day, month, and year of the announcement.',
        'How many months and years elapsed?',
        'What are the monthly and yearly sales?',
        'Who wrote Month and Year?',
        'What year was it announced?']
    rows=[]
    for q in positive+negative:
        p=planner(q);expected=q in positive
        passed=(p.kind=='date' and p.date_precision=='month' and p.operation=='single') if expected else not p.date_precision
        rows.append(dict(question=q,kind=p.kind,precision=p.date_precision,passed=passed))
    return rows


async def protocol(engine,page,question):
    module=engine.__module__.rsplit('.',1)[0]
    planner=importlib.import_module(module+'.planner').plan_query
    selector=importlib.import_module(module+'.selector')
    candidates=importlib.import_module(module+'.candidates')
    plan=planner(question,page.url)
    cs=candidates.rank(candidates.extract(plan,page),plan)
    ps=engine.run.__globals__['rank_passages'](plan,[page],cs)
    sent=selector.payload(plan,cs,ps)
    date='October 22, 2015'
    idx=next(i for i,p in enumerate(sent['passages']) if date in p['text'])
    async def reply(*args,**kwargs):return {'passage':idx,'answer':date},'ok'
    with patch.object(selector,'request_model',reply):
        chosen,state=await selector.select(plan,cs,ps,Settings(),Deadline(4))
    assert chosen is not None
    return dict(kind=plan.kind,precision=plan.date_precision,state=state,raw=chosen.raw,
        answer=chosen.answer,source=chosen.source,verified=candidates.verify(chosen,plan,[page]),
        passed=chosen.answer=='October 2015' and candidates.verify(chosen,plan,[page]),
        sent_passages=sent['passages'])


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out);assert not target.exists()
    original=json.loads((ROOT/'benchmarks/external-disjoint12b-20261023-repeat.json').read_text(encoding='utf-8'))
    question=next(r for r in original['rows'] if r['id']=='simpleqa-483')['result']['diagnostics']['plan']['question']
    source=json.loads((ROOT/'benchmarks/announcement-20261023-sources.json').read_text(encoding='utf-8'))['rows'][3]
    cap=ROOT/source['capture_path'];assert hashlib.sha256(cap.read_bytes()).hexdigest()==source['sha256']
    raw=json.loads(cap.read_text(encoding='utf-8'));raw['body']=base64.b64decode(raw.pop('body_base64'))
    page=parse_response(Response(**raw))
    old,revision,hashes=load_engine('e2115bf')
    before=checks(old.run.__globals__['plan_query'],question);after=checks(plan_query,question)
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,
        capture_sha256=source['sha256'],before=before,after=after,
        before_protocol=asyncio.run(protocol(old,page,question)),after_protocol=asyncio.run(protocol(Engine,page,question)),
        all_passed=all(r['passed'] for r in after))
    report['all_passed'] &= report['after_protocol']['passed']
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(before_passed=sum(r['passed'] for r in before),after_passed=sum(r['passed'] for r in after),
        total=len(after),before_answer=report['before_protocol']['answer'],after_answer=report['after_protocol']['answer'],
        all_passed=report['all_passed'])))
    if not report['all_passed']:sys.exit(1)


if __name__=='__main__':main()
