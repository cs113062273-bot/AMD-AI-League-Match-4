"""Mechanical source/type/conflict checks, including actual retained public responses.

No model is called. This measures guard behavior, not factual answer accuracy.
"""
import argparse
import base64
import hashlib
import importlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.engine import Engine
from agent import candidates,planner
from agent.network import Response
from agent.parser import parse_response
from agent.types import Candidate,Page,Passage
from revision_engine import load_engine


def diagnose(engine,typed,planning):
    rows=[];url='https://example.com/record'
    units=[
        ('datum-feet','What is the height of Cedar Hill in feet?','1141 ft MSL',True),
        ('literal-feet','What is the height of Cedar Hill in feet?','1141 feet',True),
        ('literal-foot','What is the height of Cedar Hill in feet?','1141 foot',True),
        ('literal-metres','What is the elevation of Cedar Hill in metres?','348 metres',True),
        ('literal-meters','What is the altitude of Cedar Hill in meters?','348 meters MSL',True),
        ('bare-elevation','What is the elevation of Cedar Hill?','348 m MSL',True),
        ('wrong-unit-ft','What is the height of Cedar Hill in feet?','348 m',False),
        ('wrong-unit-m','What is the height of Cedar Hill in metres?','1141 ft MSL',False),
        ('unknown-datum','What is the height of Cedar Hill in feet?','1141 ft XYZ',False),
        ('datum-not-voltage','What is the voltage in V?','12 V MSL',False),
        ('datum-not-width','What is the width in feet?','12 ft MSL',False),
        ('no-conversion','What is the height of Cedar Hill in feet?','348 m = 1141 ft',False),
    ]
    for name,query,raw,expected in units:
        evidence='Cedar Hill elevation: '+raw
        page=Page(url,title='Cedar Hill',passages=[Passage(evidence)])
        plan=planning.plan_query(query,url)
        chosen=Candidate(raw,raw,url,evidence,kind=plan.kind,score=8)
        actual=typed.verify(chosen,plan,[page])
        rows.append(dict(id=name,expected=expected,actual=actual,passed=actual==expected))
    for kind,query,first,second in [
        ('phone','What is the support phone number?','+1 212 555 0100','+1 212 555 0199'),
        ('price','What is the price?','$10','$20'),
    ]:
        label='Support phone' if kind=='phone' else 'Price'
        passages=[Passage(label+': '+raw,label,raw,kind='field') for raw in [first,second]]
        page=Page(url,title='Contact and prices',passages=passages)
        plan=planning.plan_query(query,url)
        options=[Candidate(raw,raw,url,p.text,label,kind=kind,score=8) for raw,p in zip([first,second],passages)]
        for chosen in [None,options[1]]:
            actual=engine._ambiguous(options,plan,[page],chosen)
            rows.append(dict(id=kind+('-selected' if chosen else '-deterministic'),actual=actual,passed=actual))
    report=json.loads((ROOT/'benchmarks/live-pipeline-20261023-before.json').read_text(encoding='utf-8'))
    for case_id,needle,raw in [('simpleqa-462','topoquest.com/place/new-york/summit/vickerman-hill','1141 ft MSL'),
                               ('simpleqa-3598','en.bharatpedia.org/wiki/We_Rollin','Anabolic Beatz')]:
        row=next(r for r in report['rows'] if r['id']==case_id)
        snapshot=json.loads((ROOT/row['capture_path']).read_text(encoding='utf-8'))
        response=next(dict(v) for u,v in snapshot.items() if needle in u)
        response['body']=base64.b64decode(response.pop('body_base64'))
        page=parse_response(Response(**response))
        plan=planning.plan_query(row['result']['diagnostics']['plan']['question'],page.url)
        selected=next(c for c in row['result']['diagnostics']['model_selections'] if c['raw']==raw)
        chosen=Candidate(**selected)
        if case_id=='simpleqa-462':actual=typed.verify(chosen,plan,[page])
        else:
            options=typed.rank(typed.extract(plan,page),plan)
            actual=not engine._ambiguous(options,plan,[page],chosen)
            deterministic=engine._ambiguous(options,plan,[page])
            rows.append(dict(id='actual-unselected-tie-retained',actual=deterministic,passed=deterministic))
        rows.append(dict(id='actual-'+case_id,actual=actual,passed=actual,
                         capture_sha256=row['capture_sha256']))
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('e74e5da');prefix=old.__module__.rsplit('.',1)[0]
    before=diagnose(old,importlib.import_module(prefix+'.candidates'),importlib.import_module(prefix+'.planner'))
    after=diagnose(Engine,candidates,planner)
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,
                before_passed=sum(r['passed'] for r in before),after_passed=sum(r['passed'] for r in after),total=len(after),
                wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
                losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],before=before,after=after,
                production_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'agent').glob('*.py')})
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    if not all(r['passed'] for r in after):sys.exit(1)
