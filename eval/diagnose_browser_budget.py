"""Fresh Chromium with real loopback HTTP, controlled analytics responses only.

No public network or model; tests content delivery within unchanged20-fetch cap.
"""
import argparse
import asyncio
import hashlib
import importlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.browser import render
from agent.network import Fetcher,Response
from agent.types import Settings,Deadline
from benchmarks.fakeweb import FakeWeb
from revision_engine import load_engine


async def diagnose(renderer):
    app="fetch('/data').then(r=>r.json()).then(d=>document.getElementById('app').innerHTML='<p>Orbit capacity: '+d.capacity+'</p>')"
    loop="(async()=>{for(let i=0;i<21;i++){try{await fetch('https://www.google-analytics.com/g/collect?n='+i)}catch(e){}}"+app+"})()"
    routes={
        '/crowded':(200,'text/html','<div id="app">Loading</div><script>'+loop+'</script>'),
        '/ordinary':(200,'text/html','<div id="app">Loading</div><script>'+app+'</script>'),
        '/redirect':(302,'text/html','',{'Location':'/ordinary'}),
        '/data':(200,'application/json','{"capacity":"24 GB"}'),
        '/post':(200,'text/html','<div id="app">Loading</div><script>fetch("/secret",{method:"POST"}).catch(()=>{});'+app+'</script>'),
        '/lookalike':(200,'text/html','<div id="app">Loading</div><script>fetch("https://google-analytics.com.example.org/value").then(r=>r.json()).then(d=>document.getElementById("app").textContent="Orbit capacity: "+d.capacity)</script>'),
    }
    rows=[];original_fetch=Fetcher.fetch
    with FakeWeb(routes) as source:
        for name in ['crowded','ordinary','redirect','post','lookalike']:
            seen=[];deadline=Deadline(9);settings=Settings(browser=True,allow_private=True,model_url='',search=False)
            async def controlled(fetcher,url,**kwargs):
                seen.append(url)
                if url.startswith('https://www.google-analytics.com/'):
                    return Response(url,b'','application/json',status=200,headers={'access-control-allow-origin':'*'})
                if url.startswith('https://google-analytics.com.example.org/'):
                    return Response(url,b'{"capacity":"24 GB"}','application/json',status=200,headers={'access-control-allow-origin':'*'})
                if not url.startswith(source.base+'/'):raise RuntimeError('Unexpected public request')
                return await original_fetch(fetcher,url,**kwargs)
            with patch.object(Fetcher,'fetch',controlled):
                async with Fetcher(settings,deadline) as fetcher:
                    page,state=await renderer(source.base+'/'+name,settings,deadline,fetcher)
            answered=bool(page and any('24 GB' in p.text for p in page.passages))
            passed=answered and state['requests']<=20
            if name=='crowded':passed=passed and state.get('blocked_analytics')==21 and not any('www.google-analytics.com' in u for u in seen)
            if name=='lookalike':passed=passed and any('google-analytics.com.example.org' in u for u in seen)
            if name=='post':passed=passed and source.base+'/secret' not in seen
            if name=='redirect':passed=passed and page.url==source.base+'/ordinary'
            rows.append(dict(id=name,passed=passed,answered=answered,state=state,fetches=seen))
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    engine,revision,hashes=load_engine('3ec6ad3');old=importlib.import_module(engine.__module__.rsplit('.',1)[0]+'.browser').render
    before=asyncio.run(diagnose(old));after=asyncio.run(diagnose(render))
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,before=before,after=after,
        before_passed=sum(row['passed'] for row in before),after_passed=sum(row['passed'] for row in after),total=len(after),
        wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
        losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
        browser_sha256=hashlib.sha256((ROOT/'agent/browser.py').read_bytes()).hexdigest())
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    if not all(row['passed'] for row in after):sys.exit(1)
