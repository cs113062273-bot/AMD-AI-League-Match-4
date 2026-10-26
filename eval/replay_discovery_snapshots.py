"""Paired search parsing on identical recorded public HTTP responses, without network or inference."""
import argparse
import asyncio
import base64
import hashlib
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent.network import Response
from agent.planner import plan_query
from agent.search import search
from revision_engine import load_engine


async def replay(row,searcher):
    source=ROOT/row['search_snapshot_path']
    if hashlib.sha256(source.read_bytes()).hexdigest()!=row['search_snapshot_sha256']:raise ValueError('Snapshot hash mismatch')
    snapshots=json.loads(source.read_text(encoding='utf-8'))
    class Replay:
        deadline=SimpleNamespace(remaining=16)
        # Only starting-page errors existed before production search ran.
        events=[event for event in row['events'] if event['url']==row['starting_url']]
        async def fetch(self,url,**kwargs):
            data=dict(snapshots[url])
            data['body']=base64.b64decode(data.pop('body_base64'))
            return Response(**data)
    return await searcher(plan_query(row['query'],row['starting_url']),Replay(),hints=row.get('search_hints',()))


async def diagnose(manifest,baseline):
    engine,revision,hashes=load_engine(baseline)
    old_search=importlib.import_module(engine.__module__.rsplit('.',1)[0]+'.search').search
    rows=[]
    for row in manifest['rows']:
        before=await replay(row,old_search);after=await replay(row,search)
        rows.append({'id':row['id'],'before':before,'after':after,'removed':[item for item in before if item not in after],
            'retained_first_four':before[:4]==after[:4],'snapshot_sha256':row['search_snapshot_sha256']})
    return {'scope':__doc__,'baseline_revision':revision,'baseline_source_sha256':hashes,
        'current_search_sha256':hashlib.sha256((ROOT/'agent/search.py').read_bytes()).hexdigest(),'rows':rows}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--manifest',required=True);ap.add_argument('--baseline',required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    result=asyncio.run(diagnose(json.loads((ROOT/args.manifest).read_text(encoding='utf-8')),args.baseline))
    target.write_text(json.dumps(result,ensure_ascii=True,indent=2),encoding='utf-8')
    print(json.dumps([{'id':row['id'],'before':len(row['before']),'after':len(row['after']),'removed':len(row['removed']),'same_first_four':row['retained_first_four']} for row in result['rows']]))
