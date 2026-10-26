"""Boot an isolated workspace-only QEMU guest and test actual Linux Docker containers.

Uses only a new virtual disk, loopback HTTP and user-mode NAT. Never mounts host disks,
changes Windows features, or installs a host service. Run after verified VM asset downloads.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import io
import json
from pathlib import Path
import socket
import subprocess
import tarfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
BASE='rocm/pytorch:rocm10.0_ubuntu26.04_py3.14_pytorch_release_2.13.0@sha256:3174cb7061d94c427da96c0edef4adea28046fa3f3b2ff3948dc4e995665ff8c'


def receive_archive(reader,target,maximum=60*1024**3):
    """Bounded HTTP chunk decoding; never buffer an image archive in RAM."""
    temporary=target.with_suffix(target.suffix+'.partial');digest=hashlib.sha256();total=0
    with temporary.open('wb') as output:
        while True:
            line=reader.readline(130)
            if not line.endswith(b'\r\n') or len(line)>128:raise ValueError('Invalid chunk header')
            size=int(line.strip(),16)
            if size<0 or total+size>maximum:raise ValueError('Archive upload limit')
            if size==0:
                if reader.readline(3)!=b'\r\n':raise ValueError('Unexpected trailer')
                break
            left=size
            while left:
                block=reader.read(min(left,1024*1024))
                if not block:raise EOFError('Incomplete archive upload')
                output.write(block);digest.update(block);left-=len(block);total+=len(block)
            if reader.read(2)!=b'\r\n':raise ValueError('Invalid chunk boundary')
    if not total:raise ValueError('Empty image archive')
    temporary.replace(target)
    receipt={'bytes':total,'sha256':digest.hexdigest()}
    target.with_suffix(target.suffix+'.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    return receipt


def archive(path, entries):
    with tarfile.open(path,'w:gz') as tar:
        for name,value,mode in entries:
            data=value.encode() if isinstance(value,str) else value
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=mode
            tar.addfile(info,io.BytesIO(data))


def guest_endpoints(text,url):
    """Expand endpoint paths without corrupting names such as APERTURE_MODEL_URL."""
    return text.replace('URL/',url.rstrip('/')+'/')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--rocm-build',action='store_true');ap.add_argument('--accel',choices=['auto','whpx','tcg'],default='auto')
    ap.add_argument('--resume-production',action='store_true',help='Reuse completed CPU validation and staged model files; continue a failed production build')
    ap.add_argument('--verify-archive-reload',action='store_true',help='Optional additional full image copy into an empty daemon; requires substantial extra disk space')
    ap.add_argument('--cpu-model',default='Skylake-Client-v3');args=ap.parse_args()
    vm=ROOT/'.vm';logroot=ROOT/'research/linux-clean-room';logs=logroot
    bridge_state=ROOT/'.state/cache-bridge.json'
    bridge=json.loads(bridge_state.read_text(encoding='utf-8'))['guest_url'] if bridge_state.exists() else ''
    alpine=(bridge+'/alpine/v3.22') if bridge else 'https://dl-cdn.alpinelinux.org/alpine/v3.22'
    if logroot.exists() and any(logroot.iterdir()):logs=logroot/time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
    logs.mkdir(parents=True,exist_ok=True)
    (logroot/'latest.json').write_text(json.dumps({'directory':str(logs.relative_to(ROOT))}))
    qemu=next(iter((vm/'qemu').rglob('qemu-system-x86_64.exe')),None)
    img=next(iter((vm/'qemu').rglob('qemu-img.exe')),None)
    if not qemu or not img:raise RuntimeError('Extract the verified QEMU installer into .vm/qemu first')
    for asset in ['vmlinuz-virt','initramfs-virt','modloop-virt']:
        target=vm/asset;receipt=json.loads(target.with_suffix(target.suffix+'.complete.json').read_text(encoding='utf-8'))
        with target.open('rb') as f:digest=hashlib.file_digest(f,'sha512').hexdigest()
        if digest!=receipt['sha512']:raise RuntimeError('VM asset changed: '+asset)
    cpu_docker='''FROM python:3.14.4-slim
WORKDIR /app
ARG PLAYWRIGHT_DOWNLOAD_HOST
ARG PIP_FIND_LINKS
ARG PIP_NO_INDEX=0
ARG PIP_TRUSTED_HOST
ARG APERTURE_APT_CACHE
COPY requirements-core.lock requirements-test.lock requirements-browser.lock /app/
RUN if [ -n "$APERTURE_APT_CACHE" ]; then sed -i "s|http://deb.debian.org|$APERTURE_APT_CACHE/apt/deb.debian.org|g" /etc/apt/sources.list.d/debian.sources; fi \
 && pip install --no-cache-dir --no-deps -r requirements-core.lock -r requirements-test.lock -r requirements-browser.lock && pip check && python -m playwright install --with-deps --only-shell chromium
COPY . /app
ENV APERTURE_MODEL_URL="" APERTURE_OUTPUT=/app/output
CMD ["sleep","infinity"]
'''
    entries=[('Dockerfile.clean',cpu_docker,0o644)]
    files=[ROOT/'app.py',ROOT/'LICENSE',ROOT/'requirements-core.lock',ROOT/'requirements-test.lock',ROOT/'Dockerfile',ROOT/'.dockerignore',
        ROOT/'requirements.txt',ROOT/'requirements-model.txt',ROOT/'requirements-runtime.lock',ROOT/'requirements-browser.lock']
    for directory in ['agent','tests','fixtures','eval','scripts']:
        files.extend(p for p in (ROOT/directory).rglob('*.py') if '__pycache__' not in p.parts)
    files.extend((ROOT/'fixtures').glob('*.json'))
    files.extend((ROOT/'benchmarks').glob('*.py'))
    files.extend(ROOT/'benchmarks'/name for name in ['fakeweb.py','__init__.py','dev.json','holdout.json','live.json'])
    for file in sorted(set(files)):
        if file.is_file():entries.append((file.relative_to(ROOT).as_posix(),file.read_bytes(),0o644))
    archive(vm/'cpu-context.tar.gz',entries)
    report={'started_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'rocm_build_requested':args.rocm_build,
        'host_mounts':False,'network':'user-mode NAT; host server loopback only','artifacts':[]}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):return
        def do_GET(self):
            mapping={'/cpu-context.tar.gz':vm/'cpu-context.tar.gz','/aperture.apkovl.tar.gz':vm/'aperture.apkovl.tar.gz','/modloop-virt':vm/'modloop-virt','/guest-job.sh':vm/'guest-job.sh',
                '/image.tar.gz':logs/'image.tar.gz','/image.tar.gz.json':logs/'image.tar.gz.json'}
            if self.path=='/model-status':
                receipt=ROOT/'models/qwen/aperture-model.json'
                try:
                    data=json.loads(receipt.read_text(encoding='utf-8'))
                    ready=bool(data.get('files'))
                except (OSError,ValueError):ready=False;data={}
                body=json.dumps({'ready':ready,'receipt':data if ready else {}}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
            if self.path.startswith('/model/'):
                name=self.path.removeprefix('/model/')
                if not any(c in name for c in '/\\:\0') and name not in {'','.','..'}:
                    modelroot=ROOT/'models/qwen';modelpath=(modelroot/name).resolve()
                    if modelpath.is_relative_to(modelroot.resolve()):mapping[self.path]=modelpath
            target=mapping.get(self.path)
            if not target or not target.is_file():self.send_error(404);return
            self.send_response(200);self.send_header('Content-Length',str(target.stat().st_size));self.end_headers()
            try:
                with target.open('rb') as stream:
                    while chunk:=stream.read(256*1024):self.wfile.write(chunk)
            except (BrokenPipeError,ConnectionResetError):return
        def do_POST(self):
            if self.path=='/image.tar.gz':
                if self.headers.get('Transfer-Encoding','').lower()!='chunked':self.send_error(411);return
                try:receipt=receive_archive(self.rfile,logs/'image.tar.gz')
                except (ValueError,OSError,EOFError) as exc:self.send_error(400,str(exc));return
                report['image_archive']=receipt
                self.send_response(200);self.end_headers();self.wfile.write(b'ok');return
            names={'/cpu.log':'cpu.log','/result.json':'result.json','/rocm.log':'rocm.log','/rocm-progress.log':'rocm-progress.log','/image.json':'image.json','/packages.json':'packages.json','/reload.json':'reload.json','/rocm-result.json':'rocm-result.json'}
            name=names.get(self.path);size=int(self.headers.get('Content-Length','0'))
            if not name or not 0<size<=20_000_000:self.send_error(400);return
            data=self.rfile.read(size)
            (logs/name).write_bytes(data);report['artifacts'].append(name)
            self.send_response(200);self.end_headers();self.wfile.write(b'ok')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    port=server.server_port;url=f'http://10.0.2.2:{port}'
    # The sole guest disk is a new workspace qcow2 file with a distinct virtio serial/label.
    guest='''#!/bin/sh
set -eu
exec > /tmp/aperture-cpu.log 2>&1
( while true; do sleep 30; curl -s --max-time 5 -X POST --data-binary @/tmp/aperture-cpu.log URL/cpu.log >/dev/null || true; done ) &
heartbeat_pid=$!
echo 'APERTURE CLEAN ROOM START'
cat /etc/os-release
apk_ok=0
for attempt in $(seq 1 5); do
 if apk add --no-cache docker e2fsprogs e2fsprogs-extra util-linux curl python3; then apk_ok=1; break; fi
 sleep 1
done
test "$apk_ok" = 1
mkdir -p /.modloop
if ! mountpoint -q /.modloop; then
 curl --fail URL/modloop-virt -o /tmp/modloop-virt
 mount -t squashfs -o loop,ro /tmp/modloop-virt /.modloop
fi
if [ ! -e /lib/modules ]; then ln -s /.modloop/modules /lib/modules; fi
modprobe overlay
modprobe veth
serial=$(cat /sys/block/vda/serial)
test "$serial" = APERTURE_DATA
if ! blkid /dev/vda; then mkfs.ext4 -L APERTUREDATA /dev/vda; fi
test "$(blkid -s LABEL -o value /dev/vda)" = APERTUREDATA
fsck_status=0
e2fsck -p -f /dev/vda || fsck_status=$?
test "$fsck_status" -le 1
resize2fs /dev/vda
mkdir -p /data /var/lib/docker
mount /dev/vda /data
mkdir -p /data/docker /data/work/cpu /data/work/rocm
mount --bind /data/docker /var/lib/docker
ln -s /data/work /work
rc-service cgroups start || true
mkdir -p /etc/docker
printf '%s\n' 'DOCKER_CONFIG' > /etc/docker/daemon.json
dockerd > /tmp/dockerd.log 2>&1 &
for attempt in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 1; done
docker info || { cat /tmp/dockerd.log; exit 1; }
docker version
cd /work/cpu
curl --fail --retry 3 URL/cpu-context.tar.gz -o /tmp/context.tar.gz
tar -xzf /tmp/context.tar.gz
rm .dockerignore
'''
    guest=guest_endpoints(guest,url).replace('DOCKER_CONFIG',json.dumps({'registry-mirrors':[bridge]} if bridge else {}))
    if args.rocm_build:
        wait_cache=(f"for attempt in $(seq 1 8640); do curl --fail '{bridge}/registry-status' -o /tmp/registry-status.json; if python3 -c 'import json,sys;sys.exit(not json.load(open(\"/tmp/registry-status.json\"))[\"rocm_ready\"])'; then break; fi; sleep 10; done; " if bridge else '')
        guest+=f"( {wait_cache} docker pull '{BASE}' ) > /tmp/aperture-rocm.log 2>&1 &\npull_pid=$!\n"
        guest+=guest_endpoints('''( while true; do sleep 30; curl -s --max-time 5 -X POST --data-binary @/tmp/aperture-rocm.log URL/rocm-progress.log >/dev/null || true; done ) &
rocm_heartbeat_pid=$!
''',url)
    if bridge:
        guest+=f"for attempt in $(seq 1 8640); do curl --fail '{bridge}/wheel-status' -o /tmp/wheel-status.json; if python3 -c 'import json,sys;sys.exit(not json.load(open(\"/tmp/wheel-status.json\"))[\"ready\"])'; then break; fi; sleep 5; done\n"
    guest+='''status=0
docker build PIP_ARGS --build-arg PLAYWRIGHT_DOWNLOAD_HOST=BRIDGE -f Dockerfile.clean -t aperture-cpu-clean:local . || status=$?
if [ "$status" = 0 ]; then
 docker run --rm aperture-cpu-clean:local python -m pytest -q || status=$?
 docker run --rm aperture-cpu-clean:local python scripts/browser_smoke_test.py || status=$?
 docker run --rm aperture-cpu-clean:local python eval/run.py benchmarks/dev.json --fixtures fixtures/dev.json --out /tmp/dev || status=$?
 docker run --rm aperture-cpu-clean:local python eval/run.py benchmarks/holdout.json --fixtures fixtures/holdout.json --out /tmp/holdout || status=$?
 docker run --name aperture-cli-clean -d aperture-cpu-clean:local
 docker exec aperture-cli-clean python /app/app.py --query-id clean01 --query 'What is the license of the httpx package on PyPI?' --diagnostics || status=$?
 docker exec aperture-cli-clean cat /app/output/clean01_output.json || status=$?
 docker exec aperture-cli-clean cat /app/output/clean01_output.trace.json || status=$?
 docker exec aperture-cli-clean python -c 'import json; x=json.load(open("/app/output/clean01_output.json")); assert set(x)=={"answer","sources"}; assert x["answer"]=="BSD-3-Clause"; assert x["sources"]==["https://pypi.org/pypi/httpx/json"]' || status=$?
 docker rm -f aperture-cli-clean
fi
printf '{"cpu_exit":%s,"python_image":"python:3.14.4-slim"}\n' "$status" > /tmp/result.json
curl --fail -X POST --data-binary @/tmp/aperture-cpu.log URL/cpu.log
curl --fail -X POST --data-binary @/tmp/result.json URL/result.json
kill "$heartbeat_pid" || true
'''
    guest=guest_endpoints(guest,url).replace('BRIDGE',bridge).replace('PIP_ARGS',f'--build-arg PIP_FIND_LINKS={bridge}/wheels/ --build-arg PIP_NO_INDEX=1 --build-arg PIP_TRUSTED_HOST=10.0.2.2 --build-arg APERTURE_APT_CACHE={bridge}' if bridge else '')
    if args.resume_production:
        start=guest.index('status=0\ndocker build ')
        end=guest.index('kill "$heartbeat_pid" || true',start)
        guest=guest[:start]+'''printf '{"cpu_exit":0,"reused_prior_validation":true}\\n' > /tmp/result.json
curl --fail -X POST --data-binary @/tmp/result.json URL/result.json
'''.replace('URL/',url+'/')+guest[end:]
    if args.rocm_build:
        guest+='''cd /work/rocm
tar -xzf /tmp/context.tar.gz
wait "$pull_pid"
docker run --rm --entrypoint python3 BASE_IMAGE -c 'print("Python startup OK");import torch;print(torch.__version__,torch.version.hip)' >> /tmp/aperture-rocm.log 2>&1 || { dmesg | tail -n 12 >> /tmp/aperture-rocm.log; exit 1; }
mkdir -p models/qwen
for attempt in $(seq 1 8640); do
 curl --fail URL/model-status -o /tmp/model-status.json
 if python3 -c 'import json,sys;sys.exit(not json.load(open("/tmp/model-status.json"))["ready"])'; then break; fi
 sleep 10
done
python3 -c 'import json;d=json.load(open("/tmp/model-status.json"));assert d["ready"];print("\\n".join(x["name"] for x in d["receipt"]["files"])+"\\naperture-model.json")' > /tmp/model-files.txt
while read -r name; do if [ "RESUME_PRODUCTION" != 1 ] || [ ! -s "models/qwen/$name" ]; then curl --fail --retry 3 "URL/model/$name" -o "models/qwen/$name"; fi; done < /tmp/model-files.txt
rocm_status=0
docker build PIP_ARGS --build-arg PLAYWRIGHT_DOWNLOAD_HOST=BRIDGE -t aperture-rocm-clean:local . >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
if [ "$rocm_status" = 0 ]; then
 docker run --rm --entrypoint python3 aperture-rocm-clean:local -c 'import torch;print(torch.__version__,torch.version.hip);assert torch.version.hip' >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
 docker run --rm --entrypoint python3 aperture-rocm-clean:local scripts/runtime_compat_smoke.py --cpu >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
 python3 scripts/check_image.py aperture-rocm-clean:local > /tmp/image.json || rocm_status=$?
 curl --fail -X POST --data-binary @/tmp/image.json URL/image.json
 docker run --rm --entrypoint python3 aperture-rocm-clean:local scripts/container_inventory.py > /tmp/packages.json || rocm_status=$?
 curl --fail -X POST --data-binary @/tmp/packages.json URL/packages.json
fi
if [ "$rocm_status" = 0 ]; then
 # Stage tests only in an ephemeral container; fixtures never enter the built image.
 docker run --name aperture-rocm-validation -d --entrypoint sleep aperture-rocm-clean:local infinity >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
 docker cp /work/cpu/benchmarks aperture-rocm-validation:/app/ >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
 docker cp /work/cpu/scripts/browser_smoke_test.py aperture-rocm-validation:/app/scripts/ >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
 docker exec aperture-rocm-validation python3 scripts/browser_smoke_test.py >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
 docker exec -e APERTURE_MODEL_URL= aperture-rocm-validation python3 /app/app.py --query-id production01 --query 'What is the license of the httpx package on PyPI?' --diagnostics >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
 docker exec aperture-rocm-validation cat /app/output/production01_output.trace.json >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
 docker exec aperture-rocm-validation python3 -c 'import json;x=json.load(open("/app/output/production01_output.json"));assert set(x)=={"answer","sources"};assert x["answer"]=="BSD-3-Clause";assert x["sources"]==["https://pypi.org/pypi/httpx/json"]' >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
 docker rm -f aperture-rocm-validation >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
fi
if [ "$rocm_status" = 0 ]; then
 set -o pipefail
 docker save aperture-rocm-clean:local | gzip -1 | curl --fail --upload-file - -X POST URL/image.tar.gz >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
 if [ "$rocm_status" = 0 ] && [ "VERIFY_ARCHIVE_RELOAD" = 1 ]; then
  # Reclaim only this VM's tested image/build cache before the second full copy.
  # Reload into a new daemon data root so no existing layer can mask bad export.
  docker image rm aperture-rocm-clean:local 'BASE_IMAGE' >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
  docker builder prune --all --force >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
  reload_root=$(mktemp -d /data/aperture-reload.XXXXXX)
  printf '{}' > /tmp/aperture-reload-config.json
  dockerd --config-file=/tmp/aperture-reload-config.json --data-root="$reload_root" --exec-root=/tmp/aperture-reload-exec --pidfile=/tmp/aperture-reload.pid --host=unix:///tmp/aperture-reload.sock --bridge=none --iptables=false --ip-forward=false --ip-masq=false > /tmp/aperture-reload-daemon.log 2>&1 &
  reload_pid=$!
  export DOCKER_HOST=unix:///tmp/aperture-reload.sock
  for attempt in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 1; done
  docker info >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
  docker image ls -q > /tmp/aperture-reload-before.txt
  test ! -s /tmp/aperture-reload-before.txt || rocm_status=1
  curl --fail URL/image.tar.gz | docker load >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
  docker run --rm --network none --entrypoint python3 aperture-rocm-clean:local -m agent.model_assets /models/qwen >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
  docker run --rm --network none --entrypoint python3 aperture-rocm-clean:local -c 'import torch;assert torch.version.hip;print(torch.__version__,torch.version.hip)' >> /tmp/aperture-rocm.log 2>&1 || rocm_status=$?
  python3 -c 'import json,subprocess;before=json.load(open("/tmp/image.json"));assert not open("/tmp/aperture-reload-before.txt").read().strip();after=json.loads(subprocess.check_output(["docker","image","inspect","aperture-rocm-clean:local"]))[0];assert before["image_id"]==after["Id"];print(json.dumps({"empty_daemon_before_load":True,"image_id_matches":True,"image_id":after["Id"],"size_bytes":after["Size"]}))' > /tmp/reload.json || rocm_status=$?
  curl --fail -X POST --data-binary @/tmp/reload.json URL/reload.json
  cat /tmp/aperture-reload-daemon.log >> /tmp/aperture-rocm.log
  kill "$reload_pid" || true
 fi
fi
printf '\nROCM BUILD/IMPORT/IMAGE EXIT=%s\nNOT YET VERIFIED ON AMD: no AMD GPU passed to this guest.\n' "$rocm_status" >> /tmp/aperture-rocm.log
printf '{"rocm_exit":%s}\n' "$rocm_status" > /tmp/rocm-result.json
kill "$rocm_heartbeat_pid" || true
curl --fail -X POST --data-binary @/tmp/rocm-result.json URL/rocm-result.json
curl --fail -X POST --data-binary @/tmp/aperture-rocm.log URL/rocm.log
'''
        guest=guest_endpoints(guest,url).replace('VERIFY_ARCHIVE_RELOAD','1' if args.verify_archive_reload else '0').replace('RESUME_PRODUCTION','1' if args.resume_production else '0').replace('BASE_IMAGE',BASE).replace('BRIDGE',bridge).replace('PIP_ARGS',f'--build-arg PIP_FIND_LINKS={bridge}/wheels/ --build-arg PIP_NO_INDEX=1 --build-arg PIP_TRUSTED_HOST=10.0.2.2 --build-arg APERTURE_APT_CACHE={bridge}' if bridge else '')
    guest+='\nexit 0\n'
    if args.rocm_build and 'APERTURE_MODEL_URL=' not in guest:
        raise RuntimeError('Guest template corrupted the explicit inference-backend environment variable')
    (vm/'guest-job.sh').write_text(guest,encoding='utf-8',newline='\n')
    # Preserve diagnostics even when bootstrap/build fails.
    wrapper=f'''#!/bin/sh
wget -O /etc/aperture-test.sh {url}/guest-job.sh
sh /etc/aperture-test.sh
status=$?
if [ "$status" != 0 ]; then
 wget -O /dev/null --post-file=/tmp/aperture-cpu.log {url}/cpu.log || true
 printf '{{"bootstrap_exit":%s}}' "$status" > /tmp/bootstrap.json
 wget -O /dev/null --post-file=/tmp/bootstrap.json {url}/result.json || true
 if [ -f /tmp/aperture-rocm.log ]; then wget -O /dev/null --post-file=/tmp/aperture-rocm.log {url}/rocm.log || true; fi
fi
poweroff -f
'''
    overlay=[('etc/apk/repositories',alpine+'/main\n'+alpine+'/community\n',0o644),('etc/.default_boot_services','',0o644),
        ('etc/aperture-test.sh',guest,0o700),('etc/local.d/aperture.start',wrapper,0o700)]
    archive(vm/'aperture.apkovl.tar.gz',overlay)
    # Add the OpenRC symlink without touching any host service.
    with tarfile.open(vm/'aperture.apkovl.tar.gz','r:gz') as tar:members=[(m,tar.extractfile(m).read()) for m in tar.getmembers()]
    with tarfile.open(vm/'aperture.apkovl.tar.gz','w:gz') as tar:
        for m,data in members:tar.addfile(m,io.BytesIO(data))
        link=tarfile.TarInfo('etc/runlevels/default/local');link.type=tarfile.SYMTYPE;link.linkname='/etc/init.d/local';tar.addfile(link)
    disk=vm/'cleanroom-data.qcow2'
    if not disk.resolve().is_relative_to((ROOT/'.vm').resolve()):raise ValueError('Unexpected virtual disk target')
    if not disk.exists():subprocess.run([str(img),'create','-f','qcow2',str(disk.relative_to(ROOT)),'160G'],check=True,capture_output=True,cwd=ROOT)
    else:
        disk_info=json.loads(subprocess.check_output([str(img),'info','--output=json',str(disk.relative_to(ROOT))],cwd=ROOT))
        if disk_info['virtual-size']<160*1024**3:
            subprocess.run([str(img),'resize',str(disk.relative_to(ROOT)),'160G'],check=True,capture_output=True,cwd=ROOT)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    command=[str(qemu),'-L',(qemu.parent/'share').relative_to(ROOT).as_posix(),'-cpu','max' if args.accel=='tcg' else args.cpu_model,'-m','4096','-smp','4','-display','none','-monitor','none','-no-reboot',
        '-kernel','.vm/vmlinuz-virt','-initrd','.vm/initramfs-virt',
        '-append',f'console=ttyS0 ip=dhcp pkgs=alpine-base,openrc-init init=/sbin/openrc-init modules=loop,squashfs,virtio_net,virtio_blk alpine_repo={alpine}/main modloop={url}/modloop-virt apkovl={url}/aperture.apkovl.tar.gz',
        '-netdev','user,id=n0','-device','virtio-net-pci,netdev=n0',
        '-drive',f'file={disk.relative_to(ROOT).as_posix()},format=qcow2,if=none,id=d0','-device','virtio-blk-pci,drive=d0,serial=APERTURE_DATA',
        '-chardev',f'file,id=console,path={(logs / "serial.log").relative_to(ROOT).as_posix()}','-serial','chardev:console']
    report['command']=command;report['context_sha256']=hashlib.sha256((vm/'cpu-context.tar.gz').read_bytes()).hexdigest()
    child=None
    try:
        with (logs/'qemu.log').open('wb') as log:
            requested='tcg,thread=multi' if args.accel=='tcg' else 'whpx'
            child=subprocess.Popen(command+['-accel',requested],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW,cwd=ROOT)
            try:code=child.wait(timeout=5)
            except subprocess.TimeoutExpired:code=None
            log.flush()
            first_error=(logs/'qemu.log').read_text(encoding='utf-8',errors='replace').lower()
            failed=code is not None and code!=0 or 'unexpected vp exit' in first_error
            if failed and args.accel=='auto':
                if child.poll() is None:child.terminate();child.wait(timeout=5)
                if not ('whpx' in first_error or 'whv' in first_error):raise RuntimeError('QEMU failed before boot; see qemu.log')
                report['acceleration']='tcg (WHPX failed; see retained qemu.log)'
                command[command.index('-cpu')+1]='max'
                child=subprocess.Popen(command+['-accel','tcg,thread=multi'],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW,cwd=ROOT)
            else:report['acceleration']=requested
            print(json.dumps(report),flush=True)
            report['qemu_exit']=child.wait(timeout=86400)
    finally:
        if child and child.poll() is None:child.terminate();child.wait(timeout=10)
        server.shutdown();server.server_close();thread.join(timeout=3)
        report['finished_at_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        (logs/'host-report.json').write_text(json.dumps(report,indent=2))
    if report.get('qemu_exit')!=0 or not (logs/'result.json').exists():raise RuntimeError('Linux guest did not complete validation; see '+str(logs))
    result=json.loads((logs/'result.json').read_text(encoding='utf-8'))
    if result.get('cpu_exit')!=0:raise RuntimeError('Linux CPU validation failed: '+str(result)+'; see '+str(logs))
    if args.rocm_build:
        result_path=logs/'rocm-result.json'
        if not result_path.is_file() or json.loads(result_path.read_text(encoding='utf-8')).get('rocm_exit')!=0 or not report.get('image_archive') or args.verify_archive_reload and not (logs/'reload.json').is_file():
            raise RuntimeError('Production image validation/export did not complete; see '+str(logs))


if __name__=='__main__':main()
