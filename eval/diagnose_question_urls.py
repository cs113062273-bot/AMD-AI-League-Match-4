"""CPU-only URL extraction and actual local HTTP paths, with models disabled.

Source handlers accept only exact expected request targets. This measures
source selection/transport, not Qwen or public-web answer accuracy.
"""
import argparse
import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from agent.engine import Engine
from agent.planner import plan_query
from agent.types import Settings
from agent.urls import text_urls
from revision_engine import load_engine


def cases():
    base='https://example.org'
    rows=[
        ('plain','Read '+base+'/docs',base+'/docs'),
        ('internal-parentheses','Read '+base+'/Plum_(tree)?',base+'/Plum_(tree)'),
        ('nested-parentheses','Read '+base+'/Plum_(tree_(fruit))',base+'/Plum_(tree_(fruit))'),
        ('outer-parentheses','Read ('+base+'/Plum_(tree))?',base+'/Plum_(tree)'),
        ('markdown','Read [source]('+base+'/Plum_(tree)).',base+'/Plum_(tree)'),
        ('outer-square','Read ['+base+'/Plum_(tree)].',base+'/Plum_(tree)'),
        ('angle','Read <'+base+'/Plum_(tree)>.',base+'/Plum_(tree)'),
        ('double-quote','Read "'+base+'/Plum_(tree)".',base+'/Plum_(tree)'),
        ('single-quote',"Read '"+base+"/Plum_(tree)'.",base+'/Plum_(tree)'),
        ('backtick','Read `'+base+'/Plum_(tree)`.',base+'/Plum_(tree)'),
        ('angle-unmatched-close','Read <'+base+'/literal)>',base+'/literal)'),
        ('quote-unmatched-open','Read "'+base+'/literal("',base+'/literal('),
        ('unclosed-original','Read '+base+'/literal_(tree',base+'/literal_(tree'),
        ('percent-encoding','Read '+base+'/Plum_%28tree%29?x=%2f&x=%2F',base+'/Plum_%28tree%29?x=%2f&x=%2F'),
        ('query-delimiters','Read '+base+'/lookup?filter=(a,b)&fields[]=name',base+'/lookup?filter=(a,b)&fields[]=name'),
        ('query-terminal-punctuation','Read '+base+'/lookup?token=a,b;',base+'/lookup?token=a,b;'),
        ('query-question-mark','Read '+base+'/lookup?q=why?',base+'/lookup?q=why?'),
        ('signed-query','Read '+base+'/file?utm_source=keep&sig=a%2Bb&x=1&x=2;',base+'/file?utm_source=keep&sig=a%2Bb&x=1&x=2;'),
        ('bare-period','Read '+base+'/docs.',base+'/docs'),
        ('bare-comma','Read '+base+'/docs, then continue.',base+'/docs'),
        ('quoted-period','Read "'+base+'/file."',base+'/file.'),
        ('markdown-period','Read [file]('+base+'/file.).',base+'/file.'),
        ('bare-empty-query','Read '+base+'/docs?',base+'/docs'),
        ('quoted-empty-query','Read "'+base+'/docs?"',base+'/docs?'),
        ('apostrophe','Read '+base+"/O'Brien",base+"/O'Brien"),
        ('quoted-apostrophe','Read "'+base+"/O'Brien\"",base+"/O'Brien"),
        ('ipv6','Read http://[2001:db8::1]:8080/Plum_(tree)','http://[2001:db8::1]:8080/Plum_(tree)'),
        ('uppercase','Read HTTPS://EXAMPLE.ORG/Plum_(tree)','HTTPS://EXAMPLE.ORG/Plum_(tree)'),
        ('two-urls','Read '+base+'/Plum_(tree) and https://other.example.net/docs',base+'/Plum_(tree)'),
        ('inner-url','Read '+base+'/go?next=https://other.example.net/docs',base+'/go?next=https://other.example.net/docs'),
        ('fragment','Read '+base+'/Plum_(tree)#details',base+'/Plum_(tree)#details'),
        ('malformed-ipv6','Read https://[broken','https://[broken'),
        ('no-url','What is the title?',''),
        ('non-http','Read ftp://example.org/docs',''),
    ]
    return rows


def direct(planner):
    rows=[]
    for name,question,expected in cases():
        error=None;actual=None
        try:actual=planner(question).url
        except Exception as exc:error=type(exc).__name__
        rows.append(dict(id=name,passed=actual==expected and error is None,actual=actual,expected=expected,error=error))
    explicit='https://explicit.example.org/docs/(a)?sig=value;'
    plan=planner('Read https://other.example.net/ignored_(item)',explicit)
    rows.append(dict(id='explicit-precedence',passed=plan.url==explicit,actual=plan.url,expected=explicit))
    return rows


