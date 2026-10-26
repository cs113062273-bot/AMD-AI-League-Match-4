"""Proof transfer and column-permutation checks without model inference.

This assesses operation construction/validation, not semantic reader accuracy.
The ten v2 cases retain the original logical inputs and repair a transport-
corrupted time-range dash; original pilot files/results remain unchanged.
"""
from itertools import permutations
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent.network import Response
from agent.parser import parse_response
from agent.planner import plan_query
from agent.proofs import propose,validate
from agent.evidence import table_supported
from eval.revision_engine import load_engine


def page(url,html):return parse_response(Response(url=url,content_type='text/html',body=html.encode('utf-8')))


def render(headers,rows):
    return '<table><tr>'+''.join('<th>'+v+'</th>' for v in headers)+'</tr>'+''.join(
        '<tr>'+''.join('<td>'+v+'</td>' for v in row)+'</tr>' for row in rows)+'</table>'


def transfer(propose_fn,plan_fn):
    cases=json.loads((ROOT/'benchmarks/transfer-20261023-v2-cases.json').read_text(encoding='utf-8'))
    routes=json.loads((ROOT/'fixtures/transfer-20261023-v2.json').read_text(encoding='utf-8'))
    rows=[]
    for case in cases:
        prefix=case['path'].rsplit('/',1)[0]+'/'
        pages=[page('https://example.org'+path,r[2]) for path,r in routes.items() if path.startswith(prefix)]
        plan=plan_fn(case['query'],'https://example.org'+case['path'])
        proof,required=propose_fn(plan,pages)
        if case['id']=='single-control':passed=proof is None and not required
        elif case['answer']:
            passed=proof is not None and proof.answer in case['answers'] and set(proof.sources)=={
                'https://example.org'+path for path in case['source_paths']}
        else:passed=proof is None and required
        rows.append({'id':case['id'],'passed':passed,'answer':proof.answer if proof else None,'required':required})
    return rows


def metamorphic():
    rows=[];dash=chr(0x2013)
    data=[['Glass','Every Friday','08:00'+dash+'09:00'],['Batteries','Every Wednesday','11:30'+dash+'14:00']]
    for order in permutations(range(3)):
        labels=['Material','Day','Hours']
        html='<title>Moss Bay collection</title>'+render([labels[i] for i in order],[[row[i] for i in order] for row in data])
        p=page('https://example.org/collection',html)
        plan=plan_query('What day and time does Moss Bay collect batteries?',p.url)
        proof,required=propose(plan,[p])
        rows.append({'id':'column_order_'+''.join(map(str,order)),
            'passed':bool(proof and validate(proof,plan,[p]) and proof.answer=='Every Wednesday, 11:30'+dash+'14:00')})
        single=plan_query('On what day does Moss Bay collect batteries?',p.url)
        bad=next(row for row in p.passages if row.kind=='table' and 'Glass' in row.text)
        rows.append({'id':'single_wrong_row_'+''.join(map(str,order)),
            'passed':not table_supported(single,p,bad,'Every Friday')})
    for order in permutations(range(2)):
        labels=['Version','Worker quota'];values=[['1','24 jobs'],['2','48 jobs']]
        p=page('https://example.org/quotas','<title>BriarQueue worker quotas</title>'+render(
            [labels[i] for i in order],[[r[i] for i in order] for r in values]))
        plan=plan_query('How did the BriarQueue worker quota change from version 1 to version 2?',p.url)
        proof,required=propose(plan,[p])
        rows.append({'id':'version_order_'+''.join(map(str,order)),
            'passed':bool(proof and proof.answer=='from 24 to 48 jobs')})
    p=page('https://example.org/catalog','<title>Cedar Shop</title>'+render(['Name','Category','Price'],
        [['Cedar Mug','Ceramics','$21'],['Cedar Bowl','Ceramics','$29']]))
    proof,required=propose(plan_query('What is the price of Cedar Mug?',p.url),[p])
    rows.append({'id':'direct_record_needs_no_category_join','passed':proof is None and not required})
    p=page('https://example.org/calendar','<title>Moss Bay collection</title>'+render(['Material','Day','Hours'],
        [['Batteries','Every Wednesday','11:30?14:00']]))
    proof,required=propose(plan_query('What day and time does Moss Bay collect batteries?',p.url),[p])
    rows.append({'id':'corrupted_clock_is_not_valid','passed':proof is None and required})
    return rows


if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('838b7ad')
    before=transfer(old.run.__globals__['propose_proof'],old.run.__globals__['plan_query'])
    after=transfer(propose,plan_query);extra=metamorphic()
    report={'scope':__doc__,'baseline_revision':revision,'before':before,'after':after,
        'metamorphic':extra,'before_passed':sum(r['passed'] for r in before),'after_passed':sum(r['passed'] for r in after),
        'metamorphic_passed':sum(r['passed'] for r in extra),'metamorphic_total':len(extra)}
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','metamorphic_passed','metamorphic_total']}))
    if not all(r['passed'] for r in after+extra):sys.exit(1)
