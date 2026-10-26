"""Deadline and cancellation contract shared by all resident-model calls."""
import asyncio
import hashlib
import json
import time
import uuid

import aiohttp


async def _cancel(session, base, request_id):
    # The cancellation is independent of the exhausted query budget and bounded.
    try:
        async with session.post(base + '/cancel', json={'request_id': request_id},
                                timeout=aiohttp.ClientTimeout(total=.2)) as response:
            await response.content.read(1024)
    except (aiohttp.ClientError, OSError, TimeoutError):
        pass


async def request_model(settings, deadline, path, data, *, cap=None, limit=100_000):
    timeout = deadline.timeout(settings.model_timeout if cap is None else min(cap, settings.model_timeout))
    if timeout < .15:
        return None, 'budget_exhausted'
    end = time.monotonic() + timeout
    base = settings.model_url.rstrip('/')
    try:
        # Freeze the actual wire bytes once. Source whitespace and JSON key
        # order can affect the resident prompt; neither may be normalized away.
        body = json.dumps(data).encode('utf-8')
    except (ValueError, TypeError):
        return None, 'invalid_json'
    timeout = end - time.monotonic()
    if timeout < .15:
        return None, 'budget_exhausted'
    memo = deadline._model_capacity_rejections
    capacity_key = (base, path, hashlib.sha256(body).digest()) if path in {'/select', '/verify'} else None
    if capacity_key is not None and capacity_key in memo:
        deadline.model_capacity_skips += 1
        return None, 'model_context_limit'
    request_id = uuid.uuid4().hex
    headers = {'X-Aperture-Request-ID': request_id,
               'X-Aperture-Expires': str(time.time() + timeout - .1),
               'Content-Type': 'application/json'}
    # Admission refusals have not run inference. Retry only that exact protocol
    # response, with the same identity/expiry and one cumulative call budget.
    async with aiohttp.ClientSession(trust_env=False) as session:
        try:
            for attempt in range(3):
                async with session.post(base + path, data=body, headers=headers,
                                        timeout=aiohttp.ClientTimeout(total=max(.001, end - time.monotonic()))) as response:
                    if response.status == 503:
                        # Error responses are untrusted too: bound their body
                        # and reading time. Generic 503s never trigger retries.
                        raw = bytearray()
                        async for chunk in response.content.iter_chunked(2049):
                            raw.extend(chunk)
                            if len(raw) > 2048:
                                return None, 'http_503'
                        try:
                            busy = json.loads(raw) == {'error': 'busy'}
                        except (ValueError, TypeError):
                            busy = False
                        if not busy:
                            return None, 'http_503'
                    elif response.status != 200:
                        return None, 'http_' + str(response.status)
                    else:
                        raw = bytearray()
                        async for chunk in response.content.iter_chunked(min(8192, limit + 1)):
                            raw.extend(chunk)
                            if len(raw) > limit:
                                return None, 'oversized_reply'
                        reply = json.loads(raw)
                        if not isinstance(reply, dict):
                            return None, 'invalid_schema'
                        if reply == {'error': 'context_limit'} and capacity_key is not None and len(memo) < 16:
                            memo.add(capacity_key)
                        if reply.get('error'):
                            return None, 'model_' + str(reply['error'])[:60]
                        return reply, 'ok'
                pause = .1 * (attempt + 1)
                if attempt == 2 or end - time.monotonic() < pause + .15:
                    return None, 'model_busy'
                await asyncio.sleep(pause)
        except asyncio.CancelledError:
            await _cancel(session, base, request_id)
            raise
        except (aiohttp.ClientError, OSError, TimeoutError) as exc:
            await _cancel(session, base, request_id)
            return None, type(exc).__name__
        except (ValueError, TypeError):
            return None, 'invalid_json'
