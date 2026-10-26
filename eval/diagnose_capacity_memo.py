"""Query-local capacity admission controls, CPU loopback HTTP without a model.

Counts below are protocol/control outcomes, not independent questions or accuracy.
"""
import argparse
import asyncio
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys

from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.engine import Engine
from revision_engine import load_engine


async def diagnose(engine):
    package = engine.__module__.rsplit('.', 1)[0]
    types = importlib.import_module(package + '.types')
    client = importlib.import_module(package + '.model_client').request_model
    rows, calls, gets = [], [], []
    mode = 'capacity'
    base = ''
    arrived = asyncio.Event()

    async def model(request):
        data = await request.json()
        if request.path == '/cancel':
            return web.json_response({'cancelled': True})
        calls.append({'path': request.path, 'data': data})
        if mode == 'slow':
            arrived.set()
            await asyncio.sleep(.3)
            return web.json_response({'error': 'context_limit'})
        if mode == 'extra':
            return web.json_response({'error': 'context_limit', 'retryable': True})
        if mode == 'unknown':
            return web.json_response({'error': 'RuntimeError'})
        if mode == 'http':
            return web.json_response({'error': 'context_limit'}, status=503)
        if mode == 'invalid':
            return web.Response(text='not JSON')
        if mode == 'unsupported':
            return web.json_response({'supported': False})
        if mode == 'abstain':
            return web.json_response({'passage': -1, 'answer': ''})
        if mode == 'engine' and len(json.dumps(data)) < 5000:
            if request.path == '/verify':
                return web.json_response({'supported': True})
            for p in data.get('passages', []):
                if 'Silver Finch' in p['text']:
                    return web.json_response({'candidate': -1, 'passage': p['id'], 'answer': 'Silver Finch'})
        return web.json_response({'error': 'context_limit'})

    async def content(request):
        gets.append(request.path)
        filler = 'Archive inventory and unrelated administrative records. ' * 13
        landing = '<h1>Cedar Observatory archive</h1>' + ''.join(
            '<p>Cedar Observatory archive volume ' + str(i) + '. ' + filler + '</p>' for i in range(8))
        landing += '<a href="/irrelevant">More</a>'
        if request.path == '/start':
            body = landing
        elif request.path == '/irrelevant':
            body = '<p>Archive index.</p>' + ('<a href="/answer">More</a>' if recover else '')
        else:
            body = '<h1>Cedar Observatory call sign</h1>' + ''.join(
                '<p>Cedar Observatory call sign record ' + str(i) + ': Silver Finch.</p>' for i in range(8))
        return web.Response(text=body, content_type='text/html')

    app = web.Application()
    app.router.add_post('/{tail:.*}', model)
    app.router.add_get('/{tail:.*}', content)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    base = 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
    settings = types.Settings(model_url=base, model_timeout=1, search=False, browser=False,
                              allow_private=True, budget=8, max_pages=3, max_depth=2)
    original = {'question': 'Which code is shown?', 'constraints': {'kind': 'text'},
                'passages': [{'id': 0, 'text': 'Source  text.', 'source': 'https://example.org/a', 'locator': 'p:1'}]}
    try:
        for name, variant in [('identical-refusal', 'same'), ('identical-verification-refusal', 'verify'), ('new-deadline', 'deadline'),
                              ('new-endpoint', 'endpoint'), ('new-operation', 'path'),
                              ('different-key-order', 'order'), ('changed-source-spacing', 'spacing'),
                              ('changed-source-locator', 'locator'), ('same-size-changed-source', 'same-size'), ('added-conflicting-context', 'conflict'),
                              ('changed-proof', 'proof')]:
            mode, calls = 'capacity', []
            data = deepcopy(original)
            deadline = types.Deadline(6)
            path = '/verify' if variant == 'verify' else '/select'
            await client(settings, deadline, path, data)
            other_settings = settings
            if variant == 'deadline':
                deadline = types.Deadline(6)
            elif variant == 'endpoint':
                other_settings = types.Settings(model_url=base + '/other', model_timeout=1)
            elif variant == 'path':
                path = '/verify'
            elif variant == 'order':
                data = dict(reversed(list(data.items())))
            elif variant == 'spacing':
                data['passages'][0]['text'] = 'Source text.'
            elif variant == 'locator':
                data['passages'][0]['locator'] = 'p:2'
            elif variant == 'same-size':
                data['passages'][0]['text'] = 'Other   text.'
                assert len(json.dumps(data)) == len(json.dumps(original))
            elif variant == 'conflict':
                data['passages'].append({'id': 1, 'text': 'Contradictory statement.', 'source': 'https://example.org/b'})
            elif variant == 'proof':
                data['proof'] = {'operation': 'count_relationships', 'premises': [{'value': 'different'}]}
            result = await client(other_settings, deadline, path, data)
            expected = 1 if variant in {'same', 'verify'} else 2
            rows.append({'id': name, 'passed': len(calls) == expected and result == (None, 'model_context_limit'),
                         'expected_http_calls': expected, 'calls': deepcopy(calls), 'result': result})

        for mode in ['extra', 'unknown', 'http', 'invalid', 'unsupported', 'abstain']:
            calls, deadline = [], types.Deadline(6)
            results = [await client(settings, deadline, '/verify' if mode == 'unsupported' else '/select', deepcopy(original))
                       for _ in range(2)]
            rows.append({'id': 'do-not-memoize-' + mode, 'passed': len(calls) == 2,
                         'calls': deepcopy(calls), 'results': results})

        mode, calls, deadline = 'capacity', [], types.Deadline(6)
        await client(settings, deadline, '/select', original)
        deadline.start -= 10
        result = await client(settings, deadline, '/select', original)
        rows.append({'id': 'budget-precedes-memo', 'passed': result == (None, 'budget_exhausted')
                     and len(calls) == 1 and getattr(deadline, 'model_capacity_skips', 0) == 0,
                     'calls': deepcopy(calls), 'result': result})

        mode, calls, deadline = 'capacity', [], types.Deadline(6)
        for i in range(17):
            await client(settings, deadline, '/select', {**original, 'variant': i})
        await client(settings, deadline, '/select', {**original, 'variant': 0})
        await client(settings, deadline, '/select', {**original, 'variant': 16})
        stored = len(getattr(deadline, '_model_capacity_rejections', ()))
        rows.append({'id': 'bounded-query-memo', 'passed': stored == 16 and len(calls) == 18,
                     'stored': stored, 'calls': deepcopy(calls)})

        for cancellation in [False, True]:
            mode, calls, deadline, arrived = 'slow', [], types.Deadline(6), asyncio.Event()
            limited = types.Settings(model_url=base, model_timeout=1 if cancellation else .2)
            pending = asyncio.create_task(client(limited, deadline, '/select', original))
            async with asyncio.timeout(1):
                await arrived.wait()
            if cancellation:
                pending.cancel()
            cancelled = False
            try:
                first = await pending
            except asyncio.CancelledError:
                cancelled = True
                first = None
            mode = 'capacity'
            second = await client(settings, deadline, '/select', original)
            rows.append({'id': 'cancelled-not-memoized' if cancellation else 'timeout-not-memoized',
                         'passed': len(calls) == 2 and second == (None, 'model_context_limit')
                         and (cancelled if cancellation else first == (None, 'TimeoutError')),
                         'calls': deepcopy(calls), 'first': first, 'second': second, 'cancelled': cancelled})

        for recover in [False, True]:
            mode, calls, gets = 'engine', [], []
            result = await engine(settings).run('What is the call sign of Cedar Observatory?', base + '/start')
            expected_hits = ['/start', '/irrelevant', '/answer'] if recover else ['/start', '/irrelevant']
            expected_calls = 3 if recover else 1
            passed = (gets == expected_hits and len(calls) == expected_calls
                      and result.answer == ('Silver Finch' if recover else '')
                      and result.sources == ([base + '/answer'] if recover else [])
                      and result.reason == ('model_verified' if recover else 'model_context_limit')
                      and result.diagnostics.get('model_capacity_skips') == 1
                      and not result.diagnostics.get('errors'))
            rows.append({'id': 'engine-' + ('changed-evidence-recovery' if recover else 'identical-evidence-stop'),
                         'passed': passed, 'calls': deepcopy(calls), 'gets': gets,
                         'answer': result.answer, 'reason': result.reason, 'diagnostics': result.diagnostics})
    finally:
        await runner.cleanup()
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = Path(args.out)
    if out.exists():
        raise FileExistsError(out)
    old, revision, hashes = load_engine('bec782c')
    async def run():
        return await diagnose(old), await diagnose(Engine)
    before, after = asyncio.run(run())
    report = {'scope': __doc__, 'baseline': revision, 'baseline_hashes': hashes, 'before': before, 'after': after,
              'before_passed': sum(r['passed'] for r in before), 'after_passed': sum(r['passed'] for r in after),
              'total': len(after), 'torch_imported': 'torch' in sys.modules,
              'diagnostic_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'production_sha256': {p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in sorted(Path('agent').glob('*.py'))}}
    report['wins'] = [a['id'] for b, a in zip(before, after) if a['passed'] and not b['passed']]
    report['losses'] = [a['id'] for b, a in zip(before, after) if b['passed'] and not a['passed']]
    with out.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({k: report[k] for k in ['before_passed', 'after_passed', 'total', 'wins', 'losses', 'torch_imported']}))
    print(json.dumps([{'id': r['id'], 'http_calls': len(r['calls'])} for r in after if not r['passed']]))
    if not all(r['passed'] for r in after):
        sys.exit(1)
