"""Audit current parsing/ranking of an exposed saved discovery receipt, without a model.

This is a raw-document replay; browser subresources are excluded and rendered
DOM is not reconstructed. It is not an Engine run or an accuracy assessment.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.engine import rank_passages
from agent.network import Response
from agent.parser import parse_response
from agent.planner import plan_query
from agent.selector import payload
from agent.urls import discovery_url


def audit(receipt_path, phrase):
    receipt_raw = receipt_path.read_bytes()
    receipt = json.loads(receipt_raw)
    if not phrase or phrase.casefold() not in receipt['question'].casefold():
        raise ValueError('Focus phrase must come from the original question')
    path = ROOT / receipt['capture_path']
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != receipt['sha256']:
        raise ValueError('Original capture changed')
    pages, source_records, skipped = [], [], []
    for item in json.loads(raw).values():
        if discovery_url(item['url']):
            skipped.append({'url': item['url'], 'reason': 'discovery_only'})
            continue
        content_type = item['content_type'].casefold().split(';')[0].strip()
        # Captures include browser scripts. Their response bodies are not
        # documents the engine supplied as evidence; never count them as such.
        if content_type not in {'text/html', 'application/xhtml+xml', 'application/pdf'}:
            skipped.append({'url': item['url'], 'reason': 'non_document', 'content_type': content_type})
            continue
        envelope = dict(item)
        envelope['body'] = base64.b64decode(envelope.pop('body_base64'), validate=True)
        page = parse_response(Response(**envelope))
        source_records.append({'url': page.url, 'status': page.status, 'error': page.error,
                               'body_sha256': hashlib.sha256(envelope['body']).hexdigest(),
                               'passages': len(page.passages), 'dynamic': page.dynamic, 'truncated': page.truncated})
        if not page.error and not any(p.url == page.url for p in pages):
            pages.append(page)
    plan = plan_query(receipt['question'], receipt['starting_url'])
    ranked = rank_passages(plan, pages)
    data = payload(plan, [], ranked)
    hits = [{'rank': i, 'source': page.url, 'locator': fact.locator, 'text': fact.text,
             'score': score, 'sent': any(p['source'] == page.url and p['locator'] == fact.locator
                                       and phrase.casefold() in p['text'].casefold() for p in data['passages'])}
            for i, (page, fact, score) in enumerate(ranked) if phrase.casefold() in fact.text.casefold()]
    return {'scope': __doc__, 'receipt': str(receipt_path.relative_to(ROOT)),
            'receipt_sha256': hashlib.sha256(receipt_raw).hexdigest(),
            'capture': str(path.relative_to(ROOT)), 'capture_sha256': digest,
            'question': plan.question, 'starting_url': plan.url, 'focus_phrase': phrase,
            'sources': source_records, 'skipped': skipped, 'ranked_passages': len(ranked),
            'matching_passages': hits, 'matching_sent_passages': sum(phrase.casefold() in p['text'].casefold()
                                                                    for p in data['passages']),
            'selection_payload': data, 'compact_payload_characters': len(json.dumps(data, ensure_ascii=False, separators=(',', ':'))),
            'torch_imported': 'torch' in sys.modules}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--phrase', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = ROOT / args.out
    if out.exists():
        raise FileExistsError(out)
    report = audit(ROOT / args.receipt, args.phrase)
    report['diagnostic_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report['production_sha256'] = {p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in sorted(Path('agent').glob('*.py'))}
    with out.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({k: report[k] for k in ['ranked_passages', 'matching_sent_passages',
                                            'compact_payload_characters', 'torch_imported']}))
