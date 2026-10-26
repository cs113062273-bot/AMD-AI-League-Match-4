"""Saved real Yahoo result replay and discovery-only isolation; no answer oracle."""
import argparse
import asyncio
import base64
import hashlib
import importlib
import json
from pathlib import Path
import sys
from urllib.parse import quote_plus

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'eval'))
from agent.network import Response
from agent.planner import plan_query
from agent.search import search
from agent.types import Deadline
from agent.urls import discovery_url
from revision_engine import load_engine


async def diagnose(searcher):
    path=ROOT/'research/search-access-20261025-v1/yahoo-question-query.json'
    data=json.loads(path.read_text(encoding='utf-8'));data['body']=base64.b64decode(data.pop('body_base64'))
    response=Response(**data)
    question='What year was the S\u00fcleymaniye damaged in the great fire?'
    wanted='https://hum54-15.omeka.fas.harvard.edu/exhibits/show/suleymaniye/deterioration'
    class Saved:
        deadline=Deadline(20)
        events=[{'url':'https://en.wikipedia.org/wiki/unavailable','error':'http_403'}]
        async def fetch(self,url,**kwargs):
            if url==response.url:return response
            return Response(url,b'','text/html',error='not_in_recorded_inputs')
    links=await searcher(plan_query(question),Saved(),providers=[('https://search.yahoo.com/search?p=','yahoo')])
    return {'links':links,'actual_content_source_recovered':wanted in [u for u,label in links],
            'serp_not_returned_as_source':all(not discovery_url(u) for u,label in links),
            'capture_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();out=Path(args.out)
    if out.exists():raise FileExistsError(out)
    old,revision,_=load_engine('1557f3f')
    previous=importlib.import_module(old.__module__.rsplit('.',1)[0]+'.search').search
    before=asyncio.run(diagnose(previous));after=asyncio.run(diagnose(search))
    guards=[]
    for url,expected in [('https://search.yahoo.com/search?p=secret',True),('https://r.search.yahoo.com/example',True),
                         ('https://finance.yahoo.com/news/article',False),('https://search.yahoo.com.evil.org/search',False)]:
        guards.append({'url':url,'passed':discovery_url(url)==expected})
    report={'scope':__doc__,'baseline':revision,'before':before,'after':after,'guards':guards,
            'passed':after['actual_content_source_recovered'] and after['serp_not_returned_as_source']
                      and all(r['passed'] for r in guards)}
    with out.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2)
    print(json.dumps({'before_content_source':before['actual_content_source_recovered'],
                      'after_content_source':after['actual_content_source_recovered'], 'passed':report['passed']}))
    if not report['passed']:sys.exit(1)
