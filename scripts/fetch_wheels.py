"""Verified wheel downloads through PyPI metadata, with small ranged transfers."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request
from packaging.tags import sys_tags
from packaging.tags import cpython_tags,compatible_tags
from packaging.utils import parse_wheel_filename
import sys
import time
import threading
import argparse
import shutil


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--target',choices=['native','linux314'],default='native');ap.add_argument('specs',nargs='+');args=ap.parse_args()
    folder=Path('.wheels')/('linux314' if args.target=='linux314' else '');folder.mkdir(parents=True,exist_ok=True)
    specs=args.specs
    platforms=[f'manylinux_2_{i}_x86_64' for i in range(41,4,-1)]+['manylinux2014_x86_64','manylinux2010_x86_64','manylinux1_x86_64','linux_x86_64']
    tags=list(cpython_tags((3,14),abis=['cp314'],platforms=platforms))+list(compatible_tags((3,14),interpreter='cp314',platforms=platforms)) if args.target=='linux314' else list(sys_tags())
    for spec in specs:
        name,version=spec.split('==')
        for attempt in range(5):
            try:
                with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=30) as r:info=json.load(r)
                break
            except OSError:
                if attempt==4:raise
                time.sleep(.5)
        options=[]
        for item in info['urls']:
            if item['packagetype']!='bdist_wheel':continue
            wt=parse_wheel_filename(item['filename'])[3]
            indices=[tags.index(t) for t in wt if t in tags]
            if indices:options.append((min(indices),item))
        if not options:raise RuntimeError('No compatible wheel for '+spec)
        item=min(options,key=lambda x:x[0])[1]
        target=folder/item['filename']
        if target.name!=item['filename'] or ':' in item['filename']:raise ValueError('Unsafe wheel filename')
        if args.target=='linux314' and not target.exists():
            native=Path('.wheels')/target.name
            if native.is_file():
                with native.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
                if digest==item['digests']['sha256']:shutil.copyfile(native,target)
        if target.exists():
            with target.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
            if digest==item['digests']['sha256']:continue
        size=item['size'];chunk=512*1024
        marker=target.with_suffix('.parts.json')
        done=set(json.loads(marker.read_text(encoding='utf-8'))) if marker.exists() and target.exists() else set()
        if not target.exists():
            with target.open('wb') as f:f.truncate(size)
        lock=threading.Lock()
        def one(i):
            if i in done:return
            start=i*chunk;end=min(size-1,start+chunk-1)
            req=urllib.request.Request(item['url'],headers={'Range':f'bytes={start}-{end}'})
            for attempt in range(5):
                try:
                    with urllib.request.urlopen(req,timeout=30) as r:
                        data=r.read(chunk+1)
                        if len(data)!=end-start+1:raise RuntimeError('Unexpected wheel range')
                    with target.open('r+b') as f:f.seek(start);f.write(data)
                    with lock:
                        done.add(i);marker.write_text(json.dumps(sorted(done)))
                    return
                except (OSError,RuntimeError):
                    if attempt==4:raise
                    time.sleep(.2)
        with ThreadPoolExecutor(max_workers=6) as p:list(p.map(one,range((size+chunk-1)//chunk)))
        with target.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        if digest!=item['digests']['sha256']:raise RuntimeError('Wheel hash mismatch')
        marker.unlink(missing_ok=True)
        print('verified',target.name,flush=True)


if __name__=='__main__':main()
