"""Independently verify a release manifest, then optionally extract into a new directory."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import zipfile


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('archive')
    parser.add_argument('--extract')
    args=parser.parse_args()
    with zipfile.ZipFile(args.archive) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate ZIP entries')
        for item in archive.infolist():
            path=PurePosixPath(item.filename)
            if path.is_absolute() or '\\' in item.filename or '..' in path.parts or not item.filename.startswith('aperture/'):
                raise ValueError('Unsafe archive path')
            if (item.external_attr>>16)&0o170000!=0o100000:raise ValueError('Unexpected non-regular archive entry')
        manifest=json.loads(archive.read('aperture/RELEASE_MANIFEST.json'))
        expected={'aperture/'+item['path'] for item in manifest['files']}
        if expected|{'aperture/RELEASE_MANIFEST.json'}!=set(names) or len(expected)!=len(manifest['files']):
            raise ValueError('Archive/manifest membership mismatch')
        total=0
        for item in manifest['files']:
            digest=hashlib.sha256();size=0
            with archive.open('aperture/'+item['path']) as source:
                while block:=source.read(1024*1024):digest.update(block);size+=len(block)
            if size!=item['bytes'] or digest.hexdigest()!=item['sha256']:raise ValueError('Manifest hash/size mismatch: '+item['path'])
            total+=size
        if args.extract:
            destination=Path(args.extract).resolve()
            destination.mkdir(parents=True,exist_ok=False)
            for name in names:
                target=destination/PurePosixPath(name)
                if not target.resolve().is_relative_to(destination):raise ValueError('Extraction escape')
                target.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(name) as source,target.open('xb') as output:shutil.copyfileobj(source,output,1024*1024)
                if target.suffix=='.sh':target.chmod(0o755)
    print(json.dumps({'verified':True,'files':len(manifest['files']),'source_bytes':total,'bundled_weights':manifest['bundled_weights'],'extracted':bool(args.extract)}))


if __name__=='__main__':main()
