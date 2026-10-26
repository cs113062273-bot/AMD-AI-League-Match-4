"""Resumable HTTPS assets for isolated local validation; verify publisher digests when available."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.request
from download_support import file_lock


def main():
    ap=argparse.ArgumentParser();ap.add_argument('url');ap.add_argument('output');ap.add_argument('--sha512',default='');ap.add_argument('--workers',type=int,default=24);ap.add_argument('--chunk-kib',type=int,default=512);args=ap.parse_args()
    if not 1<=args.workers<=64:ap.error('workers must be 1..64')
    if args.chunk_kib not in {64,128,256,512,1024}:ap.error('Unsupported chunk size')
    if not args.url.startswith('https://'):raise ValueError('HTTPS required')
    target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True)
    with file_lock(target):
        with urllib.request.urlopen(urllib.request.Request(args.url,method='HEAD'),timeout=20) as r:size=int(r.headers['Content-Length'])
        if not 0<size<=512*1024**2:raise ValueError('Unexpected asset size')
        complete=target.with_suffix(target.suffix+'.complete.json')
        if target.exists():
            with target.open('rb') as f:digest=hashlib.file_digest(f,'sha512').hexdigest()
            known=json.loads(complete.read_text(encoding='utf-8')) if complete.exists() else {}
            if (digest==args.sha512 if args.sha512 else known.get('url')==args.url and known.get('sha512')==digest):return
            raise RuntimeError('Existing completed asset differs; refusing overwrite')
        partial=target.with_suffix(target.suffix+'.download');marker=target.with_suffix(target.suffix+'.parts.json')
        chunk=args.chunk_kib*1024
        previous=json.loads(marker.read_text(encoding='utf-8')) if partial.exists() and marker.exists() else []
        old_chunk=previous.get('chunk_bytes',512*1024) if isinstance(previous,dict) else 512*1024
        old_parts=set(previous.get('parts',[])) if isinstance(previous,dict) else set(previous)
        done={i for i in range((size+chunk-1)//chunk) if all(j in old_parts for j in range(i*chunk//old_chunk,(min(size,(i+1)*chunk)-1)//old_chunk+1))}
        if not partial.exists():
            with partial.open('wb') as f:f.truncate(size)
        lock=threading.Lock()
        def one(i):
            if i in done:return
            start=i*chunk;end=min(size-1,start+chunk-1)
            req=urllib.request.Request(args.url,headers={'Range':f'bytes={start}-{end}'})
            for attempt in range(5):
                try:
                    with urllib.request.urlopen(req,timeout=30) as r:
                        if r.status!=206 and size>chunk:raise RuntimeError('Range unsupported')
                        if r.status==206 and r.headers.get('Content-Range')!=f'bytes {start}-{end}/{size}':raise RuntimeError('Range mismatch')
                        data=r.read(chunk+1)
                    if len(data)!=end-start+1:raise RuntimeError('Incomplete range')
                    with partial.open('r+b') as f:f.seek(start);f.write(data)
                    with lock:
                        done.add(i);temp=marker.with_suffix('.tmp');temp.write_text(json.dumps({'chunk_bytes':chunk,'parts':sorted(done)}));os.replace(temp,marker)
                        if len(done)%100==0:print(target.name,len(done),'chunks',flush=True)
                    return
                except (OSError,RuntimeError):
                    if attempt==4:raise
                    time.sleep(.2)
        with ThreadPoolExecutor(max_workers=args.workers) as p:list(p.map(one,range((size+chunk-1)//chunk)))
        with partial.open('rb') as f:digest=hashlib.file_digest(f,'sha512').hexdigest()
        if args.sha512 and digest!=args.sha512:
            marker.unlink(missing_ok=True)
            raise RuntimeError('Publisher SHA-512 mismatch; resume state reset for a clean retry')
        partial.replace(target);marker.unlink(missing_ok=True)
        complete.write_text(json.dumps({'url':args.url,'size':size,'sha512':digest,'publisher_digest_verified':bool(args.sha512)},indent=2))
        print('verified',target.name,digest,flush=True)



if __name__=='__main__':main()
