"""Create a reproducible allowlisted source/bundled-model artifact, never user prompts/caches."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import zipfile
import os

ROOT=Path(__file__).resolve().parents[1]


def inventory():
    packages={}
    for name in ['requirements-runtime.lock','requirements-browser.lock']:
        for line in (ROOT/name).read_text(encoding='utf-8').splitlines():
            match=re.match(r'^([A-Za-z0-9_.-]+)==([^;\s]+)',line)
            if match:packages[match[1].lower().replace('_','-')]=match[2]
    return {'format':'aperture-dependency-inventory-v1',
        'scope':'Declared application dependencies; installed OS/Python package inventory is exported separately from the actual production image.',
        'base_image':'rocm/pytorch:rocm10.0_ubuntu26.04_py3.14_pytorch_release_2.13.0',
        'base_digest':'sha256:3174cb7061d94c427da96c0edef4adea28046fa3f3b2ff3948dc4e995665ff8c',
        'pytorch':'Provided by the pinned ROCm base; never installed from this dependency inventory.',
        'packages':[{'name':name,'version':version} for name,version in sorted(packages.items())],
        'model':{'name':'Qwen/Qwen3-4B-Instruct-2507','revision':'cdbee75f17c01a7cc42f958dc650907174af0554','license':'Apache-2.0'}}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='release/aperture-source.zip');parser.add_argument('--include-model',action='store_true');args=parser.parse_args()
    output=Path(args.out).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise FileExistsError('Preserve previous artifacts; choose a new output path')
    (ROOT/'DEPENDENCIES.json').write_text(json.dumps(inventory(),indent=2),encoding='utf-8')
    names=['app.py','README.md','LICENSE','Dockerfile','Dockerfile.cpu','.dockerignore','.gitignore','pytest.ini',
        'AUDIT.md','SUBMISSION.md','BENCHMARKS.md','DEPENDENCIES.json']
    for name in names:
        if not (ROOT/name).is_file():raise FileNotFoundError('Required release document is missing: '+name)
    files={ROOT/name for name in names}
    files.update(ROOT.glob('requirements*.txt'));files.update(ROOT.glob('requirements*.lock'))
    for directory,patterns in {'agent':['*.py'],'tests':['*.py'],'eval':['*.py'],'scripts':['*.py','*.sh','*.ps1'],
        'docs':['*.md'],'fixtures':['*.json'],'benchmarks':['*.py','*.json','*.jsonl','*.csv','*.txt','*.md']}.items():
        for pattern in patterns:files.update((ROOT/directory).glob(pattern))
    model=ROOT/'models/qwen'
    if args.include_model:
        import sys
        sys.path.insert(0,str(ROOT))
        from agent.model_assets import verify
        verify(model,full=True)
        receipt=json.loads((model/'aperture-model.json').read_text(encoding='utf-8'))
        files.update(model/item['name'] for item in receipt['files'])
        files.add(model/'aperture-model.json')
    else:
        # Receipts/license permit reproducible acquisition without an 8GB source ZIP.
        files.update(model/name for name in ['aperture-model.json','LICENSE','README.md'] if (model/name).is_file())
    manifest=[]
    for path in sorted(files):
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):raise ValueError('Unexpected symlink/path in release')
        with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        manifest.append({'path':path.relative_to(ROOT).as_posix(),'bytes':path.stat().st_size,'sha256':digest})
    epoch=int(os.getenv('SOURCE_DATE_EPOCH',str(int(time.time()))))
    stamp=time.gmtime(max(epoch,315532800))[:6]
    receipt={'format':'aperture-release-v1','at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(epoch)),
        'bundled_weights':args.include_model,'files':manifest}
    partial=output.with_suffix(output.suffix+'.partial')
    with zipfile.ZipFile(partial,'w',allowZip64=True) as archive:
        for item in manifest:
            path=ROOT/item['path']
            info=zipfile.ZipInfo('aperture/'+item['path'],date_time=stamp)
            info.compress_type=zipfile.ZIP_STORED if path.suffix=='.safetensors' else zipfile.ZIP_DEFLATED
            info.external_attr=(0o100755 if path.suffix=='.sh' else 0o100644)<<16
            with path.open('rb') as source,archive.open(info,'w',force_zip64=True) as target:
                written=hashlib.sha256();size=0
                while block:=source.read(1024*1024):target.write(block);written.update(block);size+=len(block)
                if written.hexdigest()!=item['sha256'] or size!=item['bytes']:raise RuntimeError('Source changed while packaging: '+item['path'])
        info=zipfile.ZipInfo('aperture/RELEASE_MANIFEST.json',date_time=stamp)
        info.compress_type=zipfile.ZIP_DEFLATED
        info.external_attr=0o100644<<16
        archive.writestr(info,json.dumps(receipt,indent=2))
    with zipfile.ZipFile(partial) as archive:
        corrupt=archive.testzip()
        if corrupt:raise RuntimeError('ZIP CRC failed: '+corrupt)
    os.link(partial,output)  # Atomic publication that refuses to overwrite a raced-in file.
    partial.unlink()
    with output.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(digest+'  '+output.name+'\n',encoding='ascii')
    print(json.dumps({'artifact':str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else output.name,
        'bytes':output.stat().st_size,'sha256':digest,'files':len(manifest),'bundled_weights':args.include_model}))


if __name__=='__main__':main()
