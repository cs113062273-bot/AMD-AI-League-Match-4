"""CPU audit of heading-path collisions in existing exposed HTML captures.

Uses an isolated baseline parser with a diagnostic-only path decorator. No
production edit, model, new assessment rows or external request is involved.
"""
import argparse
import base64
from collections import defaultdict
import hashlib
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.network import Response
from agent.normalize import clean
from agent.urls import discovery_url
from revision_engine import load_engine


MAIN = ['h1', 'h2', 'h3', 'h4', 'p', 'li', 'dt', 'table', 'pre', 'address', 'blockquote']


def decorate(page, soup):
    main = soup.find_all(MAIN)
    blocks = soup.find_all(['div', 'span'])[:5000]
    lines = soup.find_all(['p', 'pre', 'div', 'blockquote'], limit=3000)
    paragraphs = soup.find_all('p', limit=1500)
    targets = {id(el) for el in [*main, *blocks, *lines, *paragraphs]}
    paths, stack = {}, []
    for el in soup.find_all(True):
        parents = {id(p) for p in el.parents}
        stack = [entry for entry in stack if entry[2] in parents]
        if re.fullmatch(r'h[1-6]', el.name or ''):
            rank = int(el.name[1])
            stack = [entry for entry in stack if entry[0] < rank]
            text = clean(el.get_text(' ', strip=True))
            if text:
                container = el.find_parent(['section', 'article', 'main', 'body']) or soup
                stack.append((rank, text, id(container)))
        if id(el) in targets:
            paths[id(el)] = tuple(entry[1] for entry in stack)
    for p in page.passages:
        node = None
        match = re.match(r'(?:heading|h1|inline|default|dl|signature|table|p|li|dt|pre|address|blockquote)\[(\d+)\]', p.locator)
        if match and int(match[1]) < len(main):
            node = main[int(match[1])]
        else:
            match = re.match(r'(block|lines|paragraphs)\[(\d+)\]', p.locator)
            if match:
                nodes = {'block': blocks, 'lines': lines, 'paragraphs': paragraphs}[match[1]]
                if int(match[2]) < len(nodes):
                    node = nodes[int(match[2])]
        if node is not None:
            path = paths.get(id(node), ())
            if len(path) > 1:
                p.qualifiers = {**p.qualifiers, 'heading_path': list(path)}


def audit():
    engine, revision, hashes = load_engine('858be7c')
    parse = importlib.import_module(engine.__module__.rsplit('.', 1)[0] + '.parser').parse_response
    source = subprocess.check_output(['git', 'show', revision + ':agent/parser.py']).decode('utf-8')
    original = 'key = (p.text, p.label, p.value, p.section)'
    replacement = 'key = (p.text, p.label, p.value, p.section, tuple(p.qualifiers.get("heading_path", [])))'
    if source.count(original) != 1 or source.count('        dedup = {}') != 1:
        raise ValueError('Unexpected baseline parser')
    source = source.replace('        dedup = {}', '        _decorate(page, soup)\n        dedup = {}').replace(original, replacement)
    probe = types.ModuleType('agent._heading_path_probe')
    probe.__file__ = '<isolated heading-path audit>'
    probe._decorate = decorate
    exec(compile(source, probe.__file__, 'exec'), probe.__dict__)
    files, sources, collisions, scopes, seen = [], [], [], [], set()
    for name in ['external-disjoint12-20261023', 'external-disjoint12b-20261023']:
        manifest = ROOT / 'benchmarks' / (name + '-first.json')
        for record in json.loads(manifest.read_text(encoding='utf-8'))['rows']:
            path = ROOT / record['capture_path']
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != record['capture_sha256'] or record['capture_omitted']:
                raise ValueError('Original capture changed or incomplete')
            files.append({'path': str(path.relative_to(ROOT)), 'sha256': digest})
            for item in json.loads(raw).values():
                if discovery_url(item['url']) or item['content_type'].casefold().split(';')[0].strip() not in {'text/html', 'application/xhtml+xml'}:
                    continue
                envelope = dict(item)
                envelope['body'] = base64.b64decode(envelope.pop('body_base64'), validate=True)
                digest = hashlib.sha256(envelope['body']).hexdigest()
                if envelope['error'] or not envelope['body'] or digest in seen:
                    continue
                seen.add(digest)
                response = Response(**envelope)
                before, after = parse(response), probe.parse_response(response)
                sources.append({'url': response.url, 'body_sha256': digest,
                                'before_passages': len(before.passages), 'after_passages': len(after.passages),
                                'scoped_passages': sum('heading_path' in p.qualifiers for p in after.passages)})
                groups = defaultdict(list)
                for p in after.passages:
                    groups[(p.text, p.label, p.value, p.section)].append(p)
                for key, facts in groups.items():
                    paths = {tuple(p.qualifiers.get('heading_path', ())) for p in facts}
                    if len(paths) > 1:
                        collisions.append({'capture': str(path.relative_to(ROOT)), 'capture_sha256': files[-1]['sha256'],
                                           'url': response.url, 'body_sha256': digest,
                                           'text': key[0], 'label': key[1], 'value': key[2], 'section': key[3],
                                           'contexts': [{'locator': p.locator, 'kind': p.kind,
                                                         'heading_path': p.qualifiers.get('heading_path', [])} for p in facts]})
                sections = defaultdict(list)
                for p in after.passages:
                    if p.kind != 'heading' and p.qualifiers.get('heading_path'):
                        sections[p.section].append(p)
                for section, facts in sections.items():
                    if len({tuple(p.qualifiers['heading_path']) for p in facts}) > 1:
                        scopes.append({'capture': str(path.relative_to(ROOT)), 'capture_sha256': files[-1]['sha256'],
                                       'url': response.url, 'body_sha256': digest, 'section': section,
                                       'facts': [{'text': p.text, 'locator': p.locator, 'kind': p.kind,
                                                  'heading_path': p.qualifiers['heading_path']} for p in facts]})
    return {'scope': __doc__, 'baseline': revision, 'baseline_hashes': hashes,
            'captures': files, 'html_sources': sources, 'collision_groups': collisions, 'ambiguous_sections': scopes,
            'collision_source_count': len({r['body_sha256'] for r in collisions}), 'torch_imported': 'torch' in sys.modules}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = Path(args.out)
    if out.exists():
        raise FileExistsError(out)
    report = audit()
    report['diagnostic_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report['production_sha256'] = {p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in sorted(Path('agent').glob('*.py'))}
    with out.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({'html_sources': len(report['html_sources']), 'collision_groups': len(report['collision_groups']),
                      'collision_source_count': report['collision_source_count'],
                      'ambiguous_sections': len(report['ambiguous_sections']), 'torch_imported': report['torch_imported']}))
    print(json.dumps([{'url':r['url'],'section':r['section'],'facts':r['facts'][:6]} for r in report['ambiguous_sections'][:5]]))
