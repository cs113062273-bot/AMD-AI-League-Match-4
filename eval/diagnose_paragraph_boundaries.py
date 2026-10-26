"""CPU diagnosis of omitted paragraph end tags, including saved exposed pages.

No public requests, model, browser, gold/alias changes, or accuracy estimate.
Structural development expectations; source facts must remain literal.
"""
import argparse
import base64
from dataclasses import asdict
import hashlib
import importlib
import json
from pathlib import Path
import sys

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.engine import Engine
from agent.network import Response
from agent.parser import parse_response
from agent.planner import plan_query
from agent.selector import payload
from agent.urls import discovery_url
from agent.types import Candidate
from revision_engine import load_engine


def controls(parse):
    rows = []
    cases = [
        ('omitted-p', '<p>Alpha record<p>Beta record', ['Alpha record', 'Beta record']),
        ('closed-p', '<p>Alpha record</p><p>Beta record</p>', ['Alpha record', 'Beta record']),
        ('mixed-closure', '<p>Alpha record<p>Beta record</p><p>Gamma record',
         ['Alpha record', 'Beta record', 'Gamma record']),
        ('uppercase', '<P>Alpha record<P class="v">Beta record', ['Alpha record', 'Beta record']),
        ('inline-strong', '<p>Alpha <b>record</b><p>Beta <em>record</em>', ['Alpha record', 'Beta record']),
        ('comment', '<p>Alpha<!-- <p>not an element --> record<p>Beta record', ['Alpha record', 'Beta record']),
        ('quoted-attribute', '<p data-example="<p>literal">Alpha record<p>Beta record', ['Alpha record', 'Beta record']),
        ('div-after-p', '<p>Alpha record<div>Beta record</div>', ['Alpha record', 'Beta record']),
        ('heading-after-p', '<p>Alpha record<h2>Beta heading</h2><p>Gamma record', ['Alpha record', 'Gamma record']),
        ('footer-after-p', '<p>Alpha record<footer><p>Hidden footer record</footer>', ['Alpha record']),
        ('paragraph-inside-nav', '<nav><p>Navigation record</nav><p>Alpha record<p>Beta record',
         ['Alpha record', 'Beta record']),
        ('script-literals', '<script>const x = "<p>fake";</script><p>Alpha record<p>Beta record',
         ['Alpha record', 'Beta record']),
        ('metadata-json', '<script type="application/ld+json">{"description":"<p>literal"}</script>'
         '<p>Alpha record<p>Beta record', ['Alpha record', 'Beta record']),
        ('escaped-tags', '<p>Alpha &lt;p&gt; record</p><p>Beta &amp; record</p>',
         ['Alpha <p> record', 'Beta & record']),
        ('br-inline', '<p>Alpha<br>record</p><p>Beta record</p>', ['Alpha record', 'Beta record']),
        ('list-after-p', '<p>Alpha record<ul><li>Beta record</li></ul>', ['Alpha record', 'Beta record']),
        ('table-after-p', '<p>Alpha record<table><tr><th>Code</th><td>R8</td></tr></table>', ['Alpha record']),
        ('blockquote-after-p', '<p>Alpha record<blockquote><p>Beta record</p></blockquote>',
         ['Alpha record', 'Beta record']),
    ]
    for name, html, expected in cases:
        page = parse(Response('https://example.org/document', html.encode(), 'text/html', 'utf-8', 200))
        texts = [p.text for p in page.passages]
        merged = [p.text for p in page.passages if not p.qualifiers.get('paragraph_window')
                  and (('Alpha record' in p.text and 'Beta record' in p.text)
                       or ('Alpha record' in p.text and 'Hidden footer record' in p.text))]
        passed = not page.error and all(t in texts for t in expected) and not merged
        if name == 'metadata-json':
            passed &= any(p.value == '<p>literal' and p.kind == 'jsonld' for p in page.passages)
        if name == 'heading-after-p':
            passed &= any(p.text == 'Gamma record' and p.section == 'Beta heading' for p in page.passages)
        rows.append({'id': name, 'passed': bool(passed), 'merged': merged,
                     'passages': [asdict(p) for p in page.passages]})
    html = '<p>Alpha record<p>Beta record<p>Gamma record<p>Delta record<h2>Boundary heading</h2><p>Other section'
    page = parse(Response('https://example.org/document', html.encode(), 'text/html', 'utf-8', 200))
    windows = [p for p in page.passages if p.qualifiers.get('paragraph_window')]
    rows.append({'id': 'context-bounds-and-heading-boundary', 'passed': bool(windows)
                 and all(p.kind == 'prose' and len(p.text) <= 1100 for p in windows)
                 and not any('Alpha record' in p.text and 'Delta record' in p.text for p in windows)
                 and not any('Other section' in p.text for p in windows),
                 'windows': [asdict(p) for p in windows]})
    return rows


