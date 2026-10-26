"""Exercise the production HTTP cancellation lifecycle without loading 4B weights.

The HTTP probe uses a cooperative deterministic worker. The generation probe
separately uses Runtime.infer with an actual tiny randomly initialized CPU Qwen3.
Neither probe measures full-model accuracy, GPU memory, or AMD performance.
"""
import asyncio
from collections import deque
import json
from pathlib import Path
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aiohttp
from agent.model_client import request_model
from agent.model_server import Runtime, RequestControl, InferenceStopped, make_server
from agent.types import Deadline, Settings


class ProbeRuntime:
    def __init__(self):
        self.lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.active = None
        self.busy_rejections = self.calls = 0
        self.outcomes = {}
        self.device = 'cpu'

    def health(self):
        return {'calls': self.calls, 'active_request': self.active.request_id if self.active else None,
                'outcomes': dict(self.outcomes), 'busy_rejections': self.busy_rejections}

    def infer(self, data, control):
        if data['question'] == 'wait':
            while True:
                control.check()
                time.sleep(.005)
        control.check()
        return {'candidate': -1, 'passage': 0, 'answer': '7'}


async def http_probe():
    runtime = ProbeRuntime()
    server = make_server(runtime, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    rows = []

    async def wait_for(predicate):
        end = time.monotonic() + 1
        while not predicate():
            if time.monotonic() >= end:
                raise TimeoutError('Service did not reach expected state')
            await asyncio.sleep(.005)

    async def post(session, path, data, headers=None):
        async with session.post(base + path, json=data, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=2)) as response:
            return response.status, await response.json()

    data = {'question': 'wait', 'passages': [{'id': 0, 'text': 'x: 7'}]}
    try:
        async with aiohttp.ClientSession(trust_env=False) as session:
            request_id = uuid.uuid4().hex
            task = asyncio.create_task(post(session, '/select', data,
                {'X-Aperture-Request-ID': request_id, 'X-Aperture-Expires': str(time.time() + 1.5)}))
            await wait_for(lambda: runtime.active is not None)
            status, reply = await post(session, '/select', data)
            rows.append({'id': 'single_active_request', 'passed': status == 503 and reply == {'error': 'busy'}})
            status, reply = await post(session, '/cancel', {'request_id': uuid.uuid4().hex})
            rows.append({'id': 'cancel_different_id_is_noop', 'passed': reply == {'cancelled': False} and runtime.active is not None})
            started = time.monotonic()
            await post(session, '/cancel', {'request_id': request_id})
            status, reply = await task
            rows.append({'id': 'explicit_cancel_releases_worker', 'passed': reply == {'error': 'cancelled'}
                and runtime.active is None, 'seconds': time.monotonic() - started})
            status, reply = await post(session, '/select', {**data, 'question': 'next'})
            rows.append({'id': 'next_request_after_cancel', 'passed': status == 200 and reply.get('answer') == '7'})
            started = time.monotonic()
            status, reply = await post(session, '/select', data,
                {'X-Aperture-Request-ID': uuid.uuid4().hex, 'X-Aperture-Expires': str(time.time() + .1)})
            rows.append({'id': 'deadline_releases_worker', 'passed': reply == {'error': 'deadline'}
                and runtime.active is None, 'seconds': time.monotonic() - started})
            task = asyncio.create_task(request_model(Settings(model_url=base, model_timeout=1.5),
                Deadline(3), '/select', data))
            await wait_for(lambda: runtime.active is not None)
            started = time.monotonic()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await wait_for(lambda: runtime.active is None)
            rows.append({'id': 'cancelled_client_cancels_server', 'passed': runtime.outcomes.get('cancelled') == 2,
                         'seconds': time.monotonic() - started})
            reply, state = await request_model(Settings(model_url=base), Deadline(3), '/select', {**data, 'question': 'next'})
            rows.append({'id': 'next_client_request_succeeds', 'passed': state == 'ok' and reply.get('answer') == '7'})
            calls = runtime.calls
            status, reply = await post(session, '/select', data, {'X-Aperture-Expires': str(time.time() - 1)})
            rows.append({'id': 'expired_request_does_not_start', 'passed': reply == {'error': 'deadline'} and runtime.calls == calls})
        return rows, runtime.health()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def generation_probe():
    import torch
    from transformers import AutoTokenizer, Qwen3Config, Qwen3ForCausalLM
    torch.set_num_threads(2)
    torch.manual_seed(7)
    runtime = Runtime.__new__(Runtime)
    runtime.torch, runtime.device = torch, 'cpu'
    runtime.tokenizer = AutoTokenizer.from_pretrained('models/qwen', local_files_only=True, trust_remote_code=False)
    config = Qwen3Config(vocab_size=len(runtime.tokenizer), hidden_size=32, intermediate_size=64,
        num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=1, head_dim=16,
        max_position_embeddings=4096, eos_token_id=runtime.tokenizer.eos_token_id)
    runtime.model = Qwen3ForCausalLM(config).eval()
    runtime.context_limit = 3072
    runtime.token_stats = {'max_input': 0, 'generated': 0, 'pruned_requests': 0}
    runtime.requests = deque(maxlen=32)
    data = {'question': 'Select the value of x.', 'passages': [{'id': 0, 'text': 'x: 7'}]}

    class CancelAtFirstToken(RequestControl):
        def __call__(self, input_ids, scores, **kwargs):
            self.cancelled.set()
            return super().__call__(input_ids, scores, **kwargs)

    reason = None
    try:
        runtime.infer(data, control=CancelAtFirstToken(uuid.uuid4().hex, 10))
    except InferenceStopped as exc:
        reason = str(exc)
    first = dict(runtime.requests[-1])
    reply = runtime.infer(data, control=RequestControl(uuid.uuid4().hex, 10))
    second = dict(runtime.requests[-1])
    return [
        {'id': 'actual_cpu_generate_cancels_at_token_boundary', 'passed': reason == 'cancelled'
            and first['generated_tokens'] == 1, 'record': first},
        {'id': 'actual_cpu_generate_runs_after_cancel', 'passed': second['stop_reason'] == 'completed'
            and second['generated_tokens'] > 1, 'record': second, 'reply': reply,
            'note': 'Random tiny weights are not expected to answer; invalid JSON is an explicit protocol error.'},
    ]


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    target = Path(args.out)
    if target.exists():
        raise FileExistsError(target)
    rows, health = asyncio.run(http_probe())
    rows.extend(generation_probe())
    report = {'scope': __doc__, 'passed': sum(r['passed'] for r in rows), 'total': len(rows),
              'http_health': health, 'rows': rows}
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'total': report['total'], 'rows': rows}))
    if report['passed'] != report['total']:
        sys.exit(1)
