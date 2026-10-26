"""CPU budget/cleanup controls using actual failed memory snapshots; not accuracy."""
import argparse
import asyncio
from contextlib import redirect_stderr
import io
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.gpu_memory import configure, reclaim, MIB
from agent.model_server import Runtime, make_server
from eval.diagnose_model_service import ProbeRuntime, http_probe
from agent.model_client import request_model
from agent.types import Settings, Deadline


class Cuda:
    def __init__(self, free=11*1024*MIB, total=12*1024*MIB, reserved=0, allocated=0):
        self.free, self.total, self.reserved, self.allocated = free, total, reserved, allocated
        self.fractions, self.clears = [], 0
        self.memory = SimpleNamespace(set_per_process_memory_fraction=self.fractions.append)
        self.fail = False

    def mem_get_info(self):return self.free, self.total
    def memory_reserved(self):return self.reserved
    def memory_allocated(self):return self.allocated
    def empty_cache(self):
        if self.fail:raise RuntimeError('cleanup sentinel')
        self.clears += 1
        self.reserved = self.allocated


async def diagnose():
    rows = []
    cuda = Cuda(free=12*1024*MIB)
    torch = SimpleNamespace(cuda=cuda)
    with patch.dict(os.environ, {'APERTURE_GPU_MEMORY_FRACTION': '.9'}):
        budget = configure(torch, 'cuda')
    rows.append({'id':'default-budget','passed':budget['budget_bytes']==int(cuda.total*.9)
                 and cuda.fractions==[budget['budget_bytes']/cuda.total] and budget['effective_fraction']<=.9})
    scarce = Cuda(free=6*1024*MIB)
    with patch.dict(os.environ, {'APERTURE_GPU_MEMORY_FRACTION': '.9'}):
        limited = configure(SimpleNamespace(cuda=scarce),'cuda')
    rows.append({'id':'preserve-other-process-headroom','passed':limited['budget_bytes']==scarce.free-512*MIB
                 and limited['budget_bytes']<scarce.total*.9})
    for value in ['0','-1','1.1','nan','inf','bad']:
        cuda.fractions.clear()
        with patch.dict(os.environ, {'APERTURE_GPU_MEMORY_FRACTION':value}):
            try:configure(torch,'cuda');rejected=False
            except ValueError:rejected=True
        rows.append({'id':'reject-budget-'+value,'passed':rejected and not cuda.fractions})
    with patch.dict(os.environ, {'APERTURE_GPU_MEMORY_FRACTION':'bad'}):
        rows.append({'id':'cpu-does-not-touch-gpu','passed':configure(object(),'cpu') is None})
    cuda.free=256*MIB
    with patch.dict(os.environ, {'APERTURE_GPU_MEMORY_FRACTION':'.9'}):
        try:configure(torch,'cuda');rejected=False
        except RuntimeError:rejected=True
    rows.append({'id':'no-usable-free-memory','passed':rejected and not cuda.fractions})
    for name,reserved,allocated,expected in [
        ('actual-2179-stall',12922650624,8241774080,True),
        ('actual-mixed-guard',11576279040,8061994496,True),
        ('normal-short-cache',9294577664,8061994496,False),
        ('no-unused-blocks',11000000000,11000000000,False)]:
        c=Cuda(reserved=reserved,allocated=allocated)
        b={'budget_bytes':int(12878086144*.9)}
        actual=reclaim(SimpleNamespace(cuda=c),b)
        rows.append({'id':name,'passed':actual==expected and c.allocated==allocated
                     and c.clears==int(expected),'trimmed':actual})
    lifecycle, _ = await http_probe()
    rows.extend(lifecycle)
    runtime=ProbeRuntime()
    c=Cuda(reserved=11576279040,allocated=8061994496)
    runtime.torch=SimpleNamespace(cuda=c)
    runtime.gpu_memory_budget={'budget_bytes':int(12878086144*.9)}
    runtime.cache_trim_count=runtime.cache_trim_errors=0
    runtime.trim_cache=lambda:Runtime.trim_cache(runtime)
    server=make_server(runtime,0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    settings=Settings(model_url='http://127.0.0.1:'+str(server.server_port))
    data={'question':'next','passages':[{'id':0,'text':'x: 7'}]}
    try:
        reply,state=await request_model(settings,Deadline(3),'/select',data)
        rows.append({'id':'http-trim-before-idle','passed':state=='ok' and reply['answer']=='7'
                     and runtime.active is None and runtime.cache_trim_count==1 and c.allocated==8061994496})
        c.reserved=11576279040;c.fail=True
        errors=io.StringIO()
        with redirect_stderr(errors):reply,state=await request_model(settings,Deadline(3),'/select',data)
        rows.append({'id':'cleanup-error-releases-admission','passed':state=='ok' and runtime.cache_trim_errors==1
                     and runtime.active is None and not runtime.lock.locked() and 'cleanup sentinel' in errors.getvalue()})
        c.fail=False
        reply,state=await request_model(settings,Deadline(3),'/select',data)
        rows.append({'id':'next-after-cleanup-error','passed':state=='ok' and reply['answer']=='7' and runtime.cache_trim_count==2})
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);args=parser.parse_args()
    out=Path(args.out)
    if out.exists():raise FileExistsError(out)
    rows=asyncio.run(diagnose())
    report={'scope':__doc__,'passed':sum(r['passed'] for r in rows),'total':len(rows),'rows':rows,
            'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                             [Path(__file__),ROOT/'agent/model_server.py',ROOT/'agent/gpu_memory.py']}}
    with out.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2)
    print(json.dumps({'passed':report['passed'],'total':len(rows),'failures':[r['id'] for r in rows if not r['passed']]}))
    if report['passed']!=len(rows):sys.exit(1)
