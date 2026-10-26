"""CPU HTTP controls for h5/h6 heading scope, with an unchanged saved HTML witness.

The questions and semantic responses are authored, not independent accuracy.
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
    audit_path = ROOT / 'benchmarks/heading-paths-20261024-source-probe-v2.json'
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    record = next(r for r in audit['ambiguous_sections'] if r['url'] == 'https://www.daynday.com.tw/dayday'
                  and any('Mega City' in ' '.join(p['heading_path']) for p in r['facts']))
    fact = next(p for p in record['facts'] if 'Mega City' in ' '.join(p['heading_path']))
    name = fact['heading_path'][-1]
    raw = (ROOT / record['capture']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != record['capture_sha256']:
        raise ValueError('Original capture changed')
    item = next(r for r in json.loads(raw).values() if r['url'] == record['url'])
    body = base64.b64decode(item['body_base64'], validate=True)
    if hashlib.sha256(body).hexdigest() != record['body_sha256']:
        raise ValueError('Original source body changed')
    return body, name, {'capture': record['capture'], 'capture_sha256': record['capture_sha256'],
                        'body_sha256': record['body_sha256'], 'url': record['url'],
                        'audit_sha256': hashlib.sha256(audit_path.read_bytes()).hexdigest()}


async def diagnose(engine):
    package = engine.__module__.rsplit('.', 1)[0]
    types = importlib.import_module(package + '.types')
    parser = importlib.import_module(package + '.parser')
    network = importlib.import_module(package + '.network')
    saved, name, witness = real_source()
    cases = [(f'h{level}-code', f'<h{level}>Willow Station</h{level}><p>Code: N7</p>',
              'What is the code for Willow Station?', 'Willow Station', 'N7', True) for level in range(1, 7)]
    cases += [
        ('deep-table', '<h5>Willow Station</h5><table><tr><th>Code</th></tr><tr><td>N7</td></tr></table>',
         'What is the code for Willow Station?', 'Willow Station', 'N7', True),
        ('deep-record', '<h5>Willow Station</h5><article><b>Entry Code</b><span>N7</span></article>',
         'What is the entry code for Willow Station?', 'Willow Station', 'N7', True),
        ('deep-first-line', '<h6>Willow Report</h6><pre>N7\nN8</pre>',
         'What is the first line of the Willow Report?', 'Willow Report', 'N7', True),
        ('deep-semantic-rejection', '<h6>Willow Station</h6><p>Code: N7</p>',
         'What is the code for Willow Station?', 'Willow Station', 'N7', False),
        ('country-prefix-truncation', '<h2>Willow Station</h2><p>Phone: +1 (415) 555-0199</p>',
         'What is the phone number for Willow Station?', 'Willow Station', '(415) 555-0199', False, 'accept'),
        ('extension-truncation', '<h2>Willow Station</h2><p>Phone: (415) 555-0199 ext. 42</p>',
         'What is the phone number for Willow Station?', 'Willow Station', '(415) 555-0199', False, 'accept'),
        ('actual-shop-phone', saved, 'What is the phone number for ' + name + '?', name, '(02)2951-6736', True),
    ]
    active = cases[0]
    rows, calls = [], []
    async def content(request):
        return web.Response(body=active[1].encode('utf-8') if isinstance(active[1], str) else active[1], content_type='text/html')
    async def model(request):
        data = await request.json()
        calls.append({'path': request.path, 'data': data})
        matching = [p for p in data.get('passages', []) if p['section'].split(' > ')[-1] == active[3] and active[4] in p['text']]
        if request.path == '/verify':
            return web.json_response({'supported': bool(matching) and (active[5] or len(active)>6 and active[6]=='accept')})
        p = matching[0] if matching else None
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
            result = await engine(types.Settings(model_url=base, search=False, browser=False, allow_private=True,
                                                 max_depth=0, budget=5)).run(active[2], base + '/source')
            expected = active[4] if active[5] else ''
            rows.append({'id': active[0], 'passed': result.answer == expected and result.sources == ([base + '/source'] if expected else [])
                         and not result.diagnostics.get('errors'), 'answer': result.answer, 'reason': result.reason,
                         'calls': list(calls), **({'source_witness': witness} if active[0] == 'actual-shop-phone' else {})})
        for name, html, expected in [
            ('repaired-paragraph-window', '<h6>Willow Station</h6><p>Code: N7<p>Other details.', 'Willow Station'),
            ('hidden-heading-does-not-leak', '<h2>Willow Station</h2><h6 hidden>Birch Station</h6><p>Code: N7</p>', 'Willow Station')]:
            page = parser.parse_response(network.Response('https://example.org/a', html.encode(), 'text/html', status=200))
            facts = [p for p in page.passages if p.qualifiers.get('paragraph_window')] if name.startswith('repaired') else [p for p in page.passages if p.text == 'Code: N7' and p.kind == 'prose']
            rows.append({'id': name, 'passed': bool(facts) and all(p.section == expected for p in facts),
                         'facts': [{'section': p.section, 'text': p.text, 'locator': p.locator} for p in facts]})
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
    old, revision, hashes = load_engine('858be7c')
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
    print(json.dumps([{'id': r['id'], 'answer': r.get('answer'), 'reason': r.get('reason')} for r in after if not r['passed']]))
    if not all(r['passed'] for r in after):
        sys.exit(1)
