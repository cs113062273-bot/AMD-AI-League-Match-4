"""Verified Docker Hub pull cache for slow validation links; no registry writes or credentials.

Preserves exact upstream manifest/blob bytes. Digests are checked before a blob becomes
servable. A Docker daemon can use the separate loopback cache bridge as a mirror.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import threading
import time
import urllib.request
import urllib.error
import ssl
import http.client
from registry_transport import RangeConnections
from download_support import atomic_json,file_lock,resume_parts

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'.vm/registry-cache'
ACCEPT='application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json'
# Reuse an immutable validating context. Rebuilding the Windows certificate store
# for every small byte-range request dominates CPU time at high concurrency.
TLS=ssl.create_default_context()


class Hub:
    def __init__(self,repository):self.repository=repository;self.token='';self.expires=0;self.lock=threading.Lock()
    def open(self,path,method='GET',headers=None):
        with self.lock:
            if time.monotonic()>self.expires:
                with urllib.request.urlopen('https://auth.docker.io/token?service=registry.docker.io&scope=repository:'+self.repository+':pull',timeout=30,context=TLS) as r:data=json.load(r)
                self.token=data['token'];self.expires=time.monotonic()+max(30,int(data.get('expires_in',300))-30)
        req=urllib.request.Request('https://registry-1.docker.io/v2/'+self.repository+'/'+path,method=method,
            headers={'Authorization':'Bearer '+self.token,'Accept':ACCEPT,**(headers or {})})
        return urllib.request.urlopen(req,timeout=60,context=TLS)


def put_raw(folder,raw,digest):
    if 'sha256:'+hashlib.sha256(raw).hexdigest()!=digest:raise RuntimeError('Upstream digest mismatch')
    target=folder/digest.replace(':','-');temp=target.with_suffix('.tmp');temp.write_bytes(raw);temp.replace(target)


def manifest(hub,reference,folder):
    with hub.open('manifests/'+reference) as r:raw=r.read(2_000_001)
    if len(raw)>2_000_000:raise RuntimeError('Unexpected manifest size')
    digest='sha256:'+hashlib.sha256(raw).hexdigest()
    if reference.startswith('sha256:') and reference!=digest:raise RuntimeError('Pinned manifest changed')
    put_raw(folder,raw,digest)
    return digest,json.loads(raw)


def blob(hub,entry,folder,workers,chunk=512*1024,keepalive=False):
    digest=entry['digest'];size=entry['size'];target=folder/digest.replace(':','-')
    with file_lock(target):
        if target.exists():
            with target.open('rb') as f:actual='sha256:'+hashlib.file_digest(f,'sha256').hexdigest()
            if actual==digest:return
            raise RuntimeError('Completed cache blob changed: '+digest)
        if not 0<size<=32*1024**3:raise RuntimeError('Unexpected blob size')
        if size<=1024*1024:
            with hub.open('blobs/'+digest) as r:body=r.read(1024*1024+1)
            if len(body)!=size:raise RuntimeError('Incomplete small registry blob')
            put_raw(folder,body,digest)
            print('VERIFIED',digest,size,flush=True)
            return
        partial=target.with_suffix('.partial');marker=target.with_suffix('.parts.json')
        count=(size+chunk-1)//chunk;done=resume_parts(marker,partial,size,count,chunk)
        if not partial.exists() or partial.stat().st_size!=size:
            with partial.open('wb') as f:f.truncate(size)
        url_lock=threading.Lock();signed={'url':'','at':0};progress=threading.Lock();saved={'at':0,'count':len(done)}
        connections=RangeConnections(TLS) if keepalive else None
        def endpoint():
            with url_lock:
                if not signed['url'] or time.monotonic()-signed['at']>1200:
                    with hub.open('blobs/'+digest,headers={'Range':'bytes=0-0'}) as r:
                        signed['url']=r.url;signed['at']=time.monotonic()
                return signed['url']
        def one(i):
            if i in done:return
            start=i*chunk;end=min(size-1,start+chunk-1)
            for attempt in range(8):
                url=''
                try:
                    url=endpoint();headers={'Range':f'bytes={start}-{end}'}
                    request=connections.open(url,headers) if connections else urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=45,context=TLS)
                    with request as r:
                        if r.status>=400:raise urllib.error.HTTPError(digest,r.status,'range fetch failed',r.headers,None)
                        if r.status!=206 or r.headers.get('Content-Range')!=f'bytes {start}-{end}/{size}':raise RuntimeError('Registry range mismatch')
                        body=r.read(chunk+1)
                    if len(body)!=end-start+1:raise RuntimeError('Incomplete registry range')
                    with partial.open('r+b') as f:f.seek(start);f.write(body)
                    with progress:
                        done.add(i)
                        if len(done)-saved['count']>=32 or time.monotonic()-saved['at']>3:
                            atomic_json(marker,{'chunk_bytes':chunk,'parts':sorted(done)})
                            saved.update(at=time.monotonic(),count=len(done))
                        if len(done)%1000==0:print(digest,round(len(done)*chunk/1024**2),'/',round(size/1024**2),'MiB',flush=True)
                    return
                except (OSError,RuntimeError,http.client.HTTPException) as exc:
                    if connections:connections.reset()
                    if isinstance(exc,urllib.error.HTTPError) and exc.code in {401,403}:
                        with url_lock:
                            if signed['url']==url:signed['at']=0
                    if attempt==7:raise
                    delay=min(4,.3*2**attempt)
                    if isinstance(exc,urllib.error.HTTPError) and exc.code==429:
                        try:delay=max(delay,min(60,float(exc.headers.get('Retry-After','10'))))
                        except ValueError:delay=max(delay,10)
                    time.sleep(delay)
        try:
            with ThreadPoolExecutor(workers) as pool:list(pool.map(one,range(count)))
        finally:
            if connections:connections.close()
            atomic_json(marker,{'chunk_bytes':chunk,'parts':sorted(done)})
        with partial.open('rb') as f:actual='sha256:'+hashlib.file_digest(f,'sha256').hexdigest()
        if actual!=digest:
            marker.unlink(missing_ok=True);raise RuntimeError('Registry blob SHA-256 failed; resume state reset')
        partial.replace(target);marker.unlink(missing_ok=True)
        print('VERIFIED',digest,size,flush=True)


def run(args):
    folder=CACHE/args.repository.replace('/','_');folder.mkdir(parents=True,exist_ok=True)
    hub=Hub(args.repository);root,data=manifest(hub,args.reference,folder);manifests={root:data.get('mediaType','application/vnd.docker.distribution.manifest.v2+json')}
    if 'manifests' in data:
        child=next(m for m in data['manifests'] if m.get('platform',{}).get('architecture')=='amd64' and m.get('platform',{}).get('os')=='linux')
        digest,data=manifest(hub,child['digest'],folder);manifests[digest]=data.get('mediaType','application/vnd.oci.image.manifest.v1+json')
    atomic_json(folder/'map.json',{'repository':args.repository,'reference':args.reference,'root':root,'manifests':manifests})
    entries=[data['config'],*data['layers']]
    for entry in sorted(entries,key=lambda x:x['size']):blob(hub,entry,folder,args.workers,args.chunk_kib*1024,args.keepalive)
    atomic_json(folder/'complete.json',{'repository':args.repository,'reference':args.reference,'root':root,
        'compressed_bytes':sum(e['size'] for e in entries),'blobs':entries,'digest_verified':True,
        'at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})


def main():
    ap=argparse.ArgumentParser();ap.add_argument('repository');ap.add_argument('reference');ap.add_argument('--workers',type=int,default=64);ap.add_argument('--chunk-kib',type=int,choices=[64,128,256,512,1024],default=512);ap.add_argument('--keepalive',action='store_true');args=ap.parse_args()
    if not 1<=args.workers<=256:ap.error('workers must be 1..256')
    for attempt in range(10):
        try:
            run(args)
            return
        except (TimeoutError,ConnectionError,urllib.error.URLError,http.client.HTTPException,ssl.SSLError) as exc:
            if isinstance(exc,ssl.SSLCertVerificationError) or isinstance(getattr(exc,'reason',None),ssl.SSLCertVerificationError):raise
            if isinstance(exc,urllib.error.HTTPError) and exc.code not in {408,429,500,502,503,504}:raise
            if attempt==9:raise
            print(json.dumps({'event':'transfer_interrupted','attempt':attempt+1,'error':type(exc).__name__,'resume':'verified range checkpoints retained'}),flush=True)
            time.sleep(min(10,attempt+1))


if __name__=='__main__':main()
