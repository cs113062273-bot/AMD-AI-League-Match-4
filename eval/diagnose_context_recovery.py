"""CPU loopback HTTP: distinguish evidence capacity from resident-service failure.

Authored navigation and semantic responses, not model accuracy or a new question set.
"""
import argparse
import asyncio
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
    settings_type = importlib.import_module(engine.__module__.rsplit('.', 1)[0] + '.types').Settings
    rows = []
    cases = [
        ('select-capacity-navigation', 'capacity', 2, 1, True),
        ('select-capacity-page-cap', 'capacity', 1, 1, True),
        ('select-capacity-depth-cap', 'capacity', 2, 0, True),
        ('select-capacity-terminal', 'capacity', 2, 1, False),
        ('verify-capacity-terminal', 'verify-capacity', 2, 1, False),
        ('proof-capacity-terminal', 'proof-capacity', 2, 1, False),
        ('capacity-navigation-semantic-rejection', 'reject', 2, 1, True),
        ('capacity-navigation-still-too-large', 'still-large', 2, 1, True),
        ('service-503-no-navigation', '503', 2, 1, True),
        ('service-unknown-error-no-navigation', 'unknown', 2, 1, True),
        ('invalid-reply-no-navigation', 'invalid', 2, 1, True),
        ('deadline-no-navigation', 'deadline', 2, 1, True),
        ('ordinary-abstention-navigation', 'abstain', 2, 1, True),
    ]
    for name, mode, max_pages, max_depth, links in cases:
        hits, calls = [], []
        base = ''
        filler = 'Archive inventory material and unrelated administrative records. ' * 11
        landing = '<h1>Cedar Observatory archive</h1>' + ''.join(
            '<p>Cedar Observatory archive volume ' + str(i) + '. ' + filler + '</p>' for i in range(8))
        if mode == 'verify-capacity':
            landing = '<p>The call sign of Cedar Observatory is Silver Finch.</p>'
        if mode == 'proof-capacity':
            landing = '<table><tr><th>Name</th><th>Chairs (millions)</th></tr><tr><td>Elm Hall</td><td>4.2</td></tr></table>'
        if links:
            landing += ''.join('<a href="/z' + str(i) + '">Archive</a>' for i in range(4))
            landing += '<a href="/a-record">Records</a>'
        # Eight short relevant passages displace the long archive inventory.
        answer_page = '<h1>Cedar Observatory call sign</h1>' + ''.join(
            '<p>Cedar Observatory call sign record ' + str(i) + ': Silver Finch.</p>' for i in range(8))

        async def content(request):
            hits.append(request.path)
            return web.Response(text=landing if request.path == '/start' else answer_page
                                if request.path == '/a-record' else '<p>Archive index.</p>', content_type='text/html')

        async def model(request):
            data = await request.json()
            navigation = data.get('question', '').startswith('Choose the best available page link')
            size = len(json.dumps(data, ensure_ascii=False, separators=(',', ':')))
            calls.append({'path': request.path, 'navigation': navigation, 'compact_characters': size, 'data': data})
            if navigation:
                for p in data['passages']:
                    if base + '/a-record' in p['text']:
                        return web.json_response({'candidate': -1, 'passage': p['id'], 'answer': base + '/a-record'})
                return web.json_response({'candidate': -1, 'passage': -1, 'answer': ''})
            if request.path == '/verify':
                return web.json_response({'error': 'context_limit'} if mode in {'verify-capacity', 'proof-capacity'}
                                         else {'supported': mode != 'reject'})
            if mode == '503':
                return web.json_response({'error': 'RuntimeError'}, status=503)
            if mode == 'unknown':
                return web.json_response({'error': 'RuntimeError'})
            if mode == 'invalid':
                return web.Response(text='not JSON')
            if mode == 'deadline':
                return web.json_response({'error': 'deadline'})
            if mode == 'still-large' or mode in {'capacity', 'reject'} and size > 5000:
                return web.json_response({'error': 'context_limit'})
            for p in data.get('passages', []):
                if 'Silver Finch' in p['text']:
                    return web.json_response({'candidate': -1, 'passage': p['id'], 'answer': 'Silver Finch'})
            return web.json_response({'candidate': -1, 'passage': -1, 'answer': ''})

        app = web.Application()
        app.router.add_get('/{tail:.*}', content)
        app.router.add_post('/{tail:.*}', model)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        base = 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
        try:
            settings = settings_type(model_url=base, allow_private=True, search=False, browser=False,
                                     budget=8, model_timeout=1, max_pages=max_pages, max_depth=max_depth)
            question = 'How many chairs does Elm Hall have?' if mode == 'proof-capacity' else 'What is the call sign of Cedar Observatory?'
            result = await engine(settings).run(question, base + '/start')
        finally:
            await runner.cleanup()
        recover = name in {'select-capacity-navigation', 'ordinary-abstention-navigation'}
        expected_state = 'answered' if recover else 'no_evidence' if mode == 'reject' else 'context_limit' if mode in {'capacity', 'verify-capacity', 'proof-capacity', 'still-large'} else (
            'invalid_reply' if mode == 'invalid' else 'budget_exhausted' if mode == 'deadline' else 'service_unavailable')
        expected_calls = 4 if recover else 2 if mode == 'verify-capacity' else 1
        expected_hits = ['/start', '/a-record'] if recover else ['/start']
        if mode in {'reject', 'still-large'}:
            expected_hits = ['/start', '/a-record']
            expected_calls = 4 if mode == 'reject' else 3
        if mode in {'503', 'unknown', 'invalid', 'deadline'}:
            # Existing lexical traversal remains available; failed services
            # must not gain an additional model navigation call.
            expected_hits = ['/start', '/z3']
            expected_calls = 2
        passed = (result.answer == ('Silver Finch' if recover else '')
                  and result.sources == ([base + '/a-record'] if recover else [])
                  and result.diagnostics.get('reader_state') == expected_state
                  and hits == expected_hits
                  and len(calls) == expected_calls
                  and not result.diagnostics.get('errors'))
        if mode in {'503', 'unknown', 'invalid', 'deadline'}:
            passed = passed and not any(c['navigation'] for c in calls)
        if name == 'select-capacity-navigation':
            # The deterministic capacity boundary is a character counter, NOT tokens.
            passed = passed and calls[0]['compact_characters'] > 5000 and all(
                c['compact_characters'] <= 5000 for c in calls[1:])
        if mode == 'proof-capacity':
            passed = passed and len(calls) == 1 and calls[0]['path'] == '/verify' and bool(calls[0]['data'].get('proof'))
        # No immediate resend or reduced-evidence retry: every later source
        # read follows a different fetched page, within the fixed page cap.
        selections = [c for c in calls if c['path'] == '/select' and not c['navigation']]
        if len(selections) > 1 and mode in {'capacity', 'reject', 'still-large'}:
            passed = passed and selections[0]['data'] != selections[-1]['data']
        rows.append({'id': name, 'passed': bool(passed), 'answer': result.answer, 'sources': result.sources,
                     'reason': result.reason, 'diagnostics': result.diagnostics, 'hits': hits, 'calls': calls,
                     'expected_reader_state': expected_state, 'expected_calls': expected_calls})
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = Path(args.out)
    if out.exists():
        raise FileExistsError(out)
    old, revision, hashes = load_engine('031d8be')
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
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['before_passed', 'after_passed', 'total', 'wins', 'losses', 'torch_imported']}))
    print(json.dumps([{'id': r['id'], 'reason': r['reason'], 'hits': r['hits'],
                       'sizes': [c['compact_characters'] for c in r['calls']]}
                      for r in after if not r['passed']]))
    if not all(r['passed'] for r in after):
        sys.exit(1)
