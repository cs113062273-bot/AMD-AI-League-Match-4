"""Replay the saved failing payload sequence against one owned real GPU model.

No web fetches or gold answers. Six-second request budgets/server four-second
generation cap; historical per-query remaining deadlines are not reproduced.
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
from eval.validate_frozen_version import save, production, digest, memory, health
from eval.model_readiness import wait_model_idle
from agent.model_client import request_model
from agent.types import Deadline, Settings

SERVER = '''import json,os
from agent.model_server import Runtime,make_server
import torch
if os.getenv('APERTURE_PROBE_MEMORY_FRACTION'):
    torch.cuda.memory.set_per_process_memory_fraction(float(os.environ['APERTURE_PROBE_MEMORY_FRACTION']))
original=Runtime.health
def extended(self):
    data=original(self)
    stats=self.torch.cuda.memory_stats()
    data['allocator_stats']={k:stats.get(k) for k in ['inactive_split_bytes.all.current','inactive_split_bytes.all.peak','reserved_bytes.all.current','allocated_bytes.all.current','num_alloc_retries','num_ooms']}
    return data
Runtime.health=extended
runtime=Runtime()
print(json.dumps(runtime.health()),flush=True)
make_server(runtime,8765).serve_forever(poll_interval=.25)
'''


async def replay(entries, folder):
    rows = []
    settings = Settings(model_url='http://127.0.0.1:8765', model_timeout=5)
    with (folder / 'requests.jsonl').open('x', encoding='utf-8') as journal:
        for index, item in enumerate(entries):
            idle = await wait_model_idle(settings.model_url, 10)
            if not idle['ready']:
                return rows, {'error': 'model_not_idle', 'index': index, 'state': idle, 'health': health()}
            reply, state = await request_model(settings, Deadline(6), item['request']['path'], item['request']['data'])
            snapshot = health()
            row = {'index': index, 'receipt': item['receipt'], 'request_index': item['request_index'],
                   'state': state, 'reply': reply, 'health': snapshot}
            rows.append(row)
            journal.write(json.dumps(row) + '\n')
            journal.flush()
            if index % 10 == 0 or snapshot.get('active_request'):
                print(json.dumps({'done': len(rows), 'total': len(entries), 'state': state,
                                  'reserved': snapshot['reserved_vram_bytes'], 'allocated': snapshot['allocated_vram_bytes'],
                                  'inactive_split': snapshot['allocator_stats']['inactive_split_bytes.all.current']}), flush=True)
        idle = await wait_model_idle(settings.model_url, 10)
        return rows, None if idle['ready'] else {'error': 'model_not_idle_after_last', 'state': idle, 'health': health()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--folder', required=True)
    ap.add_argument('--allocator', default='')
    ap.add_argument('--memory-fraction', type=float)
    ap.add_argument('--source-folder', default='research/fulltest-20261025-default3072-v1')
    ap.add_argument('--max-other-vram', type=int, default=2000)
    args = ap.parse_args()
    if args.memory_fraction is not None and not 0 < args.memory_fraction <= 1:
        ap.error('memory fraction must be in (0,1]')
    folder = ROOT / args.folder
    folder.mkdir(parents=True, exist_ok=False)
    before = production()
    original = ROOT / args.source_folder
    entries = []
    for spec in json.loads((original/'freeze.json').read_text(encoding='utf-8'))['specs']:
        name=spec['name']
        for path in sorted((original / name).glob('*.json')):
            if path.name in {'freeze.json', 'summary.json'} or path.name.endswith('-sources.json'):
                continue
            row = json.loads(path.read_text(encoding='utf-8'))
            for index, request in enumerate(row['requests']):
                entries.append({'receipt': path.relative_to(ROOT).as_posix(), 'receipt_sha256': digest(path),
                                'request_index': index, 'request': request})
    save(folder / 'freeze.json', {'scope': __doc__, 'production_sha256': before,
         'runner_sha256': digest(Path(__file__)), 'allocator': args.allocator, 'memory_fraction': args.memory_fraction,
         'entries': entries, 'server_wrapper': SERVER, 'source_folder': args.source_folder,
         'max_other_vram': args.max_other_vram})
    try:
        with socket.create_connection(('127.0.0.1', 8765), timeout=.3):
            raise RuntimeError('Existing service; refusing replacement')
    except (ConnectionRefusedError, TimeoutError):
        pass
    if memory()['used_mib'] > args.max_other_vram:
        raise RuntimeError('Insufficient headroom')
    env = dict(os.environ, APERTURE_MODEL=str(ROOT / 'models/qwen'), APERTURE_VERIFY_MODEL='0',
               APERTURE_CONTEXT_TOKENS='3072', APERTURE_REQUIRE_GPU='1', APERTURE_STARTUP_TOKEN=uuid.uuid4().hex,
               HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONIOENCODING='utf-8')
    env.pop('PYTORCH_ALLOC_CONF', None)
    env.pop('PYTORCH_CUDA_ALLOC_CONF', None)
    if args.allocator:
        env['PYTORCH_CUDA_ALLOC_CONF'] = args.allocator
    if args.memory_fraction is not None:
        env['APERTURE_PROBE_MEMORY_FRACTION'] = str(args.memory_fraction)
    child = None
    report = {'scope': __doc__, 'allocator': args.allocator, 'production_sha256': before}
    try:
        with (folder / 'model.stdout.log').open('xb') as out, (folder / 'model.stderr.log').open('xb') as err:
            child = subprocess.Popen([sys.executable, '-u', '-c', SERVER], cwd=ROOT, env=env, stdout=out, stderr=err,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        print(json.dumps({'stage': 'allocator-startup', 'owned_wrapper_pid': child.pid}), flush=True)
        start = time.monotonic()
        while time.monotonic() - start < 180:
            if child.poll() is not None:
                raise RuntimeError('Startup failed')
            try:
                state = health()
                if state.get('startup_token') != env['APERTURE_STARTUP_TOKEN']:
                    raise RuntimeError('Ownership mismatch')
                report['health_before'] = state
                break
            except (OSError, ValueError):
                pass
            time.sleep(.5)
        else:
            raise TimeoutError('Startup')
        rows, error = asyncio.run(replay(entries, folder))
        report.update(requests_completed=len(rows), requests_planned=len(entries), error=error, health_after=health())
    except Exception as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        if child is not None and child.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], capture_output=True, timeout=10)
            else:
                child.terminate()
            child.wait(timeout=10)
        report['production_unchanged'] = production() == before
        report['memory_after_shutdown'] = memory()
        save(folder / 'summary.json', report)
    print(json.dumps({k: report.get(k) for k in ['requests_completed', 'requests_planned', 'error', 'production_unchanged']}), flush=True)
    if report.get('error'):
        sys.exit(1)


if __name__ == '__main__':
    main()
