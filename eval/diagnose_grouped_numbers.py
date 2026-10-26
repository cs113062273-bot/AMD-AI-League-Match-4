"""CPU-only grouped-number literal boundaries; invented examples, no model weights."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.types import Settings
from revision_engine import load_engine


def direct(engine):
    literal=engine.run.__globals__['verify'].__globals__['literal_span'];rows=[]
    negative=[('10','Count: 10,000'),('617','Population: 1,617'),
        ('234','Count: 1,234,567'),('1,234','Count: 1,234,567'),
        ('234,567','Count: 1,234,567'),('234.50','Amount: 1,234.50'),
        ('234 kg','Mass: 1,234 kg'),('$10','Cost: $10,000'),
        ('10,000','Count: -10,000'),('234%','Share: 1,234%')]
    positive=[('10,000','Count: 10,000'),('1,234,567','Count: 1,234,567'),
        ('1,234.50','Amount: 1,234.50'),('1,234 kg','Mass: 1,234 kg'),
        ('$10,000','Cost: $10,000'),('-10,000','Count: -10,000'),
        ('1,234%','Share: 1,234%'),('10','Count: 10,000; reserve: 10'),
        ('617','Count: 1,617; reserve: 617'),('1,234','Count: 1,234, effective today.'),
        ('2014','March 1,2014'),('10','Counts: 10, 20'),('20','Counts: 10, 20')]
    for kind in ['number','measurement','price','percentage','duration','year','time']:
        for expected,cases in [(False,negative),(True,positive)]:
            for i,(answer,text) in enumerate(cases):
                actual=literal(answer,text,kind)
                rows.append(dict(id=kind+'-'+str(expected)+'-'+str(i),passed=actual==expected,
                    expected=expected,actual=actual,answer=answer,evidence=text))
    # Text/version punctuation does not become a numeric delimiter rule.
    for kind in ['text','version']:
        actual=literal('617','Names: 1,617',kind)
        rows.append(dict(id='unchanged-'+kind,passed=actual,expected=True,actual=actual))
    return rows


async def transport(engine):
    selected='';calls=[];rows=[]
    async def source(request):
        return web.Response(text='<h1>Birch Hall</h1><p>Birch Hall seating capacity: 10,000 seats.</p>',content_type='text/html')
    async def model(request):
        data=await request.json();calls.append(request.path)
        if request.path=='/verify':return web.json_response({'supported':True})
        passage=next((p for p in data.get('passages',[]) if '10,000 seats' in p['text']),None)
        return web.json_response({'passage':passage['id'] if passage else -1,'answer':selected if passage else ''})
    app=web.Application();app.router.add_get('/capacity',source);app.router.add_post('/{tail:.*}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    try:
        for selected,expected in [('10,000','10,000'),('10','')]:
            calls.clear()
            result=await engine(Settings(model_url=base,search=False,allow_private=True,max_depth=0,budget=4)).run(
                'How many seats does Birch Hall have?',base+'/capacity')
            rows.append(dict(id='http-'+selected,passed=result.answer==expected
                and result.sources==([base+'/capacity'] if expected else []),
                expected=expected,actual=result.answer,calls=list(calls),result=result.internal()))
    finally:await runner.cleanup()
    return rows


async def diagnose(engine):return direct(engine)+await transport(engine)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--baseline');ap.add_argument('--out',required=True)
    args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    engine=Engine;revision='working-tree';hashes={}
    if args.baseline:engine,revision,hashes=load_engine(args.baseline)
    rows=asyncio.run(diagnose(engine))
    report=dict(scope=__doc__,revision=revision,baseline_source_sha256=hashes,
        diagnostic_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path('app.py'),*sorted(Path('agent').glob('*.py'))]},
        passed=sum(r['passed'] for r in rows),total=len(rows),rows=rows)
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'],total=report['total'],failures=[r['id'] for r in rows if not r['passed']])))
    if report['passed']!=report['total']:sys.exit(1)
