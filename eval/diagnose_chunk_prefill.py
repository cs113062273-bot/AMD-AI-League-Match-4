"""Real tiny CPU Qwen3 equivalence/cancellation tests; not model accuracy."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent.chunk_prefill import prefill


def diagnose():
    import torch
    from transformers import Qwen3Config,Qwen3ForCausalLM
    torch.manual_seed(1917)
    torch.set_num_threads(1)
    config=Qwen3Config(vocab_size=128,hidden_size=64,intermediate_size=128,num_hidden_layers=2,
                       num_attention_heads=4,num_key_value_heads=2,head_dim=16)
    config._attn_implementation='sdpa'
    model=Qwen3ForCausalLM(config).eval()
    rows=[]
    class Control:
        def check(self):pass
    with torch.inference_mode():
        for length in [1,17,32,33,65,129,257]:
            ids=torch.randint(3,127,(1,length));mask=torch.ones_like(ids)
            inputs={'input_ids':ids,'attention_mask':mask}
            original=ids.clone();record={}
            baseline=model.generate(**inputs,max_new_tokens=12,do_sample=False,pad_token_id=0,eos_token_id=None,logits_to_keep=1)
            cache=prefill(model,inputs,torch,Control(),record,chunk_size=16)
            prefix_length=cache.get_seq_length() if cache is not None else 0
            result=model.generate(**inputs,past_key_values=cache,use_cache=True,max_new_tokens=12,
                                   do_sample=False,pad_token_id=0,eos_token_id=None,logits_to_keep=1)
            rows.append({'id':'equivalent-'+str(length),'passed':torch.equal(baseline,result)
                         and torch.equal(ids,original) and prefix_length==length-1
                         and record['prefill_tokens']==length-1,'length':length,'prefix_length':prefix_length,
                         'chunks':record['prefill_chunks']})
        ids=torch.randint(3,127,(1,129));record={}
        class Stop(Control):
            calls=0
            def check(self):
                self.calls+=1
                if self.calls==2:raise InterruptedError('cancelled between chunks')
        try:prefill(model,{'input_ids':ids,'attention_mask':torch.ones_like(ids)},torch,Stop(),record,chunk_size=16);stopped=False
        except InterruptedError:stopped=True
        rows.append({'id':'cancel-between-prefix-chunks','passed':stopped and record['prefill_tokens']==16
                     and record['prefill_chunks']==1})
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();out=Path(args.out)
    if out.exists():raise FileExistsError(out)
    rows=diagnose()
    report={'scope':__doc__,'passed':sum(r['passed'] for r in rows),'total':len(rows),'rows':rows,
            'source_sha256':{p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in
                             [Path(__file__),ROOT/'agent/chunk_prefill.py',ROOT/'agent/model_server.py']}}
    with out.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2)
    print(json.dumps({'passed':report['passed'],'total':len(rows),'failures':[r['id'] for r in rows if not r['passed']]}))
    if report['passed']!=len(rows):sys.exit(1)
