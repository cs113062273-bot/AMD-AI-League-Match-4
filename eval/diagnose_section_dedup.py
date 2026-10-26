"""CPU paired section-provenance controls, including one saved real-source witness.

Authored questions/semantic replies over source text are not independent accuracy.
"""
import argparse
import asyncio
import base64
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


def real_source():
    report_path = ROOT / 'benchmarks/section-dedup-20261024-source-audit-final-v3.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    record = next(r for r in report['collision_groups'] if r['text'] == 'Hit Dice . d8')
    path = ROOT / record['capture']
    raw = path.read_bytes()
    expected = next(r['sha256'] for r in report['captures'] if r['path'] == record['capture'])
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Original source capture changed')
    envelope = next(e for e in json.loads(raw).values() if e['url'] == record['url'])
    body = base64.b64decode(envelope['body_base64'], validate=True)
    if hashlib.sha256(body).hexdigest() != record['body_sha256']:
        raise ValueError('Original source body changed')
    return body, {'capture': record['capture'], 'capture_sha256': expected, 'url': record['url'],
                  'body_sha256': record['body_sha256'], 'audit_sha256': hashlib.sha256(report_path.read_bytes()).hexdigest()}


async def diagnose(engine):
    package = engine.__module__.rsplit('.', 1)[0]
    types = importlib.import_module(package + '.types')
    planner = importlib.import_module(package + '.planner')
    parser = importlib.import_module(package + '.parser')
    network = importlib.import_module(package + '.network')
    engine_module = importlib.import_module(engine.__module__)
    selector = importlib.import_module(package + '.selector')
    rows, calls = [], []
    saved, metadata = real_source()
    cases = [
        ('later-entity', '<h2>Birch Station</h2><p>Code: N7</p><h2>Willow Station</h2><p>Code: N7</p>',
         'What is the code for Willow Station?', 'Willow Station', 'N7', True),
        ('earlier-entity', '<h2>Willow Station</h2><p>Code: N7</p><h2>Birch Station</h2><p>Code: N7</p>',
         'What is the code for Willow Station?', 'Willow Station', 'N7', True),
        ('later-year', '<h2>Willow Station 2023</h2><p>Code: N7</p><h2>Willow Station 2024</h2><p>Code: N7</p>',
         'What is the code for Willow Station in 2024?', 'Willow Station 2024', 'N7', True),
        ('semantic-rejection', '<h2>Birch Station</h2><p>Code: N7</p><h2>Willow Station</h2><p>Code: N7</p>',
         'What is the code for Willow Station?', 'Willow Station', 'N7', False),
        ('real-source-later-class', saved, 'What are the hit dice of Rogue?', 'Rogue', 'd8', True),
        ('real-source-earlier-class', saved, 'What are the hit dice of Bard?', 'Bard', 'd8', True),
    ]
    active = cases[0]
    async def content(request):
        body = active[1].encode('utf-8') if isinstance(active[1], str) else active[1]
        return web.Response(body=body, content_type='text/html')

    async def model(request):
        data = await request.json()
        calls.append({'path': request.path, 'data': data})
        if request.path == '/verify':
            supported = active[5] and any(p['section'] == active[3] and active[4] in p['text']
                                          for p in data.get('passages', []))
            return web.json_response({'supported': supported})
        p = next((p for p in data.get('passages', []) if p['section'] == active[3] and active[4] in p['text']), None)
        return web.json_response({'candidate': -1, 'passage': p['id'] if p else -1, 'answer': active[4] if p else ''})

    app = web.Application()
    app.router.add_get('/source', content)
    app.router.add_post('/{tail:.*}', model)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    base = 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
    try:
        for active in cases:
            calls = []
            result = await engine(types.Settings(model_url=base, search=False, allow_private=True,
                                                 browser=False, max_depth=0, budget=5)).run(active[2], base + '/source')
            expected = active[4] if active[5] else ''
            rows.append({'id': active[0], 'passed': result.answer == expected
                         and result.sources == ([base + '/source'] if expected else [])
                         and not result.diagnostics.get('errors'), 'expected': expected,
                         'answer': result.answer, 'reason': result.reason, 'calls': list(calls),
                         **({'source_witness': metadata} if active[0].startswith('real-source') else {})})

        page = types.Page('https://example.org/a', passages=[
            types.Passage('Code: N7', section='Birch Station', locator='p:1'),
            types.Passage('Code: N7', section='Willow Station', locator='p:2')])
        plan = planner.plan_query('What is the code shared by Birch Station and Willow Station?')
        ranked = engine_module.rank_passages(plan, [page])
        sent = selector.payload(plan, [], ranked)['passages']
        rows.append({'id': 'rank-keeps-two-distinct-scopes', 'passed': {p['section'] for p in sent} == {'Birch Station', 'Willow Station'},
                     'sent': sent})
        html = b'<h2>Willow Station</h2><p>Code: N7</p><p>Code: N7</p>'
        page = parser.parse_response(network.Response('https://example.org/a', html, 'text/html', status=200))
        facts = [p for p in page.passages if p.text == 'Code: N7' and p.kind == 'prose']
        rows.append({'id': 'same-scope-duplicates-stay-deduplicated', 'passed': len(facts) == 1, 'count': len(facts)})
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
    old, revision, hashes = load_engine('26a18e8')
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
    print(json.dumps([{'id': r['id'], 'reason': r.get('reason'), 'answer': r.get('answer')} for r in after if not r['passed']]))
    if not all(r['passed'] for r in after):
        sys.exit(1)
