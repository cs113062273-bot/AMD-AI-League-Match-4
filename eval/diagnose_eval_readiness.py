"""Actual HTTP readiness waits and fail-closed sequencing; no GPU/model restart."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from eval.model_readiness import wait_model_idle,ModelNotReady
from eval import diagnose_reader
from agent.types import Settings,Result


async def diagnose():
    mode='';started=0;methods=[];engine_calls=[]
    async def health(request):
        methods.append((request.method,request.path))
        if mode=='unavailable':return web.Response(status=503)
        if mode=='invalid':return web.json_response({'ready':True})
        busy=mode in {'busy','between-cases'} or mode=='delayed' and time.monotonic()-started<.13
        return web.json_response({'ready':True,'active_request':'a'*32 if busy else None,'pid':42,'busy_rejections':0})
    app=web.Application();app.router.add_get('/health',health);runner=web.AppRunner(app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start();base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);rows=[]
    try:
        for mode,expected in [('idle',True),('delayed',True),('busy',False),('unavailable',False),('invalid',False)]:
            methods.clear();started=time.monotonic();state=await wait_model_idle(base,.35)
            passed=state['ready']==expected and state['wait_seconds']<.8
            if mode=='delayed':passed=passed and state['observations']>1
            if not expected:passed=passed and state['observations']>1
            rows.append(dict(id=mode,passed=passed,state=state,methods=list(methods)))
        mode='idle'
        class FakeEngine:
            def __init__(self,settings):pass
            async def run(self,question,url):
                nonlocal mode
                engine_calls.append(question);mode='between-cases'
                return Result(answer='R8',sources=[url])
        cases=[dict(id=str(i),query='Question '+str(i),url=base+'/source',answer='R8',answers=['R8'],sources=[base+'/source']) for i in range(3)]
        output=[];failure=None;methods.clear()
        with patch.object(diagnose_reader,'memory',lambda:{'used_mib':0}):
            try:await diagnose_reader.run(cases,Settings(model_url=base),'',engine=FakeEngine,live_web=True,rows=output,readiness_timeout=.25)
            except ModelNotReady as exc:failure=exc.state
        rows.append(dict(id='stop-before-next-case',passed=len(output)==1 and engine_calls==['Question 0'] and failure and failure['case_id']=='1',
            retained_rows=len(output),engine_calls=engine_calls,failure=failure,methods=list(methods)))
        rows.append(dict(id='observation-only',passed=all(method=='GET' and path=='/health' for row in rows for method,path in row['methods'])))
    finally:await runner.cleanup()
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    rows=asyncio.run(diagnose());report=dict(scope=__doc__,passed=sum(bool(r['passed']) for r in rows),total=len(rows),rows=rows)
    target.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({'passed':report['passed'],'total':report['total']}))
    if not all(r['passed'] for r in rows):sys.exit(1)
