"""Supplemental real-model validation of the 12GB-device default (3072 tokens).

The independent12 sample has already been exposed: its repeat is development,
never a replacement first-sample score. Production and scoring stay frozen.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.validate_frozen_version import suite, production, save, digest, health, memory
from eval.diagnose_gpu_recovery import probes
from benchmarks.fakeweb import FakeWeb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--folder', required=True)
    ap.add_argument('--memory-fraction', type=float)
    ap.add_argument('--remaining-from', help='Retain a terminal failed run and execute only its incomplete groups in a new owned service')
    args = ap.parse_args()
    if args.memory_fraction is not None and not 0 < args.memory_fraction <= 1:
        ap.error('memory fraction must be in (0,1]')
    folder = ROOT / args.folder
    folder.mkdir(parents=True, exist_ok=False)
    first = json.loads((ROOT / 'research/fulltest-20261025-gpu-v1/summary.json').read_text())
    if first.get('error') or len(first['summaries']) != 14:
        raise RuntimeError('Finish the first frozen execution before supplemental validation')
    before = production()
    assert before == first['production_sha256']
    try:
        with socket.create_connection(('127.0.0.1', 8765), timeout=.3):
            raise RuntimeError('Existing service; refusing to replace')
    except (ConnectionRefusedError, TimeoutError):
        pass
    if memory()['used_mib'] > 2000:
        raise RuntimeError('Insufficient GPU headroom')
    specs = []
    for name, stem, depth in [('reader', 'reader-20261023', 0), ('proof', 'proof-20261023', 2),
                              ('transfer-v2', 'transfer-20261023-v2', 2)]:
        specs.append({'name': name, 'cases': 'benchmarks/' + stem + '-cases.json',
                      'fixtures': 'fixtures/' + stem + '.json', 'budget': 12, 'max_depth': depth})
    specs.append({'name': 'independent12-DEVELOPMENT-REPEAT', 'cases': 'benchmarks/fulltest-20261025-independent12.json',
                  'budget': 12, 'max_depth': 2})
    for name in ['external-disjoint12-20261023', 'external-disjoint12b-20261023']:
        specs.append({'name': name + '-DEVELOPMENT-REPEAT', 'cases': 'benchmarks/' + name + '.json',
                      'budget': 24, 'max_depth': 2})
    for name in ['dev', 'holdout', 'final-holdout', 'transfer-frozen']:
        specs.append({'name': name, 'cases': 'benchmarks/' + name + '.json',
                      'fixtures': 'fixtures/' + name + '.json', 'budget': 24, 'max_depth': 2})
    continuation = None
    if args.remaining_from:
        previous_path = ROOT / args.remaining_from
        previous = json.loads(previous_path.read_text(encoding='utf-8'))
        assert previous.get('error') and previous['production_sha256'] == before
        completed = {item['name'] for item in previous['summaries']}
        specs = [spec for spec in specs if spec['name'] not in completed]
        continuation = {'path': args.remaining_from, 'sha256': digest(previous_path),
                        'completed_groups_retained': sorted(completed),
                        'scope': 'New resident for incomplete groups; does not erase the prior failure or prove a continuous mixed-workload pass.'}
    launcher = ('import torch; torch.cuda.memory.set_per_process_memory_fraction(' + str(args.memory_fraction)
                + '); from agent.model_server import main; main()') if args.memory_fraction is not None else None
    save(folder / 'freeze.json', {'scope': __doc__, 'production_sha256': before, 'context_tokens': 3072,
         'memory_fraction': args.memory_fraction, 'server_launcher': launcher,
         'continuation': continuation,
         'allocator_environment': {name: os.getenv(name) for name in ['PYTORCH_CUDA_ALLOC_CONF', 'PYTORCH_ALLOC_CONF']},
         'specs': specs, 'runner_sha256': digest(Path(__file__)),
         'shared_runner_sha256': digest(ROOT / 'eval/validate_frozen_version.py'),
         'inputs': {path: digest(ROOT / path) for spec in specs for path in
                    [spec['cases'], *([spec['fixtures']] if 'fixtures' in spec else [])]},
         'first_run_preserved': 'research/fulltest-20261025-gpu-v1',
         'limitations': 'Live repeat also changes network state; do not attribute any answer change solely to capacity. No new sample.'})
    token = uuid.uuid4().hex
    env = dict(os.environ, APERTURE_MODEL=str(ROOT / 'models/qwen'), APERTURE_VERIFY_MODEL='0',
               APERTURE_CONTEXT_TOKENS='3072', APERTURE_STARTUP_TOKEN=token, APERTURE_REQUIRE_GPU='1',
               HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONIOENCODING='utf-8')
    child = None
    report = {'scope': __doc__, 'production_sha256': before, 'summaries': []}
    try:
        with (folder / 'model.stdout.log').open('xb') as out, (folder / 'model.stderr.log').open('xb') as err:
            command = [sys.executable, '-u', '-c', launcher] if launcher else [sys.executable, '-u', '-m', 'agent.model_server']
            child = subprocess.Popen(command, cwd=ROOT, env=env,
                                     stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        print(json.dumps({'stage': 'default-profile-startup', 'owned_wrapper_pid': child.pid}), flush=True)
        started = time.monotonic()
        while time.monotonic() - started < 180:
            if child.poll() is not None:
                raise RuntimeError('Resident startup failed')
            try:
                state = health()
                if state.get('startup_token') != token:
                    raise RuntimeError('Service ownership mismatch')
                assert state['device'] == 'cuda' and state['context_limit'] == 3072
                assert all(before.get('agent/' + name) == value for name, value in state['backend_source_sha256'].items())
                report['health_before'] = state
                break
            except (OSError, ValueError):
                pass
            if memory()['used_mib'] > 11800:
                raise RuntimeError('GPU memory guard during startup')
            time.sleep(.5)
        else:
            raise TimeoutError('Resident startup')
        for spec in specs:
            report['summaries'].append(asyncio.run(suite(spec, folder, before)))
        # Cooperative cancellation/deadline and subsequent-call recovery use
        # the same owned real backend, after scoring all fixed cases.
        report['lifecycle'] = asyncio.run(probes(health()))
        routes = json.loads((ROOT / 'fixtures/dev.json').read_text(encoding='utf-8'))
        cases = json.loads((ROOT / 'benchmarks/dev.json').read_text(encoding='utf-8'))[:3]
        report['fresh_cli'] = []
        with FakeWeb(routes) as web:
            for index, case in enumerate(cases):
                dest = folder / ('cli-' + str(index))
                cli_env = dict(env, APERTURE_MODEL_URL='http://127.0.0.1:8765', APERTURE_SEARCH='0',
                               APERTURE_BROWSER='0', APERTURE_ALLOW_PRIVATE='1', APERTURE_BUDGET='12')
                proc = subprocess.run([sys.executable, 'app.py', '--query-id', 'fulltest-' + str(index),
                                       '--query', case['query'], '--url', web.base + case['path'],
                                       '--output-dir', str(dest), '--diagnostics'], cwd=ROOT, env=cli_env,
                                      capture_output=True, timeout=30)
                result = json.loads(proc.stdout)
                report['fresh_cli'].append({'id': case['id'], 'exit_code': proc.returncode,
                    'passed': proc.returncode == 0 and result['answer'] == case['answer']
                    and result['sources'] == [web.base + case['source_path']],
                    'result': result, 'stderr': proc.stderr.decode('utf-8', errors='replace')})
        report['health_after'] = health()
    except Exception as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)
        print(json.dumps({'error': report['error']}), flush=True)
    finally:
        if child is not None and child.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], capture_output=True, timeout=10)
            else:
                child.terminate()
            child.wait(timeout=10)
        report['memory_after_shutdown'] = memory()
        report['production_unchanged'] = production() == before
        save(folder / 'summary.json', report)
    print(json.dumps({'finished_suites': len(report['summaries']), 'error': report.get('error'),
                      'lifecycle_passed': sum(r['passed'] for r in report.get('lifecycle', [])),
                      'cli_passed': sum(r['passed'] for r in report.get('fresh_cli', []))}), flush=True)
    if report.get('error'):
        sys.exit(1)


if __name__ == '__main__':
    main()
