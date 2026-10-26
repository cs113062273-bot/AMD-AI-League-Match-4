"""Download the official CUDA wheel from the primary host, validating its published checksum."""
import hashlib
from pathlib import Path
import urllib.request
import json
import threading
from concurrent.futures import ThreadPoolExecutor

URL="https://download.pytorch.org/whl/cu128/torch-2.9.1%2Bcu128-cp313-cp313-win_amd64.whl"
SHA="ad9183864acdd99fc5143d7ca9d3d2e7ddfc9a9600ff43217825d4e5e9855ccc"


def main():
    target=Path(".wheels/torch-2.9.1+cu128-cp313-cp313-win_amd64.whl")
    target.parent.mkdir(exist_ok=True)
    size=2862036321
    chunk=1024*1024
    marker=target.with_suffix('.parts.json')
    if target.exists() and target.stat().st_size==size:
        if marker.exists():done=set(json.loads(marker.read_text(encoding='utf-8')))
        else:
            # Resume completed earlier 32 MiB range writes. Final whole-file SHA is mandatory.
            done=set()
            with target.open('rb') as f:
                for start in range(0,size,32*1024*1024):
                    end=min(size,start+32*1024*1024)
                    f.seek(start);head=f.read(128);f.seek(end-128);tail=f.read(128)
                    if any(head) and any(tail):done.update(range(start//chunk,(end+chunk-1)//chunk))
    else:
        done=set()
        with target.open("wb") as f:f.truncate(size)
    lock=threading.Lock()
    def download(i):
        if i in done:return
        start=i*chunk;end=min(size-1,start+chunk-1)
        req=urllib.request.Request(URL,headers={"Range":f"bytes={start}-{end}"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req,timeout=40) as r:
                    if r.status!=206 or r.headers.get("Content-Range")!=f"bytes {start}-{end}/{size}":
                        raise RuntimeError("Unexpected range response")
                    data=r.read(chunk+1)
                if len(data)!=end-start+1:
                    raise RuntimeError("Incomplete chunk")
                with target.open("r+b") as f:
                    f.seek(start);f.write(data)
                with lock:
                    done.add(i);marker.write_text(json.dumps(sorted(done)))
                    if len(done)%100==0:print(f"completed {len(done)} MiB chunks",flush=True)
                return
            except (OSError,RuntimeError):
                if attempt==2:raise
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(download,range((size+chunk-1)//chunk)))
    digest=hashlib.file_digest(target.open("rb"),"sha256").hexdigest()
    if digest!=SHA:
        raise RuntimeError(f"Checksum mismatch {digest}")
    marker.unlink(missing_ok=True)
    print(target,digest,flush=True)


if __name__=="__main__":
    main()
