"""Paired owned-full4B diagnosis on frozen Oyez responses and authored member controls.

Actual source replay, not live discovery, unseen accuracy or official scoring.
Both engines share the current backend; member prompting is request-specific.
"""
import argparse
import asyncio
import base64
import gc
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from dataclasses import replace

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.engine import Engine
from agent.model_server import Runtime,make_server
from agent.types import Settings
from benchmarks.fakeweb import FakeWeb
from diagnose_gpu_recovery import memory
from diagnose_oyez import API,FRONT,captured,replay_transport
from revision_engine import load_engine


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze():
    response,capture_sha=captured();data=json.loads(response.text)
    front_path=ROOT/'research/browser-budget-20261023/responses.json'
    front=json.loads(front_path.read_text(encoding='utf-8'))[FRONT]
    front_body=base64.b64decode(front['body_base64']).decode('utf-8')
    wrong=json.dumps({**data,'docket_number':'38'})
    question='What two football teams were mentioned in the libel case against "The Saturday Evening Post" in 1963?'
    cases=[
        dict(id='real-case-teams',query=question,url=FRONT,answer='University of Georgia and University of Alabama',source=API,mode='case'),
        dict(id='real-api-teams',query=question,url=API,answer='University of Georgia and University of Alabama',source=API,mode='case'),
        dict(id='real-case-informant',query='Who was the source of the article in Curtis Publishing v. Butts?',url=FRONT,answer='George Burnett',source=API,mode='case'),
        dict(id='wrong-case-identity',query=question,url=API,answer='',source='',mode='wrong'),
        dict(id='teams-with-coaches',query='Which two football teams played in the Cedar Cup?',answer='Maple United and Cedar FC',mode='plain',
             text='The Cedar Cup featured Maple United, coached by Mira Chen, against Cedar FC, coached by Orin Vale.'),
        dict(id='one-team-only',query='Which two football teams played in the Cedar Cup?',answer='',mode='plain',
             text='Maple United played in the Cedar Cup. Its coach was Mira Chen.'),
        dict(id='different-award-years',query='Which two authors won the Cedar Prize in 1998?',answer='',mode='plain',
             text='Mira Chen won the Cedar Prize in 1998. Orin Vale won the Cedar Prize in 2001.'),
        dict(id='same-award-year',query='Which two authors won the Cedar Prize in 1998?',answer='Mira Chen and Orin Vale',mode='plain',
             text='Mira Chen won the Cedar Prize in 1998. Orin Vale won the Cedar Prize in 1998.'),
        dict(id='scalar-retained',query='What is the access code of the Cedar Library?',answer='R8',mode='plain',text='The access code of the Cedar Library is R8.'),
        dict(id='three-countries',query='Which three countries joined the Birch Accord?',answer='Canada, Japan and Chile',mode='plain',
             text='Canada signed the Birch Accord on Monday. Japan signed it on Tuesday. Chile joined the accord on Wednesday.'),
        dict(id='aliases-are-one',query='Which two football teams played in the Cedar Cup?',answer='',mode='plain',
             text='Maple United, also known as MUFC, played in the Cedar Cup. No other participating team is identified.'),
        dict(id='contiguous-pair',query='Which two football teams played in the Cedar Cup?',answer='Maple United and Cedar FC',mode='plain',
             text='Maple United and Cedar FC played in the Cedar Cup.')]
    fixture=dict(front=front_body,api=response.text,wrong=wrong)
    target=ROOT/'research/case-members-20261023';target.mkdir(parents=True,exist_ok=True)
    fixtures=target/'fixtures.json';case_path=ROOT/'benchmarks/case-members-20261023-cases.json';manifest=ROOT/'benchmarks/case-members-20261023-freeze.json'
    for path in [fixtures,case_path,manifest]:
        if path.exists():raise FileExistsError(path)
    fixtures.write_text(json.dumps(fixture,ensure_ascii=True,indent=2),encoding='utf-8')
    case_path.write_text(json.dumps(cases,ensure_ascii=True,indent=2),encoding='utf-8')
    manifest.write_text(json.dumps(dict(scope=__doc__,baseline='4141065',cases_sha256=sha(case_path),fixtures_sha256=sha(fixtures),
        original_api_capture_sha256=capture_sha,original_front_capture_sha256=sha(front_path),
        production_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'agent').glob('*.py')}),indent=2),encoding='utf-8')
    print(json.dumps({'frozen_cases':len(cases),'case_sha256':sha(case_path),'fixture_sha256':sha(fixtures)}))


