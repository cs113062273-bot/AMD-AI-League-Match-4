"""Small owned-process full-4B CUDA recovery probe; no benchmark sweep or model download."""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aiohttp
from agent.engine import Engine
from agent.model_client import request_model
from agent.types import Deadline, Settings
from benchmarks.fakeweb import FakeWeb

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8765'


def memory():
    result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.total',
        '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5, check=True)
    used, total = map(int, result.stdout.strip().splitlines()[0].split(','))
    return {'used_mib': used, 'total_mib': total}


async def probes(health):
    rows = []
    settings = Settings(model_url=BASE, model_timeout=4)
    data = {'question': 'What is the value of x?', 'passages': [{'id': 0, 'text': 'x: 7'}]}
    reply, state = await request_model(settings, Deadline(6), '/select', data)
    rows.append({'id': 'full_model_select', 'passed': state == 'ok' and reply.get('answer') == '7', 'reply': reply, 'state': state})
    long_data = {'question': 'What is the exact description of Alder? Copy the complete description.',
        'passages': [{'id': 0, 'text': 'Alder description: A compact device with a bright display, a durable frame, '
            'a removable battery, a quiet cooling system, and a weather resistant carrying case. ' * 3}]}
    async with aiohttp.ClientSession(trust_env=False) as session:
        async def current():
            async with session.get(BASE + '/health', timeout=aiohttp.ClientTimeout(total=2)) as response:
                return await response.json()

        before = await current()
        task = asyncio.create_task(request_model(settings, Deadline(6), '/select', long_data))
        limit = time.monotonic() + 3
        active = None
        while time.monotonic() < limit and not task.done():
            active = await current()
            if active.get('active_request') and active.get('recent_requests') and active['recent_requests'][-1].get('request_id') == active['active_request']:
                break
            await asyncio.sleep(.01)
        started = time.monotonic()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        limit = time.monotonic() + 5
        after = await current()
        while after.get('active_request') and time.monotonic() < limit:
            await asyncio.sleep(.02)
            after = await current()
        rows.append({'id': 'full_model_cancel_inflight', 'passed': not after.get('active_request')
            and after['outcomes'].get('cancelled', 0) > before['outcomes'].get('cancelled', 0),
            'seconds': time.monotonic() - started, 'active_before_cancel': active.get('active_request') if active else None,
            'last_request': after.get('recent_requests', [])[-1:]})
        reply, state = await request_model(settings, Deadline(6), '/select', data)
        rows.append({'id': 'full_model_next_after_cancel', 'passed': state == 'ok' and reply.get('answer') == '7', 'reply': reply, 'state': state})
        started = time.monotonic()
        async with session.post(BASE + '/select', json=long_data,
            headers={'X-Aperture-Request-ID': uuid.uuid4().hex, 'X-Aperture-Expires': str(time.time() + .05)},
            timeout=aiohttp.ClientTimeout(total=5)) as response:
            reply = await response.json()
        rows.append({'id': 'full_model_deadline', 'passed': reply.get('error') == 'deadline',
                     'seconds': time.monotonic() - started, 'reply': reply})
        reply, state = await request_model(settings, Deadline(6), '/select', data)
        rows.append({'id': 'full_model_next_after_deadline', 'passed': state == 'ok' and reply.get('answer') == '7', 'reply': reply, 'state': state})
    with FakeWeb({'/author': [200, 'text/html', '<h1>Alder</h1><p>Alder was authored by Mira Chen.</p>']}) as source:
        result = await Engine(Settings(model_url=BASE, search=False, allow_private=True, budget=8, max_depth=0)).run(
            'Who is the author of Alder?', source.base + '/author')
        rows.append({'id': 'full_model_engine_select_verify', 'passed': result.answer == 'Mira Chen'
            and result.sources == [source.base + '/author'], 'result': result.internal()})
    return rows


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    target = Path(args.out)
    if target.exists():
        raise FileExistsError(target)
    try:
        with socket.create_connection(('127.0.0.1', 8765), timeout=.3):
            raise RuntimeError('Refusing to use or replace an existing model service')
    except (ConnectionRefusedError, TimeoutError):
        pass
    initial = memory()
    if initial['used_mib'] > 2000:
        raise RuntimeError('Insufficient uncontended headroom for this narrow probe: ' + str(initial))
    token = uuid.uuid4().hex
    folder = ROOT / 'research/p0-gpu-20261023'
    folder.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, APERTURE_MODEL=str(ROOT / 'models/qwen'), APERTURE_VERIFY_MODEL='0',
        APERTURE_CONTEXT_TOKENS='1024', APERTURE_STARTUP_TOKEN=token,
        HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONIOENCODING='utf-8')
    report = {'scope': __doc__, 'context_limit': 1024, 'memory_before': initial, 'rows': []}
    child = None
    try:
        with (folder / 'stdout.log').open('wb') as stdout, (folder / 'stderr.log').open('wb') as stderr:
            child = subprocess.Popen([sys.executable, '-u', '-m', 'agent.model_server'], cwd=ROOT,
                env=env, stdout=stdout, stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        report['owned_wrapper_pid'] = child.pid
        print(json.dumps({'stage': 'starting_owned_4b', 'pid': child.pid, 'memory': initial}), flush=True)
        import urllib.request
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def health():
            with opener.open(BASE + '/health', timeout=2) as response:
                return json.load(response)

        start = time.monotonic()
        while time.monotonic() - start < 180:
            if child.poll() is not None:
                raise RuntimeError('Model startup failed; inspect ' + str(folder / 'stderr.log'))
            try:
                current = health()
                if current.get('startup_token') != token:
                    raise RuntimeError('Another service occupied the port')
                report['health_before'] = current
                break
            except (OSError, ValueError):
                pass
            current_memory = memory()
            report['startup_peak_used_mib'] = max(report.get('startup_peak_used_mib', 0), current_memory['used_mib'])
            if current_memory['used_mib'] > 11800:
                raise RuntimeError('Stopped before exhausting dedicated GPU memory')
            time.sleep(.5)
        else:
            raise TimeoutError('Model startup')
        print(json.dumps({'stage': 'ready', 'startup_seconds': time.monotonic() - start,
                          'memory': memory()}), flush=True)
        report['rows'] = asyncio.run(probes(health))
        report['health_after'] = health()
        report['memory_after_probes'] = memory()
    except Exception as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        if child is not None and child.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], capture_output=True, timeout=10)
            else:
                child.terminate()
            child.wait(timeout=10)
        report['memory_after_shutdown'] = memory()
        report['passed'] = sum(row['passed'] for row in report['rows'])
        report['total'] = len(report['rows'])
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'total': report['total'], 'error': report.get('error'),
                      'memory_after_shutdown': report['memory_after_shutdown']}), flush=True)
    if report.get('error') or report['passed'] != report['total']:
        sys.exit(1)
