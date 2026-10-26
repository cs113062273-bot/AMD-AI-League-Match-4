"""Inventory the actual installed image, independently of declared dependency locks."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess


def main():
    root=Path(__file__).resolve().parents[1]
    packages=sorted([{'name':d.metadata['Name'],'version':d.version,'license':d.metadata.get('License-Expression') or d.metadata.get('License')}
        for d in importlib.metadata.distributions() if d.metadata.get('Name')],key=lambda p:p['name'].lower())
    command=shutil.which('dpkg-query')
    system=subprocess.check_output([command,'-W','-f=${Package}\t${Version}\n'],text=True).splitlines() if command else None
    receipt=Path(os.getenv('APERTURE_MODEL',str(root/'models/qwen')))/'aperture-model.json'
    files=[root/'app.py',*(root/'agent').glob('*.py')]
    result={'python':platform.python_version(),'system':platform.system(),'python_packages':packages,
        'os_packages':system,'model_receipt':json.loads(receipt.read_text(encoding='utf-8')) if receipt.is_file() else None,
        'application_sha256':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':main()
