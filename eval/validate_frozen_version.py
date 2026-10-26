"""Full frozen-version validation with one owned model and per-case durable receipts.

No production edits, restarts between failed cases, or score-driven sample changes.
NVIDIA/CUDA results do not establish AMD acceptance. Gold stays in the scorer.
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
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.engine import Engine
from agent import selector, navigation
from agent.network import Fetcher
from agent.types import Settings
from benchmarks.fakeweb import FakeWeb
from eval.model_readiness import wait_model_idle, ModelNotReady
from eval.diagnose_gpu_recovery import memory
from eval.run import score


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def production():
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in [ROOT / 'app.py', *sorted((ROOT / 'agent').glob('*.py'))]}


def save(path, data):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=True, indent=2, allow_nan=False)


def health():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:8765/health', timeout=2) as response:
        return json.load(response)


async def suite(spec, folder, before):
    name = spec['name']
    cases_path = ROOT / spec['cases']
    cases = json.loads(cases_path.read_text(encoding='utf-8'))
    routes = json.loads((ROOT / spec['fixtures']).read_text(encoding='utf-8')) if spec.get('fixtures') else None
    local = routes is not None
    settings = Settings(model_url='http://127.0.0.1:8765', budget=spec['budget'], max_depth=spec['max_depth'],
                        search=not local, allow_private=local, browser=False)
    dest = folder / name
    dest.mkdir(exist_ok=False)
    save(dest / 'freeze.json', {'spec': spec, 'cases_sha256': digest(cases_path),
         'fixtures_sha256': digest(ROOT / spec['fixtures']) if local else None,
         'settings': asdict(settings), 'production_sha256': before, 'health': health(),
         'scoring': 'Existing answer aliases and source rule retained; strict all-returned-source score reported separately.'})
    rows = []
    original_request = selector.request_model
    original_fetch = Fetcher.fetch
    started_suite = time.monotonic()
    with FakeWeb(routes) if local else nullcontext(None) as web:
        for index, case in enumerate(cases):
            readiness = await wait_model_idle(settings.model_url, timeout=10)
            if not readiness['ready']:
                raise ModelNotReady(name + '/' + str(case['id']), readiness)
            if memory()['used_mib'] > 11800:
                raise RuntimeError('Dedicated memory headroom guard before ' + name + '/' + str(case['id']))
            requests, captures = [], {}
            captured_bytes = 0
            omitted = []

            async def observed_request(*args, **kwargs):
                entry = {'path': args[2], 'data': json.loads(json.dumps(args[3]))}
                began = time.monotonic()
                try:
                    reply, state = await original_request(*args, **kwargs)
                    entry.update(reply=reply, state=state)
                    return reply, state
                finally:
                    entry['seconds'] = time.monotonic() - began
                    requests.append(entry)

            async def observed_fetch(fetcher, url, **kwargs):
                nonlocal captured_bytes
                response = await original_fetch(fetcher, url, **kwargs)
                if url not in captures:
                    if captured_bytes + len(response.body) <= 20_000_000 and len(captures) < 64:
                        data = asdict(response)
                        data['body_base64'] = base64.b64encode(data.pop('body')).decode('ascii')
                        captures[url] = data
                        captured_bytes += len(response.body)
                    else:
                        omitted.append(url)
                return response

            began = time.monotonic()
            error = ''
            result = None
            base = web.base if web else ''
            url = base + case['path'] if 'path' in case else case.get('url', '')
            with patch.object(selector, 'request_model', observed_request), patch.object(navigation, 'request_model', observed_request), \
                    patch.object(Fetcher, 'fetch', observed_fetch) if not local else nullcontext():
                try:
                    result = await Engine(settings).run(case['query'], url)
                    json.dumps(result.internal(), allow_nan=False)
                    answer, sources = result.answer, result.sources
                except Exception as exc:
                    error = type(exc).__name__ + ': ' + str(exc)
                    answer, sources = '', []
            elapsed = time.monotonic() - began
            answer_ok, source_ok, expected, joint, category = score(answer, sources, case, base, error)
            blank = not case.get('answer', case.get('answers', [''])[0])
            accepted = ([base + path for path in case['source_paths']] if 'source_paths' in case else
                        [base + case['source_path']] if 'source_path' in case else
                        [case['source']] if case.get('source') else case.get('sources', []))
            strict_source = (not sources if blank else bool(sources) and
                             all(source in accepted if accepted else source.startswith(tuple(case.get('source_prefixes', [])))
                                 for source in sources))
            row = {'id': case['id'], 'answer': answer, 'sources': sources, 'answer_ok': answer_ok,
                   'source_ok': source_ok, 'joint_ok': joint, 'strict_source_ok': strict_source,
                   'strict_joint_ok': answer_ok and strict_source and not error, 'seconds': elapsed,
                   'error': error, 'failure_category': category, 'result': result.internal() if result else None,
                   'model_readiness': readiness, 'health_after': health(), 'requests': requests,
                   'capture_omitted': omitted}
            filename = str(index).zfill(3) + '-' + str(case['id'])
            save(dest / (filename + '.json'), row)
            if not local:
                save(dest / (filename + '-sources.json'), captures)
            rows.append(row)
            print(json.dumps({'stage': name, 'done': len(rows), 'total': len(cases), 'id': case['id'],
                              'answer_ok': answer_ok, 'strict_joint_ok': row['strict_joint_ok'],
                              'reason': result.reason if result else error, 'seconds': round(elapsed, 3)}), flush=True)
            assert production() == before, 'Production changed during validation'
    summary = {'name': name, 'n': len(rows), 'answer_passed': sum(r['answer_ok'] for r in rows),
               'source_passed': sum(r['source_ok'] for r in rows), 'joint_passed': sum(r['joint_ok'] for r in rows),
               'strict_joint_passed': sum(r['strict_joint_ok'] for r in rows), 'errors': sum(bool(r['error']) for r in rows),
               'abstentions': sum(not r['answer'] for r in rows), 'seconds': time.monotonic() - started_suite,
               'context_limit_requests': sum(q.get('state') == 'model_context_limit' for r in rows for q in r['requests']),
               'cases_sha256': digest(cases_path), 'production_sha256': before}
    save(dest / 'summary.json', summary)
    print(json.dumps({'stage_complete': summary}), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', required=True)
    args = parser.parse_args()
    folder = ROOT / args.folder
    folder.mkdir(parents=True, exist_ok=False)
    before = production()
    fixed = json.loads((ROOT / 'benchmarks/acceptance-inputs-20261024-v1.json').read_text(encoding='utf-8'))
    assert before == fixed['production_sha256']
    for name, value in fixed['fixed_input_sha256'].items():
        assert digest(ROOT / name) == value, name
    try:
        with socket.create_connection(('127.0.0.1', 8765), timeout=.3):
            raise RuntimeError('Existing service; refusing to replace')
    except (ConnectionRefusedError, TimeoutError):
        pass
    if memory()['used_mib'] > 2000:
        raise RuntimeError('Insufficient GPU headroom')
    token = uuid.uuid4().hex
    env = dict(os.environ, APERTURE_MODEL=str(ROOT / 'models/qwen'), APERTURE_VERIFY_MODEL='0',
               APERTURE_CONTEXT_TOKENS='1536', APERTURE_STARTUP_TOKEN=token, APERTURE_REQUIRE_GPU='1',
               HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONIOENCODING='utf-8')
    specs = [{'name': 'proof', 'cases': 'benchmarks/proof-20261023-cases.json', 'fixtures': 'fixtures/proof-20261023.json', 'budget': 12, 'max_depth': 2},
             {'name': 'transfer-v2', 'cases': 'benchmarks/transfer-20261023-v2-cases.json', 'fixtures': 'fixtures/transfer-20261023-v2.json', 'budget': 12, 'max_depth': 2}]
    fresh = 'benchmarks/fulltest-20261025-independent12.json'
    specs.append({'name': 'independent12', 'cases': fresh, 'budget': 12, 'max_depth': 2})
    for name in ['dev', 'holdout', 'final-holdout', 'transfer-frozen']:
        specs.append({'name': name, 'cases': 'benchmarks/' + name + '.json', 'fixtures': 'fixtures/' + name + '.json', 'budget': 24, 'max_depth': 2})
    for name in ['live', 'live-holdout', 'external-simpleqa20', 'external-simpleqa100', 'external-transfer100-v2',
                 'external-disjoint12-20261023', 'external-disjoint12b-20261023']:
        specs.append({'name': name, 'cases': 'benchmarks/' + name + '.json', 'budget': 24, 'max_depth': 2})
    freeze = {'scope': __doc__, 'production_sha256': before, 'runner_sha256': digest(Path(__file__)), 'specs': specs,
              'context_tokens': 1536, 'browser': False, 'hardware': 'Local NVIDIA RTX4070SUPER; not AMD',
              'fresh_sample_protocol': fixed['next_independent_sample_protocol'],
              'input_sha256': {name: digest(ROOT / name) for spec in specs for name in [spec['cases'], *([spec['fixtures']] if 'fixtures' in spec else [])] if (ROOT / name).exists()},
              'retention': 'Every case receipt is created once. Failures are not replaced or omitted; production stays fixed. Stop only for runtime safety/service failure, retaining partial rows.'}
    save(folder / 'execution-freeze.json', freeze)
    child = None
    report = {'scope': __doc__, 'summaries': [], 'production_sha256': before}
    try:
        with (folder / 'model.stdout.log').open('xb') as out, (folder / 'model.stderr.log').open('xb') as err:
            child = subprocess.Popen([sys.executable, '-u', '-m', 'agent.model_server'], cwd=ROOT, env=env,
                                     stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        print(json.dumps({'stage': 'startup', 'owned_wrapper_pid': child.pid}), flush=True)
        started = time.monotonic()
        while time.monotonic() - started < 180:
            if child.poll() is not None:
                raise RuntimeError('Model startup failed; inspect retained stderr')
            try:
                state = health()
                if state.get('startup_token') != token:
                    raise RuntimeError('Service ownership mismatch')
                report['health_before'] = state
                assert state['device'] == 'cuda' and state['context_limit'] == 1536
                assert all(before.get('agent/' + name) == value for name, value in state['backend_source_sha256'].items())
                break
            except (OSError, ValueError):
                pass
            if memory()['used_mib'] > 11800:
                raise RuntimeError('GPU headroom guard during startup')
            time.sleep(.5)
        else:
            raise TimeoutError('Model startup')
        # Freeze the actual backend identity before drawing the unseen sample.
        save(folder / 'backend-before-sampling.json', report['health_before'])
        cmd = [sys.executable, 'scripts/freeze_external_assessment.py', '--count', '12', '--seed', '20261024',
               '--starting-url', 'none', '--out', fresh]
        for name in fixed['next_independent_sample_protocol']['excluded_assessments_sha256']:
            assert digest(ROOT / name) == fixed['next_independent_sample_protocol']['excluded_assessments_sha256'][name]
            cmd += ['--exclude', name]
        subprocess.run(cmd, cwd=ROOT, env=env, check=True)
        for spec in specs:
            report['summaries'].append(asyncio.run(suite(spec, folder, before)))
        report['health_after'] = health()
    except Exception as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)
        if isinstance(exc, ModelNotReady):
            report['readiness_failure'] = exc.state
        print(json.dumps({'error': report['error']}), flush=True)
    finally:
        if child is not None and child.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], capture_output=True, timeout=10)
            else:
                child.terminate()
            child.wait(timeout=10)
        report['memory_after_shutdown'] = memory()
        report['production_after_sha256'] = production()
        report['production_unchanged'] = before == production()
        save(folder / 'summary.json', report)
    print(json.dumps({'finished_suites': len(report['summaries']), 'error': report.get('error'),
                      'production_unchanged': report['production_unchanged']}), flush=True)
    if report.get('error'):
        sys.exit(1)


if __name__ == '__main__':
    main()
