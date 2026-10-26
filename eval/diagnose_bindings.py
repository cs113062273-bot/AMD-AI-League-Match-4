"""Replay concrete wrong-column/row/section candidates through source verification.

No model or network is used. Old candidates/parser/planner match the previous
P0 tree (unchanged from 81d7a9e); reports are development diagnostics only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent import candidates, parser, planner
from agent.network import Response
from agent.types import Candidate


def legacy(name):
    source=subprocess.check_output(['git','show','81d7a9e:agent/'+name+'.py'])
    module=types.ModuleType('agent._binding_baseline_'+name)
    module.__package__='agent'
    exec(compile(source,'git:81d7a9e:agent/'+name+'.py','exec'),module.__dict__)
    return module


def diagnose(parse,plan_query,verify,extract):
    rows=[]
    html='<h1>Lunar directory</h1><table><tr><th>Code</th><th>Feature name</th></tr>' \
         '<tr><td>NW06</td><td>Lagrange</td></tr><tr><td>NW07</td><td>Gilgamesh</td></tr></table>'
    roles='<h1>Turnstone Hall</h1><h2>Guest entry limits</h2><table><tr><th>Plan</th><th>Maximum entries</th></tr>' \
          '<tr><td>Studio</td><td>6 entries</td></tr></table><h2>Operator entry limits</h2>' \
          '<table><tr><th>Plan</th><th>Maximum entries</th></tr><tr><td>Studio</td><td>12 entries</td></tr></table>'
    for name,body,question,row_text,answer,expected in [
        ('right_column',html,'What is the feature name for code NW06?','Code: NW06','Lagrange',True),
        ('wrong_column',html,'What is the feature name for code NW06?','Code: NW06','NW06',False),
        ('wrong_row',html,'What is the feature name for code NW06?','Code: NW07','Gilgamesh',False),
        ('right_section',roles,'What is the operator entry limit for the Studio plan?','12 entries','12 entries',True),
        ('wrong_section',roles,'What is the operator entry limit for the Studio plan?','6 entries','6 entries',False),
    ]:
        page=parse(Response(url='https://example.org/reference',body=body.encode(),content_type='text/html'))
        passage=next(p for p in page.passages if p.kind=='table' and row_text in p.text)
        plan=plan_query(question,page.url)
        candidate=Candidate(answer,answer,page.url,passage.text,passage.label,passage.section,plan.kind,10)
        actual=verify(candidate,plan,[page])
        rows.append({'id':name,'expected':expected,'actual':actual,'passed':actual==expected})
    for name,question,body,answer,expected in [
        ('person_boolean_is_not_fact','Who is the author of Alder?',
         '<h1>Alder</h1><script type="application/ld+json">{"@type":"WebPage","author":false}</script>','false',False),
        ('technical_false_is_fact','What is the default value of the `enable_cache` field?',
         '<script type="application/json">{"settings":{"enable_cache":false}}</script>','false',True),
        ('technical_zero_is_fact','What is the default value of the `retry_count` field?',
         '<script type="application/json">{"settings":{"retry_count":0}}</script>','0',True),
        ('webpage_author_is_fact','Who is the author of Alder?',
         '<script type="application/ld+json">{"@type":"WebPage","name":"Alder","author":"Mira Chen"}</script>','Mira Chen',True),
        ('webpage_title_is_fact','What is the page title?',
         '<script type="application/ld+json">{"@type":"WebPage","name":"Alder"}</script>','Alder',True),
    ]:
        page=parse(Response(url='https://example.org/reference',body=body.encode(),content_type='text/html'))
        plan=plan_query(question,page.url)
        actual=any(c.raw==answer and verify(c,plan,[page]) for c in extract(plan,page))
        rows.append({'id':name,'expected':expected,'actual':actual,'passed':actual==expected})
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old={name:legacy(name) for name in ['parser','planner','candidates']}
    before=diagnose(old['parser'].parse_response,old['planner'].plan_query,old['candidates'].verify,old['candidates'].extract)
    after=diagnose(parser.parse_response,planner.plan_query,candidates.verify,candidates.extract)
    report={'scope':__doc__,'before':before,'after':after,
        'before_passed':sum(r['passed'] for r in before),'after_passed':sum(r['passed'] for r in after),
        'wins':[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
        'losses':[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
        'production_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'agent').glob('*.py')}}
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({key:report[key] for key in ['before_passed','after_passed','wins','losses']}))
    if not all(r['passed'] for r in after):sys.exit(1)
