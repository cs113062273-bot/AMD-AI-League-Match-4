"""Re-score retained answers after a benchmark schema correction. Does not rerun queries."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eval.run import score,summarize
from agent.output import atomic_json


def main():
    ap=argparse.ArgumentParser();ap.add_argument('cases');ap.add_argument('results');ap.add_argument('--out',required=True);args=ap.parse_args()
    cases=json.loads(Path(args.cases).read_text(encoding='utf-8'))
    old=json.loads(Path(args.results).read_text(encoding='utf-8'))
    by_id={r['id']:r for r in old['rows']};rows=[]
    for case in cases:
        if 'source_path' in case:raise ValueError('Live cases only; fixture base URL must not be invented')
        row=by_id[case['id']]
        a,s,e,j,c=score(row['answer'],row['sources'],case,error=row['error'])
        row.update(answer_ok=a,source_ok=s,expected_source=e,joint_ok=j,failure_category=c)
        rows.append(row)
    data={'summary':summarize(rows,cases),'rows':rows,'rescore':{
        'original_sha256':hashlib.sha256(Path(args.results).read_bytes()).hexdigest(),
        'reason':'Accept plural sources in benchmark truth; answers, evidence and original timing unchanged. No queries rerun.'}}
    atomic_json(args.out,data)
    print(json.dumps(data['summary'],indent=2))


if __name__=='__main__':main()
