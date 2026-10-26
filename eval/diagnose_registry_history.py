"""CPU registry release metadata: local HTTP with logical API identities, no live score."""
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
from aiohttp import web
from agent.engine import Engine
from agent.types import Settings
from revision_engine import load_engine

NAME='river-sample'
OLD={'name':NAME,'version':'1.0','license':'BSD-3-Clause','author':'Early Author','home_page':'https://example.org/old'}
NEW={'name':NAME,'version':'2.0','license':'MIT','author':'Current Author','home_page':'https://example.org/new'}


def files(day):return [{'upload_time_iso_8601':day+'T00:00:00Z','yanked':False}]


async def diagnose(engine):
    rows=[];mode='';family='';hits=[];logical=[];calls=[]
    old={'info':OLD,'urls':files('2019-01-02')}
    root={'info':NEW,'urls':files('2022-01-02'),'releases':{'1.0':files('2019-01-02'),'2.0':files('2022-01-02')}}
    npm={'name':NAME,'license':'MIT','dist-tags':{'latest':'2.0.0'},'versions':{
        '1.0.0':{'name':NAME,'version':'1.0.0','license':'BSD-3-Clause','author':{'name':'Early Author'}},
        '2.0.0':{'name':NAME,'version':'2.0.0','license':'MIT','author':{'name':'Current Author'}}},
        'time':{'1.0.0':'2019-01-02T00:00:00Z','2.0.0':'2022-01-02T00:00:00Z'}}

    async def source(request):
        hits.append(request.path)
        if request.path=='/external':return web.Response(text='<h1>River Sample historical license</h1><p>On 2020-12-31, license: BSD-3-Clause</p>',content_type='text/html')
        if request.path.startswith('/project/'):
            return web.Response(text='<h1>River Sample</h1><p>license: MIT</p>',content_type='text/html')
        data=deepcopy(npm if family=='npm' else old if '/1.0/' in request.path else root)
        if family=='pypi':
            if mode in {'empty-history','frontend-bypass'}:data['releases']={};data.pop('urls',None)
            if mode=='unknown-higher' and 'releases' in data:data['releases']['2.0']=[]
            if mode=='alias-collision' and 'releases' in data:data['releases']['1.0.0']=files('2019-01-02')
            if '/1.0/' in request.path:
                if mode=='wrong-name':data['info']['name']='other-package'
                if mode=='wrong-version':data['info']['version']='9.0'
                if mode=='missing-field':data['info'].pop('license',None)
                if mode=='missing-date':data['urls']=[]
                if mode=='future-own-date':data['urls']=files('2023-01-02')
                if mode=='invalid-time':data['urls']=[{'upload_time_iso_8601':'2019-01-02T99:99:99Z'}]
                if mode=='description-author':data['info'].pop('author',None);data['info']['description']='author: Early Author'
            if mode=='already-current' and 'releases' in data:
                data={'info':deepcopy(OLD),'urls':files('2019-01-02'),'releases':{'1.0':files('2019-01-02')}}
        else:
            if mode=='empty-history':data['versions']={};data['time']={}
            if mode=='unknown-higher':data['time'].pop('2.0.0')
            if mode=='wrong-name':data['versions']['1.0.0']['name']='other-package'
            if mode=='wrong-version':data['versions']['1.0.0']['version']='9.0.0'
            if mode=='missing-field':data['versions']['1.0.0'].pop('license',None)
            if mode=='missing-date':data['time'].pop('1.0.0')
            if mode=='invalid-time':data['time']['1.0.0']='2019-01-02T99:99:99Z'
            if mode=='description-author':data['versions']['1.0.0'].pop('author',None);data['versions']['1.0.0']['description']='author: Early Author'
            added={'build-tie':['1.0.0+aaa','1.0.0+bbb'],
                'preview':['1.1.0-custom.2','1.1.0-custom.10'],
                'default-stable':['1.1.0-custom.2','1.1.0-custom.10'],
                'named-beta':['1.1.0-custom.2','1.1.0-custom.10'],
                'named-beta-release':['1.1.0-custom.2','1.1.0-custom.10'],
                'numeric-order':['1.9.0','1.10.0']}.get(mode,[])
            for i,version in enumerate(added):
                data['versions'][version]={'name':NAME,'version':version,'license':'BSD-3-Clause' if i==0 else 'Apache-2.0'}
                data['time'][version]='2019-06-01T00:00:00Z'
            if mode=='already-current':
                data['dist-tags']['latest']='1.0.0';data['license']='BSD-3-Clause'
                data['versions'].pop('2.0.0');data['time'].pop('2.0.0')
        if mode.startswith('named-beta'):data=json.loads(json.dumps(data).replace(NAME,'beta'))
        return web.json_response(data)

    async def model(request):
        data=await request.json();calls.append(request.path)
        if request.path=='/verify':return web.json_response({'supported':True})
        field='author' if 'author' in data['question'].casefold() else 'license'
        for p in data.get('passages',[]):
            match=re.search(r'\b'+field+r':\s*([^|]+)',p['text'])
            if match:return web.json_response({'passage':p['id'],'answer':match[1].strip()})
        return web.json_response({'passage':-1,'answer':''})

    app=web.Application();app.router.add_get('/{tail:.*}',source);app.router.add_post('/{tail:.*}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    fetcher=engine.run.__globals__['Fetcher'];original=fetcher.fetch
    async def replay(self,url,**kwargs):
        logical.append(url)
        response=await original(self,base+urlsplit(url).path,**kwargs)
        response.url=url
        if mode=='redirect-lookalike' and '/1.0/' in url:response.url=url.replace('pypi.org','fake.pypi.org')
        if mode=='truncated':response.truncated=True
        return response
    try:
        for family in ['pypi','npm']:
            scenarios=[('snapshot','BSD-3-Clause'),('current','MIT'),('already-current','BSD-3-Clause'),
                ('empty-history',''),('unknown-higher',''),('missing-field',''),('missing-date',''),
                ('wrong-name',''),('wrong-version',''),('author','Early Author'),('description-author','Early Author'),('invalid-time','')]
            if family=='pypi':scenarios += [('future-own-date',''),('redirect-lookalike',''),('truncated',''),('low-budget',''),('frontend-bypass',''),('alias-collision','')]
            else:scenarios += [('build-tie',''),('preview','Apache-2.0'),('default-stable','BSD-3-Clause'),('named-beta','BSD-3-Clause'),('named-beta-release','BSD-3-Clause'),('numeric-order','Apache-2.0')]
            for mode,expected in scenarios:
                hits.clear();logical.clear();calls.clear()
                field='author' if mode in {'author','description-author'} else 'license'
                temporal='' if mode=='current' else ' as of 2020-12-31'
                name='beta' if mode.startswith('named-beta') else NAME
                q=f'What was the {field} of the '+('preview release of the ' if mode=='preview' else '')+f'{family} package {name}'+(' release' if mode=='named-beta-release' else '')+temporal+'?'
                url=('https://pypi.org/project/'+name+'/' if mode=='frontend-bypass' else 'https://pypi.org/pypi/'+name+'/json') if family=='pypi' else 'https://registry.npmjs.org/'+name
                with patch.object(fetcher,'fetch',replay):
                    result=await engine(Settings(model_url=base,search=False,allow_private=True,max_depth=0,
                        budget=3 if mode=='low-budget' else 12)).run(q,url)
                passed=result.answer==expected and (bool(result.sources) if expected else not result.sources)
                if mode=='snapshot' and family=='pypi':passed &= result.sources==['https://pypi.org/pypi/'+NAME+'/1.0/json']
                if mode=='low-budget':passed &= not any('/1.0/' in u for u in logical)
                rows.append(dict(id=family+'-'+mode,passed=bool(passed),expected=expected,actual=result.answer,
                    local_hits=list(hits),logical_requests=list(logical),model_calls=list(calls),result=result.internal()))
            mode='snapshot'
            for label,temporal,model_url in [('no-model',' as of 2020-12-31',''),('year',' in 2019',base)]:
                hits.clear();logical.clear();calls.clear()
                url='https://pypi.org/pypi/'+NAME+'/json' if family=='pypi' else 'https://registry.npmjs.org/'+NAME
                with patch.object(fetcher,'fetch',replay):
                    result=await engine(Settings(model_url=model_url,search=False,allow_private=True,max_depth=0,budget=12)).run(
                        f'What was the license of the {family} package {NAME}'+temporal+'?',url)
                passed=result.answer=='BSD-3-Clause' and bool(result.sources) and (bool(model_url) or not calls)
                rows.append(dict(id=family+'-'+label,passed=passed,expected='BSD-3-Clause',actual=result.answer,
                    logical_requests=list(logical),model_calls=list(calls),result=result.internal()))
        # Explicit releases must survive, and a future release cannot be
        # backdated merely because its version was supplied in the question.
        family='pypi';mode='snapshot'
        for version,expected in [('1.0','BSD-3-Clause'),('2.0','')]:
            hits.clear();logical.clear();calls.clear()
            with patch.object(fetcher,'fetch',replay):
                result=await engine(Settings(model_url=base,search=False,allow_private=True,max_depth=0,budget=12)).run(
                    f'What was the license of version {version} of the PyPI package {NAME} as of 2020-12-31?',
                    'https://pypi.org/pypi/'+NAME+'/json')
            rows.append(dict(id='explicit-'+version,passed=result.answer==expected and (bool(result.sources) if expected else not result.sources),
                expected=expected,actual=result.answer,logical_requests=list(logical),result=result.internal()))
        with patch.object(fetcher,'fetch',replay):
            result=await engine(Settings(model_url=base,search=False,allow_private=True,max_depth=0,budget=12)).run(
                'What was the license of River Sample as of 2020-12-31?',base+'/external')
        rows.append(dict(id='external-dated-source',passed=result.answer=='BSD-3-Clause' and result.sources==[base+'/external'],
            expected='BSD-3-Clause',actual=result.answer,result=result.internal()))
    finally:await runner.cleanup()
    return rows


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
