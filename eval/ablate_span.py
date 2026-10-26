"""Controlled input ablation: remove proposed candidate values, keep retrieved passages.

This changes no expected answers and makes no production-source edit. The result explicitly
records the experiment. Intended to measure candidate-option priming before integration.
"""
import hashlib
import json
from pathlib import Path
import runpy
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import agent.selector as selector
from agent.output import atomic_json

original=selector.payload
def span_payload(*args):
    data=original(*args);data['candidates']=[];return data


if __name__=='__main__':
    selector.payload=span_payload
    arguments=sys.argv[1:]
    if '--model' not in arguments:arguments.append('--model')
    output=arguments[arguments.index('--out')+1] if '--out' in arguments else 'benchmarks/results'
    sys.argv=['eval/run.py',*arguments]
    runpy.run_path('eval/run.py',run_name='__main__')
    path=Path(output+'.json');data=json.loads(path.read_text(encoding='utf-8'))
    data['experiment']={'span_only':True,'candidate_options_removed':True,'production_source_unchanged':True,
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    atomic_json(path,data)
