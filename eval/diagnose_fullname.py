"""Full-name request routing versus genuine multi-output requests; no LLM accuracy claim."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.planner import plan_query
from revision_engine import load_engine


def diagnose(planner):
    cases=[
        ('first-last','What is the first and last name of the partner of Orin Vale?','single'),
        ('plural','What are the first and last names of the partner of Orin Vale?','single'),
        ('given-family','Which given and family name belongs to the partner of Orin Vale?','single'),
        ('two-name-nouns','What is the first name and last name of the partner of Orin Vale?','single'),
        ('surname','What is the first and surname of the partner of Orin Vale?','single'),
        ('explicit-columns','What are the first name and surname columns of Orin Vale?','compose_fields'),
        ('name-email','What are the first name and email of Orin Vale?','compose_fields'),
        ('day-time','What day and time does Pine Harbor collect glass?','compose_fields'),
        ('month-year','What month and year was Pine Harbor founded?','single'),
        ('version-comparison','How did the capacity change from version 2 to version 3?','compare_versions'),
    ]
    return [dict(id=name,query=query,expected=expected,actual=planner(query).operation,
                 passed=planner(query).operation==expected) for name,query,expected in cases]


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('3fe17ab')
    before=diagnose(old.run.__globals__['plan_query']);after=diagnose(plan_query)
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,
        before=before,after=after,before_passed=sum(r['passed'] for r in before),
        after_passed=sum(r['passed'] for r in after),total=len(after),
        wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
        losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
        planner_sha256=hashlib.sha256((ROOT/'agent/planner.py').read_bytes()).hexdigest())
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    if not all(r['passed'] for r in after):sys.exit(1)
