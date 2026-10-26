"""Dated GitHub license premises from two fetched, SHA-bound REST resources.

Commit times are declared Git timestamps, not a reconstructed publication log.
The adapter uses history reachable from the API's current default branch.
"""
import base64
import binascii
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit, unquote, urlencode, quote

from .types import Page, Passage
from .normalize import clean, literal_span

HOSTS={'github.com','api.github.com','raw.githubusercontent.com'}
SHA=re.compile(r'[0-9a-f]{40}')


def _host(parsed):
    host=parsed.hostname
    return 'github.com' if host=='www.github.com' else host


def request(plan):
    """Return (historical GitHub request, safely unambiguous repository)."""
    if plan.kind!='license' or not (plan.as_of or plan.year):return False,''
    try:p=urlsplit(plan.url)
    except ValueError:return False,''
    if plan.url and _host(p) not in HOSTS:return False,''
    names=set(re.findall(r'(?<![\w./-])([\w.-]+/[\w.-]+)(?![\w./-])',plan.question))
    names={n.removesuffix('.git').casefold() for n in names}
    if plan.url:
        parts=[unquote(v) for v in p.path.strip('/').split('/')]
        if p.hostname=='api.github.com' and parts[:1]==['repos']:parts=parts[1:]
        repo='/'.join(parts[:2]).removesuffix('.git').casefold()
        # Tags/branches, contents paths and versioned questions need an explicit
        # reference policy. Do not silently substitute default-branch history.
        if (len(parts)!=2 or p.query or p.fragment or p.scheme!='https'
                or names and names!={repo}):return True,''
    elif re.search(r'\bgithub\b',plan.question,re.I):
        repo=next(iter(names)) if len(names)==1 else ''
    else:return False,''
    if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*',repo)
            or plan.versions or re.search(r'\b(?:tag|branch|commit|revision)\s+[`"\w]',plan.question,re.I)):
        return True,''
    return True,repo


def stamp(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})',value):return None
    try:return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)
    except ValueError:return None


def cutoff(plan):
    try:
        day=date.fromisoformat(plan.as_of or plan.year+'-12-31')
        if not 1970<=day.year<=2099:return None
        end=datetime.combine(day+timedelta(days=1),datetime.min.time(),timezone.utc)
        return end if end.year<=2099 else None
    except (ValueError,OverflowError):return None


def _json(response,expected):
    if response.error or response.truncated or response.status!=200 or response.url!=expected:return None
    try:return json.loads(response.text)
    except (ValueError,RecursionError):return None


def _repository_url(actual,expected):
    """GitHub owner/repo components are case-insensitive; refs/files are not."""
    if not isinstance(actual,str):return False
    try:
        parsed=urlsplit(actual);target=urlsplit(expected)
        parts=parsed.path.split('/')
        start=2 if target.hostname=='api.github.com' else 1
        if len(parts)<start+2:return False
        parts[start:start+2]=[p.casefold() for p in parts[start:start+2]]
        return parsed._replace(path='/'.join(parts))==target
    except ValueError:return False


