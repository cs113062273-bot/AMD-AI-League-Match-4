"""Small paired CPU fixture regression for parser/field/type changes; not model accuracy."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent.engine import Engine
from agent.types import Settings
from benchmarks.fakeweb import FakeWeb
from eval.diagnose_bindings import legacy
from eval.run import run


async def diagnose():
    selected={
        'dev':['support-phone-0','price-0','history-0','spec-0','jsonld-0','json-0','count-0','csv-0','date-0'],
        'holdout':['rowspan-0','asof-release-0','duration-0','meta-author-0','schema-conflict-0','hidden-duplicate-0']}
    old={name:legacy(name) for name in ['engine','parser','planner','candidates']}
    old['engine'].parse_response=old['parser'].parse_response
    old['engine'].plan_query=old['planner'].plan_query
    for name in ['extract','rank','verify','conflicts','passage_score','overlap']:
        setattr(old['engine'],name,getattr(old['candidates'],name))
    output=[]
    for dataset,ids in selected.items():
        cases=[case for case in json.loads((ROOT/'benchmarks'/f'{dataset}.json').read_text(encoding='utf-8')) if case['id'] in ids]
        routes=json.loads((ROOT/'fixtures'/f'{dataset}.json').read_text(encoding='utf-8'))
        settings=Settings(model_url='',search=False,allow_private=True,budget=4)
        with FakeWeb(routes) as web:
            with patch('eval.run.Engine',old['engine'].Engine):before=await run(cases,settings,web.base)
            with patch('eval.run.Engine',Engine):after=await run(cases,settings,web.base)
        output.extend({'id':a['id'],'before':b,'after':a} for b,a in zip(before,after))
    return {'scope':__doc__,'baseline_note':'81d7a9e parser/planner/candidates; these were unchanged through P0. CPU fixture paths only.',
        'before_passed':sum(r['before']['joint_ok'] for r in output),
        'after_passed':sum(r['after']['joint_ok'] for r in output), 'total':len(output),
        'wins':[r['id'] for r in output if r['after']['joint_ok'] and not r['before']['joint_ok']],
        'losses':[r['id'] for r in output if r['before']['joint_ok'] and not r['after']['joint_ok']], 'rows':output}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);args=parser.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    report=asyncio.run(diagnose())
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:report[key] for key in ['before_passed','after_passed','total','wins','losses']}))
    if report['losses']:sys.exit(1)
