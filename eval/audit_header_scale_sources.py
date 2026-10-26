"""Inspect HTML table headers in 24 already exposed, hash-verified captures.

No question/gold lookup, external request or model; this is source coverage,
not an accuracy assessment.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.network import Response
from agent.parser import parse_response
from agent.table_scales import header
from agent.urls import discovery_url


def audit():
    seen=set();files=[];hits=[];parsed=0;tables=0
    for name in ['external-disjoint12-20261023','external-disjoint12b-20261023']:
        manifest=ROOT/'benchmarks'/ (name+'-first.json')
        for record in json.loads(manifest.read_text(encoding='utf-8'))['rows']:
            path=ROOT/record['capture_path'];raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
            if digest!=record['capture_sha256'] or record['capture_omitted']:raise ValueError('Original capture changed')
            files.append({'path':str(path.relative_to(ROOT)),'sha256':digest})
            for envelope in json.loads(raw).values():
                if discovery_url(envelope['url']):continue
                body=base64.b64decode(envelope['body_base64'],validate=True);body_sha=hashlib.sha256(body).hexdigest()
                if not body or body_sha in seen:continue
                seen.add(body_sha)
                if 'html' not in envelope['content_type'].lower() and not re.search(rb'<table\b',body,re.I):continue
                response=dict(envelope);response.pop('body_base64');response['body']=body
                page=parse_response(Response(**response));parsed+=1
                for p in page.passages:
                    if p.kind!='table':continue
                    tables+=1
                    for i,label in enumerate(p.qualifiers.get('columns',[])):
                        if not re.search(r'\b(?:thousand|million|billion|trillion)s?\b',label,re.I):continue
                        hits.append({'capture':str(path.relative_to(ROOT)),'url':page.url,'body_sha256':body_sha,
                                     'locator':p.locator,'column':i,'header':label,'recognized_scale':header(label),
                                     'source_text':p.text})
    return {'scope':__doc__,'captures':files,'unique_nonempty_content_bodies':len(seen),'html_bodies_parsed':parsed,
            'table_rows':tables,'scale_header_rows':len(hits),'rows':hits,'torch_imported':'torch' in sys.modules}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    report=audit();report['diagnostic_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['unique_nonempty_content_bodies','html_bodies_parsed','table_rows','scale_header_rows','torch_imported']}))
