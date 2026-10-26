"""Paired CPU phone syntax and complete-source-span controls; no model or web."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.engine import Engine
from revision_engine import load_engine


def diagnose(engine):
    package = engine.__module__.rsplit('.', 1)[0]
    types = importlib.import_module(package + '.types')
    candidates = importlib.import_module(package + '.candidates')
    protocol = importlib.import_module(package + '.model_protocol')
    planner = importlib.import_module(package + '.planner')
    plan = planner.plan_query('What is the phone number for Willow Station?')
    rows = []
    values = ['+1 (415) 555-0199', '(415) 555-0199', '+44 20 7946 0018', '555-0199',
              '+886-2-2951-6736', '(02)2951-6736', '(020)79460018', '+1(415)555-0199',
              '(03)311-8691', '(02)2951-6736 ext. 42']
    cases = [(value, value, True) for value in values] + [
        ('(02)2951-6736', '2951-6736', False),
        ('+1 (415) 555-0199', '(415) 555-0199', False),
        ('+886-2-2951-6736', '886-2-2951-6736', False),
        ('(02)2951-6736 ext. 42', '(02)2951-6736', False),
        ('2024-10-24', '2024-10-24', False), ('127.0.0.1', '127.0.0.1', False),
        ('(02)123', '(02)123', False), ('(02)12345678901234', '(02)12345678901234', False),
        ('(02)2951-6736; backup number 2951-6736.', '2951-6736', True),
    ]
    for i, (source, value, expected) in enumerate(cases):
        text = 'Willow Station phone: ' + source
        fact = types.Passage(text, 'phone', source, 'Willow Station', 'field', 'phone')
        page = types.Page('https://example.org/a', title='Willow Station', passages=[fact])
        chosen = types.Candidate(value, value, page.url, text, fact.label, fact.section, 'phone', 10,
                                 {'locator': fact.locator, 'structure': fact.kind, 'field_value': fact.value})
        verified = candidates.verify(chosen, plan, [page])
        request = {'question': plan.question, 'constraints': {'kind': 'phone'}, 'passages': [{'id': 0, 'text': text}]}
        reply = protocol.validate_reply({'candidate': -1, 'passage': 0, 'answer': value}, request)
        accepted = not reply.get('error') and reply.get('answer') == value
        candidate_request = {**request, 'candidates': [{'id': 0, 'value': value, 'evidence': text}]}
        candidate_reply = protocol.validate_reply({'candidate': 0, 'passage': -1, 'answer': ''}, candidate_request)
        candidate_accepted = not candidate_reply.get('error') and candidate_reply.get('candidate') == 0
        rows.append({'id': 'phone-' + str(i), 'source': source, 'selected': value, 'expected': expected,
                     'verified': verified, 'protocol_accepted': accepted, 'reply': reply,
                     'candidate_protocol_accepted': candidate_accepted, 'candidate_reply': candidate_reply,
                     'passed': verified == expected and accepted == expected and candidate_accepted == expected})
    source = 'Willow Station phone: (02)2951-6736'
    page = types.Page('https://example.org/a', title='Willow Station', passages=[types.Passage(source, section='Willow Station')])
    extracted = [c.raw for c in candidates.extract(plan, page)]
    rows.append({'id': 'extract-complete-area-number', 'extracted': extracted,
                 'passed': '(02)2951-6736' in extracted and '2951-6736' not in extracted})
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = Path(args.out)
    if out.exists():
        raise FileExistsError(out)
    old, revision, hashes = load_engine('858be7c')
    before, after = diagnose(old), diagnose(Engine)
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
    print(json.dumps([r['id'] for r in after if not r['passed']]))
    if not all(r['passed'] for r in after):
        sys.exit(1)
