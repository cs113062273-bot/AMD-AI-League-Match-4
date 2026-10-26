"""Cross-process crates API pacing against loopback HTTP; no public requests or model.

Authored transport controls, not competition questions or model accuracy.
"""
import argparse
import asyncio
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
from urllib.parse import urlsplit

import aiohttp
from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.network import Fetcher
from agent.types import Deadline, Settings
from revision_engine import load_engine


def fetcher_for(revision):
    if not revision:
        return Fetcher
    engine, _, _ = load_engine(revision)
    return importlib.import_module(engine.__module__.rsplit('.', 1)[0] + '.network').Fetcher


def transport_to(base):
    original = aiohttp.ClientSession._request

    async def transport(self, method, url, *args, **kwargs):
        p = urlsplit(str(url))
        if p.hostname in {'crates.io', 'www.crates.io'}:
            url = base + p.path + ('?' + p.query if p.query else '')
        elif p.hostname != '127.0.0.1':
            raise ValueError('Unexpected external transport')
        return await original(self, method, url, *args, **kwargs)
    return transport


async def worker(payload):
    cls = fetcher_for(payload.get('baseline'))
    base = payload['base']
    settings = Settings(model_url='', search=False, browser=False, allow_private=True)
    with patch.object(aiohttp.ClientSession, '_request', transport_to(base)):
        async with cls(settings, Deadline(8)) as fetcher:
            async with aiohttp.ClientSession() as session:
                async with session.get(base + '/ready', timeout=aiohttp.ClientTimeout(total=8)) as r:
                    await r.read()
            response = await fetcher.fetch(payload['url'], timeout=6)
            return {'status': response.status, 'error': response.error, 'torch_imported': 'torch' in sys.modules}


