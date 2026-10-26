"""Resumable pinned HF download with LFS SHA-256 validation; useful behind slow bulk proxies."""
import hashlib
import json
from pathlib import Path
import urllib.request
from concurrent.futures import ThreadPoolExecutor
import time
import argparse
from download_support import atomic_json, file_lock, resume_parts

MODEL="Qwen/Qwen3-4B-Instruct-2507"
REV="cdbee75f17c01a7cc42f958dc650907174af0554"


def fetch(req,timeout=45):
    return urllib.request.urlopen(req,timeout=timeout)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--shard',type=int,choices=[1,2,3],help='Fetch one shard in parallel with the main downloader')
    parser.add_argument('--workers',type=int,default=24)
    parser.add_argument('--chunk-kib',type=int,choices=[256,512,1024,4096],default=512)
    args=parser.parse_args()
    if not 1 <= args.workers <= 64:parser.error('workers must be 1..64')
    folder=Path("models/qwen");folder.mkdir(parents=True,exist_ok=True)
    data=json.load(fetch(f"https://huggingface.co/api/models/{MODEL}/revision/{REV}?blobs=true"))
    atomic_json(Path("research/model-files.json"),data)
    for item in data["siblings"]:
        name=item["rfilename"]
        if "/" in name or not (name.endswith((".json",".txt",".safetensors",".jinja")) or name in {"LICENSE","README.md"}):
            continue
        if args.shard and name.endswith('.safetensors') and not name.startswith(f'model-{args.shard:05d}-'):
            continue
        url=f"https://huggingface.co/{MODEL}/resolve/{REV}/{name}"
        target=folder/name
        size=item.get("size",0)
        sha=(item.get("lfs") or {}).get("sha256")
        with file_lock(target):
            if target.exists() and (not size or target.stat().st_size==size):
                with target.open('rb') as stream:
                    if sha:
                        valid=hashlib.file_digest(stream,'sha256').hexdigest()==sha
                    else:
                        content=stream.read()
                        valid=hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()==item.get('blobId')
                if valid:
                    continue
            if not name.endswith(".safetensors"):
                with fetch(url) as r: body=r.read(30_000_001)
                if len(body)>30_000_000 or size and len(body)!=size:raise RuntimeError('Incomplete small model file')
                if sha and hashlib.sha256(body).hexdigest()!=sha:raise RuntimeError('Small model file hash mismatch')
                blob=item.get('blobId')
                if not sha and blob and hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()!=blob:
                    raise RuntimeError('Git blob digest mismatch')
                temp=target.with_suffix(target.suffix+'.tmp');temp.write_bytes(body);temp.replace(target)
                print("small",name,flush=True)
                continue
            partial=target.with_suffix(".partial")
            marker=target.with_suffix(".parts.json")
            chunk=args.chunk_kib*1024
            done=resume_parts(marker,partial,size,(size+chunk-1)//chunk,chunk)
            if not partial.exists() or partial.stat().st_size!=size:
                with partial.open("wb") as f:f.truncate(size)
            import threading
            lock=threading.Lock()
            def one(i):
                if i in done:return
                start=i*chunk;end=min(size-1,start+chunk-1)
                for attempt in range(8):
                    try:
                        req=urllib.request.Request(url,headers={"Range":f"bytes={start}-{end}"})
                        with fetch(req) as r:
                            if r.status!=206 or r.headers.get("Content-Range")!=f"bytes {start}-{end}/{size}":
                                raise RuntimeError("Unexpected Content-Range")
                            body=r.read(chunk+1)
                        if len(body)!=end-start+1:raise RuntimeError("Incomplete shard chunk")
                        with partial.open("r+b") as f:f.seek(start);f.write(body)
                        with lock:
                            done.add(i);atomic_json(marker,{'chunk_bytes':chunk,'parts':sorted(done)})
                            if len(done)%50==0:print(name,len(done),"chunks",flush=True)
                        return
                    except (OSError,RuntimeError):
                        if attempt==7:raise
                        time.sleep(min(3,.25*2**attempt))
            with ThreadPoolExecutor(max_workers=args.workers) as pool:list(pool.map(one,range((size+chunk-1)//chunk)))
            with partial.open("rb") as f:digest=hashlib.file_digest(f,"sha256").hexdigest()
            if digest!=sha:
                marker.unlink(missing_ok=True)
                raise RuntimeError("Model SHA-256 mismatch; resume state reset: "+name)
            partial.replace(target);marker.unlink()
            print("verified",name,sha,flush=True)
    if not args.shard:
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from agent.model_assets import record
        print(record(folder,data),flush=True)


if __name__=="__main__":main()