def recorded(engine):
    path = ROOT / 'research/external-disjoint12b-20261023/simpleqa-4145.json'
    raw = path.read_bytes()
    data = json.loads(raw)
    original = json.loads((ROOT / 'benchmarks/external-disjoint12b-20261023-first.json').read_text(encoding='utf-8'))
    record = next(r for r in original['rows'] if r['id'] == 'simpleqa-4145')
    if hashlib.sha256(raw).hexdigest() != record['capture_sha256']:
        raise ValueError('Immutable capture changed')
    namespace = engine.__module__.rsplit('.', 1)[0]
    parser = importlib.import_module(namespace + '.parser').parse_response
    planner = importlib.import_module(namespace + '.planner').plan_query
    rank = engine.run.__globals__['rank_passages']
    selector_payload = importlib.import_module(namespace + '.selector').payload
    plan = planner(record['result']['diagnostics']['plan']['question'], record['result']['diagnostics']['plan']['url'])
    pages = []
    sources = []
    for url, envelope in data.items():
        if envelope['status'] != 200 or discovery_url(envelope['url']):
            continue
        response = dict(envelope)
        response['body'] = base64.b64decode(response.pop('body_base64'), validate=True)
        page = parser(Response(**response))
        if page.error:
            continue
        pages.append(page)
        soup = BeautifulSoup(response['body'].decode(response['charset'] or 'utf-8', errors='replace'), 'html.parser')
        sources.append({'url': url, 'body_sha256': hashlib.sha256(response['body']).hexdigest(),
                        'max_nested_paragraphs': max((len(p.find_all('p')) for p in soup.find_all('p')), default=0),
                        'passage_count': len(page.passages)})
    ranked = rank(plan, pages)
    request = selector_payload(plan, [], ranked)
    source = 'https://noehill.com/humboldt/nat1978000673.asp'
    # Literal source witness, manually inspected during exposed error analysis;
    # this is not a lookup against the frozen answer/gold or a model decision.
    witness = "This is Eureka's finest example of Second Empire architecture."
    first = next((i for i, p in enumerate(request['passages']) if p['source'] == source and witness in p['text']), None)
    polluted = [p for page in pages for p in page.passages if witness in p.text and 'Historic IOOF Buildings' in p.text]
    return {'id': 'saved-source-witness-and-boundary', 'passed': first is not None and not polluted,
            'scope': 'Source context availability only, not model correctness or a new answer win',
            'capture_path': str(path.relative_to(ROOT)), 'capture_sha256': record['capture_sha256'],
            'witness_first_payload_position': first,
            'witness_ranked_positions': [i for i, (page, p, score) in enumerate(ranked)
                                         if page.url == source and witness in p.text],
            'polluted_witness_passages': len(polluted), 'sources': sources,
            'first_payload': request['passages']}


def scope_checks(engine):
    g = engine.run.__globals__
    namespace = engine.__module__.rsplit('.', 1)[0]
    parse = importlib.import_module(namespace + '.parser').parse_response
    plan = g['plan_query']('What was the population of Maple Harbour at the 2004 census?')
    html = ('<h1>Maple Harbour</h1><p>At the 2004 census, its population was 617, in 142 families.'
            '<p>In 2014 its population was 839.')
    page = parse(Response('https://example.org/population', html.encode(), 'text/html', 'utf-8', 200))
    windows = [p for p in page.passages if p.qualifiers.get('paragraph_window')]
    rows = []
    for raw, expected in [('617', True), ('142', False), ('2004', False), ('839', False)]:
        results = [g['verify'](Candidate(raw, raw, page.url, p.text, kind='number', score=20), plan, [page])
                   for p in windows if raw in p.text]
        rows.append({'id': 'context-population-' + raw, 'passed': bool(results)
                     and all(r == expected for r in results), 'accepted': results, 'expected': expected})
    return rows


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--baseline')
    args = ap.parse_args()
    target = Path(args.out)
    if target.exists():
        raise FileExistsError(target)
    engine = Engine
    if args.baseline:
        engine, _, _ = load_engine(args.baseline)
    parse = importlib.import_module(engine.__module__.rsplit('.', 1)[0] + '.parser').parse_response
    rows = controls(parse) + scope_checks(engine) + [recorded(engine)]
    source_hashes = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in [ROOT/'agent/parser.py',ROOT/'agent/html_paragraphs.py']}
    if args.baseline:
        import subprocess
        source_hashes = {'agent/parser.py': hashlib.sha256(subprocess.check_output(
            ['git','show',args.baseline+':agent/parser.py'])).hexdigest()}
    report = {'scope': __doc__, 'baseline': args.baseline, 'rows': rows,
              'diagnostic_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'passed': sum(r['passed'] for r in rows), 'total': len(rows),
              'source_sha256': source_hashes,
              'torch_imported': 'torch' in sys.modules}
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'total': report['total'],
                      'failures': [r['id'] for r in rows if not r['passed']]}))
