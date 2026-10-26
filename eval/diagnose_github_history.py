"""GitHub historical license source joins: actual local HTTP and explicit CPU stubs."""
import argparse
import asyncio
import base64
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

REPO='example/river-sample';REF='a'*40;OTHER='b'*40
QUERY=f'What was the license of the GitHub repository {REPO} as of 2020-12-31?'


async def diagnose(engine):
    mode='';hits=[];calls=[];rows=[];payloads=[]
    async def source(request):
        hits.append(request.path_qs)
        if request.path=='/external':return web.Response(text='<p>On 2020-12-31 the license: BSD-3-Clause</p>',content_type='text/html')
        if request.path.endswith('/commits') or '/commits/' in request.path:
            if mode=='commit-403':return web.json_response({'message':'limited'},status=403,headers={'X-RateLimit-Remaining':'0'})
            if mode=='commit-429':return web.json_response({'message':'limited'},status=429,headers={'Retry-After':'0'})
            if mode=='commit-500':return web.json_response({'message':'unavailable'},status=500)
            commit={'sha':REF,'url':f'https://api.github.com/repos/{REPO}/commits/{REF}',
                'commit':{'committer':{'date':'2019-12-30T12:00:00Z'}}}
            if mode=='future':commit['commit']['committer']['date']='2021-01-01T00:00:00Z'
            if mode=='invalid-date':commit['commit']['committer']['date']='2019-12-30T99:99:00Z'
            if mode=='boundary':commit['commit']['committer']['date']='2021-01-01T00:00:00Z'
            if mode=='missing-date':commit['commit']['committer'].pop('date')
            if mode=='wrong-commit-repo':commit['url']=commit['url'].replace('example/','other/')
            if mode=='bad-sha':commit['sha']='short'
            if mode=='canonical-case':commit['url']=commit['url'].replace(REPO,'Example/River-Sample')
            data=[] if mode=='no-commit' else [commit,deepcopy(commit)] if mode=='multiple' else [commit]
            headers={'X-RateLimit-Remaining':'0'} if mode=='last-credit' else {}
            if '/commits/' in request.path:data=commit
            return web.json_response(data,headers=headers)
        if request.path.endswith('/license'):
            if mode=='license-403':return web.json_response({'message':'limited'},status=403)
            if mode=='license-429':return web.json_response({'message':'limited'},status=429,headers={'Retry-After':'0'})
            raw=b'Licensed under the Apache License, Version 2.0 (the License).'
            if mode not in {'raw','raw-reject','raw-no-model'}:raw=b'BSD-3-Clause license declaration.'
            if mode=='excess-paragraphs':raw=b'\n\n'.join([b'BSD-3-Clause license declaration.']*257)
            blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            data={'type':'file','name':'LICENSE','path':'LICENSE','encoding':'base64','size':len(raw),
                'sha':blob,'content':base64.b64encode(raw).decode(),
                'url':f'https://api.github.com/repos/{REPO}/contents/LICENSE?ref={REF}',
                'html_url':f'https://github.com/{REPO}/blob/{REF}/LICENSE',
                'license':{'spdx_id':'NOASSERTION' if mode in {'raw','raw-reject','raw-no-model'} else 'BSD-3-Clause'}}
            if mode=='wrong-ref':data['url']=data['url'].replace(REF,OTHER)
            if mode=='wrong-html-ref':data['html_url']=data['html_url'].replace(REF,OTHER)
            if mode=='wrong-license-repo':data['url']=data['url'].replace('example/','other/')
            if mode=='bad-blob':data['sha']='f'*40
            if mode=='wrong-size':data['size']+=1
            if mode=='missing-content':data.pop('content')
            if mode=='directory':data['type']='dir'
            if mode=='malformed-base64':data['content']='!!not base64!!'
            if mode=='bad-path':data['path']='../LICENSE'
            if mode=='canonical-case':
                for field in ['url','html_url']:data[field]=data[field].replace(REPO,'Example/River-Sample')
            return web.json_response(data,status=206 if mode=='partial' else 200)
        return web.json_response({'full_name':REPO,'license':{'spdx_id':'MIT'},'created_at':'2010-01-01T00:00:00Z'})

    async def model(request):
        data=await request.json();calls.append(request.path);payloads.append(data)
        if request.path=='/verify':
            if mode=='unavailable':return web.json_response({'error':'unavailable'},status=503)
            return web.json_response({'supported':mode not in {'reject','raw-reject'}})
        for p in data.get('passages',[]):
            name=re.search(r'Licensed under the ([^(]+)',p['text'])
            if name:return web.json_response({'passage':p['id'],'answer':name[1].strip()})
            name=re.search(r'license:\s*(MIT|BSD-3-Clause)',p['text'])
            if name:return web.json_response({'passage':p['id'],'answer':name[1]})
        return web.json_response({'passage':-1,'answer':''})

    app=web.Application();app.router.add_get('/{tail:.*}',source);app.router.add_post('/{tail:.*}',model)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
    original=aiohttp.ClientSession._request
    async def transport(self,method,url,*args,**kwargs):
        parsed=urlsplit(str(url))
        if parsed.hostname in {'api.github.com','github.com','www.github.com'}:url=base+parsed.path+('?' +parsed.query if parsed.query else '')
        elif parsed.hostname!='127.0.0.1':raise ValueError('Unexpected external request in controlled HTTP test')
        return await original(self,method,url,*args,**kwargs)
    scenarios=[('identified','BSD-3-Clause'),('raw','Apache License, Version 2.0'),('current','MIT'),
        *[(name,'') for name in ['no-commit','future','invalid-date','wrong-commit-repo','bad-sha','multiple',
            'wrong-ref','wrong-html-ref','wrong-license-repo','bad-blob','wrong-size','missing-content','directory','partial',
            'commit-403','commit-429','last-credit','license-403','license-429','low-budget','reject','raw-reject','unavailable','no-model','raw-no-model']]]
    try:
        with patch.object(aiohttp.ClientSession,'_request',transport):
            for mode,expected in scenarios:
                hits.clear();calls.clear();payloads.clear()
                q=QUERY.replace(' as of 2020-12-31','') if mode=='current' else QUERY
                result=await engine(Settings(model_url='' if mode in {'no-model','raw-no-model'} else base,
                    search=False,browser=False,allow_private=True,max_depth=0,budget=3 if mode=='low-budget' else 12)).run(q,'https://github.com/'+REPO)
                passed=result.answer==expected and (bool(result.sources) if expected else not result.sources)
                if expected and mode!='current':
                    passed &= len(result.sources)==2 and any('/commits' in u for u in result.sources) and any('/license?ref='+REF in u for u in result.sources)
                    passed &= bool(result.diagnostics.get('proposed_proof'))
                if mode=='commit-429':passed &= sum('/commits?' in u for u in hits)==1
                if mode=='license-429':passed &= sum('/license?' in u for u in hits)==1
                if mode in {'no-commit','future','invalid-date','wrong-commit-repo','bad-sha','multiple','commit-403','commit-429','last-credit','low-budget'}:
                    passed &= not any('/license?' in u for u in hits)
                if mode in {'no-model','raw-no-model'}:passed &= not calls
                rows.append(dict(id=mode,passed=bool(passed),expected=expected,actual=result.answer,
                    local_requests=list(hits),model_calls=list(calls),model_payloads=list(payloads),result=result.internal()))
            mode='identified';hits.clear();calls.clear()
            result=await engine(Settings(model_url=base,search=False,browser=False,allow_private=True,max_depth=0,budget=12)).run(QUERY,base+'/external')
            rows.append(dict(id='external-dated',passed=result.answer=='BSD-3-Clause' and result.sources==[base+'/external'],
                expected='BSD-3-Clause',actual=result.answer,result=result.internal()))
            scope_checks=[
                ('question-only',QUERY,'','BSD-3-Clause'),
                ('api-start',QUERY,'https://api.github.com/repos/'+REPO,'BSD-3-Clause'),
                ('www-start',QUERY,'https://www.github.com/'+REPO,'BSD-3-Clause'),
                ('canonical-case',QUERY,'https://github.com/'+REPO,'BSD-3-Clause'),
                ('year-only',f'What was the license of the GitHub repository {REPO} in 2019?', 'https://github.com/'+REPO,'BSD-3-Clause'),
                ('wrong-year',f'What was the license of the GitHub repository {REPO} in 2020?', 'https://github.com/'+REPO,''),
                ('conflicting-repository',QUERY,'https://github.com/other/river-sample',''),
                ('branch-url',QUERY,'https://github.com/'+REPO+'/tree/main',''),
                ('version-question',QUERY.replace('license of','license of version 2.0 of'),'https://github.com/'+REPO,''),
                ('tag-question',QUERY.replace(' as of',' at tag archive as of'),'https://github.com/'+REPO,''),
                *[(m,QUERY,'https://github.com/'+REPO,'') for m in ['boundary','missing-date','malformed-base64','bad-path','commit-500','excess-paragraphs']]]
            for mode,q,start,expected in scope_checks:
                hits.clear();calls.clear();payloads.clear()
                result=await engine(Settings(model_url=base,search=False,browser=False,allow_private=True,max_depth=2,budget=12)).run(q,start)
                passed=result.answer==expected and (len(result.sources)==2 if expected else not result.sources)
                if mode=='commit-500':passed &= len(hits)==1
                if mode in {'conflicting-repository','branch-url','version-question','tag-question'}:passed &= not hits and not calls
                rows.append(dict(id=mode,passed=bool(passed),expected=expected,actual=result.answer,
                    local_requests=list(hits),model_calls=list(calls),result=result.internal()))
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
        production_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('app.py'),*sorted(Path('agent').glob('*.py'))]},
        passed=sum(r['passed'] for r in rows),total=len(rows),rows=rows)
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'],total=report['total'],failures=[r['id'] for r in rows if not r['passed']])))
    if report['passed']!=report['total']:sys.exit(1)
