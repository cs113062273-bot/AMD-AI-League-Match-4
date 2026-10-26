"""Exact answer AND source scoring. Input carries explicit expected source criteria."""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path
import statistics
import sys
import time
import hashlib
import platform
from dataclasses import asdict
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from agent.engine import Engine
from agent.types import Settings
from agent.output import atomic_json
from benchmarks.fakeweb import FakeWeb


def percentile(values, p):
    if not values:
        return 0
    a=sorted(values)
    k=(len(a)-1)*p
    lo=int(k); hi=min(lo+1,len(a)-1)
    return a[lo]+(a[hi]-a[lo])*(k-lo)


def score(answer,sources,case,base='',error=''):
    answer_ok=answer in case.get('answers',[case.get('answer','')])
    expected=base+case['source_path'] if 'source_path' in case else case.get('source',(case.get('sources') or [''])[0])
    blank=not case.get('answer',case.get('answers',[''])[0])
    accepted=[base+case['source_path']] if 'source_path' in case else [case['source']] if case.get('source') else case.get('sources',[])
    source_ok=not sources if blank else bool(sources) and (bool(set(accepted).intersection(sources)) if accepted else any(s.startswith(tuple(case.get('source_prefixes',[]))) for s in sources))
    joint=answer_ok and source_ok and not error
    category='' if joint else 'CTR' if error else 'CIT' if answer_ok else 'ABS' if not answer else 'RANK'
    return answer_ok,source_ok,expected,joint,category


async def run(cases, settings, base=""):
    rows=[]
    for case in cases:
        start=time.monotonic()
        error=""; malformed=False;confidence=None;reason=''
        try:
            result=await Engine(settings).run(case["query"],base+case["path"] if "path" in case else case.get("url", ""))
            answer=result.answer
            sources=result.sources
            diag=result.diagnostics
            try:
                if not isinstance(answer,str) or not isinstance(sources,list) or not all(isinstance(s,str) for s in sources):
                    raise TypeError('Invalid result value types')
                json.dumps(result.internal(),ensure_ascii=False,allow_nan=False)
                confidence=result.confidence
                reason=result.reason
            except (TypeError,ValueError):
                malformed=True
                raise
        except Exception as exc:
            answer,sources,diag="",[],{}
            error=f"{type(exc).__name__}: {exc}"
        answer_ok,source_ok,expected,joint,category=score(answer,sources,case,base,error)
        rows.append({"id":case["id"],"family":case.get("family","live"),"answer":answer,"sources":sources,
            "expected_answer":case.get("answers",[case.get("answer","")]),"expected_source":expected,
            "answer_ok":answer_ok,"source_ok":source_ok,"joint_ok":joint,
            "seconds":time.monotonic()-start,"error":error,"failure_category":category,
            "confidence":confidence,"reason":reason,
            "malformed_output":malformed,
            "diagnostics":diag})
        if not joint:
            print(f"FAIL {case['id']}: {answer!r}; expected {case.get('answer',case.get('answers'))!r}",flush=True)
    return rows


