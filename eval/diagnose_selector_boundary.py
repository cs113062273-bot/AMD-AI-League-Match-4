"""Actual HTTP client check of sent IDs, literal spans and safe abstention; no LLM."""
import argparse
import asyncio
import hashlib
import importlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent import selector
from agent.planner import plan_query
from agent.types import Candidate,Deadline,Page,Passage,Settings
from revision_engine import load_engine


async def diagnose(select):
    requests=[];mode='';url='https://example.com/evidence'
    replies={
        'unsent-zero':{'candidate':0,'passage':-1,'answer':''},
        'unsent-copy':{'candidate':0,'passage':-1,'answer':'Hidden value'},
        'unsent-second':{'candidate':1,'passage':-1,'answer':''},
        'valid-zero':{'passage':0,'answer':'R8'},
        'valid-last':{'candidate':-1,'passage':7,'answer':'S7'},
        'unsent-passage':{'candidate':-1,'passage':8,'answer':'S8'},
        'unsent-text':{'passage':0,'answer':'Hidden value'},
        'boolean-id':{'candidate':True,'passage':-1,'answer':''},
        'mixed-mode':{'candidate':0,'passage':0,'answer':'R8'},
        'abstain':{'candidate':-1,'passage':-1,'answer':''},
    }
    async def endpoint(request):
        requests.append(await request.json())
        return web.json_response(replies[mode])
    app=web.Application();app.router.add_post('/select',endpoint)
    runner=web.AppRunner(app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    rows=[]
    try:
        plan=plan_query('What is the code?',url)
        passages=[Passage('Code: R8')]+[Passage('Other code: S'+str(i)) for i in range(1,9)]
        page=Page(url,passages=passages)
        local=[Candidate('Hidden value','Hidden value',url,'Hidden value',score=10),
               Candidate('Other hidden value','Other hidden value',url,'Other hidden value',score=9)]
        ranked=[(page,p,8) for p in passages]
        for mode in replies:
            chosen,state=await select(plan,local,ranked,Settings(model_url=base),Deadline(5))
            expected='R8' if mode=='valid-zero' else 'S7' if mode=='valid-last' else None
            expected_state='span' if expected else 'abstain' if mode=='abstain' else 'invalid_schema' if mode=='boolean-id' else 'invalid_selection'
            sent=requests[-1]
            passed=(chosen.answer if chosen else None)==expected and state==expected_state
            passed=passed and sent['candidates']==[] and [p['id'] for p in sent['passages']]==list(range(8))
            rows.append(dict(id=mode,passed=passed,state=state,answer=chosen.answer if chosen else None))
    finally:await runner.cleanup()
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('254741a')
    old_select=importlib.import_module(old.__module__.rsplit('.',1)[0]+'.selector').select
    before=asyncio.run(diagnose(old_select));after=asyncio.run(diagnose(selector.select))
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,before=before,after=after,
                before_passed=sum(r['passed'] for r in before),after_passed=sum(r['passed'] for r in after),total=len(after),
                wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
                losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
                selector_sha256=hashlib.sha256((ROOT/'agent/selector.py').read_bytes()).hexdigest())
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    if not all(r['passed'] for r in after):sys.exit(1)
