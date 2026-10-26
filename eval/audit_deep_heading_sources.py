"""Compare h5/h6 source parsing on existing exposed, hash-verified HTML only.

Content atoms ignore version-specific locators and changed section labels;
scope changes and any lost atoms are reported separately. Not answer accuracy.
"""
import argparse
import base64
from dataclasses import asdict
import hashlib
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.network import Response
from agent.parser import parse_response
from agent.urls import discovery_url
from revision_engine import load_engine


def audit():
    engine, revision, hashes = load_engine('858be7c')
    before_parse = importlib.import_module(engine.__module__.rsplit('.', 1)[0] + '.parser').parse_response
    files, sources, seen = [], [], set()
    atom = lambda p: (p.text, p.label, p.value, p.kind)
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
                before, after = before_parse(response), parse_response(response)
                old, new = {atom(p) for p in before.passages}, {atom(p) for p in after.passages}
                new_fields = {(p.text, p.label, p.value) for p in after.passages}
                old_scopes = {(atom(p), p.section) for p in before.passages}
                new_scopes = {(atom(p), p.section) for p in after.passages}
                changed = [{'text': p.text, 'label': p.label, 'kind': p.kind, 'section': p.section, 'locator': p.locator}
                           for p in after.passages if atom(p) in old and (atom(p), p.section) not in old_scopes]
                sources.append({'url': response.url, 'body_sha256': digest,
                                'before_passages': len(before.passages), 'after_passages': len(after.passages),
                                'added_heading_atoms': len({atom(p) for p in after.passages if p.kind == 'heading'} - old),
                                'lost_content_atoms': sorted(old - new), 'added_content_atoms': len(new - old),
                                'lost_text_fields': sorted({a[:3] for a in old - new} - new_fields),
                                'reclassified_content_atoms': sorted(a for a in old - new if a[:3] in new_fields),
                                'unchanged_page': asdict(before) == asdict(after),
                                'changed_scope_records': changed,
                                'before_error': before.error, 'after_error': after.error,
                                'before_truncated': before.truncated, 'after_truncated': after.truncated})
    return {'scope': __doc__, 'baseline': revision, 'baseline_hashes': hashes,
            'captures': files, 'html_sources': sources, 'torch_imported': 'torch' in sys.modules}


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
    print(json.dumps({'sources': len(report['html_sources']),
                      'sources_with_added_headings': sum(bool(s['added_heading_atoms']) for s in report['html_sources']),
                      'sources_with_lost_content_atoms': sum(bool(s['lost_content_atoms']) for s in report['html_sources']),
                      'sources_with_lost_text_fields': sum(bool(s['lost_text_fields']) for s in report['html_sources']),
                      'unchanged_pages': sum(s['unchanged_page'] for s in report['html_sources']),
                      'changed_scope_records': sum(len(s['changed_scope_records']) for s in report['html_sources']),
                      'torch_imported': report['torch_imported']}))
    print(json.dumps([{'url': s['url'], 'lost': s['lost_content_atoms'][:3]} for s in report['html_sources'] if s['lost_content_atoms']]))
