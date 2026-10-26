"""Release-scoped registry metadata, selected from dated records rather than today's tags."""
import re
from datetime import datetime
from urllib.parse import urlsplit
from packaging.version import Version,InvalidVersion

from .normalize import iso_date,literal_span


def metadata_history(plan):
    return bool((plan.as_of or plan.year) and plan.kind not in {'version','date','year'})


def file_dates(files):
    if not isinstance(files,list):return []
    return [published_day(item.get('upload_time_iso_8601') or item.get('upload_time'))
        for item in files if isinstance(item,dict) and not item.get('yanked')]


def published_day(value):
    if not isinstance(value,str):return ''
    if iso_date(value)==value:return value
    # Registry publication timestamps are UTC. Validate the complete value,
    # not just a calendar-looking prefix of malformed or offset data.
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)?',value):return ''
    try:datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:return ''
    return value[:10]


def eligible_dates(plan,dates):
    return [day for day in dates if iso_date(day)==day and day
        and (not plan.as_of or day<=plan.as_of) and (not plan.year or day.startswith(plan.year+'-'))]


def _semver(label):
    match=re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)'
        r'(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?',label)
    if not match:return None
    pre=match[4].split('.') if match[4] else []
    if any(part.isdigit() and len(part)>1 and part[0]=='0' for part in pre):return None
    # Build metadata does not participate in SemVer precedence.
    return ((tuple(int(match[i]) for i in (1,2,3)),not pre,
        tuple((0,int(part)) if part.isdigit() else (1,part) for part in pre)),bool(pre))


def choose_release(plan,records,registry='pypi'):
    requested=list(dict.fromkeys(plan.versions))
    if len(requested)>1:return None
    if requested:
        if registry in {'npm','crates'} and not _semver(requested[0]):return None
        days=eligible_dates(plan,records.get(requested[0],[]))
        return (requested[0],min(days)) if days else None
    channel=r'(?:alpha|beta|preview|pre[- ]?release|release candidate|rc)'
    request=re.sub(r'\b(?:package|project|module|crate)\s+(?:(?:named|called)\s+)?[`"\x27]?'
        r'@?[\w.-]+(?:/[\w.-]+)?[`"\x27]?',' ',plan.question,flags=re.I)
    preview=bool(re.search(r'\b'+channel+r'\s+(?:release|version)\b|'
        r'\b(?:latest|newest)\s+'+channel+r'\b|\b(?:release|version)\s+'+channel+r'\b',request,re.I))
    available=[];unknown=[]
    for label,dates in records.items():
        if registry in {'npm','crates'}:
            parsed=_semver(label)
            if not parsed:continue
            version,is_preview=parsed
        else:
            try:version=Version(label)
            except (InvalidVersion,TypeError):continue
            is_preview=version.is_prerelease or version.is_devrelease
        if not preview and is_preview:continue
        days=eligible_dates(plan,dates)
        if days:available.append((version,label,min(days)))
        elif not dates or any(not day or iso_date(day)!=day for day in dates):unknown.append(version)
    if not available:return None
    maximum=max(item[0] for item in available)
    best=[item for item in available if item[0]==maximum]
    if len(best)!=1 or any(version>=maximum for version in unknown):return None
    return best[0][1:]


def source_registry(url):
    try:parsed=urlsplit(url)
    except ValueError:return ''
    host=(parsed.hostname or '').removeprefix('www.')
    if host=='pypi.org' and re.match(r'^/(?:pypi|project)/',parsed.path):return 'pypi'
    if host=='registry.npmjs.org' or host=='npmjs.com' and parsed.path.startswith('/package/'):return 'npm'
    if host=='crates.io' and re.match(r'^/(?:api/v1/)?crates/',parsed.path):return 'crates'
    return ''


def metadata_supported(plan,page,passage):
    if not metadata_history(plan):return True
    family=page.identity.get('registry') or source_registry(page.url)
    if family=='crates':
        from .crates_history import supported
        return source_registry(page.url)==family and supported(plan,page,passage)
    if family not in {'pypi','npm'}:return True
    if source_registry(page.url)!=family:return False
    scope=passage.qualifiers.get('registry_release')
    if not isinstance(scope,dict):return False
    version,day=scope.get('version'),scope.get('date')
    if not isinstance(version,str) or not isinstance(day,str) or not eligible_dates(plan,[day]):return False
    if plan.versions and version not in plan.versions:return False
    return literal_span(version,passage.text,'version') and literal_span(day,passage.text,'date')
