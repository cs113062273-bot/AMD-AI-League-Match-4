"""Summarize observed failure signals without relabeling answers or changing gold data."""
import argparse
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit


def discovery(url):
    host=urlsplit(url).hostname or ''
    return any(host==domain or host.endswith('.'+domain) for domain in ('google.com','bing.com','duckduckgo.com')) or 'list=search' in url or 'wbsearchentities' in url


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('result')
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    report=json.loads(Path(args.result).read_text(encoding='utf-8'))
    counts=Counter();failures=[]
    for row in report['rows']:
        if row['joint_ok']:continue
        diagnostic=row.get('diagnostics',{})
        fetches=diagnostic.get('fetches',[])
        signals=[]
        source_errors=[{'url':item['url'],'error':item['error'],'status':item.get('status')} for item in fetches if item.get('error') and not discovery(item['url'])]
        search_errors=[item for item in fetches if discovery(item['url']) and item.get('error')]
        if source_errors:signals.append('NET_SOURCE_FAILURE')
        if search_errors:signals.append('SEA_PROVIDER_FAILURE')
        if any(str(item.get('error','')).startswith('parse_') for item in diagnostic.get('errors',[])):signals.append('PAR_PARSE_FAILURE')
        if any(item.get('error')=='internal_deadline' for item in diagnostic.get('errors',[])):signals.append('TME_INTERNAL_DEADLINE')
        if any(item.get('state') not in {'rendered','disabled_or_budget'} for item in diagnostic.get('browser',[])):signals.append('DYN_RENDER_FAILURE')
        if row['answer_ok'] and not row['source_ok']:signals.append('CIT_EXACT_SOURCE_MISMATCH')
        if row.get('answer') and not row['answer_ok']:signals.append('RANK_OR_ANSWER_FORMAT_MISMATCH')
        if not row.get('answer'):signals.append('ABS_UNANSWERED')
        if row.get('error'):signals.append('CTR_HARNESS_EXCEPTION')
        counts.update(signals)
        failures.append({'id':row['id'],'signals':signals,'source_errors':source_errors,
            'search_failure_count':len(search_errors),'engine_errors':diagnostic.get('errors',[]),
            'selector':diagnostic.get('selector',[]),'verification':diagnostic.get('verification',[])})
    output={'source_result':args.result,'n':len(report['rows']),'failed':len(failures),
        'interpretation':'Signals may coexist. They are observations, not mutually exclusive proven root causes. Exact-scoring mismatches may require manual answer/source review.',
        'signal_counts':dict(counts),'failures':failures}
    Path(args.out).write_text(json.dumps(output,indent=2,ensure_ascii=True),encoding='utf-8')
    print(json.dumps({'failed':len(failures),'signal_counts':dict(counts)}))


if __name__=='__main__':main()
