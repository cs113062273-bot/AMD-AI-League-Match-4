"""Audit section collisions in already exposed, hash-verified HTML captures.

An isolated diagnostic parser retains section in the existing deduplication key.
Production is unchanged. New output is evidence of scope loss, not answer accuracy.
"""
import argparse
import base64
from collections import defaultdict
from dataclasses import asdict
import hashlib
import importlib
import json
from pathlib import Path
import sys
import subprocess
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.network import Response
from agent.parser import parse_response as current_parse
from agent.urls import discovery_url
from revision_engine import load_engine


def audit():
    engine, revision, hashes = load_engine('26a18e8')
    parse_response = importlib.import_module(engine.__module__.rsplit('.', 1)[0] + '.parser').parse_response
    source = subprocess.check_output(['git', 'show', revision + ':agent/parser.py']).decode('utf-8')
    original = 'key = (p.text, p.label, p.value)'
    changed = 'key = (p.text, p.label, p.value, p.section)'
    if source.count(original) != 1:
        raise ValueError('Diagnostic patch no longer matches the baseline parser')
    probe = types.ModuleType('agent._section_dedup_probe')
    probe.__file__ = '<isolated section-dedup audit>'
    exec(compile(source.replace(original, changed), probe.__file__, 'exec'), probe.__dict__)
    captures, sources, collisions, seen = [], [], [], set()
    for name in ['external-disjoint12-20261023', 'external-disjoint12b-20261023']:
        manifest = ROOT / 'benchmarks' / (name + '-first.json')
        for record in json.loads(manifest.read_text(encoding='utf-8'))['rows']:
            path = ROOT / record['capture_path']
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != record['capture_sha256'] or record['capture_omitted']:
                raise ValueError('Original capture changed or incomplete')
            captures.append({'path': str(path.relative_to(ROOT)), 'sha256': digest})
            for item in json.loads(raw).values():
                if discovery_url(item['url']) or item['content_type'].casefold().split(';')[0].strip() not in {'text/html', 'application/xhtml+xml'}:
                    continue
                envelope = dict(item)
                envelope['body'] = base64.b64decode(envelope.pop('body_base64'), validate=True)
                if envelope['error'] or not envelope['body']:
                    continue
                body_sha = hashlib.sha256(envelope['body']).hexdigest()
                if body_sha in seen:
                    continue
                seen.add(body_sha)
                response = Response(**envelope)
                before, after = parse_response(response), probe.parse_response(response)
                actual = current_parse(response)
                signature = lambda p: json.dumps(asdict(p), sort_keys=True)
                old_records = {signature(p) for p in before.passages}
                new_records = {signature(p) for p in actual.passages}
                sources.append({'url': response.url, 'body_sha256': body_sha,
                                'before_passages': len(before.passages), 'after_passages': len(after.passages),
                                'before_truncated': before.truncated, 'after_truncated': after.truncated,
                                'old_passage_records_preserved': old_records.issubset(new_records),
                                'production_matches_scoped_variant': asdict(actual) == asdict(after)})
                groups = defaultdict(list)
                for fact in after.passages:
                    groups[(fact.text, fact.label, fact.value)].append(fact)
                for key, facts in groups.items():
                    if len({p.section for p in facts}) < 2:
                        continue
                    collisions.append({'capture': str(path.relative_to(ROOT)), 'url': response.url,
                                       'body_sha256': body_sha, 'text': key[0], 'label': key[1], 'value': key[2],
                                       'contexts': [{'section': p.section, 'locator': p.locator, 'kind': p.kind,
                                                     'qualifiers': p.qualifiers} for p in facts]})
    return {'scope': __doc__, 'baseline': revision, 'baseline_hashes': hashes,
            'captures': captures, 'html_sources': sources, 'collision_groups': collisions,
            'collision_source_count': len({r['body_sha256'] for r in collisions}),
            'diagnostic_patch': {'original': original, 'replacement': changed}, 'torch_imported': 'torch' in sys.modules}


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
    print(json.dumps({'captures': len(report['captures']), 'html_sources': len(report['html_sources']),
                      'collision_groups': len(report['collision_groups']),
                      'collision_source_count': report['collision_source_count'], 'torch_imported': report['torch_imported']}))
    print(json.dumps([{'url': r['url'], 'text': r['text'][:170], 'contexts': r['contexts'][:4]}
                      for r in report['collision_groups'][:8]]))
