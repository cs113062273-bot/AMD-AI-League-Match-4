"""Measure real CUDA startup, resident lifecycle, process-per-query contract and model ablations."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
import signal
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def health():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8765/health',timeout=1) as r:return json.load(r)
    except (OSError,ValueError):return None


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--keep-server',action='store_true');ap.add_argument('--tag',default='');ap.add_argument('--browser',action='store_true')
    ap.add_argument('--fixtures-only',action='store_true',help='Run offline inference and actual loopback CLI checks; omit public-web measurements')
    ap.add_argument('--online-only',action='store_true',help='Measure public-web suites and fresh CLI without repeating completed fixture suites')
    args=ap.parse_args()
    if args.fixtures_only and args.online_only:ap.error('Choose one validation scope')
    if args.tag and (not args.tag.isalnum() or len(args.tag)>30):ap.error('tag must be a short alphanumeric label')
    suffix='-'+args.tag if args.tag else ''
    os.chdir(ROOT)
    logdir=ROOT/('research/local-gpu'+suffix);logdir.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env.update(APERTURE_MODEL=str(ROOT/'models/qwen'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONIOENCODING='utf-8',APERTURE_STATE=str(logdir/'state'))
    env['APERTURE_BROWSER']='1' if args.browser else '0'
    samples=[];stop=threading.Event()
    def monitor():
        while not stop.is_set():
            try:
                raw=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],timeout=3,text=True)
                samples.append({'seconds':time.monotonic()-start,'device_used_mib':int(raw.splitlines()[0])})
            except (OSError,ValueError,subprocess.SubprocessError):
                samples.append({'seconds':time.monotonic()-start,'unavailable':True})
            stop.wait(1)
    child=None;startup_clients=[];start=time.monotonic();thread=threading.Thread(target=monitor,daemon=True);thread.start()
    report={'hardware':'actual local execution','scope':'offline fixtures and loopback HTTP' if args.fixtures_only else 'public web' if args.online_only else 'fixtures and public web',
        'started_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'runs':[]}
    try:
        ready=health()
        if ready:
            raise RuntimeError('Port already has a server; require an isolated cold-start measurement')
        with (logdir/'server.log').open('wb') as log:
            child=subprocess.Popen([sys.executable,'app.py','--serve'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                start_new_session=os.name!='nt',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        # Race the default container command with two real process-per-startup clients.
        for index in range(2):
            with (logdir/f'startup-client-{index}.log').open('wb') as log:
                startup_clients.append(subprocess.Popen([sys.executable,'app.py','--warmup'],cwd=ROOT,env=env,
                    stdout=log,stderr=subprocess.STDOUT,start_new_session=os.name!='nt',
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
        limit=start+540
        while time.monotonic()<limit:
            ready=health()
            if ready and ready.get('ready'):break
            if child.poll() is not None:
                report['startup_exit_code']=child.returncode
                raise RuntimeError(f'Model startup failed (exit {child.returncode}); see server.log')
            time.sleep(.25)
        if not ready or not ready.get('ready'):raise RuntimeError('Model did not become inference-ready')
        report['cold_start_seconds']=time.monotonic()-start
        report['health_before']=ready
        report['startup_clients']=[]
        for index,client in enumerate(startup_clients):
            code=client.wait(timeout=15)
            if code:raise RuntimeError(f'Concurrent startup client {index} failed; inspect its log')
            data=json.loads((logdir/f'startup-client-{index}.log').read_text(encoding='utf-8'))
            report['startup_clients'].append({'returncode':code,'pid':data.get('pid'),'ready':data.get('ready')})
        if not all(item['pid']==ready['pid'] and item['ready'] for item in report['startup_clients']):
            raise RuntimeError('Concurrent startup clients did not reach the same resident instance')
        load_events=[]
        for line in (logdir/'state/model.log').read_text(encoding='utf-8',errors='replace').splitlines():
            try:data=json.loads(line)
            except ValueError:continue
            if isinstance(data,dict) and data.get('ready') and data.get('parameters'):load_events.append(data)
        report['startup_model_load_events']=len(load_events)
        if len(load_events)!=1:raise RuntimeError('Startup race loaded the resident model more than once')
        def post(data,origin=None):
            headers={'Content-Type':'application/json'}
            if origin:headers['Origin']=origin
            req=urllib.request.Request('http://127.0.0.1:8765/select',data=json.dumps(data).encode(),headers=headers)
            try:
                with urllib.request.urlopen(req,timeout=8) as r:return {'status':r.status,'reply':json.load(r)}
            except urllib.error.HTTPError as exc:return {'status':exc.code,'reply':json.load(exc)}
        sample={'question':'What is the value of x?','candidates':[],'passages':[{'id':0,'text':'x: 7'}]}
        report['protocol_checks']={'invalid_schema':post({'question':7}),'cross_origin':post(sample,'https://untrusted.example')}
        if report['protocol_checks']['invalid_schema']['status']!=400 or report['protocol_checks']['cross_origin']['status']!=403:
            raise RuntimeError('Resident protocol rejection failed')
        with ThreadPoolExecutor(6) as pool:report['concurrent_requests']=list(pool.map(lambda _:post(sample),range(6)))
        statuses=[row['status'] for row in report['concurrent_requests']]
        if not 200 in statuses or any(s not in {200,503} for s in statuses):raise RuntimeError('Concurrent selector health failed')
        long_request={'question':'What is x?','candidates':[],
            'passages':[{'id':i,'text':'x: 19. '+('unrelated reference observation '*145)} for i in range(8)]}
        report['long_context']=post(long_request)
        if report['long_context']['status']!=200 or report['long_context']['reply'].get('error'):
            raise RuntimeError('Bounded long-context inference failed')
        commands=[
            ['scripts/gpu_smoke_test.py','--server'],
            ['eval/run.py','benchmarks/dev.json','--fixtures','fixtures/dev.json','--budget','24','--model','--out','benchmarks/dev-model'],
            ['eval/run.py','benchmarks/holdout.json','--fixtures','fixtures/holdout.json','--budget','24','--model','--out','benchmarks/holdout-model'],
            ['eval/run.py','benchmarks/final-holdout.json','--fixtures','fixtures/final-holdout.json','--budget','24','--model','--out','benchmarks/final-holdout-model'],
            ['eval/run.py','benchmarks/live.json','--budget','24','--model','--out','benchmarks/live-model'],
            ['eval/run.py','benchmarks/live-holdout.json','--budget','24','--model','--out','benchmarks/live-transfer-model'],
            ['eval/run_public_baseline.py'],
        ]
        commands.insert(4,['eval/run.py','benchmarks/transfer-frozen.json','--fixtures','fixtures/transfer-frozen.json','--budget','24','--model','--out','benchmarks/transfer-frozen-model'])
        if args.fixtures_only:
            commands=[cmd for cmd in commands if cmd[0]=='scripts/gpu_smoke_test.py' or '--fixtures' in cmd]
        elif args.online_only:
            commands=[cmd for cmd in commands if '--fixtures' not in cmd]
        for command in commands:
            if command[0]=='eval/run.py':command[command.index('--out')+1]+=suffix
            if command[0]=='eval/run.py' and '--fixtures' not in command and args.browser:command+=['--browser']
            if command[0]=='eval/run_public_baseline.py':command+=['--out','benchmarks/public-pinpoint-comparison'+suffix]
        for index,cmd in enumerate(commands):
            print('RUN',*cmd,flush=True)
            began=time.monotonic()
            with (logdir/f'run-{index}.log').open('wb') as out:
                p=subprocess.run([sys.executable,*cmd],env=env,stdout=out,stderr=subprocess.STDOUT,timeout=2400)
            report['runs'].append({'command':cmd,'returncode':p.returncode,'seconds':time.monotonic()-began})
            if p.returncode:raise RuntimeError('Validation command failed: '+' '.join(cmd))
        cases=json.loads(Path('benchmarks/dev.json' if args.fixtures_only else 'benchmarks/live.json').read_text(encoding='utf-8'))
        chosen=cases[:3] if args.fixtures_only else [c for c in cases if c['id'] in {'pep-440','arxiv-first-author','pypi-flask-requires_python'}]
        contract=[]
        from contextlib import nullcontext
        from benchmarks.fakeweb import FakeWeb
        fixture=FakeWeb(json.loads(Path('fixtures/dev.json').read_text(encoding='utf-8'))) if args.fixtures_only else nullcontext(None)
        with fixture as web:
            for i,c in enumerate(chosen):
                url=c.get('url',c.get('path',''));source=c.get('source',c.get('source_path',''))
                cli_env=dict(env)
                if web:
                    from urllib.parse import urlsplit
                    url=web.base+urlsplit(url).path;source=web.base+urlsplit(source).path
                    cli_env.update(APERTURE_ALLOW_PRIVATE='1',APERTURE_SEARCH='0')
                cmd=[sys.executable,'app.py','--query-id',f'gpu-process-{i}','--query',c['query'],'--output-dir','output/gpu-contract','--diagnostics']
                if url:cmd+=['--url',url]
                p=subprocess.run(cmd,env=cli_env,capture_output=True,timeout=28)
                data=json.loads(p.stdout)
                contract.append({'id':c['id'],'returncode':p.returncode,'answer_ok':data['answer']==c['answer'],
                    'source_ok':data['sources']==[source],'sources':data['sources']})
        report['process_contract']=contract
        if not all(row['returncode']==0 and row['answer_ok'] and row['source_ok'] for row in contract):
            raise RuntimeError('Fresh CLI answer/source contract failed; inspect process_contract')
        report['health_after']=health()
        report['launcher_pid']=child.pid
        # Windows venv redirectors launch a second Python process; compare the actual
        # server-reported PID across queries rather than confusing it with its launcher.
        report['server_pid_stable']=report['health_before'].get('pid')==report['health_after'].get('pid')
        if not report['server_pid_stable']:raise RuntimeError('Resident model restarted during query validation')
        if report['health_after']['peak_vram_bytes']>report['health_after']['device_memory_bytes']:
            raise RuntimeError('Torch allocation exceeded physical device memory; do not claim a VRAM fit')
    except Exception as exc:
        report['error']=f'{type(exc).__name__}: {exc}'
        raise
    finally:
        if not args.keep_server and report.get('health_before',{}).get('pid'):
            try:os.kill(report['health_before']['pid'],signal.SIGTERM)
            except OSError:pass
        from agent.processes import stop_started_process
        for client in startup_clients:
            if client.poll() is None:stop_started_process(client)
        if child and not args.keep_server:
            stop_started_process(child)
        stop.set();thread.join(timeout=5)
        report['device_samples']=samples
        report['peak_total_device_mib']=max((s.get('device_used_mib',0) for s in samples),default=None)
        Path('benchmarks/local-gpu-validation'+suffix+'.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k!='device_samples'},indent=2),flush=True)


if __name__=='__main__':main()
