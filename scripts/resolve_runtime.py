"""Resolve accelerator-neutral pins from primary PyPI metadata without downloading torch.

Torch is inspected for dependency constraints, then excluded from the install lock: the accelerator
package is installed separately locally and supplied by the organizer base on ROCm.
"""
from collections import defaultdict,deque
import json
from pathlib import Path
import urllib.request
import time
from packaging.requirements import Requirement
from packaging.version import Version,InvalidVersion
from packaging.utils import canonicalize_name
from packaging.markers import default_environment


def info(name,version=''):
    folder=Path('research/package-info');folder.mkdir(parents=True,exist_ok=True)
    target=folder/f'{name}-{version or "latest"}.json'
    if target.exists():return json.loads(target.read_text(encoding='utf-8'))
    url=f'https://pypi.org/pypi/{name}/'+(version+'/' if version else '')+'json'
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url,timeout=20) as r:
                body=b''
                for _ in range(128):
                    chunk=r.read(16384)
                    if not chunk:break
                    body+=chunk
                    try:
                        text=body.decode('utf-8')
                        start=text.index('"info":')+len('"info":')
                        value,end=json.JSONDecoder().raw_decode(text[start:].lstrip())
                        target.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
                        return value
                    except (ValueError,UnicodeError):continue
        except OSError:
            if attempt==2:raise
            time.sleep(.25)
    raise RuntimeError('No bounded info object in '+url)


def main():
    constraints=defaultdict(list);resolved={};cache={};pending=deque()
    seeds=[]
    for file in ['requirements.txt','requirements-model.txt']:
        seeds += [x for x in Path(file).read_text(encoding='utf-8').splitlines() if x and not x.startswith('#')]
    seeds+=['torch==2.9.1','mpmath==1.3.0','hf-xet==1.2.0']
    environments=[default_environment(),dict(default_environment(),platform_system='Linux',sys_platform='linux',
        os_name='posix',platform_machine='x86_64',python_version='3.14',python_full_version='3.14.4')]
    def add(raw):
        req=Requirement(raw)
        if req.marker and not any(req.marker.evaluate(dict(env,extra='')) for env in environments):return
        name=canonicalize_name(req.name)
        if name.startswith('nvidia-') or name in {'triton','pytorch-triton-rocm'}:return
        if name=='torch' and Version('2.9.1') not in req.specifier:raise RuntimeError('Local torch constraint mismatch: '+raw)
        if name not in {'torch','torchvision','torchaudio'} or name=='torch' and str(req.specifier)=='==2.9.1':
            spec=str(req.specifier)
            if spec not in constraints[name]:constraints[name].append(spec);pending.append(name)
    for s in seeds:add(s)
    while pending:
        name=pending.popleft()
        from packaging.specifiers import SpecifierSet
        spec=SpecifierSet(','.join(s for s in constraints[name] if s))
        if name in resolved and Version(resolved[name]) in spec:continue
        exact=next((s.split('==',1)[1] for s in constraints[name] if s.startswith('==') and '*' not in s),'')
        meta=info(name,exact)
        version=meta['version']
        if Version(version) not in spec:
            # Existing seeds constrain the only expected bounded upper ranges (HF/tokenizers).
            # Fail explicitly instead of guessing an incompatible dependency version.
            raise RuntimeError(f'Cannot satisfy {name}{spec}; candidate {version}')
        resolved[name]=version;cache[name]={'version':version,'requires_dist':meta.get('requires_dist') or [],'source':f'https://pypi.org/pypi/{name}/{version}/json'}
        print(name,version,flush=True)
        for raw in meta.get('requires_dist') or []:add(raw)
    pins=[f'{n}=={v}' for n,v in sorted(resolved.items()) if n not in {'torch','torchvision','torchaudio'}]
    Path('requirements-runtime.lock').write_text('# Accelerator-neutral runtime; torch is supplied separately.\n'+'\n'.join(pins)+'\n',encoding='utf-8')
    Path('research/runtime-resolution.json').write_text(json.dumps(cache,indent=2),encoding='utf-8')
    core=set();queue=deque(['aiohttp','beautifulsoup4','packaging','pypdf'])
    while queue:
        name=queue.popleft()
        if name in core:continue
        core.add(name)
        for raw in cache[name]['requires_dist']:
            req=Requirement(raw)
            if not req.marker or any(req.marker.evaluate(dict(env,extra='')) for env in environments):
                queue.append(canonicalize_name(req.name))
    Path('requirements-core.lock').write_text('# CPU retrieval runtime, pinned for Windows and Linux.\n'+'\n'.join(f'{n}=={resolved[n]}' for n in sorted(core))+'\n',encoding='utf-8')


if __name__=='__main__':main()
