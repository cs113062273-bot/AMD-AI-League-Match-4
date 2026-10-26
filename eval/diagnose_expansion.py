"""Owned full4B actual-HTTP expansion comparison on identical prompts and weights.

Measures completed anchored discovery hints, not answers or web accuracy. Rebind
the historical/current infer methods on one owned model, only while idle.
"""
import argparse
import asyncio
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from types import MethodType

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.model_client import request_model
from agent.model_server import Runtime,make_server
from agent.navigation import expand_navigation
from agent.planner import plan_query
from agent.search import concise_query
from agent.types import Deadline,Settings
from diagnose_gpu_recovery import memory
from revision_engine import load_engine


async def probe(runtime,base,cases,old_infer):
    settings=Settings(model_url=base);current=Runtime.infer;rows=[]
    # Alternate order to reduce systematic warm-cache/order effects.
    try:
        for i,case in enumerate(cases):
            pair={}
            for stage,method in ([('before',old_infer),('after',current)] if i%2==0 else [('after',current),('before',old_infer)]):
                if memory()['used_mib']>11800:raise RuntimeError('Dedicated VRAM guard')
                if runtime.active is not None:raise RuntimeError('Cannot switch active inference implementation')
                runtime.infer=MethodType(method,runtime)
                plan=plan_query(case['question']);started=time.monotonic()
                hints,state=await expand_navigation(plan,settings,Deadline(6));seconds=time.monotonic()-started
                # A cancellation reply can precede kernel cleanup by a token.
                end=time.monotonic()+2
                while runtime.active is not None and time.monotonic()<end:await asyncio.sleep(.02)
                if runtime.active is not None:raise RuntimeError('Expansion worker did not release')
                query=concise_query(plan,hints)
                pair[stage]={'state':state,'hints':hints,'concise_query':query,
                    'completed':state=='expanded','anchored':bool(query),
                    'completed_with_anchored_hint':state=='expanded' and bool(hints) and query in hints,
                    'seconds':seconds,
                    'request':dict(runtime.requests[-1])}
                print(json.dumps({'id':case['id'],'stage':stage,**pair[stage]},ensure_ascii=True),flush=True)
            rows.append({'id':case['id'],**pair})
        runtime.infer=MethodType(current,runtime)
        reply,state=await request_model(settings,Deadline(6),'/select',{'question':'What is the value of x?',
            'passages':[{'id':0,'text':'x: 7'}],'candidates':[]})
        recovery={'state':state,'reply':reply,'passed':state=='ok' and reply.get('answer')=='7'}
        return rows,recovery
    finally:runtime.infer=MethodType(current,runtime)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    try:
        with socket.create_connection(('127.0.0.1',8765),timeout=.3):raise RuntimeError('Existing model service; refusing another load')
    except (ConnectionRefusedError,TimeoutError):pass
    initial=memory()
    if initial['used_mib']>2000:raise RuntimeError('Insufficient GPU headroom')
    os.environ.update(APERTURE_MODEL=str(ROOT/'models/qwen'),APERTURE_VERIFY_MODEL='0',APERTURE_CONTEXT_TOKENS='1536',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    case_path=ROOT/'benchmarks/expansion-20261023-cases.json';freeze=json.loads((ROOT/'benchmarks/expansion-20261023-freeze.json').read_text(encoding='utf-8'))
    assert freeze['cases_sha256']==hashlib.sha256(case_path.read_bytes()).hexdigest()
    actual={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('app.py'),*Path('agent').glob('*.py')]}
    if actual!=freeze['production_sha256']:raise ValueError('Production changed after freeze')
    cases=json.loads(case_path.read_text(encoding='utf-8'))
    engine,revision,hashes=load_engine(freeze['baseline'])
    old_runtime=importlib.import_module(engine.__module__.rsplit('.',1)[0]+'.model_server').Runtime
    report={'scope':__doc__,'baseline_revision':revision,'baseline_source_sha256':hashes,'cases_sha256':freeze['cases_sha256'],
            'production_sha256':actual,'memory_before':initial,'rows':[]}
    server=None;thread=None
    try:
        print(json.dumps({'stage':'loading_owned_full4b','pid':os.getpid(),'memory':initial}),flush=True)
        runtime=Runtime()
        if memory()['used_mib']>11800:raise RuntimeError('Dedicated VRAM guard after load')
        report['health_before']=runtime.health()
        server=make_server(runtime,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        report['rows'],report['next_request']=asyncio.run(probe(runtime,'http://127.0.0.1:'+str(server.server_port),cases,old_runtime.infer))
        report['health_after']=runtime.health();report['memory_after']=memory()
    except Exception as exc:report['error']=type(exc).__name__+': '+str(exc)
    finally:
        if server:server.shutdown();server.server_close();thread.join(timeout=2)
        report['production_changed_during_run']=actual!={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('app.py'),*Path('agent').glob('*.py')]}
        report['summary']={stage:{'completed':sum(row[stage]['completed'] for row in report['rows']),
            'anchored':sum(row[stage]['anchored'] for row in report['rows']),
            'completed_with_anchored_hint':sum(row[stage]['completed_with_anchored_hint'] for row in report['rows']),
            'total':len(report['rows'])} for stage in ['before','after']}
        target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'summary':report['summary'],'error':report.get('error'),'next_request':report.get('next_request')}),flush=True)
    if report.get('error') or not report.get('next_request',{}).get('passed'):sys.exit(1)
