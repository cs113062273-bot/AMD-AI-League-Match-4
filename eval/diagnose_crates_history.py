"""Authored crates.io historical metadata controls, actual loopback HTTP and CPU stubs.

Not independent held-out questions or resident-model accuracy.
"""
import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import aiohttp
from aiohttp import web
from agent.engine import Engine
from agent.types import Settings
from revision_engine import load_engine

NAME='river-sample'
OLD={'id':1,'crate':NAME,'num':'1.0.0','created_at':'2019-01-02T00:00:00Z','yanked':False,
    'license':'BSD-3-Clause','description':'Old description','homepage':'https://example.org/old'}
NEW={**OLD,'id':2,'num':'2.0.0','created_at':'2022-01-02T00:00:00Z','license':'MIT',
    'description':'Current description','homepage':'https://example.org/current'}


async def diagnose(engine):
    mode='';hits=[];calls=[];rows=[]
    async def source(request):
        hits.append(request.path_qs)
        if request.path=='/external':return web.Response(text='<p>On 2020-12-31 license: BSD-3-Clause</p>',content_type='text/html')
        if not request.path.startswith('/api/'):
            return web.Response(text='<h1>River Sample</h1><p>license: MIT</p><p>description: Current description</p>',content_type='text/html')
        if mode=='http-403':return web.json_response({'errors':[]},status=403)
        if mode=='http-429':return web.json_response({'errors':[]},status=429,headers={'Retry-After':'0'})
        old=deepcopy(OLD);new=deepcopy(NEW)
        if mode=='missing-field':old.pop('license')
        if mode=='missing-date':old.pop('created_at')
        if mode=='invalid-time':old['created_at']='2019-01-02T99:99:00Z'
        if mode=='date-only':old['created_at']='2019-01-02'
        if mode=='naive-time':old['created_at']='2019-01-02T00:00:00'
        if mode=='foreign-row':old['crate']='another-crate'
        if mode in {'yanked','explicit-yanked'}:old['yanked']=True
        if mode=='missing-yanked':old.pop('yanked')
        versions=[new,old]
        if mode=='empty-history':versions=[]
        if mode=='unknown-higher':new.pop('created_at')
        if mode=='duplicate-label':versions.append({**old,'id':3,'license':'ISC'})
        if mode in {'semver-build-tie','explicit-build'}:versions.append({**old,'id':3,'num':'1.0.0+other','license':'ISC'})
        if mode in {'preview','stable-default','named-beta','explicit-preview','explicit-preview-question'}:
            versions.append({**old,'id':3,'num':'1.1.0-custom.10','license':'Apache-2.0'})
        if mode=='numeric-order':
            versions.extend([{**old,'id':3,'num':'1.9.0','license':'ISC'},{**old,'id':4,'num':'1.10.0','license':'Apache-2.0'}])
        crate={'id':NAME,'name':NAME,'description':'Current description','homepage':'https://example.org/current',
            'max_stable_version':'2.0.0','num_versions':len(versions),'versions':[v['id'] for v in versions]}
        if mode=='wrong-root':crate['name']='another-crate'
        if mode=='wrong-root-id':crate['id']='another-crate'
        if mode=='missing-count':crate.pop('num_versions')
        if mode=='missing-id-list':crate.pop('versions')
        if mode=='invalid-semver':old['num']='1.02.0'
        if mode=='duplicate-id':new['id']=old['id'];crate['versions']=[old['id'],old['id']]
        if mode=='incomplete-catalog':crate['num_versions']+=1
        if mode=='wrong-id-list':crate['versions']=[999]
        data={'crate':crate,'versions':versions}
        if re.search(r'/\d',request.path):
            label=request.path.rsplit('/',1)[-1];record=next((v for v in versions if v['num']==label),None)
            data={'version':record}
            if mode=='wrong-version' and record:record['num']='9.0.0'
        if mode=='named-beta':data=json.loads(json.dumps(data).replace(NAME,'beta'))
        return web.json_response(data,status=206 if mode=='partial' else 200)

    async def model(request):
        data=await request.json();calls.append(request.path)
        if request.path=='/verify':return web.json_response({'supported':mode!='semantic-reject'})
        question=data['question'].lower()
        field='description' if 'description' in question else r'homepage(?: URL)?' if 'homepage' in question else 'license'
        for p in data.get('passages',[]):
            match=re.search(r'\b'+field+r':\s*([^|]+)',p['text'])
            if match:return web.json_response({'passage':p['id'],'answer':match[1].strip()})
        return web.json_response({'passage':-1,'answer':''})

    app=web.Application();app.router.add_get('/{tail:.*}',source);app.router.add_post('/{tail:.*}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    original=aiohttp.ClientSession._request
    async def transport(self,method,url,*args,**kwargs):
        parsed=urlsplit(str(url))
        if parsed.hostname in {'crates.io','www.crates.io'}:url=base+parsed.path+('?' +parsed.query if parsed.query else '')
        elif parsed.hostname!='127.0.0.1':raise ValueError('Unexpected external request')
        return await original(self,method,url,*args,**kwargs)
    checks=[('snapshot','BSD-3-Clause'),('description','Old description'),('homepage','https://example.org/old'),
        ('current','Current description'),('preview','Apache-2.0'),('stable-default','BSD-3-Clause'),
        ('named-beta','BSD-3-Clause'),('numeric-order','Apache-2.0'),('question-only','BSD-3-Clause'),
        ('api-start','BSD-3-Clause'),('explicit-question','BSD-3-Clause'),('explicit-url','BSD-3-Clause'),
        ('explicit-api-url','BSD-3-Clause'),('year','BSD-3-Clause'),
        ('explicit-yanked','BSD-3-Clause'),('explicit-preview','Apache-2.0'),
        ('explicit-preview-question','Apache-2.0'),('explicit-build','ISC'),('no-model','BSD-3-Clause'),
        ('timeless-pinned-api','BSD-3-Clause'),
        *[(m,'') for m in ['missing-field','missing-date','invalid-time','date-only','naive-time','foreign-row','yanked','missing-yanked',
            'empty-history','unknown-higher','duplicate-label','semver-build-tie','wrong-root','incomplete-catalog',
            'wrong-id-list','wrong-version','partial','http-403','http-429','semantic-reject','conflicting-name',
            'conflicting-version','future-version','wrong-root-id','missing-count','missing-id-list','invalid-semver','duplicate-id']]]
    try:
        with patch.object(aiohttp.ClientSession,'_request',transport):
            for mode,expected in checks:
                hits.clear();calls.clear()
                name='beta' if mode=='named-beta' else NAME
                field='description' if mode in {'description','current'} else 'homepage URL' if mode=='homepage' else 'license'
                temporal='' if mode in {'current','timeless-pinned-api'} else ' in 2019' if mode=='year' else ' as of 2020-12-31'
                prefix='preview release of the ' if mode=='preview' else 'version 1.0.0 of the ' if mode in {'explicit-question','wrong-version','conflicting-version','explicit-yanked'} else 'version 2.0.0 of the ' if mode=='future-version' else 'version 1.1.0-custom.10 of the ' if mode=='explicit-preview-question' else ''
                q=f'What was the {field} of {prefix}crates.io crate {name}{temporal}?'
                start='https://crates.io/crates/'+name
                if mode in {'explicit-url','conflicting-version'}:start+='/'+('2.0.0' if mode=='conflicting-version' else '1.0.0')
                if mode in {'explicit-api-url','timeless-pinned-api'}:start='https://crates.io/api/v1/crates/'+name+'/1.0.0'
                if mode=='explicit-preview':start+='/1.1.0-custom.10'
                if mode=='explicit-build':start+='/1.0.0+other'
                if mode=='api-start':start='https://crates.io/api/v1/crates/'+name
                if mode=='question-only':start=''
                if mode=='conflicting-name':start=start.replace(name,'another-crate')
                result=await engine(Settings(model_url='' if mode=='no-model' else base,search=False,browser=False,allow_private=True,max_depth=0,budget=12)).run(q,start)
                passed=result.answer==expected and (bool(result.sources) if expected else not result.sources)
                if mode=='http-429':passed &= sum('/api/' in u for u in hits)==1
                if mode in {'conflicting-name','conflicting-version'}:passed &= not hits
                if mode=='no-model':passed &= not calls
                rows.append(dict(id=mode,passed=bool(passed),expected=expected,actual=result.answer,
                    local_requests=list(hits),cpu_stub_calls=list(calls),result=result.internal()))
            mode='external';hits.clear();calls.clear()
            result=await engine(Settings(model_url=base,search=False,browser=False,allow_private=True,max_depth=0,budget=12)).run(
                f'What was the license of the crates.io crate {NAME} as of 2020-12-31?',base+'/external')
            rows.append(dict(id='external-dated',passed=result.answer=='BSD-3-Clause' and result.sources==[base+'/external'],result=result.internal()))
    finally:await runner.cleanup()
    return rows


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--baseline');ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    engine=Engine;revision='working-tree';hashes={}
    if args.baseline:engine,revision,hashes=load_engine(args.baseline)
    rows=asyncio.run(diagnose(engine))
    report=dict(scope=__doc__,revision=revision,baseline_source_sha256=hashes,
        diagnostic_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('app.py'),*sorted(Path('agent').glob('*.py'))]},
        passed=sum(r['passed'] for r in rows),total=len(rows),rows=rows)
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'],total=report['total'],failures=[r['id'] for r in rows if not r['passed']])))
    if report['passed']!=report['total']:sys.exit(1)
