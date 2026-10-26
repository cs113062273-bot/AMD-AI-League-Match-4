"""CPU-only explicit inline labels and actual selector payload visibility.

No model endpoint, GPU, Chromium or public network is used. The observed
full-name passage still lacks the local birth-year witness required by the
question, so visibility is not counted as a correct verified answer.
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
from agent.network import Response
from agent.parser import parse_response
from agent.planner import plan_query
from agent.selector import payload
from revision_engine import load_engine


def controls(parser):
    rows=[]
    for name,html,label,value in [
        ('span','<p><span>Full Name:</span> Rowan Vale</p>','Full Name','Rowan Vale'),
        ('bold','<p><b>Access Code:</b> R8</p>','Access Code','R8'),
        ('strong','<p><strong>Departure:</strong> 17:35</p>','Departure','17:35'),
        ('formatted-value','<p><span>Full Name:</span> Rowan <em>Vale</em></p>','Full Name','Rowan Vale'),
        ('comment-before','<p><!-- label --><span>Full Name:</span> Rowan Vale</p>','Full Name','Rowan Vale'),
        ('hidden-before','<p><span hidden>Wrong:</span><span>Full Name:</span> Rowan Vale</p>','Full Name','Rowan Vale'),
        ('hidden-value','<p><b>Access Code:</b><span style="display:none">R9</span> R8</p>','Access Code','R8'),
        ('not-leading','<p>Editor says <span>Full Name:</span> Rowan Vale</p>','',''),
        ('not-marked','<p>Full Name: Rowan Vale</p>','',''),
        ('no-colon','<p><span>Full Name</span> Rowan Vale</p>','',''),
        ('inline-formatting','<p>The <b>Full Name</b> is Rowan Vale.</p>','',''),
        ('empty-label','<p><b>:</b> R8</p>','',''),
        ('empty-value','<p><b>Access Code:</b> </p>','',''),
        ('long-value','<p><b>Description:</b> '+'x'*351+'</p>','',''),
        ('long-label','<p><b>This sentence has more than six label words:</b> R8</p>','',''),
        ('multiple-fields','<p><b>Name:</b> Rowan <b>Age:</b> 44</p>','',''),
        ('line-break','<p><b>Name:</b> Rowan<br>Age: 44</p>','',''),
        ('div-not-paragraph','<div><span>Full Name:</span> Rowan Vale</div>','',''),
    ]:
        page=parser(Response('https://example.org/profile',html.encode(),'text/html',status=200))
        fields=[p for p in page.passages if p.locator.startswith('inline[')]
        actual=[(p.label,p.value) for p in fields]
        expected=[(label,value)] if label else []
        passed=not page.error and actual==expected
        if label:
            passed=passed and len(fields)==1 and fields[0].value in fields[0].text
            passed=passed and any(p.text==fields[0].text and p.kind=='prose' for p in page.passages)
        rows.append(dict(id=name,passed=passed,actual=actual,expected=expected))
    return rows


def recorded(engine):
    source=ROOT/'research/external-disjoint12b-20261023-repeat/simpleqa-3120.json'
    report=json.loads((ROOT/'benchmarks/external-disjoint12b-20261023-repeat.json').read_text(encoding='utf-8'))
    record=next(r for r in report['rows'] if r['id']=='simpleqa-3120')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==record['capture_sha256']
    responses=json.loads(source.read_text(encoding='utf-8'));pages=[]
    module=importlib.import_module(engine.__module__);parser=module.parse_response
    cases=json.loads((ROOT/'benchmarks/external-disjoint12b-20261023.json').read_text(encoding='utf-8'))
    case=next(c for c in cases if c['id']=='simpleqa-3120')
    plan=plan_query(case['query'],case['url'])
    selected=[
        'https://www.soccerstats247.com/players/juan-pablo-guzman-perdomo-134947/',
        'https://en.soccerwiki.org/player.php?pid=85733',
        'https://www.footballdatabase.eu/en/player/details/204458-juan-guzman',
    ]
    for url in selected:
        data=dict(responses[url]);data['body']=base64.b64decode(data.pop('body_base64'))
        pages.append(parser(Response(**data)))
    candidates=module.rank([c for p in pages for c in module.extract(plan,p)],plan)
    ranked=module.rank_passages(plan,pages,candidates)
    data=payload(plan,candidates,ranked)
    # Track the original standalone inline paragraph separately from newer
    # source groups that contain their own explicit birth-date witness.
    full=next(p for page in pages for p in page.passages if p.text.startswith('Full Name:')
              and not p.locator.startswith('fieldgroup['))
    visible=[p for p in data['passages'] if p['text']==full.text]
    score_position=next(i+1 for i,(page,p,score) in enumerate(ranked) if p.text==full.text)
    literal_candidates=[c for c in candidates if c.label=='Full Name' and c.evidence==full.text]
    # Recovery of a field must not bypass the existing temporal evidence guard.
    unverified=not any(module.verify(c,plan,pages) for c in literal_candidates)
    return dict(id='actual-profile-payload',passed=bool(visible) and unverified,
                complete_field_in_first_eight=bool(visible),position=score_position,
                local_temporal_witness_still_required=unverified,passages=data['passages'],
                source_capture_sha256=record['capture_sha256'])


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('5a59ae9')
    parser=importlib.import_module(old.__module__.rsplit('.',1)[0]+'.parser').parse_response
    before=controls(parser)+[recorded(old)];after=controls(parse_response)+[recorded(Engine)]
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,before=before,after=after,
                before_passed=sum(r['passed'] for r in before),after_passed=sum(r['passed'] for r in after),total=len(after),
                wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
                losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
                production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('agent').glob('*.py')})
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    print(json.dumps({'before_position':before[-1]['position'],'after_position':after[-1]['position']}))
    if not all(r['passed'] for r in after):sys.exit(1)
