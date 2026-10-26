"""Bounded resident-client busy recovery, actual loopback HTTP and CPU workers only.

Authored protocol controls, not real-model or public-web accuracy. No weights loaded.
"""
import argparse
import asyncio
import hashlib
import importlib
import json
from pathlib import Path
import sys
import threading
import time
import uuid

import aiohttp
from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.engine import Engine
from agent.model_client import request_model
from agent.types import Deadline, Settings
from revision_engine import load_engine
from diagnose_model_service import ProbeRuntime
from agent.model_server import make_server


async def diagnose(client, engine):
    rows = []
    hits = []
    cancels = []
    mode = ''
    first_busy = asyncio.Event()

    async def endpoint(request):
        if request.path == '/cancel':
            cancels.append(await request.json())
            return web.json_response({'cancelled': False})
        data = await request.json()
        hits.append({'path': request.path, 'id': request.headers.get('X-Aperture-Request-ID'),
                     'expires': request.headers.get('X-Aperture-Expires'), 'data': data})
        n = sum(h['path'] == request.path for h in hits)
        if mode == 'budget-shared' and n > 1:
            await asyncio.sleep(.4)
        busy = mode in {'always-busy', 'short-budget', 'short-query', 'short-cap', 'cancel-backoff', 'budget-shared'} or (
            mode in {'busy-once', 'busy-twice', 'reject-after-busy', 'abstain-after-busy'}
            and n <= (2 if mode == 'busy-twice' else 1))
        if busy:
            first_busy.set()
            return web.json_response({'error': 'busy'}, status=503)
        if mode == 'unknown-503':
            return web.json_response({'error': 'RuntimeError'}, status=503)
        if mode == 'unrecognized-503':
            return web.json_response({'error': 'busy', 'other': True}, status=503)
        if mode == 'html-503':
            return web.Response(text='<h1>busy</h1>', status=503)
        if mode == 'large-503':
            return web.json_response({'error': 'busy', 'padding': 'x' * 10000}, status=503)
        if mode in {'500', '429'}:
            return web.json_response({'error': 'busy'}, status=int(mode))
        if mode == 'invalid-200':
            return web.Response(text='not JSON')
        if mode == 'busy-200':
            return web.json_response({'error': 'busy'})
        if mode == 'large-200':
            return web.json_response({'answer': 'x' * 3000})
        if request.path == '/verify':
            return web.json_response({'supported': mode != 'reject-after-busy'})
        if mode == 'abstain-after-busy':
            return web.json_response({'passage': -1, 'answer': ''})
        if request.path == '/expand':
            return web.json_response({'terms': []})
        if 'passages' in data:
            for p in data['passages']:
                if '+1 800 555 0142' in p['text']:
                    return web.json_response({'passage': p['id'], 'answer': '+1 800 555 0142'})
        return web.json_response({'answer': 'R8'})

    async def page(request):
        return web.Response(text='<title>Clearwater Workshop</title><p>Support phone: +1 800 555 0142</p>',
                            content_type='text/html')

    app = web.Application()
    app.router.add_post('/{tail:.*}', endpoint)
    app.router.add_get('/source', page)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    base = 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
    data = {'question': 'What is the code?', 'passages': [{'id': 0, 'text': 'Code: R8'}]}

    def add(name, passed, **detail):
        rows.append({'id': name, 'passed': bool(passed), **detail})

    def reset(name):
        nonlocal mode
        mode = name
        hits.clear()
        cancels.clear()
        first_busy.clear()

    try:
        cases = [('normal', 1, 'ok'), ('busy-once', 2, 'ok'), ('busy-twice', 3, 'ok'),
                 ('always-busy', 3, 'model_busy'), ('unknown-503', 1, 'http_503'),
                 ('unrecognized-503', 1, 'http_503'), ('html-503', 1, 'http_503'),
                 ('large-503', 1, 'http_503'), ('500', 1, 'http_500'), ('429', 1, 'http_429'),
                 ('invalid-200', 1, 'invalid_json'), ('large-200', 1, 'oversized_reply'),
                 ('busy-200', 1, 'model_busy'), ('short-budget', 1, 'model_busy'),
                 ('short-query', 1, 'model_busy'), ('short-cap', 1, 'model_busy')]
        for mode_name, count, expected in cases:
            reset(mode_name)
            reply, state = await client(Settings(model_url=base, model_timeout=.2 if mode == 'short-budget' else 1.5),
                                        Deadline(.5 if mode == 'short-query' else 3), '/select', data, limit=2048,
                                        cap=.2 if mode == 'short-cap' else None)
            add(mode_name, state == expected and len(hits) == count and (reply is not None) == (state == 'ok'),
                state=state, attempts=len(hits), expected_attempts=count)
            if mode_name in {'busy-once', 'busy-twice', 'always-busy'}:
                add(mode_name + '-request-identity', len(hits) == count
                    and len({h['id'] for h in hits}) == 1 and len({h['expires'] for h in hits}) == 1
                    and all(h['data'] == data for h in hits), requests=list(hits))
        for path in ['/verify', '/expand']:
            reset('busy-once')
            reply, state = await client(Settings(model_url=base), Deadline(3), path, data)
            add(path + '-busy-recovery', state == 'ok' and len(hits) == 2, state=state, attempts=len(hits))

        reset('normal')
        reply, state = await client(Settings(model_url=base), Deadline(.1), '/select', data)
        add('exhausted-no-http', state == 'budget_exhausted' and not hits and reply is None)

        reset('budget-shared')
        start = time.monotonic()
        reply, state = await client(Settings(model_url=base, model_timeout=.35), Deadline(3), '/select', data)
        elapsed = time.monotonic() - start
        add('original-call-cap', reply is None and len(hits) == 2 and .25 <= elapsed < .65
            and len(cancels) == 1 and cancels[0]['request_id'] == hits[-1]['id']
            and len({h['expires'] for h in hits}) == 1, state=state, seconds=elapsed, attempts=len(hits))

        reset('cancel-backoff')
        task = asyncio.create_task(client(Settings(model_url=base), Deadline(3), '/select', data))
        await asyncio.wait_for(first_busy.wait(), 1)
        await asyncio.sleep(.025)
        start = time.monotonic()
        task.cancel()
        cancelled = False
        try:
            await task
        except asyncio.CancelledError:
            cancelled = True
        add('cancel-backoff', cancelled and len(hits) == 1 and len(cancels) == 1
            and cancels[0]['request_id'] == hits[0]['id'] and time.monotonic() - start < .3)

        # End-to-end evidence flow must still require a separate verification.
        for mode_name, expected in [('busy-once', '+1 800 555 0142'),
                                    ('reject-after-busy', ''), ('abstain-after-busy', ''), ('always-busy', '')]:
            reset(mode_name)
            result = await engine(Settings(model_url=base, search=False, browser=False, allow_private=True,
                max_depth=0, budget=4, model_timeout=1.5)).run(
                    'What is the support phone number of Clearwater Workshop?', base + '/source')
            paths = [h['path'] for h in hits]
            verified = '/verify' in paths
            add('engine-' + mode_name, result.answer == expected
                and (not expected or verified and result.sources == [base + '/source'])
                and (mode_name != 'reject-after-busy' or verified),
                answer=result.answer, paths=paths, reason=result.reason)
    finally:
        await runner.cleanup()
    return rows


