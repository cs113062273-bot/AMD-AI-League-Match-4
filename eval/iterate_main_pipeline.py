"""Frozen main-pipeline evaluation: development first, then a fresh uniform sample.

No edits between questions; all rows and failed startup/runtime are retained.
Local CUDA and exact adapted scoring do not establish official AMD readiness.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from eval.validate_frozen_version import production,save,digest,health,memory,suite
from eval.diagnose_gpu_recovery import probes


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--folder',required=True)
    ap.add_argument('--context-tokens',type=int,default=5800)
    ap.add_argument('--fresh-out',required=True)
    args=ap.parse_args()
    folder=ROOT/args.folder;folder.mkdir(parents=True,exist_ok=False)
    before=production()
    try:
        with socket.create_connection(('127.0.0.1',8765),timeout=.3):
            raise RuntimeError('Existing service; refusing replacement')
    except (ConnectionRefusedError,TimeoutError):pass
    if memory()['used_mib']>2600:raise RuntimeError('Insufficient GPU headroom')
    exclusions=['benchmarks/'+name+'.json' for name in ['external-simpleqa20','external-simpleqa100',
                'external-transfer100-v2','external-disjoint12-20261023','external-disjoint12b-20261023',
                'fulltest-20261025-independent12']]
    specs=[]
    for name,stem,depth in [('reader','reader-20261023',0),('proof','proof-20261023',2),
                          ('transfer-v2','transfer-20261023-v2',2)]:
        specs.append({'name':name,'cases':'benchmarks/'+stem+'-cases.json','fixtures':'fixtures/'+stem+'.json',
                      'budget':12,'max_depth':depth})
    for name in ['fulltest-20261025-independent12','external-disjoint12-20261023','external-disjoint12b-20261023']:
        specs.append({'name':name+'-DEVELOPMENT','cases':'benchmarks/'+name+'.json','budget':24,'max_depth':2})
    specs.append({'name':'fresh24-FIRST','cases':args.fresh_out,'budget':24,'max_depth':2})
    for name in ['holdout','final-holdout','transfer-frozen']:
        specs.append({'name':name,'cases':'benchmarks/'+name+'.json','fixtures':'fixtures/'+name+'.json',
                      'budget':24,'max_depth':2})
    save(folder/'freeze.json',{'scope':__doc__,'production_sha256':before,'runner_sha256':digest(Path(__file__)),
         'shared_runner_sha256':digest(ROOT/'eval/validate_frozen_version.py'),'specs':specs,
         'context_tokens':args.context_tokens,'browser':False,
         'fresh_sampling':{'n':24,'seed':20261025,'starting_url':'none','excluded_sha256':{p:digest(ROOT/p) for p in exclusions},
           'selection':'Uniform remaining rows, no topic/source/answerability filtering. Backend attested before drawing. Run all rows unchanged.',
           'scoring':'Existing answer aliases, strict joint requires correct answer and every returned source among original expected sources.'},
         'input_sha256':{p:digest(ROOT/p) for spec in specs for p in [spec['cases'],*([spec['fixtures']] if spec.get('fixtures') else [])] if (ROOT/p).exists()}})
    token=uuid.uuid4().hex
    env=dict(os.environ,APERTURE_MODEL=str(ROOT/'models/qwen'),APERTURE_VERIFY_MODEL='0',
             APERTURE_REQUIRE_GPU='1',APERTURE_CONTEXT_TOKENS=str(args.context_tokens),APERTURE_STARTUP_TOKEN=token,
             HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONIOENCODING='utf-8')
    child=None;report={'scope':__doc__,'production_sha256':before,'summaries':[]}
    try:
        with (folder/'model.stdout.log').open('xb') as out,(folder/'model.stderr.log').open('xb') as err:
            child=subprocess.Popen([sys.executable,'-u','-m','agent.model_server'],cwd=ROOT,env=env,
                                    stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        print(json.dumps({'stage':'startup','owned_wrapper_pid':child.pid}),flush=True)
        start=time.monotonic()
        while time.monotonic()-start<180:
            if child.poll() is not None:raise RuntimeError('Resident startup failed')
            try:
                h=health()
                if h.get('startup_token')!=token:raise RuntimeError('Ownership mismatch')
                assert all(before.get('agent/'+name)==value for name,value in h['backend_source_sha256'].items())
                report['health_before']=h;save(folder/'backend-before-sampling.json',h);break
            except (OSError,ValueError):pass
            time.sleep(.5)
        else:raise TimeoutError('Resident startup')
        command=[sys.executable,'scripts/freeze_external_assessment.py','--count','24','--seed','20261025',
                 '--starting-url','none','--out',args.fresh_out]
        for p in exclusions:command+=['--exclude',p]
        subprocess.run(command,cwd=ROOT,env=env,check=True)
        for spec in specs:report['summaries'].append(asyncio.run(suite(spec,folder,before)))
        report['lifecycle']=asyncio.run(probes(health()))
        report['health_after']=health()
    except Exception as exc:
        report['error']=type(exc).__name__+': '+str(exc)
        print(json.dumps({'error':report['error']}),flush=True)
    finally:
        if child is not None and child.poll() is None:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True,timeout=10)
            else:child.terminate()
            child.wait(timeout=10)
        report['production_unchanged']=production()==before
        report['memory_after_shutdown']=memory();save(folder/'summary.json',report)
    print(json.dumps({'finished_suites':len(report['summaries']),'error':report.get('error'),
                      'unchanged':report['production_unchanged']}),flush=True)
    if report.get('error'):sys.exit(1)


if __name__=='__main__':main()
