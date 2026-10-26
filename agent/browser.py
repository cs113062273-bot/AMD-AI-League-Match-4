"""Selective JS rendering. Page HTTP is fulfilled by the guarded, bounded Fetcher.

A rejecting proxy catches unrouted browser traffic. WebSockets, service workers,
POSTs, media and downloads are disabled. No user browser/profile is used.
"""
import asyncio
import os
import time
from urllib.parse import urlsplit
from .network import Response
from .parser import parse_response
from .urls import canonical_url


async def render(url, settings, deadline, fetcher):
    if not settings.browser or deadline.remaining < 3:
        return None, {'state':'disabled_or_budget'}
    try:
        from playwright.async_api import async_playwright, Error
    except ImportError:
        return None, {'state':'dependency_missing'}
    report={'state':'started','requests':0,'blocked':0,'blocked_analytics':0,'bytes':0}
    started=time.monotonic()
    async def reject(reader, writer):
        writer.close()
        await writer.wait_closed()
    proxy=await asyncio.start_server(reject,'127.0.0.1',0)
    port=proxy.sockets[0].getsockname()[1]
    source=url
    try:
        async with asyncio.timeout(deadline.timeout(6)):
            # Resolve a main-document redirect through the guarded fetcher
            # before navigation. Chromium may follow a synthetic302 via its
            # rejecting proxy without invoking the route again.
            initial=await fetcher.fetch(url,timeout=min(3,deadline.remaining))
            if initial.error or initial.truncated:
                report['state']=initial.error or 'truncated_document'
                return None,report
            target=canonical_url(initial.url)
            async with async_playwright() as pw:
                options={'headless':True,'proxy':{'server':f'http://127.0.0.1:{port}','bypass':'<-loopback>'},
                    'args':['--disable-gpu','--disable-quic','--disable-background-networking',
                        '--disable-extensions','--force-webrtc-ip-handling-policy=disable_non_proxied_udp']}
                executable=os.getenv('APERTURE_BROWSER_EXECUTABLE')
                if executable:options['executable_path']=executable
                browser=await pw.chromium.launch(**options)
                report['browser_version']=browser.version
                context=None
                try:
                    context=await browser.new_context(service_workers='block',accept_downloads=False)
                    async def block_socket(ws):await ws.close()
                    await context.route_web_socket('**/*',block_socket)
                    async def route(request_route):
                        nonlocal source
                        request=request_route.request
                        if request.resource_type=='document' and request.frame!=page.main_frame:
                            report['blocked']+=1
                            return await request_route.abort()
                        host=(urlsplit(request.url).hostname or '').lower()
                        analytics=('google-analytics.com','googletagmanager.com','doubleclick.net')
                        if request.resource_type in {'script','xhr','fetch'} and any(host==domain or host.endswith('.'+domain) for domain in analytics):
                            report['blocked']+=1
                            report['blocked_analytics']+=1
                            return await request_route.abort()
                        if request.method!='GET' or request.resource_type not in {'document','script','xhr','fetch'} or report['requests']>=20 or report['bytes']>=6_000_000:
                            report['blocked']+=1
                            return await request_route.abort()
                        report['requests']+=1
                        response=initial if request.resource_type=='document' and canonical_url(request.url)==target else await fetcher.fetch(request.url,timeout=min(3,deadline.remaining))
                        report['bytes']+=len(response.body)
                        if response.error or response.truncated:
                            report['blocked']+=1
                            return await request_route.abort()
                        if response.url!=canonical_url(request.url):
                            return await request_route.fulfill(status=302,headers={'location':response.url},body=b'')
                        if request.resource_type=='document':source=response.url
                        await request_route.fulfill(status=response.status or 200,
                            headers={**response.headers,'content-type':response.content_type or 'text/plain'},body=response.body)
                    await context.route('**/*',route)
                    page=await context.new_page()
                    await page.goto(target,wait_until='domcontentloaded',timeout=int(deadline.timeout(4)*1000))
                    try:await page.wait_for_load_state('networkidle',timeout=int(deadline.timeout(1.2)*1000))
                    except Error:pass
                    content=(await page.content()).encode('utf-8')
                    if len(content)>settings.max_bytes:
                        report['state']='body_limit';return None,report
                    parsed=parse_response(Response(canonical_url(source),content,'text/html'))
                    report['state']='rendered' if not parsed.error else parsed.error
                    return parsed,report
                finally:
                    try:
                        if context:
                            # Fence callbacks before closing their target.
                            try:await context.unroute_all(behavior='ignoreErrors')
                            except Error:pass  # An already-closed context has no live routes.
                    finally:
                        await browser.close()
    except (TimeoutError,OSError,Error) as exc:
        report['state']=type(exc).__name__
        report['error']=str(exc)[:200]
        return None,report
    finally:
        report['seconds']=round(time.monotonic()-started,4)
        proxy.close();await proxy.wait_closed()
