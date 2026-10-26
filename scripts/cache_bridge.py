"""Loopback-only public artifact cache for the isolated validation guest.

Docker bytes come from digest-verified cache_registry.py; APK packages retain their
upstream signatures; browser archives use the exact pinned Playwright download paths.
No user directories or credentials are exposed. Nothing is pushed to a registry.
"""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'.vm/bridge-cache';CACHE.mkdir(parents=True,exist_ok=True)
BROWSERS={
 '/builds/cft/156.0.8078.4/linux64/chrome-headless-shell-linux64.zip':'https://cdn.playwright.dev/builds/cft/156.0.8078.4/linux64/chrome-headless-shell-linux64.zip',
 '/builds/ffmpeg/1013/ffmpeg-linux.zip':'https://cdn.playwright.dev/dbazure/download/playwright/builds/ffmpeg/1013/ffmpeg-linux.zip',
}


def cached_asset(path):
    if path in BROWSERS:upstream=BROWSERS[path]
    elif re.fullmatch(r'/alpine/v3\.22/(?:main|community)/x86_64/[A-Za-z0-9+_.-]+\.(?:apk|tar\.gz)',path):upstream='https://dl-cdn.alpinelinux.org'+path
    elif re.fullmatch(r'/apt/(?:deb\.debian\.org/(?:debian|debian-security)|archive\.ubuntu\.com/ubuntu|security\.ubuntu\.com/ubuntu)/[A-Za-z0-9_+~%./-]+',path) and '..' not in path.split('/'):
        upstream='https://'+path.removeprefix('/apt/')
    else:return None
    target=CACHE/path.lstrip('/')
    if not target.resolve().is_relative_to(CACHE.resolve()):return None
    if not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.with_suffix(target.suffix+'.log').open('ab') as log:
            result=subprocess.run([sys.executable,str(ROOT/'scripts/download_asset.py'),upstream,str(target),'--workers','16','--chunk-kib','256'],
                cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
        if result.returncode or not target.is_file():return None
    return target


class Handler(BaseHTTPRequestHandler):
    def log_message(self,format,*args):print(format%args,flush=True)
    def send_bytes(self,body,content_type='application/json'):
        self.send_response(200);self.send_header('Docker-Distribution-Api-Version','registry/2.0');self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)));self.end_headers()
        if self.command!='HEAD':self.wfile.write(body)
    def send_file(self,target,content_type='application/octet-stream',digest=''):
        size=target.stat().st_size;start=0;end=size-1
        requested=self.headers.get('Range','') if self.command=='GET' else ''
        if requested:
            match=re.fullmatch(r'bytes=(\d+)-(\d*)',requested)
            if not match:self.send_error(416);return
            start=int(match[1]);end=min(size-1,int(match[2]) if match[2] else size-1)
            if not 0<=start<=end<size:self.send_error(416);return
        self.send_response(206 if requested else 200);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(end-start+1))
        self.send_header('Accept-Ranges','bytes')
        if requested:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        if digest:self.send_header('Docker-Content-Digest',digest)
        self.end_headers()
        if self.command=='HEAD':return
        try:
            with target.open('rb') as stream:
                stream.seek(start);left=end-start+1
                while left:
                    data=stream.read(min(512*1024,left))
                    if not data:break
                    self.wfile.write(data);left-=len(data)
        except ConnectionError:return
    def do_HEAD(self):self.do_GET()
    def do_GET(self):
        try:self.get_content()
        except ConnectionError:return

    def get_content(self):
        path=urlsplit(self.path).path
        if path in {'/v2','/v2/'}:
            self.send_bytes(b'{}');return
        if path=='/registry-status':
            ready=(ROOT/'.vm/registry-cache/rocm_pytorch/complete.json').is_file()
            self.send_bytes(json.dumps({'rocm_ready':ready}).encode());return
        if path=='/wheel-status':
            self.send_bytes(json.dumps({'ready':(ROOT/'.wheels/linux314/index.html').is_file()}).encode());return
        if path=='/wheels/':
            target=ROOT/'.wheels/linux314/index.html'
            if not target.is_file():self.send_error(503);return
            self.send_file(target,'text/html');return
        wheel=re.fullmatch(r'/wheels/([A-Za-z0-9_.+-]+\.whl)',path)
        if wheel:
            target=ROOT/'.wheels/linux314'/wheel[1]
            if not target.is_file():self.send_error(404);return
            self.send_file(target);return
        match=re.fullmatch(r'/v2/([A-Za-z0-9_/-]+)/(manifests|blobs)/([A-Za-z0-9_:.-]+)',path)
        if match:
            repo,kind,reference=match.groups();folder=ROOT/'.vm/registry-cache'/repo.replace('/','_')
            try:metadata=json.loads((folder/'map.json').read_text(encoding='utf-8'))
            except (OSError,ValueError):self.send_error(404);return
            if metadata['repository']!=repo:self.send_error(404);return
            digest=reference
            if kind=='manifests' and reference==metadata['reference']:digest=metadata['root']
            if not re.fullmatch(r'sha256:[0-9a-f]{64}',digest):self.send_error(404);return
            target=folder/digest.replace(':','-')
            if not target.is_file():self.send_error(404);return
            content=metadata['manifests'].get(digest,'application/octet-stream') if kind=='manifests' else 'application/octet-stream'
            self.send_file(target,content,digest);return
        asset=cached_asset(path)
        if not asset:self.send_error(404);return
        self.send_file(asset)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int);args=ap.parse_args()
    previous=ROOT/'.state/cache-bridge.json'
    port=args.port
    if port is None:
        port=urlsplit(json.loads(previous.read_text(encoding='utf-8'))['host_url']).port if previous.exists() else 0
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True
    port=server.server_port
    import os
    state={'host_url':f'http://127.0.0.1:{port}','guest_url':f'http://10.0.2.2:{port}','pid':os.getpid()}
    (ROOT/'.state/cache-bridge.json').write_text(json.dumps(state))
    print(json.dumps(state),flush=True)
    server.serve_forever()
