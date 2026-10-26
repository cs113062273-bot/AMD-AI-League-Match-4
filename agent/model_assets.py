"""Pinned model receipt verification, independent of torch and the network."""
import argparse
import hashlib
import json
from pathlib import Path


MODEL='Qwen/Qwen3-4B-Instruct-2507'
REVISION='cdbee75f17c01a7cc42f958dc650907174af0554'


def wanted(name):
    return '/' not in name and '\\' not in name and (name.endswith(('.json','.txt','.safetensors','.jinja')) or name in {'LICENSE','README.md'})


def record(folder, metadata):
    from agent.output import atomic_json
    folder=Path(folder);files=[]
    if metadata.get('sha')!=REVISION:raise ValueError('Unexpected model revision')
    for item in metadata['siblings']:
        name=item['rfilename']
        if not wanted(name):continue
        target=folder/name
        if not target.is_file() or target.stat().st_size!=item['size']:raise ValueError('Missing/incomplete model asset: '+name)
        with target.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        official=(item.get('lfs') or {}).get('sha256')
        if official:
            if digest!=official:raise ValueError('LFS SHA-256 mismatch: '+name)
        else:
            body=target.read_bytes()
            blob=hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()
            if blob!=item.get('blobId'):raise ValueError('Git blob mismatch: '+name)
        files.append({'name':name,'size':item['size'],'sha256':digest,'upstream_digest':official or item['blobId'],
            'upstream_digest_type':'sha256' if official else 'git-blob-sha1'})
    atomic_json(folder/'aperture-model.json',{'model':MODEL,'revision':REVISION,'files':files})
    return verify(folder,full=True)


def verify(folder,full=True):
    folder=Path(folder)
    data=json.loads((folder/'aperture-model.json').read_text(encoding='utf-8'))
    if data.get('model')!=MODEL or data.get('revision')!=REVISION:raise ValueError('Unrecognized model receipt')
    files=data.get('files',[])
    names=[entry['name'] for entry in files]
    if len(names)!=len(set(names)) or not {'config.json','tokenizer.json','tokenizer_config.json','model.safetensors.index.json'}.issubset(names):
        raise ValueError('Incomplete or duplicate model receipt')
    index=json.loads((folder/'model.safetensors.index.json').read_text(encoding='utf-8'))
    shards=set(index['weight_map'].values())
    if not shards or not shards.issubset(names):raise ValueError('Missing indexed weight shards')
    for entry in files:
        name=entry['name']
        if not wanted(name) or name in {'.','..'}:raise ValueError('Unsafe model asset path')
        target=folder/name
        if not target.is_file() or target.stat().st_size!=entry['size']:raise ValueError('Missing/incomplete model asset: '+name)
        if full:
            with target.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            if digest!=entry['sha256']:raise ValueError('Model asset SHA-256 mismatch: '+name)
    return {'model':MODEL,'revision':REVISION,'verified_files':len(files),'full_sha256':full,'weight_shards':len(shards)}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('directory');ap.add_argument('--sizes-only',action='store_true');args=ap.parse_args()
    print(json.dumps(verify(args.directory,not args.sizes_only)))
