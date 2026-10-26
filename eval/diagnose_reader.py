"""Small fixed-page or actual-public-web diagnosis with an owned full-4B CUDA service.

Cases are exposed development data, not a held-out or public-web accuracy claim.
An oracle URL supplies the answer page; this separates reading from discovery.
"""
import argparse
import asyncio
import base64
from contextlib import nullcontext
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.engine import Engine
from agent.network import Fetcher
from agent.types import Settings
from benchmarks.fakeweb import FakeWeb
from eval.diagnose_gpu_recovery import memory
from eval.model_readiness import wait_model_idle,ModelNotReady


async def run(cases, settings, base,engine=None,stage='current',live_web=False,capture_dir=None,rows=None,readiness_timeout=3.0):
    rows = [] if rows is None else rows
    for case in cases:
        if memory()['used_mib']>11800:raise RuntimeError('Dedicated memory guard during diagnosis')
        readiness=await wait_model_idle(settings.model_url,readiness_timeout) if settings.model_url else None
        if readiness and not readiness['ready']:raise ModelNotReady(case['id'],readiness)
        responses={};capture_bytes=0;omitted=[]
        original_fetch=Fetcher.fetch
        async def capture(fetcher,url,**kwargs):
            nonlocal capture_bytes
            response=await original_fetch(fetcher,url,**kwargs)
            if url not in responses:
                if capture_bytes+len(response.body)<=20_000_000 and len(responses)<64:
                    data=asdict(response);data['body_base64']=base64.b64encode(data.pop('body')).decode('ascii')
                    responses[url]=data;capture_bytes+=len(response.body)
                else:omitted.append(url)
            return response
        with patch.object(Fetcher,'fetch',capture) if capture_dir else nullcontext():
            result = await (engine or Engine)(settings).run(case['query'],case.get('url','') if live_web else base + case['path'])
        answer_ok = result.answer in case['answers']
        expected_sources=case.get('sources',[]) if live_web else [base+path for path in case.get('source_paths',[case.get('source_path','')])]
        source_ok = (bool(result.sources) and all(source in expected_sources for source in result.sources) if live_web else set(result.sources)==set(expected_sources)) if case['answer'] else not result.sources
        rows.append({'id': case['id'], 'answer_ok': answer_ok, 'source_ok': source_ok,
                     'joint_ok': answer_ok and source_ok, 'result': result.internal(),
                     **({'model_readiness':readiness} if readiness else {})})
        if capture_dir:
            snapshot=capture_dir/(case['id']+'.json')
            if snapshot.exists():raise FileExistsError(snapshot)
            snapshot.write_text(json.dumps(responses,ensure_ascii=True,indent=2),encoding='utf-8')
            rows[-1].update(capture_path=str(snapshot.relative_to(ROOT)),capture_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),capture_omitted=omitted)
        print(json.dumps({'stage':stage,'id': case['id'], 'answer': result.answer,
                          'passed': answer_ok and source_ok, 'reason': result.reason}), flush=True)
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--cases', default='benchmarks/reader-20261023-cases.json')
    parser.add_argument('--fixtures', default='fixtures/reader-20261023.json')
    parser.add_argument('--max-depth',type=int,default=0)
    parser.add_argument('--budget',type=float,default=12)
    revisions=parser.add_mutually_exclusive_group()
    revisions.add_argument('--baseline',help='Isolated historical agent package at this revision')
    revisions.add_argument('--compare-baseline',help='Run baseline then current under the same owned model service')
    parser.add_argument('--context-tokens',type=int,default=1536)
    parser.add_argument('--max-other-vram',type=int,default=2000)
    parser.add_argument('--live-web',action='store_true',help='Use actual case URLs and public search instead of local fixtures')
    parser.add_argument('--browser',action='store_true')
    parser.add_argument('--capture-web',help='Retain bounded actual HTTP responses locally for diagnosis')
    parser.add_argument('--assessment-freeze',help='Pre-run manifest for a first frozen live assessment; verify cases and production hashes')
    args = parser.parse_args()
    if args.live_web and args.compare_baseline:parser.error('Use frozen response replay for paired web comparisons')
    if args.capture_web and not args.live_web:parser.error('--capture-web requires --live-web')
    if args.assessment_freeze and (not args.live_web or args.baseline or args.compare_baseline):
        parser.error('--assessment-freeze requires the current engine on live web')
    target = Path(args.out)
    if target.exists():raise FileExistsError(target)
    try:
        with socket.create_connection(('127.0.0.1', 8765), timeout=.3):
            raise RuntimeError('Refusing to replace an existing service')
    except (ConnectionRefusedError, TimeoutError):pass
    if memory()['used_mib'] > args.max_other_vram:raise RuntimeError('Insufficient GPU headroom')
    baseline_revision=None;baseline_hashes=None
    baseline_engine=None
    if args.baseline or args.compare_baseline:
        from eval.revision_engine import load_engine
        baseline_engine,baseline_revision,baseline_hashes=load_engine(args.baseline or args.compare_baseline)
        if args.baseline:Engine=baseline_engine
    cases_path = ROOT / args.cases
    fixture_path = None if args.live_web else ROOT / args.fixtures
    cases = json.loads(cases_path.read_text(encoding='utf-8'))
    routes = json.loads(fixture_path.read_text(encoding='utf-8')) if fixture_path else {}
    capture_dir=ROOT/args.capture_web if args.capture_web else None
    if capture_dir:
        capture_dir.mkdir(parents=True,exist_ok=True)
        for case in cases:
            snapshot=capture_dir/(case['id']+'.json')
            if snapshot.exists():raise FileExistsError(snapshot)
    token = uuid.uuid4().hex
    settings = Settings(model_url='http://127.0.0.1:8765', budget=args.budget, max_depth=args.max_depth,
                        search=args.live_web, allow_private=not args.live_web,browser=args.browser)
    folder = ROOT / 'research/reader-20261023'
    folder.mkdir(parents=True, exist_ok=True)
    stem = target.stem
    env = dict(os.environ, APERTURE_MODEL=str(ROOT / 'models/qwen'), APERTURE_VERIFY_MODEL='0',
        APERTURE_CONTEXT_TOKENS=str(args.context_tokens), APERTURE_STARTUP_TOKEN=token,
        HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONIOENCODING='utf-8')
    source = [ROOT / 'app.py', *(ROOT / 'agent').glob('*.py')]
    assessment=None
    if args.assessment_freeze:
        assessment_path=ROOT/args.assessment_freeze
        assessment=json.loads(assessment_path.read_text(encoding='utf-8'))
        if assessment['cases_sha256']!=hashlib.sha256(cases_path.read_bytes()).hexdigest():
            raise ValueError('Assessment cases changed after freeze')
        actual={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source}
        if assessment['production_sha256']!=actual:raise ValueError('Production changed after assessment freeze')
    report = {'scope': 'Local starting-page end-to-end diagnosis with bounded navigation; exposed development cases.' if args.max_depth else __doc__, 'context_limit': args.context_tokens,
        'comparison_mode':bool(args.compare_baseline),
        'baseline_revision':baseline_revision,'baseline_source_sha256':baseline_hashes,
        'case_path':args.cases,'fixture_path':args.fixtures if fixture_path else None,'max_depth':args.max_depth,'budget':args.budget,
        'live_web':args.live_web,'browser':args.browser,
        'production_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source},
        'cases_sha256': hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        'fixtures_sha256': hashlib.sha256(fixture_path.read_bytes()).hexdigest() if fixture_path else None, 'rows': []}
    if args.live_web:report['scope']='Actual public HTTP/search + full4B end-to-end diagnosis on exposed failures. Exact answer aliases and gold sources frozen before run; not holdout or official accuracy.'
    if assessment:
        report['scope']='First frozen disjoint uniform sample, actual public HTTP/search + full4B. Exact answer and gold source scoring; not official SimpleQA or Match 4 accuracy.'
        report['assessment_freeze_path']=args.assessment_freeze
        report['assessment_freeze_sha256']=hashlib.sha256(assessment_path.read_bytes()).hexdigest()
        report['assessment_selection']=assessment['selection']
    report['runner_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    child = None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def health():
        with opener.open(settings.model_url + '/health', timeout=2) as response:return json.load(response)
    try:
        with (folder / (stem + '.stdout.log')).open('wb') as stdout, (folder / (stem + '.stderr.log')).open('wb') as stderr:
            child = subprocess.Popen([sys.executable, '-u', '-m', 'agent.model_server'], cwd=ROOT,
                env=env, stdout=stdout, stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        started = time.monotonic()
        print(json.dumps({'stage': 'starting', 'owned_wrapper_pid': child.pid}), flush=True)
        while time.monotonic() - started < 180:
            if child.poll() is not None:raise RuntimeError('Resident startup failed; see stderr log')
            try:
                state = health()
                if state.get('startup_token') != token:raise RuntimeError('Service ownership mismatch')
                report['health_before'] = state
                break
            except (OSError, ValueError):pass
            if memory()['used_mib'] > 11800:raise RuntimeError('Dedicated memory guard')
            time.sleep(.5)
        else:raise TimeoutError('Resident startup')
        with (nullcontext(SimpleNamespace(base='')) if args.live_web else FakeWeb(routes)) as web:
            if args.compare_baseline:
                report['baseline_rows']=[]
                asyncio.run(run(cases,settings,web.base,engine=baseline_engine,stage='baseline',rows=report['baseline_rows']))
                report['health_after_baseline']=health()
            asyncio.run(run(cases,settings,web.base,live_web=args.live_web,capture_dir=capture_dir,rows=report['rows']))
        report['health_after'] = health()
        report['memory_after_run'] = memory()
    except Exception as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)
        if isinstance(exc,ModelNotReady):report['readiness_failure']=exc.state
    finally:
        if child is not None and child.poll() is None:
            if os.name == 'nt':subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], capture_output=True, timeout=10)
            else:child.terminate()
            child.wait(timeout=10)
        report['memory_after_shutdown'] = memory()
        report['production_after_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source}
        report['production_changed_during_run']=report['production_sha256']!=report['production_after_sha256']
        report['passed'] = sum(r['joint_ok'] for r in report['rows'])
        report['total'] = len(report['rows'])
        if args.compare_baseline and len(report['rows'])==len(cases) and report.get('baseline_rows'):
            pairs=list(zip(report['baseline_rows'],report['rows']))
            report['comparison']={'before_passed':sum(row['joint_ok'] for row in report['baseline_rows']),
                'after_passed':report['passed'],'total':len(cases),
                'wins':[after['id'] for before,after in pairs if after['joint_ok'] and not before['joint_ok']],
                'losses':[after['id'] for before,after in pairs if before['joint_ok'] and not after['joint_ok']]}
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'total': report['total'], 'error': report.get('error'),
        **({'comparison':report['comparison']} if 'comparison' in report else {})}), flush=True)
    if report.get('error'):sys.exit(1)
