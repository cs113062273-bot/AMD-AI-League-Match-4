"""Compare real immutable CDN byte ranges; report transport speed and byte equality."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
import urllib.request

from cache_registry import Hub,TLS
from registry_transport import RangeConnections


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--samples',type=int,default=64)
    parser.add_argument('--workers',type=int,default=16)
    parser.add_argument('--range-kib',type=int,choices=[128,256,512,1024])
    parser.add_argument('--out',default='research/registry-transport-comparison.json')
    args=parser.parse_args()
    if not 1<=args.samples<=256 or not 1<=args.workers<=64:parser.error('Bounded sample/worker counts required')
    root=Path('.vm/registry-cache/rocm_pytorch')
    mapping=json.loads((root/'map.json').read_text(encoding='utf-8'))
    raw=(root/mapping['root'].replace(':','-')).read_bytes()
    assert 'sha256:'+hashlib.sha256(raw).hexdigest()==mapping['root']
    entry=max(json.loads(raw)['layers'],key=lambda item:item['size'])
    target=root/entry['digest'].replace(':','-')
    marker=json.loads(target.with_suffix('.parts.json').read_text(encoding='utf-8'))
    original_chunk=marker['chunk_bytes'];chunk=args.range_kib*1024 if args.range_kib else original_chunk
    done=set(marker['parts'])
    if chunk==original_chunk:indices=sorted(done)[:args.samples]
    else:
        candidates=sorted({part*original_chunk//chunk for part in done})
        indices=[index for index in candidates if all(part in done for part in
            range(index*chunk//original_chunk,min(entry['size'],(index+1)*chunk-1)//original_chunk+1))][:args.samples]
    if len(indices)!=args.samples:raise ValueError('Insufficient completed ranges for comparison')
    hub=Hub('rocm/pytorch')
    with hub.open('blobs/'+entry['digest'],headers={'Range':'bytes=0-0'}) as response:url=response.url
    reports={};expected=[]
    with target.with_suffix('.partial').open('rb') as source:
        for index in indices:
            source.seek(index*chunk);expected.append(hashlib.sha256(source.read(min(chunk,entry['size']-index*chunk))).hexdigest())
    for mode in ('urllib_shared_context','persistent_https'):
        connections=RangeConnections(TLS) if mode=='persistent_https' else None
        def one(index):
            start=index*chunk;end=min(entry['size']-1,start+chunk-1)
            headers={'Range':f'bytes={start}-{end}'}
            response=connections.open(url,headers) if connections else urllib.request.urlopen(urllib.request.Request(url,headers=headers),context=TLS,timeout=45)
            with response:
                if response.status!=206 or response.headers.get('Content-Range')!=f'bytes {start}-{end}/{entry["size"]}':raise ValueError('Wrong range response')
                body=response.read(chunk+1)
            if len(body)!=end-start+1:raise ValueError('Wrong range length')
            return hashlib.sha256(body).hexdigest()
        began=time.monotonic()
        try:
            with ThreadPoolExecutor(args.workers) as pool:hashes=list(pool.map(one,indices))
        finally:
            if connections:connections.close()
        if hashes!=expected:raise ValueError('CDN range bytes disagree with checkpoint cache')
        seconds=time.monotonic()-began
        reports[mode]={'seconds':seconds,'mib_per_second':len(indices)*chunk/1048576/seconds,'matches_cache':True}
    report={'blob_digest':entry['digest'],'sample_ranges':len(indices),'chunk_bytes':chunk,'workers':args.workers,
        'scope':'Real TLS/CDN sample transport comparison; full blob digest is separately required before Docker may use the cache. Not an agent latency measurement.',
        'results':reports}
    Path(args.out).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
