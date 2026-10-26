"""Real fresh headless Chromium integration; local HTTP fixtures, no user profile."""
import asyncio
import json
from pathlib import Path
import sys
import time
import os
import subprocess
import tempfile
import io
from contextlib import redirect_stderr
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from benchmarks.fakeweb import FakeWeb
from agent.engine import Engine
from agent.types import Settings,Deadline
from agent.browser import render
from agent.network import Fetcher,Response


async def exercise():
    routes={
        '/':(200,'text/html','<h1>Orbit specifications</h1><div id="app">Loading</div><script src="/app.js"></script>'),
        '/app.js':(200,'text/javascript',"fetch('/data').then(r=>r.json()).then(d=>{document.getElementById('app').innerHTML='<p>Orbit memory capacity: '+d.memory+'</p>'})"),
        '/data':(200,'application/json','{"memory":"24 GB"}'),
        '/redirect':(302,'text/html','',{'Location':'/'}),
        '/spin':(200,'text/html','<div>Loading</div><script src="/spin.js"></script>'),
        '/spin.js':(200,'text/javascript','while(true){}'),
        '/late':(200,'text/html','<div id="app">Loading</div><script>document.getElementById("app").innerHTML="<p>Orbit memory capacity: 24 GB</p>";fetch("/late-data")</script>'),
        '/late-data':(200,'application/json','{"unrelated":true}',{'X-Delay':'2.5'}),
    }
    rows=[]
    with FakeWeb(routes) as web:
        settings=Settings(budget=9,search=False,model_url='',allow_private=True,browser=True,max_depth=0)
        for path,answer,source in [('/','24 GB','/'),('/redirect','24 GB','/'),('/late','24 GB','/late'),('/spin','','')]:
            began=time.monotonic()
            result=await Engine(settings).run('What is Orbit memory capacity?',web.base+path)
            row={'path':path,'answer':result.answer,'sources':result.sources,'seconds':time.monotonic()-began,
                'browser':result.diagnostics.get('browser',[]),'expected':answer}
            row['ok']=result.answer==answer and (not answer or result.sources==[web.base+source])
            rows.append(row)
        baseline=await Engine(Settings(budget=4,search=False,model_url='',allow_private=True,max_depth=0)).run('What is Orbit memory capacity?',web.base+'/')
        with tempfile.TemporaryDirectory() as directory:
            env=os.environ.copy();env.update(APERTURE_BROWSER='1',APERTURE_ALLOW_PRIVATE='1',APERTURE_SEARCH='0',APERTURE_MODEL_URL='',APERTURE_BUDGET='12',PYTHONIOENCODING='utf-8')
            began=time.monotonic()
            process=subprocess.run([sys.executable,'app.py','--query','What is Orbit memory capacity?','--url',web.base+'/',
                '--output-dir',directory,'--diagnostics'],env=env,capture_output=True,timeout=14)
            data=json.loads(process.stdout)
            trace=json.loads((Path(directory)/'output.trace.json').read_text(encoding='utf-8'))
            rows.append({'test':'fresh CLI browser worker with process/memory limits','ok':process.returncode==0 and data['answer']=='24 GB',
                'answer':data['answer'],'seconds':time.monotonic()-began,'browser':trace.get('diagnostics',{}).get('browser',[])})
        # Public-mode browser must not bypass the Fetcher to reach a private endpoint.
        async with Fetcher(Settings(),Deadline(9)) as fetcher:
            script="setTimeout(()=>{location.href='"+web.base+"/secret'},10)"
            body=('<h1>Public test</h1><script>'+script+'</script>').encode()
            fetcher.cache['http://example.com/']=Response('http://example.com/',body,'text/html')
            page,state=await render('http://example.com/',settings,Deadline(9),fetcher)
            rows.append({'test':'private destination blocked','ok':'/secret' not in web.hits and state.get('blocked',0)>0,'browser':state})
    report={'method':'actual fresh Chromium + loopback HTTP; security case injects a public document cache only',
        'http_only_answer':baseline.answer,'rows':rows,'all_passed':all(row['ok'] for row in rows)}
    return report


async def main():
    errors=io.StringIO()
    with redirect_stderr(errors):
        report=await exercise()
        await asyncio.sleep(.05)
    report['unexpected_stderr']=errors.getvalue()[:4000]
    report['all_passed']=report['all_passed'] and not report['unexpected_stderr'] and not report['http_only_answer']
    Path('benchmarks/browser-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
    if not report['all_passed']:raise RuntimeError('Browser validation failed')


if __name__=='__main__':asyncio.run(main())