def summarize(rows,cases):
    n=len(rows); times=[r["seconds"] for r in rows]
    ground_blank=[not c.get("answer",c.get("answers",[""])[0]) for c in cases]
    tp=sum(not r["answer"] and b for r,b in zip(rows,ground_blank))
    predicted=sum(not r["answer"] for r in rows)
    actual=sum(ground_blank)
    failures={}
    for r in rows:
        if r["failure_category"]:
            key=r["failure_category"];failures[key]=failures.get(key,0)+1
    summary={"n":n,"answer_accuracy":sum(r["answer_ok"] for r in rows)/n,
        "source_accuracy":sum(r["source_ok"] for r in rows)/n,
        "joint_accuracy":sum(r["joint_ok"] for r in rows)/n,
        "abstention_precision":tp/predicted if predicted else None,"abstention_recall":tp/actual if actual else None,
        "crashes":sum(bool(r["error"]) for r in rows),"malformed_outputs":sum(r.get('malformed_output',False) for r in rows),
        "internal_deadlines":sum(any(e.get("error")=="internal_deadline" for e in r["diagnostics"].get("errors",[])) for r in rows),
        "recovered_engine_errors":sum(any(e.get("error") not in {"internal_deadline"} and e.get("message") for e in r["diagnostics"].get("errors",[])) for r in rows),
        "latency":{"mean":statistics.mean(times),"p50":percentile(times,.5),"p90":percentile(times,.9),
                   "p95":percentile(times,.95),"p99":percentile(times,.99),"max":max(times)},
        "failure_taxonomy":failures,
        "pages_per_query":statistics.mean(r["diagnostics"].get("pages_fetched",0) for r in rows),
        "llm_calls":sum(r["diagnostics"].get("llm_calls",0) for r in rows),
        "search_requests":sum(r["diagnostics"].get("search_requests",0) for r in rows)}
    from eval.calibration import analyze
    summary['confidence_diagnostic']=analyze(rows)
    return summary


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8',errors='backslashreplace')
    ap=argparse.ArgumentParser()
    ap.add_argument("cases")
    ap.add_argument("--fixtures")
    ap.add_argument("--model",action="store_true")
    ap.add_argument('--browser',action='store_true',help='Use the production selective Chromium fallback')
    ap.add_argument("--out",default="benchmarks/results")
    ap.add_argument("--budget",type=float,default=12)
    args=ap.parse_args()
    production=[Path('app.py'),*Path('agent').glob('*.py')]
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in production}
    def model_health():
        if not args.model:return None
        import urllib.request
        try:
            with urllib.request.urlopen('http://127.0.0.1:8765/health',timeout=2) as response:return json.load(response)
        except (OSError,ValueError):return {'unavailable':True}
    health_before=model_health()
    cases=json.loads(Path(args.cases).read_text(encoding="utf-8"))
    if not isinstance(cases,list) or not cases:raise ValueError('Benchmark must be a nonempty list')
    for case in cases:
        if not isinstance(case,dict) or not isinstance(case.get('query'),str) or 'id' not in case:
            raise ValueError('Every case needs a string query and ID')
        if case.get('answer',case.get('answers',[''])[0]) and not any(case.get(k) for k in ['source_path','source','sources','source_prefixes']):
            raise ValueError('Answerable case lacks an explicit expected source: '+str(case['id']))
    settings=Settings(budget=args.budget,search=not bool(args.fixtures),allow_private=bool(args.fixtures),
        browser=args.browser,
        model_url="http://127.0.0.1:8765" if args.model else "")
    if args.fixtures:
        routes=json.loads(Path(args.fixtures).read_text(encoding="utf-8"))
        with FakeWeb(routes) as server:
            rows=asyncio.run(run(cases,settings,server.base))
    else:
        rows=asyncio.run(run(cases,settings))
    summary=summarize(rows,cases)
    production=[Path('app.py'),*Path('agent').glob('*.py')]
    metadata={'at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'python':platform.python_version(),
        'platform':platform.system(),'settings':asdict(settings),'cases_sha256':hashlib.sha256(Path(args.cases).read_bytes()).hexdigest(),
        'production_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in production}}
    metadata['production_before_sha256']=before
    metadata['production_changed_during_run']=before!=metadata['production_sha256']
    metadata['model_before']=health_before
    metadata['model_after']=model_health()
    if health_before and health_before.get('backend_source_sha256'):
        metadata['backend_matches_starting_source']=all(before.get(str(Path('agent')/name))==digest
            for name,digest in health_before['backend_source_sha256'].items())
    atomic_json(args.out+".json",{"summary":summary,"rows":rows,'run':metadata})
    with open(args.out+".csv","w",newline="",encoding="utf-8") as f:
        keys=[k for k in rows[0] if k!="diagnostics"]
        w=csv.DictWriter(f,fieldnames=keys,extrasaction="ignore");w.writeheader();w.writerows(rows)
    print(json.dumps(summary,indent=2))


if __name__=="__main__":
    main()