async def production_probe(client):
    """Exercise the real admission lock and cancellation IDs, without Runtime()."""
    runtime = ProbeRuntime()
    server = make_server(runtime, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    rows = []
    wait_data = {'question': 'wait', 'passages': [{'id': 0, 'text': 'x: 7'}]}

    async def until(predicate):
        end = time.monotonic() + 1
        while not predicate():
            if time.monotonic() >= end:
                raise TimeoutError('CPU worker did not reach expected state')
            await asyncio.sleep(.005)

    async def post(session, path, data, headers=None):
        async with session.post(base + path, json=data, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=2)) as response:
            return await response.json()

    try:
        async with aiohttp.ClientSession() as session:
            for cancel_waiter in [False, True]:
                owner_id = uuid.uuid4().hex
                owner = asyncio.create_task(post(session, '/select', wait_data,
                    {'X-Aperture-Request-ID': owner_id, 'X-Aperture-Expires': str(time.time() + 1.5)}))
                await until(lambda: runtime.active is not None)
                busy_count = runtime.busy_rejections
                waiter = asyncio.create_task(client(Settings(model_url=base, model_timeout=1), Deadline(2),
                    '/select', {**wait_data, 'question': 'next'}))
                await until(lambda: runtime.busy_rejections > busy_count)
                await asyncio.sleep(.025)
                if cancel_waiter:
                    waiter.cancel()
                    cancelled = False
                    try:
                        await waiter
                    except asyncio.CancelledError:
                        cancelled = True
                    rows.append({'id': 'production-waiter-cancel-keeps-owner',
                                 'passed': cancelled and runtime.active is not None
                                 and runtime.active.request_id == owner_id and not runtime.active.cancelled.is_set()})
                await post(session, '/cancel', {'request_id': owner_id})
                owner_reply = await owner
                if not cancel_waiter:
                    reply, state = await waiter
                    rows.append({'id': 'production-lock-recovery',
                        'passed': owner_reply == {'error': 'cancelled'} and state == 'ok'
                        and reply.get('answer') == '7' and runtime.active is None,
                        'state': state, 'health': runtime.health()})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--baseline')
    args = parser.parse_args()
    target = Path(args.out)
    if target.exists():
        raise FileExistsError(target)
    hashes = {'agent/' + name: hashlib.sha256((ROOT / 'agent' / name).read_bytes()).hexdigest()
              for name in ['model_client.py', 'model_server.py']}
    revision = None
    if args.baseline:
        Engine, revision, hashes = load_engine(args.baseline)
        request_model = importlib.import_module(Engine.__module__.rsplit('.', 1)[0] + '.model_client').request_model
    async def run():
        return await diagnose(request_model, Engine) + await production_probe(request_model)
    rows = asyncio.run(run())
    report = {'scope': __doc__, 'baseline': revision, 'source_hashes': hashes,
              'diagnostic_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'passed': sum(r['passed'] for r in rows), 'total': len(rows), 'rows': rows,
              'torch_imported': 'torch' in sys.modules}
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'total': report['total'],
                      'failures': [r['id'] for r in rows if not r['passed']]}))
