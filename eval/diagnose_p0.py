"""Small fixed-evidence diagnosis of service failures and registry identity.

Runs the actual engine/parser and HTTP clients. Registry HTTP is replayed at
the fetch boundary; no public network, model weights, or evaluation gold is
available to production. This is a development diagnosis, not a holdout score.
"""
import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
import subprocess
import types
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aiohttp import web
from agent.engine import Engine
from agent.network import Fetcher
from agent.planner import plan_query
from agent.resolvers import route
from agent.types import Settings
from benchmarks.fakeweb import FakeWeb


async def diagnose():
    rows = []
    mode = 'busy'

    async def model(request):
        data = await request.json()
        if request.path == '/cancel':
            return web.json_response({'cancelled': True})
        if mode in {'supported', 'verify_unavailable', 'verify_invalid'}:
            if request.path == '/verify':
                if mode == 'verify_unavailable':
                    return web.json_response({'error': 'busy'}, status=503)
                if mode == 'verify_invalid':
                    return web.json_response({'supported': 'yes'})
                return web.json_response({'supported': True})
            passage = next(p for p in data['passages'] if 'Mira Chen' in p['text'])
            return web.json_response({'passage': passage['id'], 'answer': 'Mira Chen'})
        if mode == 'busy':
            return web.json_response({'error': 'busy'}, status=503)
        if mode == 'timeout':
            await asyncio.sleep(.7)
        if mode == 'invalid_json':
            return web.Response(text='{broken')
        if mode == 'invalid_schema':
            return web.json_response({'passage': False, 'answer': 'false'})
        return web.json_response({'candidate': -1, 'passage': -1, 'answer': ''})

    app = web.Application()
    app.router.add_post('/{path}', model)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    model_url = 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
    routes = {
        '/metadata': [200, 'text/html', '<h1>Alder</h1><script type="application/ld+json">'
            '{"@type":"WebPage","author":false}</script>'],
        '/signature': [200, 'text/html', '<h1>connect</h1><dl><dt class="sig">connect(timeout=30)</dt></dl>'],
        '/author': [200, 'text/html', '<h1>Alder</h1><p>Alder was authored by Mira Chen.</p>'],
    }
    for name, version in [('PyPI', '2.1'), ('httpx', '0.28.1'), ('wrong-project', '9.9.9')]:
        routes['/pypi/' + name + '/json'] = [200, 'application/json', json.dumps(
            {'info': {'name': name, 'version': version, 'license': 'BSD-3-Clause'}, 'releases': {}})]
    routes['/pypi/mismatched/json'] = routes['/pypi/wrong-project/json']
    try:
        with FakeWeb(routes) as source:
            for mode in ['busy', 'invalid_json', 'invalid_schema', 'timeout', 'abstain']:
                result = await Engine(Settings(search=False, allow_private=True, max_depth=0,
                    model_url=model_url, model_timeout=.35, budget=2)).run(
                    'Who is the author of Alder?', source.base + '/metadata')
                rows.append({'id': 'metadata_' + mode, 'expected': '', 'result': asdict(result),
                             'passed': not result.answer and not result.sources})
            mode = 'busy'
            result = await Engine(Settings(search=False, allow_private=True, max_depth=0,
                model_url=model_url, model_timeout=.35, budget=2)).run(
                'What is the default value of timeout parameter in connect?', source.base + '/signature')
            rows.append({'id': 'bound_signature_busy', 'expected': '30', 'result': asdict(result),
                         'passed': result.answer == '30' and result.sources == [source.base + '/signature']})
            for mode in ['supported', 'verify_unavailable', 'verify_invalid']:
                expected = 'Mira Chen' if mode == 'supported' else ''
                result = await Engine(Settings(search=False, allow_private=True, max_depth=0,
                    model_url=model_url, model_timeout=.35, budget=3)).run(
                    'Who is the author of Alder?', source.base + '/author')
                rows.append({'id': 'reader_' + mode, 'expected': expected, 'result': asdict(result),
                    'passed': result.answer == expected and (bool(result.sources) if expected else not result.sources)})
            mode = 'busy'

            original_fetch = Fetcher.fetch
            requested = []

            async def replay(fetcher, url, **kwargs):
                requested.append(url)
                if urlsplit(url).hostname != 'pypi.org':
                    raise AssertionError('Unexpected non-replayed fetch: ' + url)
                response = await original_fetch(fetcher, source.base + urlsplit(url).path, **kwargs)
                response.url = url
                return response

            for name, query, expected in [
                ('nonexistent', 'What is the latest version of the PyPI package zzqx-nonexistent-pkg-4821?', ''),
                ('version', 'What is the latest version of the PyPI package httpx?', '0.28.1'),
                ('license', 'What is the license of the httpx package on PyPI?', 'BSD-3-Clause'),
                ('mismatched', 'What is the latest version of the PyPI package mismatched?', ''),
            ]:
                requested.clear()
                with patch.object(Fetcher, 'fetch', replay):
                    result = await Engine(Settings(search=False, allow_private=True, max_depth=0,
                        model_url=model_url, model_timeout=.35, budget=2)).run(query)
                rows.append({'id': 'pypi_' + name, 'expected': expected, 'requested': list(requested),
                    'result': asdict(result), 'passed': result.answer == expected and
                    (bool(result.sources) if expected else not result.sources)})
            for query, expected in [
                ('What is the latest version of PyPI package httpx?', ('pypi', 'httpx')),
                ('What is the version of package `httpx` on PyPI?', ('pypi', 'httpx')),
                ('What is the version of the npm package @scope/tool?', ('npm', '@scope/tool')),
            ]:
                actual = route(plan_query(query))
                rows.append({'id': 'route_' + query, 'actual': actual, 'expected': expected,
                             'passed': actual == expected})
    finally:
        await runner.cleanup()
    return {'scope': 'fixed evidence, actual local HTTP, injected model faults; no public-web accuracy claim',
            'passed': sum(row['passed'] for row in rows), 'total': len(rows), 'rows': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--baseline', help='Load engine/selector/resolver from this git revision, without a checkout')
    args = parser.parse_args()
    target = Path(args.out)
    if target.exists():
        raise FileExistsError(target)
    if args.baseline:
        modules = {}
        for name in ['engine', 'selector', 'resolvers']:
            source = subprocess.check_output(['git', 'show', args.baseline + ':agent/' + name + '.py'])
            module = types.ModuleType('agent._baseline_' + name)
            module.__package__ = 'agent'
            exec(compile(source, 'git:' + args.baseline + ':agent/' + name + '.py', 'exec'), module.__dict__)
            modules[name] = module
        modules['engine'].resolve = modules['resolvers'].resolve
        modules['engine'].select = modules['selector'].select
        modules['engine'].verify_selection = modules['selector'].verify_selection
        Engine = modules['engine'].Engine
        route = modules['resolvers'].route
    report = asyncio.run(diagnose())
    report['baseline_revision'] = args.baseline
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'total': report['total'],
                      'failures': [r['id'] for r in report['rows'] if not r['passed']]}))