async def paired(cases,fixtures,base_model,runtime,engines):
    rows=[]
    for index,case in enumerate(cases):
        html='<title>Cedar facts</title><p>'+case.get('text','')+'</p>'
        routes={'/front':(200,'text/html',fixtures['front']),'/api':(200,'application/json',fixtures['wrong'] if case['mode']=='wrong' else fixtures['api']),
                '/landing':(200,'text/html',html)}
        with FakeWeb(routes) as server,replay_transport(list(engines.values()),server.base):
            url=case.get('url','https://example.org/'+case['id']);expected_source=case.get('source',url)
            pair={}
            stages=['before','after'] if index%2==0 else ['after','before']
            for stage in stages:
                if memory()['used_mib']>11800:raise RuntimeError('Dedicated VRAM guard')
                settings=Settings(model_url=base_model,search=False,allow_private=True,max_depth=0,budget=12)
                started=time.monotonic();result=await engines[stage](settings).run(case['query'],url)
                pair[stage]=dict(result=result.internal(),seconds=time.monotonic()-started,
                    passed=result.answer==case['answer'] and result.sources==([expected_source] if case['answer'] else []))
                print(json.dumps(dict(id=case['id'],stage=stage,answer=result.answer,passed=pair[stage]['passed'],reason=result.reason)),flush=True)
                end=time.monotonic()+2
                while runtime.active is not None and time.monotonic()<end:await asyncio.sleep(.02)
                if runtime.active is not None:raise RuntimeError('Inference did not release')
            rows.append(dict(id=case['id'],**pair))
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--freeze',action='store_true');ap.add_argument('--out')
    ap.add_argument('--manifest',default='benchmarks/case-members-20261023-freeze.json');args=ap.parse_args()
    if args.freeze:freeze();sys.exit(0)
    if not args.out:ap.error('--out is required for model run')
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    manifest_path=ROOT/args.manifest;manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    case_path=ROOT/'benchmarks/case-members-20261023-cases.json';fixture_path=ROOT/'research/case-members-20261023/fixtures.json'
    assert sha(case_path)==manifest['cases_sha256'] and sha(fixture_path)==manifest['fixtures_sha256']
    actual={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'agent').glob('*.py')}
    assert actual==manifest['production_sha256'],'Production changed after freeze'
    try:
        with socket.create_connection(('127.0.0.1',8765),timeout=.3):raise RuntimeError('Existing service; refusing another load')
    except (ConnectionRefusedError,TimeoutError):pass
    initial=memory()
    if initial['used_mib']>2000:raise RuntimeError('Insufficient GPU headroom')
    os.environ.update(APERTURE_MODEL=str(ROOT/'models/qwen'),APERTURE_VERIFY_MODEL='0',APERTURE_CONTEXT_TOKENS='1536',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    old,revision,hashes=load_engine(manifest['baseline']);report=dict(scope=__doc__,baseline=revision,baseline_source_sha256=hashes,
        freeze_sha256=sha(manifest_path),production_sha256=actual,memory_before=initial,rows=[])
    server=None;thread=None;runtime=None
    try:
        print(json.dumps({'stage':'loading_owned_full4b','pid':os.getpid(),'memory':initial}),flush=True)
        runtime=Runtime();report['health_before']=runtime.health()
        if memory()['used_mib']>11800:raise RuntimeError('Dedicated VRAM guard after load')
        server=make_server(runtime,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        report['rows']=asyncio.run(paired(json.loads(case_path.read_text(encoding='utf-8')),json.loads(fixture_path.read_text(encoding='utf-8')),
            'http://127.0.0.1:'+str(server.server_port),runtime,{'before':old,'after':Engine}))
        report['health_after']=runtime.health();report['memory_after_run']=memory()
    except Exception as exc:report['error']=type(exc).__name__+': '+str(exc)
    finally:
        if server:server.shutdown();server.server_close();thread.join(timeout=2)
        report['production_changed_during_run']=actual!={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'agent').glob('*.py')}
        report['comparison']=dict(before_passed=sum(r['before']['passed'] for r in report['rows']),after_passed=sum(r['after']['passed'] for r in report['rows']),
            total=len(report['rows']),wins=[r['id'] for r in report['rows'] if r['after']['passed'] and not r['before']['passed']],
            losses=[r['id'] for r in report['rows'] if r['before']['passed'] and not r['after']['passed']])
        target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'comparison':report['comparison'],'error':report.get('error')}),flush=True)
    if report.get('error') or report['comparison']['losses']:sys.exit(1)
