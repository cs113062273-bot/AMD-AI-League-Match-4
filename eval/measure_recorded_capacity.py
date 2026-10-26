"""Measure saved actual requests through Runtime.infer with the real local tokenizer.

Stops at tensor construction: no model load, generation or GPU allocation.
This establishes input capacity, not answer accuracy at alternative capacities.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.model_server import Runtime


class Encoded(Exception):
    pass


class ObserveTokenizer:
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
        self.encodes = []
        self.packed = None

    def __getattr__(self, name):
        return getattr(self.tokenizer, name)

    def encode(self, text, *args, **kwargs):
        values = self.tokenizer.encode(text, *args, **kwargs)
        self.encodes.append({'tokens': len(values), 'text_sha256': hashlib.sha256(text.encode()).hexdigest()})
        return values

    def __call__(self, text, **kwargs):
        self.packed = {'tokens': len(self.tokenizer.encode(text)),
                       'text_sha256': hashlib.sha256(text.encode()).hexdigest()}
        raise Encoded()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--folder', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--suite', help='Measure only this completed suite')
    args = ap.parse_args()
    out = Path(args.out)
    if out.exists():
        raise FileExistsError(out)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(ROOT / 'models/qwen', local_files_only=True, trust_remote_code=False)
    rows = []
    for path in sorted(Path(args.folder).glob('*/*.json')):
        if args.suite and path.parent.name != args.suite:
            continue
        if path.name.endswith('-sources.json') or path.name in {'summary.json', 'freeze.json'}:
            continue
        row = json.loads(path.read_text(encoding='utf-8'))
        for i, request in enumerate(row.get('requests', [])):
            data = deepcopy(request['data'])
            if request['path'] == '/verify':
                data['mode'] = 'verify'
            elif request['path'] == '/expand':
                data['mode'] = 'expand'
            else:
                data.pop('mode', None)
            caps = []
            for cap in [1536, 3072, 5800]:
                observer = ObserveTokenizer(tokenizer)
                runtime = Runtime.__new__(Runtime)
                runtime.torch = object()
                runtime.tokenizer = observer
                runtime.context_limit = cap
                try:
                    reply = runtime.infer(deepcopy(data), max_time=60)
                    fits = False
                except Encoded:
                    reply = None
                    fits = True
                caps.append({'cap': cap, 'fits': fits, 'reply': reply, 'original_tokens': observer.encodes[0]['tokens'],
                             'last_encoded_tokens': observer.encodes[-1]['tokens'], 'packed': observer.packed})
            rows.append({'case_id': row['id'], 'receipt': path.as_posix(),
                         'receipt_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                         'request': i, 'path': request['path'], 'observed_state': request.get('state'),
                         'data_sha256': hashlib.sha256(json.dumps(request['data']).encode()).hexdigest(), 'capacities': caps})
    summary = {str(cap): {'fits': sum(r['capacities'][j]['fits'] for r in rows), 'total': len(rows),
                         'overflow': sum(not r['capacities'][j]['fits'] for r in rows)}
               for j, cap in enumerate([1536, 3072, 5800])}
    report = {'scope': __doc__, 'rows': rows, 'summary': summary,
              'diagnostic_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'runtime_sha256': hashlib.sha256((ROOT / 'agent/model_server.py').read_bytes()).hexdigest(),
              'tokenizer_files_sha256': {name: hashlib.sha256((ROOT / 'models/qwen' / name).read_bytes()).hexdigest()
                                         for name in ['tokenizer_config.json', 'tokenizer.json']},
              'model_loaded': False, 'generation_performed': False}
    with out.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
