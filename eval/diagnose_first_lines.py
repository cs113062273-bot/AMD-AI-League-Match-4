"""Source-line boundaries using authored text and the old preview's eligibility.

No copyrighted passage is printed. Controls measure parser/guard behavior, not
model or public-web accuracy.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.engine import Engine
from agent.network import Response
from agent.types import Candidate
from revision_engine import load_engine

FIRST='Quiet lamps mark the river.'
SECOND='The harbor waits for morning.'
QUERY='What is the first line of the poem River Notes?'


def diagnose(engine):
    g=engine.run.__globals__;parse=g['parse_response'];planner=g['plan_query'];verify=g['verify']
    rows=[]
    sources=[
        ('br','<title>River Notes poem</title><div>'+FIRST+'<br>'+SECOND+'</div>','text/html',FIRST),
        ('inline','<title>River Notes poem</title><p>Quiet <b>lamps</b> mark the river.<br>'+SECOND+'</p>','text/html',FIRST),
        ('pre','<title>River Notes poem</title><pre>'+FIRST+'\n'+SECOND+'</pre>','text/html',FIRST),
        ('plain',FIRST+'\n'+SECOND,'text/plain',FIRST),
        ('preview-only','<title>River Notes poem</title><meta name="description" content="'+FIRST+' '+SECOND+'">','text/html',None),
        ('fake-line','<title>River Notes poem</title><div data-source-line="1">'+FIRST+' '+SECOND+'</div>','text/html',None),
        ('hidden','<title>River Notes poem</title><div><span hidden>Wrong hidden text.</span>'+FIRST+'<br>'+SECOND+'</div>','text/html',FIRST),
        ('long','<title>River Notes poem</title><div>'+('Longword '*50)+'<br>'+SECOND+'</div>','text/html',None),
        ('leading-empty-pre','<title>River Notes poem</title><pre>\n'+FIRST+'\n'+SECOND+'</pre>','text/html',None),
        ('leading-empty-plain','\n'+FIRST+'\n'+SECOND,'text/plain',None),
    ]
    for name,body,ct,expected in sources:
        page=parse(Response('https://example.org/'+name,body.encode(),ct));plan=planner(QUERY,page.url)
        eligible=g['rank_passages'](plan,[page],[])
        lines=[p.text for _,p,_ in eligible if p.qualifiers.get('source_line')==1 and p.qualifiers.get('complete_line')]
        passed=(expected in lines) if expected else not eligible
        rows.append(dict(id=name+'-structure',passed=passed,source_lines=lines))
        if expected:
            passage=next((p for p in page.passages if p.qualifiers.get('source_line')==1 and p.qualifiers.get('complete_line')),None)
            # Historical parsers had no line qualifier. Still exercise their
            # actual verifier on the ordinary source block, rather than count
            # missing new metadata as failure of literal answer acceptance.
            if passage is None:passage=next((p for p in page.passages if expected in p.text),None)
            if passage:
                base=dict(source=page.url,evidence=passage.text,label=passage.label,section=passage.section,kind=plan.kind,
                    signals={'locator':passage.locator})
                full=Candidate(expected,expected,**base);partial=Candidate('Quiet lamps','Quiet lamps',**base)
                rows.append(dict(id=name+'-full',passed=verify(full,plan,[page])))
                rows.append(dict(id=name+'-partial-refused',passed=not verify(partial,plan,[page])))
            else:
                rows.extend([dict(id=name+'-full',passed=False),dict(id=name+'-partial-refused',passed=False)])
    # A normal description request still uses its literal metadata value.
    page=parse(Response('https://example.org/description',('<meta name="description" content="'+FIRST+'">').encode(),'text/html'))
    plan=planner('What is the description of River Notes?',page.url);p=next(p for p in page.passages if p.label=='description')
    rows.append(dict(id='ordinary-description-retained',passed=verify(Candidate(FIRST,FIRST,page.url,p.text,p.label,kind=plan.kind),plan,[page])))
    report=json.loads((ROOT/'benchmarks/external-disjoint12-20261023-first.json').read_text(encoding='utf-8'))
    row=next(r for r in report['rows'] if r['id']=='simpleqa-1507');source=ROOT/row['capture_path']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==row['capture_sha256']
    selection=Candidate(**row['result']['diagnostics']['model_selections'][0]);data=dict(json.loads(source.read_text(encoding='utf-8'))[selection.source])
    data['body']=base64.b64decode(data.pop('body_base64'));page=parse(Response(**data))
    plan=planner(row['result']['diagnostics']['plan']['question'],page.url)
    actual=verify(selection,plan,[page])
    rows.append(dict(id='actual-merged-preview-refused',passed=not actual,preview_accepted=actual,capture_sha256=row['capture_sha256']))
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('a701685');before=diagnose(old);after=diagnose(Engine)
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,before=before,after=after,
        before_passed=sum(r['passed'] for r in before),after_passed=sum(r['passed'] for r in after),total=len(after),
        wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
        losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
        production_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'agent').glob('*.py')})
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    if not all(r['passed'] for r in after):sys.exit(1)
