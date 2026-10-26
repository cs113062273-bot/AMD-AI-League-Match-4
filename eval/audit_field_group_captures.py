"""CPU-only paired parser audit over existing, hash-verified public captures.

No network, models or browsers. Checks original passages are preserved while
adding bounded field groups, not answer accuracy or semantic identity.
"""
import argparse
import base64
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.engine import Engine
from agent.network import Response
from agent.urls import discovery_url
from revision_engine import load_engine


def audit():
    old,revision,hashes=load_engine('26ad9fb')
    parsers=[old.run.__globals__['parse_response'],Engine.run.__globals__['parse_response']]
    inputs=[];seen=set();rows=[]
    for filename in ['benchmarks/external-disjoint12b-20261023-first.json',
                     'benchmarks/external-disjoint12b-20261023-repeat.json']:
        report=json.loads((ROOT/filename).read_text(encoding='utf-8'))
        for record in report['rows']:
            path=ROOT/record['capture_path'];digest=hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest==record['capture_sha256'] and not record['capture_omitted']
            inputs.append(dict(case_id=record['id'],report=filename,capture_path=record['capture_path'],sha256=digest))
            for url,raw in json.loads(path.read_text(encoding='utf-8')).items():
                if raw['error'] or 'html' not in raw['content_type'].lower() or discovery_url(url):continue
                data=dict(raw);data['body']=base64.b64decode(data.pop('body_base64'))
                body_sha=hashlib.sha256(data['body']).hexdigest();key=(url,body_sha)
                if key in seen:continue
                seen.add(key);before,after=[parser(Response(**data)) for parser in parsers]
                groups={}
                for p in after.passages:
                    if p.locator.startswith('fieldgroup['):
                        groups.setdefault(p.locator.split('/')[0],dict(text=p.text,bindings=p.qualifiers['bindings'],identity=p.qualifiers['identity']))
                original=[asdict(p) for p in before.passages]
                remaining=[asdict(p) for p in after.passages if not p.locator.startswith('fieldgroup[')]
                passed=original==remaining and before.error==after.error and before.links==after.links and before.truncated==after.truncated
                passed=passed and all(len(p['text'])<=1000 and len(p['identity'])==1 for p in groups.values())
                rows.append(dict(case_id=record['id'],url=url,body_sha256=body_sha,bytes=len(data['body']),passed=passed,
                                 original_passages=len(original),added_fields=len(after.passages)-len(remaining),groups=list(groups.values())))
    return dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,inputs=inputs,rows=rows,
                total=len(rows),passed=sum(r['passed'] for r in rows),
                pages_with_groups=sum(bool(r['groups']) for r in rows),groups=sum(len(r['groups']) for r in rows),
                production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('agent').glob('*.py')})


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    report=audit();target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['passed','total','pages_with_groups','groups']}))
    print(json.dumps({'failures':[r['url'] for r in report['rows'] if not r['passed']]}))
    if report['passed']!=report['total']:sys.exit(1)
