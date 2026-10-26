"""Add a separately labeled redirect-provenance score without changing external truth."""
import argparse
import json
from pathlib import Path
import sys
import hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.urls import canonical_url
from agent.output import atomic_json


def main():
    parser=argparse.ArgumentParser();parser.add_argument('result');parser.add_argument('--out',required=True);parser.add_argument('--cases');args=parser.parse_args()
    data=json.loads(Path(args.result).read_text(encoding='utf-8'))
    path=Path(args.cases) if args.cases else None
    if path is None:
        expected=data.get('run',{}).get('cases_sha256')
        path=next((p for p in Path('benchmarks').glob('*.json') if hashlib.sha256(p.read_bytes()).hexdigest()==expected),None)
    if path is None:raise ValueError('Cannot identify frozen cases; pass --cases explicitly')
    cases={c['id']:c for c in json.loads(path.read_text(encoding='utf-8'))}
    rows=[]
    for row in data['rows']:
        case=cases[row['id']]
        gold={canonical_url(url) for url in (case.get('sources') or [case.get('source','')]) if url}
        blank=not case.get('answer',case.get('answers',[''])[0])
        if not gold and not blank:raise ValueError('Case lacks explicit web sources')
        allowed=set(gold)
        for event in row['diagnostics'].get('fetches',[]):
            chain=[event.get('url',''),*event.get('redirects',[])]
            if not event.get('error') and any(canonical_url(url) in gold for url in chain):allowed.add(canonical_url(event.get('final','')))
        correct=not row['sources'] if blank else bool(row['sources']) and all(canonical_url(url) in allowed for url in row['sources'])
        rows.append({'id':row['id'],'answer':row['answer'],'answer_ok':row['answer_ok'],
            'exact_source_ok':row['source_ok'],'gold_redirect_provenance_ok':correct,
            'joint_with_redirect_provenance':row['answer_ok'] and correct})
    atomic_json(args.out,{'method':'Gold-URL redirect chains may establish the fetched final URL. No answer labels or gold URLs are edited.','cases':path.as_posix(),
        'strict_summary':data['summary'],'n':len(rows),
        'joint_with_redirect_provenance':sum(r['joint_with_redirect_provenance'] for r in rows)/len(rows),'rows':rows})


if __name__=='__main__':main()