async def http(engine):
    base='';hits=[];rows=[]
    variants=[
        ('bare','/docs/Plum_(tree)',lambda u:'What is the title at '+u+'?'),
        ('markdown','/docs/Plum_(tree)',lambda u:'What is the title at [source]('+u+')?'),
        ('nested','/docs/Plum_(tree_(fruit))',lambda u:'What is the title at '+u+'?'),
        ('query','/lookup?filter=(a,b)&fields[]=name',lambda u:'What is the title at '+u),
        ('encoded','/docs/Plum_%28tree%29?x=%2f&x=%2F',lambda u:'What is the title at '+u),
        ('signed','/lookup?utm_source=keep&sig=s%2C&x=1&x=2;',lambda u:'What is the title at '+u),
        ('unmatched','/docs/unmatched)',lambda u:'What is the title at "'+u+'"?'),
        ('terminal-period','/docs/version.',lambda u:'What is the title at <'+u+'>?'),
        ('apostrophe',"/docs/O'Brien",lambda u:'What is the title at '+u),
        ('plain','/docs/plain',lambda u:'What is the title at '+u+'?'),
        ('explicit','/docs/Plum_(tree)',lambda u:'What is the title at https://other.example.net/ignored_(item)?'),
    ]
    allowed={path for name,path,question in variants}
    async def source(request):
        hits.append(request.raw_path)
        if request.raw_path not in allowed:return web.Response(status=404)
        return web.Response(text='<title>Cobalt Guide</title><h1>Cobalt Guide</h1>',content_type='text/html')
    app=web.Application();app.router.add_get('/{tail:.*}',source);runner=web.AppRunner(app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    try:
        for name,path,question in variants:
            hits.clear();url=base+path;error=None;result=None
            try:result=await engine(Settings(model_url='',search=False,allow_private=True,max_depth=0,budget=3)).run(question(url),url if name=='explicit' else '')
            except Exception as exc:error=type(exc).__name__
            passed=error is None and hits==[path] and result.answer=='Cobalt Guide' and result.sources==[url]
            rows.append(dict(id='http-'+name,passed=passed,expected_target=path,actual_targets=list(hits),error=error,result=result.internal() if result else None))
        for name,question in [
            ('private', 'What is the title at '+base+'/docs/Plum_(tree)?'),
            ('credentials','What is the title at '+base.replace('://','://sample:sample@')+'/docs/plain?'),
            ('malformed','What is the title at https://[broken'),
        ]:
            hits.clear();error=None;result=None
            try:result=await engine(Settings(model_url='',search=False,allow_private=False,max_depth=0,budget=3)).run(question)
            except Exception as exc:error=type(exc).__name__
            passed=not hits and error is None and not result.answer and not result.sources
            passed=passed and result.reason!='engine_error'
            rows.append(dict(id='guard-'+name,passed=passed,actual_targets=list(hits),error=error,result=result.internal() if result else None))
    finally:await runner.cleanup()
    return rows


def corpus(planners):
    rows=[];inputs=[];total=0;explicit=0;inline=0
    for filename in ['external-simpleqa20.json','external-simpleqa100.json','external-transfer100-v2.json',
                     'external-disjoint12-20261023.json','external-disjoint12b-20261023.json']:
        path=ROOT/'benchmarks'/filename;inputs.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        for case in json.loads(path.read_text(encoding='utf-8')):
            total+=1;explicit+=bool(case.get('url'));inline+=bool(text_urls(case['query']))
            plans=[asdict(planner(case['query'],case.get('url',''))) for planner in planners]
            if plans[0]!=plans[1]:rows.append(dict(id=case['id'],changed={key:[plans[0][key],plans[1][key]] for key in plans[0] if plans[0][key]!=plans[1][key]}))
    return dict(scope='Static planning of previously exposed questions and original starting URLs only; no fetch/reader/model and no unseen sample. Explicit starting URLs do not exercise URL extraction from prose.',
                inputs=inputs,total=total,explicit_starting_urls=explicit,inline_url_questions=inline,changes=rows)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    old,revision,hashes=load_engine('b02880a');old_planner=old.run.__globals__['plan_query']
    before=direct(old_planner)+asyncio.run(http(old));after=direct(plan_query)+asyncio.run(http(Engine))
    report=dict(scope=__doc__,baseline_revision=revision,baseline_source_sha256=hashes,before=before,after=after,
                before_passed=sum(r['passed'] for r in before),after_passed=sum(r['passed'] for r in after),total=len(after),
                wins=[a['id'] for b,a in zip(before,after) if a['passed'] and not b['passed']],
                losses=[a['id'] for b,a in zip(before,after) if b['passed'] and not a['passed']],
                corpus=corpus([old_planner,plan_query]),
                extractor_checks=[
                    dict(id='multiple-order',passed=text_urls('Read https://example.org/a_(b) and https://other.example.net/c')==['https://example.org/a_(b)','https://other.example.net/c']),
                    dict(id='nested-query-url-is-not-second-source',passed=text_urls('Read https://example.org/go?next=https://other.example.net/c')==['https://example.org/go?next=https://other.example.net/c']),
                ],
                production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('agent').glob('*.py')})
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['before_passed','after_passed','total','wins','losses']}))
    print(json.dumps({'exposed_planning_changes':report['corpus']['changes']}))
    if not all(r['passed'] for r in after+report['extractor_checks']):sys.exit(1)
