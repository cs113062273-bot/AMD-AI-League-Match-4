"""Actual Runtime.infer packing with authored CPU string counters, no ML loads.

The counter is not a real tokenizer or an estimate of actual token capacity.
Generation is intercepted before tensor construction. This probes evidence
mutation, not a real-model wrong answer or competition score.
"""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys
import argparse

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.engine import Engine
from revision_engine import load_engine


class Packed(Exception):pass


class Counter:
    def __init__(self):self.first_size=None;self.packed=None
    def apply_chat_template(self,messages,**kwargs):
        text=json.dumps(messages,ensure_ascii=False)
        if self.first_size is None:self.first_size=len(text)
        return text
    def encode(self,text):return range(len(text))
    def __call__(self,text,**kwargs):self.packed=json.loads(text);raise Packed()


def diagnose(engine):
    module=importlib.import_module(engine.__module__.rsplit('.',1)[0]+'.model_server')
    rows=[]
    prefix='Oak Hall has 4 chairs. ';target='Elm Hall has '
    text=prefix+'x'*(649-len(prefix)-len(target)-1)+' '+target+'4 million chairs.'
    assert text[:650].endswith('Elm Hall has 4')
    base={'question':'How many chairs does Elm Hall have?','candidates':[],
          'constraints':{'kind':'number','operation':'single'},'passages':[
              {'id':0,'source':'https://example.org/source','locator':'p:1','text':text},
              {'id':1,'source':'https://example.org/other','locator':'p:1','text':'Other ordinary context.'}]}
    contexts=[{'id':i,'source':'https://example.org/'+str(i),'locator':'p:1',
               'text':'Elm Hall has 4 million chairs.' if i==0 else 'Elm Hall has 5 million chairs; source conflict.' if i==7
               else 'Other source context '+str(i)} for i in range(8)]
    cases=[]
    for mode in ['select','verify']:
        data=deepcopy(base);data['mode']=mode
        if mode=='verify':data['proposed']='4'
        cases.append((mode+'-quantity-boundary',data))
        data=deepcopy(base);data.update(mode=mode,passages=deepcopy(contexts))
        if mode=='verify':data['proposed']='4000000'
        cases.append((mode+'-eighth-conflict',data))
    data=deepcopy(base);data.update(mode='verify',passages=deepcopy(contexts),proposed='4000000',
        proof={'operation':'scale_table_count','premises':[{'role':'column_header','value':'Chairs (millions)'},{'role':'coefficient','value':'4'}]})
    cases.append(('table-proof-eighth-conflict',data))
    data=deepcopy(base);data.update(mode='verify',proposed='Maple United and Cedar FC',
        selected_spans=['Maple United','Cedar FC'],constraints={'kind':'text','member_count':2},
        passages=deepcopy(contexts))
    data['passages'][0].update(text='Maple United and Cedar FC played in Cedar City.',
        source_fields={'Name':'Cedar City','Text':'Preserve  two spaces, quotes " and Unicode: \u6797\u3002'},
        source_start=13,source_end=58)
    cases.append(('member-fields-and-unicode',data))
    data=deepcopy(base);data.update(mode='verify',passages=deepcopy(contexts),proposed='4 million',
        proof={'operation':'compose_fields','premises':[{'source':'https://example.org/0','locator':'table[0]/row[0]',
               'span':'actual  source row','value':'4','role':'field'}]})
    cases.append(('literal-proof-premises',data))
    cases=[(name+'-'+regime,deepcopy(data),regime) for name,data in cases
           for regime in ['fits-initial','fits-compact','cannot-fit']]
    for name,data,regime in cases:
        original=deepcopy(data);counter=Counter()
        runtime=module.Runtime.__new__(module.Runtime);runtime.torch=object();runtime.tokenizer=counter
        # The cap is determined from the actual first packing, so exactly one
        # passage removal or legacy hard cut makes the historical pack fit.
        class Limit:
            def value(self):return 10 if regime=='cannot-fit' else counter.first_size+(1 if regime=='fits-initial' else -1)
            def __gt__(self,other):return self.value()>other
            def __lt__(self,other):return self.value()<other
        runtime.context_limit=Limit()
        result=None;intercepted=False
        try:result=runtime.infer(data)
        except Packed:intercepted=True
        unchanged=data==original
        packed=json.loads(counter.packed[1]['content']) if counter.packed else None
        expected=(result and result.get('error')=='context_limit' and not intercepted) if regime=='cannot-fit' else (intercepted and packed==original)
        rows.append({'id':name,'passed':bool(unchanged and expected),
                     'input':original,'after_packing':data,'result':result,'intercepted_generation':intercepted,
                     'source_context_unchanged':unchanged,'first_counter_units':counter.first_size,
                     'lost_ids':sorted({p['id'] for p in original['passages']}-{p['id'] for p in data['passages']}),
                     'quantity_prefix_exposed':any(p['text'].endswith('Elm Hall has 4') for p in data['passages'])})
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();out=Path(args.out)
    if out.exists():raise FileExistsError(out)
    old,revision,hashes=load_engine('229bb5a');before=diagnose(old);after=diagnose(Engine)
    report={'scope':__doc__,'baseline':revision,'baseline_hashes':hashes,'before':before,'after':after,
            'before_passed':sum(r['passed'] for r in before),'after_passed':sum(r['passed'] for r in after),'total':len(after),
            'torch_imported':'torch' in sys.modules,'diagnostic_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'production_sha256':{p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path('agent').glob('*.py'))}}
    report['wins']=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']]
    report['losses']=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']]
    out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','torch_imported']}))
    print(json.dumps([{'id':r['id'],'lost_ids':r['lost_ids'],'quantity_prefix_exposed':r['quantity_prefix_exposed']} for r in after]))
    if not all(r['passed'] for r in after):sys.exit(1)
