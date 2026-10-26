"""Fresh CLI/worker HTTP round trips, with inference and browser disabled.

Only a task-owned loopback server is used. No GPU, model loading or external
network; preserve generated result/trace files under a new local directory.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
from aiohttp import web


async def diagnose(directory):
    hits=[]
    async def source(request):
        hits.append(request.raw_path)
        if request.raw_path not in {'/docs/Plum_(tree)','/lookup?filter=(a,b)&sig=x%2Fy&k=1&k=2;'}:
            return web.Response(status=404)
        return web.Response(text='<title>Cobalt Guide</title><h1>Cobalt Guide</h1>',content_type='text/html')
    app=web.Application();app.router.add_get('/{tail:.*}',source);runner=web.AppRunner(app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);rows=[]
    env={**os.environ,'APERTURE_MODEL_URL':'','APERTURE_BROWSER':'0','APERTURE_SEARCH':'0',
         'APERTURE_BUDGET':'3','PYTHONIOENCODING':'utf-8'}
    try:
        for name,url,private,expected in [
            ('balanced',base+'/docs/Plum_(tree)',True,'Cobalt Guide'),
            ('query',base+'/lookup?filter=(a,b)&sig=x%2Fy&k=1&k=2;',True,'Cobalt Guide'),
            ('private',base+'/docs/Plum_(tree)',False,''),
            ('malformed','https://[broken',False,''),
        ]:
            hits.clear();question='What is the title at '+url
            process=await asyncio.create_subprocess_exec(sys.executable,str(ROOT/'app.py'),
                '--query-id',name,'--query',question,'--output-dir',str(directory),'--diagnostics',
                cwd=ROOT,env={**env,'APERTURE_ALLOW_PRIVATE':'1' if private else '0'},
                stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            stdout,stderr=await asyncio.wait_for(process.communicate(),timeout=9)
            result_path=directory/(name+'_output.json');trace_path=directory/(name+'_output.trace.json')
            result=json.loads(result_path.read_text(encoding='utf-8'));trace=json.loads(trace_path.read_text(encoding='utf-8'))
            expected_result={'answer':expected,'sources':[url] if expected else []}
            passed=process.returncode==0 and not stderr and result==expected_result and json.loads(stdout)==result
            passed=passed and trace.get('reason') not in {'worker_failure','worker_watchdog','engine_error'}
            passed=passed and trace.get('diagnostics',{}).get('llm_calls')==0
            passed=passed and hits==([url[len(base):]] if expected else [])
            rows.append(dict(id=name,passed=passed,exit_code=process.returncode,actual_targets=list(hits),
                result=result,reason=trace.get('reason'),llm_calls=trace.get('diagnostics',{}).get('llm_calls'),
                result_path=result_path.relative_to(ROOT).as_posix(),trace_path=trace_path.relative_to(ROOT).as_posix(),
                result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),trace_sha256=hashlib.sha256(trace_path.read_bytes()).hexdigest()))
    finally:await runner.cleanup()
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--output-dir',required=True);args=ap.parse_args()
    target=Path(args.out);directory=(ROOT/args.output_dir).resolve()
    if target.exists():raise FileExistsError(target)
    if not directory.is_relative_to(ROOT/'research'):raise ValueError('Use a fresh task-owned research directory')
    directory.mkdir(parents=True,exist_ok=False)
    rows=asyncio.run(diagnose(directory))
    report=dict(scope=__doc__,passed=sum(r['passed'] for r in rows),total=len(rows),rows=rows,
                model_url='',browser=False,search=False,
                production_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in [ROOT/'app.py',*(ROOT/'agent').glob('*.py')]})
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'total':report['total'],'failures':[r['id'] for r in rows if not r['passed']]}))
    if report['passed']!=report['total']:sys.exit(1)
