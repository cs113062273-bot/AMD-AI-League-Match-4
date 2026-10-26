"""Projection must prefer exact fields without accepting forged or duplicate columns."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.parser import parse_response
from agent.network import Response
from agent.planner import plan_query
from agent.proofs import Atom,Proof,propose,validate
from revision_engine import load_engine


def diagnose(proposer,validator,planner):
    def table(headers,values):
        return '<title>Northline directory and timetable</title><table><tr>'+''.join('<th>'+v+'</th>' for v in headers)+'</tr><tr>'+''.join('<td>'+v+'</td>' for v in values)+'</tr></table>'
    cases=[
        ('exact-name',['Name','First name','Email'],['Orin Vale','Orin','orin@example.org'],'What are the first name and email of Orin Vale?','Orin, orin@example.org'),
        ('exact-clock',['Name','Time','Departure time','Platform'],['Northline','09:00','09:15','4'],'What are the departure time and platform for Northline?','09:15, 4'),
        ('duplicate-exact',['Name','First name','First name','Email'],['Orin Vale','Orin','Mira','orin@example.org'],'What are the first name and email of Orin Vale?',None),
        ('duplicate-fallback',['Name','Given name','Display name','Email'],['Orin Vale','Orin','O. Vale','orin@example.org'],'What are the first name and email of Orin Vale?',None),
        ('unknown-field',['Name','Email'],['Orin Vale','orin@example.org'],'What are the phone and email of Orin Vale?',None),
        ('same-column',['Name','Time'],['Northline','09:15'],'What are the time and departure time for Northline?',None),
    ]
    rows=[]
    for name,headers,values,query,expected in cases:
        url='https://example.org/'+name
        page=parse_response(Response(url,table(headers,values).encode(),'text/html'))
        plan=planner(query,url);proof,required=proposer(plan,[page])
        actual=proof.answer if proof else None
        passed=actual==expected and required and (not proof or validator(proof,plan,[page]))
        rows.append(dict(id=name,passed=passed,expected=expected,actual=actual))
        if name in {'exact-name','exact-clock'}:
            raw=next(p for p in page.passages if p.kind=='table')
            wrong=values[0 if name=='exact-name' else 1]
            other=values[2 if name=='exact-name' else 3]
            forged=Proof('compose_fields',tuple(Atom(url,raw.locator,raw.text,value,role)
                for value,role in zip([wrong,other],plan.required_fields)))
            rows.append(dict(id=name+'-wrong-overlap',passed=not validator(forged,plan,[page])))
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('eed167d');g=old.run.__globals__
    before=diagnose(g['propose_proof'],g['validate_proof'],g['plan_query'])
    after=diagnose(propose,validate,plan_query)
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,before=before,after=after,
        before_passed=sum(r['passed'] for r in before),after_passed=sum(r['passed'] for r in after),total=len(after),
        wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
        losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
        proof_sha256=hashlib.sha256((ROOT/'agent/proofs.py').read_bytes()).hexdigest())
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    if not all(r['passed'] for r in after):sys.exit(1)
