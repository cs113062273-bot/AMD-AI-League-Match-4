"""Run the public Pinpoint 15-question set with its published answer-only scoring.

Question/scorer provenance: ctmakc/pinpoint-web-agent, MIT,
commit 1a722b91221369d98156c9fcd33fab4f9d088824. This is a visible development
comparison on different hardware/network, not a head-to-head official AMD result.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unicodedata
import hashlib
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.output import atomic_json


def squash(text):
    return re.sub(r'[\s\-.·_,]','',unicodedata.normalize('NFKC',text)).upper()


def published_ok(answer,expected):
    if expected==['']:return answer==''
    actual=squash(answer)
    return bool(actual) and any(squash(e) in actual or actual in squash(e) and len(actual)>=len(squash(e))-1 for e in expected if e)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',default='benchmarks/public-pinpoint-comparison');ap.add_argument('--rules',action='store_true');args=ap.parse_args()
    path=Path('benchmarks/published-pinpoint.jsonl')
    production=[Path('app.py'),*Path('agent').glob('*.py')]
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in production}
    try:
        with urllib.request.urlopen('http://127.0.0.1:8765/health',timeout=2) as response:backend=json.load(response)
    except (OSError,ValueError):backend=None
    cases=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    rows=[];env=os.environ.copy();env.update(APERTURE_BUDGET='24',APERTURE_PROFILE='minimal',PYTHONIOENCODING='utf-8')
    if args.rules:env['APERTURE_MODEL_URL']=''
    directory=Path('output/public-reference-'+('rule' if args.rules else 'model'))
    for case in cases:
        command=[sys.executable,'app.py','--query-id',case['id'],'--query',case['query'],'--output-dir',str(directory),'--diagnostics']
        if case.get('url'):command+=['--url',case['url']]
        began=time.monotonic();error=''
        try:
            p=subprocess.run(command,capture_output=True,timeout=28,env=env)
            if p.returncode:raise RuntimeError('Adapter exit '+str(p.returncode))
            result=json.loads((directory/(case['id']+'_output.json')).read_text(encoding='utf-8'))
            if not isinstance(result,dict) or set(result)!={'answer','sources'} or not isinstance(result['answer'],str) or not isinstance(result['sources'],list):
                raise ValueError('Malformed evaluator result')
        except (OSError,ValueError,subprocess.SubprocessError,RuntimeError) as exc:
            result={'answer':'','sources':[]};error=type(exc).__name__+': '+str(exc)
        good=not error and published_ok(result['answer'],case['expect'])
        flags=[]
        if '@' in result['answer'] and not any('@' in e for e in case['expect']):flags.append('email_returned_for_non_email_expectation')
        try:trace=json.loads((directory/(case['id']+'_output.trace.json')).read_text(encoding='utf-8'))
        except (OSError,ValueError):trace={}
        rows.append({**case,**result,'published_answer_pass':good,'error':error,'wall_seconds':time.monotonic()-began,'review_flags':flags,'trace':trace})
        print(case['id'],'PASS' if good else 'FAIL',repr(result['answer']),flush=True)
    data={'method':'Published answer substring scorer; does NOT score source correctness. Fresh CLI per query.',
        'comparison_limit':'Different GPU/network from the competitor self-reported 11/15; visible development questions, not untuned holdout.',
        'reference':'https://github.com/ctmakc/pinpoint-web-agent/tree/1a722b91221369d98156c9fcd33fab4f9d088824',
        'passed':sum(r['published_answer_pass'] for r in rows),'total':len(rows),'rows':rows}
    after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in production}
    data['run']={'production_before_sha256':before,'production_after_sha256':after,
        'production_changed_during_run':before!=after,'backend_before':backend,
        'cases_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    atomic_json(args.out+'.json',data);print(data['passed'],'/',data['total'],flush=True)


if __name__=='__main__':main()
