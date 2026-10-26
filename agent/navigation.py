"""Use the resident selector to choose an existing link, never to invent a destination."""
from dataclasses import replace
from .types import Candidate,Page,Passage
from .selector import select
from .urls import canonical_url
import aiohttp
import re
from .model_client import request_model


async def expand_navigation(plan,settings,deadline):
    """Unverified model hints influence discovery only, never answer verification."""
    try:
        reply,state=await request_model(settings,deadline,'/expand',{'question':plan.question},cap=3.8,limit=4096)
        if reply is None:return [],state
        terms=reply.get('terms',[])
        if not isinstance(terms,list):return [],'invalid_schema'
        return [t.strip().casefold() for t in terms[:8] if isinstance(t,str) and 1<len(t)<=60
            and not re.search(r'https?://|[\r\n]',t) and not re.search(r'\d',t)],'expanded'
    except (aiohttp.ClientError,OSError,TimeoutError,ValueError,TypeError,AttributeError) as exc:return [],type(exc).__name__


async def suggest_link(plan, links, settings, deadline):
    if not settings.model_url or deadline.remaining<2:return '', 'disabled'
    selected=[];seen=set()
    for score,url,anchor in links:
        if url in seen or len(url)>350:continue
        seen.add(url);selected.append((url,anchor))
        if len(selected)>=56:break
    if not selected:return '', 'no_links'
    candidates=[Candidate(u,u,u,a,kind='url') for u,a in selected[:14]]
    passages=[];text=''
    for url,anchor in selected:
        line=f'{anchor[:150]} -> {url}\n'
        if len(text)+len(line)>1050:
            passages.append((Page(''),Passage(text,section='Available page links'),0));text=''
            if len(passages)==8:break
        text+=line
    if text and len(passages)<8:passages.append((Page(''),Passage(text,section='Available page links'),0))
    request=replace(plan,kind='url',choices=[],operation='single',required_fields=[],question='Choose the best available page link to OPEN NEXT to find evidence for this question. '
        'Return the link candidate or copy its exact URL; do not answer the original question. Original question: '+plan.question)
    chosen,state=await select(request,candidates,passages,settings,deadline)
    target=canonical_url(chosen.answer) if chosen else ''
    allowed={canonical_url(u) for u,a in selected}
    return (target,state) if target in allowed else ('',state)
