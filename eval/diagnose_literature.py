"""Actual scholarly discovery/field-ranking CPU replay with identity negatives.

No model, GPU or browser. API metadata supplies discovery only; answer spans
are checked against the actual fetched article, not API metadata or URLs.
"""
import argparse
import asyncio
import base64
from copy import deepcopy
from dataclasses import replace
import importlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.candidates import passage_score,verify
from agent.engine import Engine,rank_passages
from agent.literature import matching_links,paper_title,title_query,title_links
from agent.network import Response
from agent.parser import parse_response
from agent.planner import plan_query
from agent.selector import payload,select
from agent.types import Deadline,Settings
from diagnose_source_title import Replay,read_capture
from revision_engine import load_engine
from unittest.mock import patch


def controls(response,question):
    rows=[];expected=[('https://pmc.ncbi.nlm.nih.gov/articles/PMC7905350/',
        'EEG-Based Driving Fatigue Detection Using a Two-Level Learning Hierarchy Radial Basis Function.')]
    def check(name,resp,wanted):rows.append(dict(id=name,passed=matching_links(resp,question)==wanted))
    check('actual-exact-title',response,expected)
    for name,changes in [('http-error',dict(error='http_403')),('truncated',dict(truncated=True)),
        ('wrong-status',dict(status=202)),('lookalike-host',dict(url=response.url.replace('www.ebi.ac.uk/','www.ebi.ac.uk.example.org/'))),
        ('wrong-query',dict(url=response.url.replace('TITLE','BODY'))),('bad-json',dict(body=b'{}'))]:
        check(name,replace(response,**changes),[])
    original=json.loads(response.text)
    for name,mutate in [
        ('different-title',lambda d:d['resultList']['result'][0].update(title='A different research paper')),
        ('different-year',lambda d:d['resultList']['result'][0].update(pubYear='2023')),
        ('unsafe-id',lambda d:d['resultList']['result'][0].update(pmcid='PMC7905350/../../other')),
        ('non-open-access',lambda d:d['resultList']['result'][0].update(isOpenAccess='N')),
        ('wrong-source',lambda d:d['resultList']['result'][0].update(source='PAT')),
        ('wrong-request',lambda d:d['request'].update(queryString='another title')),
        ('duplicate-title-id',lambda d:d['resultList']['result'].append({**d['resultList']['result'][0],'pmcid':'PMC12345'})),
        ('invalid-result-shape',lambda d:d.update(resultList=[])),
    ]:
        data=deepcopy(original);mutate(data)
        check(name,replace(response,body=json.dumps(data).encode()),[])
    for q in ['Who was called "The Horse"?', 'What is the age range?',
        'What does `pool_size` mean?', 'What is the paper titled "Short title" about?',
        question+' Compare the article titled "A second complete publication title here".']:
        rows.append(dict(id='no-title-'+str(len(rows)),passed=not paper_title(q) and not title_query(q)))
    return rows


async def discovery(searcher,plan,hints,captures):
    f=Replay(captures,plan.url);links=await searcher(plan,f,hints=hints)
    pages=[parse_response(await f.fetch(u)) for u,a in links[:4]]
    pages=[p for p in pages if not p.error]
    return dict(links=links,missing_captures=f.misses,
        cohort_found=any('aged 23 to 27 years' in x.text for p in pages for x in p.passages),
        requests=f.events)


async def protocol(plan,page):
    ranked=rank_passages(plan,[page]);sent=payload(plan,[],ranked)
    idx=next(i for i,p in enumerate(sent['passages']) if 'aged 23 to 27 years' in p['text'])
    async def reply(*args,**kwargs):return {'passage':idx,'answer':'23 to 27'},'ok'
    with patch('agent.selector.request_model',reply):
        chosen,state=await select(plan,[],ranked,Settings(),Deadline(4))
    valid=bool(chosen and verify(chosen,plan,[page]))
    # A count from the same paragraph is not a complete age range: retain
    # raw evidence in this report rather than declaring semantic correctness.
    return dict(state=state,raw=chosen.raw if chosen else '',answer=chosen.answer if chosen else '',
        source=chosen.source if chosen else '',literal_verified=valid,sent_passages=sent['passages'])


async def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out);assert not target.exists()
    report=json.loads((ROOT/'benchmarks/external-disjoint12b-20261023-repeat.json').read_text(encoding='utf-8'))
    row=next(r for r in report['rows'] if r['id']=='simpleqa-516');diag=row['result']['diagnostics']
    original=read_capture(row['capture_path'],row['capture_sha256'])
    live=json.loads((ROOT/'benchmarks/literature-20261023-live-v1.json').read_text(encoding='utf-8'))
    current=read_capture(live['capture_path'],live['sha256']);captures={**original,**current}
    plan=plan_query(diag['plan']['question'],diag['plan']['url'])
    old,revision,hashes=load_engine('186f268')
    old_search=importlib.import_module(old.__module__.rsplit('.',1)[0]+'.search').search
    old_score=importlib.import_module(old.__module__.rsplit('.',1)[0]+'.candidates').passage_score
    before=await discovery(old_search,plan,diag['search_hints'],captures)
    after=await discovery(Engine.run.__globals__['search'],plan,diag['search_hints'],captures)
    response=next(r for u,r in current.items() if '/europepmc/webservices/rest/search?' in u)
    checks=controls(response,plan.question)
    page=parse_response(current['https://pmc.ncbi.nlm.nih.gov/articles/PMC7905350/'])
    old_ranked=old.run.__globals__['rank_passages'](plan,[page])
    new_ranked=rank_passages(plan,[page])
    before_ranks=[i+1 for i,(p,x,s) in enumerate(old_ranked) if 'aged 23 to 27 years' in x.text]
    after_ranks=[i+1 for i,(p,x,s) in enumerate(new_ranked) if 'aged 23 to 27 years' in x.text]
    other=replace(page,title='Different paper about EEG')
    unaffected=all(old_score(plan,other,p)==passage_score(plan,other,p) for p in page.passages)
    no_title_plan=plan_query('What was the age range of the drivers?',page.url)
    unaffected &= all(old_score(no_title_plan,page,p)==passage_score(no_title_plan,page,p) for p in page.passages)
    selected=await protocol(plan,page)
    low_budget=Replay({},plan.url);low_budget.deadline=Deadline(.5)
    skipped=await title_links(plan,low_budget)==[] and len(low_budget.events)==1
    all_passed=(not before['cohort_found'] and after['cohort_found'] and not before['missing_captures']
        and not after['missing_captures'] and before_ranks==[65] and after_ranks==[1]
        and all(r['passed'] for r in checks) and unaffected and skipped and selected['literal_verified'])
    result=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,
        input_sha256={row['capture_path']:row['capture_sha256'],live['capture_path']:live['sha256']},
        before=before,after=after,controls=checks,before_cohort_ranks=before_ranks,after_cohort_ranks=after_ranks,
        mismatched_or_unquoted_source_score_unchanged=unaffected,low_budget_no_request=skipped,
        stub_protocol=selected,all_passed=all_passed)
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(all_passed=all_passed,before_found=before['cohort_found'],after_found=after['cohort_found'],
        before_misses=before['missing_captures'],after_misses=after['missing_captures'],
        before_ranks=before_ranks,after_ranks=after_ranks,controls=sum(r['passed'] for r in checks),total=len(checks),
        unchanged=unaffected,low_budget_skipped=skipped,literal_span_passed=selected['literal_verified'])))
    if not all_passed:sys.exit(1)


if __name__=='__main__':asyncio.run(main())