async def diagnose(cls, baseline):
    rows = []
    hits = []
    mode = ''
    waiting = 0
    ready = asyncio.Event()
    hanging = asyncio.Event()
    release = asyncio.Event()

    async def source(request):
        nonlocal waiting
        if request.path == '/ready':
            waiting += 1
            if waiting >= (3 if mode == 'processes' else 1):
                ready.set()
            await asyncio.wait_for(ready.wait(), 8)
            return web.Response(text='ready')
        if request.path == '/redirect':
            return web.Response(status=302, headers={'Location': 'https://crates.io/api/v1/crates/from-redirect'})
        if not request.path.startswith('/api/'):
            return web.Response(text='ordinary page')
        now = time.monotonic()
        gap = now - hits[-1]['start'] if hits else None
        status = 429 if mode == 'processes' and gap is not None and gap < 1 else 200
        if mode == 'error':
            status = 429
        row = {'path': request.path_qs, 'start': now, 'status': status}
        hits.append(row)
        if mode == 'redirect-api' and request.path.endswith('/first'):
            row['end'] = time.monotonic()
            return web.Response(status=302, headers={'Location': 'https://www.crates.io/api/v1/crates/second'})
        if mode == 'slow':
            await asyncio.sleep(.15)
        if mode in {'kill-owner', 'cancel-owner'} and request.path.endswith('/held'):
            response = web.StreamResponse(headers={'Content-Type': 'application/json'})
            await response.prepare(request)
            hanging.set()
            await release.wait()
            row['end'] = time.monotonic()
            return response
        row['end'] = time.monotonic()
        return web.json_response({'crate': 'sample'}, status=status)

    app = web.Application()
    app.router.add_get('/{tail:.*}', source)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    base = 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
    settings = Settings(model_url='', search=False, browser=False, allow_private=True)
    children = []

    def add(name, passed, **detail):
        rows.append({'id': name, 'passed': bool(passed), **detail})

    def reset(name, folder):
        nonlocal mode, waiting
        mode = name
        hits.clear()
        waiting = 0
        ready.clear()
        hanging.clear()
        release.clear()
        os.environ['APERTURE_STATE'] = str(folder)

    async def read(url, seconds=8, timeout=6):
        async with cls(settings, Deadline(seconds)) as fetcher:
            return await fetcher.fetch(url, timeout=timeout)

    async def spawn(url):
        payload = {'base': base, 'url': url, 'baseline': baseline}
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        child = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).resolve()),
            '--worker', json.dumps(payload), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
        children.append(child)
        return child

    async def collect(child):
        stdout, stderr = await asyncio.wait_for(child.communicate(), 12)
        if child.returncode:
            raise RuntimeError(stderr.decode('utf-8', errors='replace')[-2000:])
        return json.loads(stdout)

    try:
        with tempfile.TemporaryDirectory(prefix='aperture-crates-pacing-') as temp, patch.dict(os.environ), \
                patch.object(aiohttp.ClientSession, '_request', transport_to(base)):
            root = Path(temp)
            reset('processes', root / 'processes')
            processes = [await spawn('https://' + ('www.crates.io' if i == 1 else 'crates.io')
                + '/api/v1/crates/package-' + str(i)) for i in range(3)]
            outputs = await asyncio.gather(*(collect(child) for child in processes))
            gaps = [b['start'] - a['start'] for a, b in zip(hits, hits[1:])]
            add('three-workers-shared-bucket', len(hits) == 3 and all(o['status'] == 200 for o in outputs)
                and all(gap >= 1 for gap in gaps), gaps=gaps, outputs=outputs)

            reset('slow', root / 'slow')
            responses = await asyncio.gather(*(read('https://crates.io/api/v1/crates/' + str(i)) for i in range(2)))
            add('independent-fetchers-and-response-completion', all(r.status == 200 for r in responses)
                and len(hits) == 2 and hits[1]['start'] - hits[0]['end'] >= 1, hits=list(hits))

            reset('cache', root / 'cache')
            async with cls(settings, Deadline(4)) as fetcher:
                one = await fetcher.fetch('https://crates.io/api/v1/crates/cached')
                start = time.monotonic()
                two = await fetcher.fetch('https://crates.io/api/v1/crates/cached')
                add('cache-needs-no-slot', one is two and len(hits) == 1 and time.monotonic() - start < .2)

            reset('deadline', root / 'deadline')
            await read('https://crates.io/api/v1/crates/seed')
            start = time.monotonic()
            result = await read('https://crates.io/api/v1/crates/too-soon', seconds=.6)
            add('waiting-counts-against-query-deadline', len(hits) == 1 and 'TimeoutError' in result.error
                and time.monotonic() - start < .8, error=result.error)
            result = await read('https://crates.io/api/v1/crates/after-deadline')
            add('deadline-releases-lock', result.status == 200 and len(hits) == 2
                and hits[1]['start'] - hits[0]['start'] >= 1)

            reset('request-timeout', root / 'request-timeout')
            await read('https://crates.io/api/v1/crates/seed')
            start = time.monotonic()
            result = await read('https://crates.io/api/v1/crates/too-soon', timeout=.15)
            add('waiting-counts-against-request-timeout', len(hits) == 1 and 'TimeoutError' in result.error
                and time.monotonic() - start < .5, error=result.error)

            reset('cancel', root / 'cancel')
            await read('https://crates.io/api/v1/crates/seed')
            task = asyncio.create_task(read('https://crates.io/api/v1/crates/cancelled'))
            await asyncio.sleep(.05)
            task.cancel()
            cancelled = False
            try:
                await task
            except asyncio.CancelledError:
                cancelled = True
            add('cancel-waiter-sends-no-http', cancelled and len(hits) == 1)
            result = await read('https://crates.io/api/v1/crates/after-cancel')
            add('cancel-releases-lock', result.status == 200 and len(hits) == 2
                and hits[1]['start'] - hits[0]['start'] >= 1)

            reset('unrelated', root / 'unrelated')
            await read('https://crates.io/api/v1/crates/seed')
            start = time.monotonic()
            result = await read('https://crates.io/crates/frontend')
            add('frontend-not-in-api-bucket', result.status == 200 and time.monotonic() - start < .2)
            result = await read(base + '/ordinary')
            add('other-origin-unaffected', result.status == 200 and len(hits) == 1)

            reset('redirect-api', root / 'redirect-api')
            result = await read('https://crates.io/api/v1/crates/first')
            add('each-api-redirect-hop-paced', result.status == 200 and len(hits) == 2
                and hits[1]['start'] - hits[0]['start'] >= 1, hits=list(hits))

            reset('redirect-into-api', root / 'redirect-into-api')
            await read('https://crates.io/api/v1/crates/seed')
            result = await read(base + '/redirect')
            add('redirect-into-api-paced', result.status == 200 and len(hits) == 2
                and hits[1]['start'] - hits[0]['start'] >= 1)

            reset('error', root / 'error')
            responses = [await read('https://crates.io/api/v1/crates/' + str(i)) for i in range(2)]
            add('429-no-retry-and-counted', all(r.status == 429 for r in responses) and len(hits) == 2
                and hits[1]['start'] - hits[0]['start'] >= 1)

            reset('state-failure', root / 'not-directory')
            Path(os.environ['APERTURE_STATE']).write_text('file', encoding='ascii')
            result = await read('https://crates.io/api/v1/crates/unpaced')
            add('state-failure-no-unpaced-request', bool(result.error) and not hits, error=result.error)

            reset('corrupt-state', root / 'corrupt')
            folder = Path(os.environ['APERTURE_STATE'])
            folder.mkdir()
            (folder / 'crates-api.pacing').write_bytes(b'broken record')
            start = time.monotonic()
            result = await read('https://crates.io/api/v1/crates/repaired')
            add('corrupt-record-cooldown', result.status == 200 and len(hits) == 1
                and time.monotonic() - start >= 1)

            reset('kill-owner', root / 'kill-owner')
            child = await spawn('https://crates.io/api/v1/crates/held')
            await asyncio.wait_for(hanging.wait(), 8)
            child.terminate()  # Only this diagnostic's own cooperative CPU child.
            await asyncio.wait_for(child.communicate(), 5)
            result = await read('https://crates.io/api/v1/crates/after-kill')
            add('killed-owner-lock-recovers', result.status == 200 and len(hits) == 2
                and hits[1]['start'] - hits[0]['start'] >= 1, hits=list(hits))
            release.set()

            reset('kill-owner', root / 'kill-old-owner')
            child = await spawn('https://crates.io/api/v1/crates/held')
            await asyncio.wait_for(hanging.wait(), 8)
            await asyncio.sleep(1.15)
            child.terminate()
            await asyncio.wait_for(child.communicate(), 5)
            start = time.monotonic()
            result = await read('https://crates.io/api/v1/crates/after-old-kill')
            add('incomplete-old-owner-full-cooldown', result.status == 200 and len(hits) == 2
                and time.monotonic() - start >= 1)
            release.set()

            reset('cancel-owner', root / 'cancel-active-owner')
            owner = asyncio.create_task(read('https://crates.io/api/v1/crates/held'))
            await asyncio.wait_for(hanging.wait(), 8)
            waiter = asyncio.create_task(read('https://crates.io/api/v1/crates/cancelled-waiter'))
            await asyncio.sleep(.05)
            waiter.cancel()
            cancelled = False
            try:
                await waiter
            except asyncio.CancelledError:
                cancelled = True
            add('cancel-contending-waiter-keeps-owner', cancelled and not owner.done() and len(hits) == 1)
            owner.cancel()
            try:
                await owner
            except asyncio.CancelledError:
                pass
            start = time.monotonic()
            result = await read('https://crates.io/api/v1/crates/after-owner-cancel')
            add('cancel-active-owner-full-cooldown', result.status == 200 and len(hits) == 2
                and time.monotonic() - start >= 1)
            release.set()
    finally:
        release.set()
        for child in children:
            if child.returncode is None:
                child.terminate()
                await child.communicate()
        await runner.cleanup()
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out')
    parser.add_argument('--baseline')
    parser.add_argument('--worker')
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(asyncio.run(worker(json.loads(args.worker)))))
        sys.exit(0)
    target = Path(args.out)
    if target.exists():
        raise FileExistsError(target)
    rows = asyncio.run(diagnose(fetcher_for(args.baseline), args.baseline))
    sources = ['agent/network.py', 'agent/request_pacing.py']
    if args.baseline:
        import subprocess
        source_hashes = {'agent/network.py': hashlib.sha256(subprocess.check_output(
            ['git', 'show', args.baseline + ':agent/network.py'])).hexdigest()}
    else:
        source_hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources}
    report = {'scope': __doc__, 'baseline': args.baseline, 'platform': sys.platform,
              'source_sha256': source_hashes,
              'diagnostic_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'passed': sum(r['passed'] for r in rows), 'total': len(rows), 'rows': rows,
              'torch_imported': 'torch' in sys.modules}
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'total': report['total'],
                      'failures': [r['id'] for r in rows if not r['passed']]}))
