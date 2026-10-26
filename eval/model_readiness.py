"""Bounded observation of an existing model service; never cancel or restart it."""
import asyncio
import json
import time

import aiohttp


class ModelNotReady(RuntimeError):
    def __init__(self,case_id,state):
        self.state={'case_id':case_id,**state}
        super().__init__('Model not idle before '+str(case_id)+': '+str(state['reason']))


async def wait_model_idle(base,timeout=3.0):
    started=time.monotonic();until=started+timeout;observations=0
    state={'ready':False,'reason':'observation_timeout','active_request':None}
    async with aiohttp.ClientSession(trust_env=False) as session:
        while time.monotonic()<until:
            observations+=1
            try:
                async with session.get(base.rstrip('/')+'/health',allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=min(1,until-time.monotonic()))) as response:
                    if response.status!=200:
                        state={'ready':False,'reason':'health_http_'+str(response.status),'active_request':None}
                    else:
                        body=bytearray()
                        async for chunk in response.content.iter_chunked(8192):
                            body.extend(chunk)
                            if len(body)>100_000:raise ValueError('oversized_health')
                        health=json.loads(body)
                        if not isinstance(health,dict) or type(health.get('ready')) is not bool or 'active_request' not in health:
                            raise ValueError('invalid_health')
                        idle=health['ready'] and health['active_request'] is None
                        state={'ready':idle,'reason':'idle' if idle else 'active_request' if health['active_request'] is not None else 'not_ready',
                            'active_request':health['active_request'],'pid':health.get('pid'),'busy_rejections':health.get('busy_rejections')}
                        if idle:break
            except (aiohttp.ClientError,OSError,TimeoutError,ValueError) as exc:
                state={'ready':False,'reason':type(exc).__name__,'active_request':None}
            remaining=until-time.monotonic()
            if remaining>0:await asyncio.sleep(min(.1,remaining))
    return {**state,'observations':observations,'wait_seconds':time.monotonic()-started}
