"""Release-local crates.io metadata, without backfilling today's crate fields."""
import json
import re
from urllib.parse import urlsplit, unquote, quote

from .types import Page, Passage
from .normalize import clean, literal_span
from .registry_history import metadata_history, choose_release, eligible_dates, published_day, _semver


def location(url):
    try:
        p=urlsplit(url)
        match=re.fullmatch(r'/(?:api/v1/)?crates/([A-Za-z0-9_-]+)(?:/([^/]+))?/?',p.path)
        if p.scheme!='https' or p.hostname not in {'crates.io','www.crates.io'} or p.query or p.fragment or not match:return None
        version=unquote(match[2] or '')
        return match[1],version
    except ValueError:return None


def requested(plan,identifier):
    """Resolve subject/ref constraints before making an API request."""
    names={m.casefold() for m in re.findall(r'\b(?:crate|package)\s+(?:(?:named|called)\s+)?[`"\x27]?([A-Za-z0-9_-]+)',plan.question,re.I)}
    if names and names!={identifier.casefold()}:return None
    labels=set(re.findall(r'\b(?:version|release|v)\s*([0-9][A-Za-z0-9.+-]*)',plan.question,re.I))
    if plan.url:
        found=location(plan.url)
        if not found or found[0].casefold()!=identifier.casefold():return None
        if found[1]:labels.add(found[1])
    if len(labels)>1 or any(not _semver(label) for label in labels):return None
    if plan.versions and not labels:return None
    return next(iter(labels)) if labels else ''


def _date(record):
    value=record.get('created_at')
    return published_day(value) if isinstance(value,str) and 'T' in value and value.endswith(('Z','+00:00')) else ''


def _record(record,identifier):
    return (isinstance(record,dict) and isinstance(record.get('crate'),str)
        and record['crate'].casefold()==identifier.casefold() and type(record.get('id')) is int
        and record['id']>0 and isinstance(record.get('num'),str) and _semver(record['num'])
        and type(record.get('yanked')) is bool)


async def resolve(plan,fetcher,identifier):
    release=requested(plan,identifier)
    if release is None:return []
    root='https://crates.io/api/v1/crates/'+quote(identifier,safe='')
    endpoint=root+('/'+quote(release,safe='') if release else '')
    response=await fetcher.fetch(endpoint,max_bytes=8_000_000,timeout=8)
    if response.error or response.status!=200 or response.truncated or response.url!=endpoint:return []
    try:data=json.loads(response.text)
    except (ValueError,RecursionError):return []
    if not isinstance(data,dict):return []
    if release:
        chosen=data.get('version')
        if not _record(chosen,identifier) or chosen['num']!=release:return []
        days=eligible_dates(plan,[_date(chosen)])
        if not days:return []
        day=days[0];prefix='version'
    else:
        crate=data.get('crate');versions=data.get('versions')
        if (not isinstance(crate,dict) or not isinstance(crate.get('name'),str)
                or crate['name'].casefold()!=identifier.casefold() or not isinstance(crate.get('id'),str)
                or crate['id'].casefold()!=identifier.casefold() or not isinstance(versions,list)
                or not versions or len(versions)>10000 or type(crate.get('num_versions')) is not int
                or crate['num_versions']!=len(versions) or not all(_record(v,identifier) for v in versions)):return []
        ids=[v['id'] for v in versions];labels=[v['num'] for v in versions];declared=crate.get('versions')
        if (len(set(ids))!=len(ids) or len(set(labels))!=len(labels) or not isinstance(declared,list)
                or any(type(value) is not int for value in declared) or len(declared)!=len(ids) or set(declared)!=set(ids)):return []
        records={v['num']:[_date(v)] for v in versions if not v['yanked']}
        selection=choose_release(plan,records,'crates')
        if not selection:return []
        release,day=selection;index=labels.index(release);chosen=versions[index];prefix=f'versions[{index}]'
    scope={'registry_release':{'version':release,'date':day,'name':identifier}}
    context=f'crate {identifier} version {release} published {day}'
    page=Page(response.url,title='crates.io '+identifier,identity={'registry':'crates','name':identifier,'historical_release':release})
    for field in ['license','description','homepage','documentation','repository','rust_version','edition']:
        value=chosen.get(field)
        if not isinstance(value,str) or not clean(value) or len(value)>8000:continue
        value=clean(value)
        label='homepage URL' if field=='homepage' else field.replace('_',' ')
        page.passages.append(Passage(label+': '+value+' | '+context,label,value,context,'field',
            prefix+'.'+field,dict(scope)))
    return [page]


def supported(plan,page,passage):
    if not metadata_history(plan):return True
    facts=page.identity;scope=passage.qualifiers.get('registry_release')
    if facts.get('registry')!='crates' or not isinstance(scope,dict):return False
    name=facts.get('name');release=scope.get('version');day=scope.get('date')
    if not isinstance(name,str) or not isinstance(release,str) or not _semver(release):return False
    explicit=requested(plan,name)
    if explicit is None or explicit and explicit!=release:return False
    if (facts.get('historical_release')!=release or scope.get('name')!=name
            or not isinstance(day,str) or not eligible_dates(plan,[day])):return False
    target=location(page.url)
    return (bool(target) and urlsplit(page.url).hostname=='crates.io'
        and urlsplit(page.url).path.startswith('/api/v1/crates/') and target[0].casefold()==name.casefold()
        and (not target[1] or target[1]==release)
        and literal_span(release,passage.text,'version') and literal_span(day,passage.text,'date'))