async def resolve(plan,fetcher):
    active,repo=request(plan);end=cutoff(plan)
    if not active or not repo or not end or fetcher.deadline.remaining<=4:return []
    root='https://api.github.com/repos/'+repo
    endpoint=root+'/commits?'+urlencode({'until':end.strftime('%Y-%m-%dT%H:%M:%SZ'),'per_page':1})
    response=await fetcher.fetch(endpoint,timeout=min(4,fetcher.deadline.remaining-2))
    data=_json(response,endpoint)
    if not isinstance(data,list) or len(data)!=1 or not isinstance(data[0],dict):return []
    commit=data[0];ref=commit.get('sha','')
    detail=commit.get('commit');committer=detail.get('committer') if isinstance(detail,dict) else None
    when=committer.get('date') if isinstance(committer,dict) else None
    observed=stamp(when)
    if (not isinstance(ref,str) or not SHA.fullmatch(ref) or not _repository_url(commit.get('url'),root+'/commits/'+ref)
            or not observed or observed>=end or plan.year and not plan.as_of and str(observed.year)!=plan.year):return []
    if str(next((v for k,v in response.headers.items() if k.lower()=='x-ratelimit-remaining'),''))=='0':return []
    if fetcher.deadline.remaining<=3:return []
    license_url=root+'/license?ref='+ref
    response2=await fetcher.fetch(license_url,timeout=min(4,fetcher.deadline.remaining-1.5))
    item=_json(response2,license_url)
    if not isinstance(item,dict) or item.get('type')!='file' or item.get('encoding')!='base64':return []
    path=item.get('path');content=item.get('content');size=item.get('size')
    if (not isinstance(path,str) or not path or any(v in {'','..','.'} for v in path.split('/'))
            or not isinstance(content,str) or type(size) is not int or not 0<size<=500000):return []
    encoded_path=quote(path,safe='/')
    if (not _repository_url(item.get('url'),root+'/contents/'+encoded_path+'?ref='+ref)
            or not _repository_url(item.get('html_url'),'https://github.com/'+repo+'/blob/'+ref+'/'+encoded_path)):return []
    try:
        raw=base64.b64decode(re.sub(r'\s','',content),validate=True)
        text=raw.decode('utf-8')
    except (ValueError,binascii.Error,UnicodeError):return []
    blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    if len(raw)!=size or item.get('sha')!=blob:return []
    identity={'github_snapshot':True,'repository':repo,'commit':ref,'commit_date':when,
        'commit_source':endpoint,'license_source':license_url,'blob':blob}
    dated=Page(endpoint,title=repo,identity=dict(identity))
    dated.passages=[Passage('commit.sha: '+ref+' | commit.committer.date: '+when,
        'commit date',when,repo,'field','[0].commit.committer.date',{'github_role':'date'})]
    licensed=Page(license_url,title=repo,identity=dict(identity))
    classification=item.get('license');spdx=classification.get('spdx_id') if isinstance(classification,dict) else None
    if isinstance(spdx,str) and spdx not in {'NOASSERTION','NONE',''} and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+-]{0,100}',spdx):
        licensed.passages.append(Passage('license: '+spdx,'license',spdx,repo,'field',
            'license.spdx_id',{'github_role':'license'}))
    # Exact decoded paragraphs preserve file provenance, without claiming that
    # the download_url was fetched or copying dates into the license response.
    paragraphs=re.split(r'\n\s*\n',text,maxsplit=256)
    if len(paragraphs)>256:return []
    for i,paragraph in enumerate(paragraphs):
        value=clean(paragraph)
        if value and len(value)<=8000:
            licensed.passages.append(Passage(value,section=repo,locator=f'content/base64/paragraph/{i}',
                qualifiers={'github_role':'license_text'}))
    return [dated,licensed] if licensed.passages else []


def supported(plan,page,passage):
    if plan.kind!='license' or not (plan.as_of or plan.year):return True
    try:host=_host(urlsplit(page.url))
    except ValueError:return False
    if host not in HOSTS:return True
    active,repo=request(plan);facts=page.identity
    if not active or not repo or not facts.get('github_snapshot') or facts.get('repository')!=repo:return False
    ref=facts.get('commit','');when=stamp(facts.get('commit_date'));end=cutoff(plan)
    if not isinstance(ref,str) or not SHA.fullmatch(ref) or not when or not end or when>=end:return False
    if plan.year and not plan.as_of and str(when.year)!=plan.year:return False
    role=passage.qualifiers.get('github_role')
    if role=='date':return page.url==facts.get('commit_source') and passage.value==facts.get('commit_date') and literal_span(ref,passage.text)
    return role in {'license','license_text'} and page.url==facts.get('license_source')


def pair(plan,pages):
    dates=[(p,s) for p in pages for s in p.passages if s.qualifiers.get('github_role')=='date' and supported(plan,p,s)]
    licenses=[(p,s) for p in pages for s in p.passages if s.qualifiers.get('github_role') in {'license','license_text'} and supported(plan,p,s)]
    pairs=[(d,l) for d in dates for l in licenses if d[0].identity==l[0].identity]
    return pairs


def premises(plan,pages,chosen=None):
    for (dp,d),(lp,l) in pair(plan,pages):
        if l.qualifiers.get('github_role')=='license':return (dp,d,d.value),(lp,l,l.value)
        if (chosen and chosen.source==lp.url and chosen.evidence==l.text
                and chosen.signals.get('locator')==l.locator and literal_span(chosen.raw,l.text)):
            return (dp,d,d.value),(lp,l,chosen.raw)
    return None
