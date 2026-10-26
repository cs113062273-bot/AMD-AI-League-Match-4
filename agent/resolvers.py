"""Structured primary-source adapters. No answer is returned without an actual fetch."""
from __future__ import annotations

import re
from urllib.parse import quote, urlsplit, unquote
from packaging.version import Version, InvalidVersion

from .types import Page, Passage
from .parser import parse_response,segments,_json,_scalar
from .normalize import clean,iso_date
from .registry_history import metadata_history,file_dates,eligible_dates,choose_release,published_day


def _data(resp):
    if resp.error:
        return None
    try:
        return _json(resp.text)
    except (ValueError, RecursionError):
        return None


def _mapping(value):
    return value if isinstance(value,dict) else {}


def _records(value):
    return [item for item in value if isinstance(item,dict)] if isinstance(value,list) else []


def _field(page, label, value, context="",qualifiers=None):
    if len(page.passages) >= 3500:
        page.truncated=True
        return
    if value is None or isinstance(value, (dict, list)) or not clean(value):
        return
    value = clean(_scalar(value))
    page.passages.append(Passage(f"{label}: {value}" + (f" | {context}" if context else ""),
        label, value, context, "field", "adapter/" + label,dict(qualifiers or {})))


def _package_name(question, registry):
    token = r'(@[\w.-]+/[\w.-]+|[\w.-]+)' if registry == 'npm' else r'([\w.-]+)'
    patterns = [
        r'\b(?:package|project|module)\s+(?:(?:named|called)\s+)?[`\"\x27]?' + token,
        r'\b(?:of|for)\s+(?:the\s+)?[`\"\x27]?' + token + r'[`\"\x27]?\s+(?:package|project|module)\b',
        r'\b(?:of|for)\s+[`\"\x27]?' + token + r'[`\"\x27]?\s+(?:on|from)\s+' + registry + r'\b',
    ]
    excluded = {'pypi', 'npm', 'on', 'from', 'in', 'at', 'version', 'named', 'called'}
    names = {m[1].rstrip('.') for pattern in patterns for m in re.finditer(pattern, question, re.I)
             if m[1].casefold() not in excluded}
    return next(iter(names)) if len(names) == 1 else ''


def _package_key(name):
    return re.sub(r'[-_.]+', '-', name).casefold()


def _pypi_source(url,identifier,release=''):
    try:
        parsed=urlsplit(url);parts=[unquote(p) for p in parsed.path.strip('/').split('/')]
        return (parsed.scheme=='https' and parsed.hostname=='pypi.org'
            and len(parts)==(4 if release else 3) and parts[0]=='pypi'
            and _package_key(parts[1])==_package_key(identifier) and parts[-1]=='json'
            and (not release or parts[2]==release))
    except (ValueError,IndexError):return False


async def _pypi_metadata(plan,fetcher,resp,data,identifier,release):
    if resp.truncated or resp.error or not _pypi_source(resp.url,identifier,release):return None
    if len(set(plan.versions))>1:return None
    if release:
        days=eligible_dates(plan,file_dates(data.get('urls')))
        return (resp,data,release,min(days)) if days else None
    info=data['info'];current=info.get('version')
    if not isinstance(current,str):return None
    try:Version(current)
    except InvalidVersion:return None
    records={version:file_dates(files) for version,files in _mapping(data.get('releases')).items()}
    if current not in records:records[current]=file_dates(data.get('urls'))
    chosen=choose_release(plan,records)
    if not chosen:return None
    version,day=chosen
    if current==version:return resp,data,version,day
    # Preserve time for the reader instead of spending a short budget on a
    # second metadata request. The unbound current fields remain ineligible.
    if fetcher.deadline.remaining<=4:return None
    endpoint=f"https://pypi.org/pypi/{quote(identifier,safe='')}/{quote(version,safe='')}/json"
    answer=await fetcher.fetch(endpoint,max_bytes=8_000_000,timeout=min(4,fetcher.deadline.remaining-2))
    snapshot=_data(answer)
    if (answer.truncated or not _pypi_source(answer.url,identifier,version) or not isinstance(snapshot,dict)
            or not isinstance(snapshot.get('info'),dict)):return None
    record=snapshot['info']
    if (not isinstance(record.get('name'),str) or _package_key(record['name'])!=_package_key(identifier)
            or record.get('version')!=version):return None
    days=eligible_dates(plan,file_dates(snapshot.get('urls')))
    return (answer,snapshot,version,min(days)) if days else None


def route(plan):
    q, url = plan.question, plan.url
    try:parsed = urlsplit(url)
    except ValueError:return '', ''
    host = (parsed.hostname or "").lower().removeprefix("www.")
    pypi = re.match(r"/(?:project|pypi)/([^/]+)", parsed.path) if host == "pypi.org" else None
    npm = re.match(r"/package/((?:@[^/]+/)?[^/]+)", parsed.path) if host == "npmjs.com" else None
    if host == 'registry.npmjs.org':
        name = unquote(parsed.path).strip('/')
        match = re.match(r'(@[^/]+/[^/]+|[^/]+)', name)
        if match:return 'npm', match[1]
    if pypi:
        requested = _package_name(q, 'pypi')
        if requested and _package_key(requested) != _package_key(unquote(pypi[1])):
            return '', ''
        return "pypi", unquote(pypi[1])
    if not url and re.search(r"\bpypi\b", q, re.I):
        name = _package_name(q, 'pypi')
        if name:
            return 'pypi', name
    if npm:
        return "npm", unquote(npm[1].rstrip("/"))
    if not url and re.search(r"\bnpm\b", q, re.I):
        name = _package_name(q, 'npm')
        if name:
            return 'npm', name
    gh = re.match(r"/repos/([\w.-]+/[\w.-]+)", parsed.path) if host == 'api.github.com' else re.match(r"/([\w.-]+/[\w.-]+)", parsed.path) if host == 'github.com' else None
    if not url and not gh and re.search(r"github", q, re.I):
        gh = re.search(r"\b([\w.-]+/[\w.-]+)\b", q)
    if gh:
        return "github", gh[1].removesuffix(".git").rstrip("/")
    crate_path=r"/(?:api/v1/)?crates/([\w-]+)" if metadata_history(plan) else r"/crates/([\w-]+)"
    crate = re.search(crate_path, parsed.path) if host == "crates.io" else None
    if not crate and not url and re.search(r"crates\.io|rust crate", q, re.I):
        crate = re.search(r"(?:crate|package)\s+([\w-]+)", q, re.I)
    if crate:
        return "crates", crate[1]
    arxiv = re.search(r"(?:arxiv(?:\.org/(?:abs|pdf)/)?\s*(?:paper\s*)?)(\d{4}\.\d{4,5}(?:v\d+)?)", q + " " + url, re.I) if not url or host == "arxiv.org" else None
    if arxiv:
        return "arxiv", arxiv[1]
    pep = re.search(r"\bPEP\s*[- ]?\s*(\d{1,4})\b", q, re.I)
    if pep and (not url or host == "python.org" or host.endswith(".python.org")):
        return "pep", pep[1]
    rfc = re.search(r"\bRFC\s*[- ]?(\d{1,5})\b", q, re.I)
    if rfc and (not url or host in {"datatracker.ietf.org", "rfc-editor.org"}):
        return "rfc", rfc[1]
    return "", ""


async def resolve(plan, fetcher):
    family, identifier = route(plan)
    if not family:
        return [], False
    if family == "pypi":
        release = plan.versions[0] if plan.versions else ''
        if not release and not plan.latest:
            match = re.match(r'/(?:project|pypi)/[^/]+/([^/]+)',urlsplit(plan.url).path)
            if match and match[1] != 'json':release=unquote(match[1])
        suffix = f'/{quote(release,safe="")}' if release else ''
        endpoint = f"https://pypi.org/pypi/{quote(identifier, safe='')}{suffix}/json"
        resp = await fetcher.fetch(endpoint, max_bytes=8_000_000, timeout=8)
        data = _data(resp)
        if not isinstance(data, dict) or not isinstance(data.get("info"), dict):
            if resp.status == 404:
                return [], True
            # Large release histories can exceed request budgets. The official project page is
            # a separate, smaller source, not a fabricated API value or a search snippet.
            fallback = parse_response(await fetcher.fetch(f"https://pypi.org/project/{quote(identifier, safe='')}{suffix}/"))
            return ([fallback] if not fallback.error else []), False
        info = data["info"]
        name = info.get('name')
        if not isinstance(name, str) or _package_key(name) != _package_key(identifier):
            return [], True
        if release and str(info.get('version', '')) != release:
            return [], True
        historical=metadata_history(plan);allowed=True;scope={}
        context=f"package {identifier}"+(f" version {release}" if release else '')
        if historical:
            snapshot=await _pypi_metadata(plan,fetcher,resp,data,identifier,release)
            allowed=bool(snapshot)
            if snapshot:
                resp,data,release,day=snapshot;info=data['info']
                context=f"package {identifier} version {release} file uploaded {day}"
                scope={'registry_release':{'version':release,'date':day}}
        page = Page(resp.url, title=f"PyPI {identifier}", identity={'registry': 'pypi', 'name': name})
        page.links.append((f"https://pypi.org/project/{quote(identifier, safe='')}/", f"{identifier} project metadata author license"))
        mapping = {"author": "author", "author_email": "author email", "maintainer": "maintainer",
                   "license": "license", "license_expression": "license expression", "summary": "summary",
                   "requires_python": "requires python", "home_page": "homepage URL", "version": "version" if release else "current stable version"}
        for k, label in mapping.items():
            if not allowed:continue
            if k == "version" and (plan.as_of or plan.year):
                continue
            _field(page, label, info.get(k),context,scope)
        if allowed and plan.kind=='text' and re.search(r'\bwho\b|\bauthor\b|\bmaintainer\b',plan.question,re.I):
            from email.utils import parseaddr
            name,_=parseaddr(str(info.get('author_email') or ''))
            if name and name in str(info.get('author_email')):_field(page,'author name',name,context if scope else identifier,scope)
            for offset,span in segments(str(info.get('description') or '')[:120000]):
                page.passages.append(Passage(context+' | '+span if scope else span,section='Project description',
                    locator=f'info.description:{offset}',qualifiers=dict(scope)))
        releases=_mapping(data.get('releases'))
        for version, files in releases.items():
            if plan.kind != "version" or not (plan.as_of or plan.year):
                break
            try:
                v = Version(version)
            except InvalidVersion:
                continue
            if plan.stable and v.is_prerelease:
                continue
            dates = [str(f.get("upload_time_iso_8601") or '')[:10] for f in _records(files) if not f.get("yanked")]
            dates = [d for d in dates if iso_date(d)==d and (not plan.as_of or d <= plan.as_of) and (not plan.year or d.startswith(plan.year))]
            if dates:
                _field(page, "stable version", version, f"package {identifier} release date {min(dates)}")
        if plan.kind in {"date", "year"}:
            release_files = {release: data.get('urls',[])} if release else releases
            for version, files in release_files.items():
                if plan.versions:
                    try:
                        if not any(Version(version) == Version(v) for v in plan.versions):
                            continue
                    except InvalidVersion:
                        continue
                elif not plan.first and version != info.get("version"):
                    continue
                dates = sorted(str(f.get("upload_time_iso_8601") or f.get("upload_time") or "")[:10]
                               for f in _records(files) if not f.get("yanked"))
                dates=[date for date in dates if iso_date(date)==date]
                if dates:
                    _field(page, "release date", dates[0][:4] if plan.kind == "year" else dates[0],
                           f"package {identifier} version {version}")
        return [page], True
    if family == "npm":
        historical = bool(plan.as_of or plan.year)
        endpoint = f"https://registry.npmjs.org/{quote(identifier, safe='@')}" + ("" if historical else "/latest")
        resp = await fetcher.fetch(endpoint, max_bytes=8_000_000 if historical else None, timeout=8 if historical else None)
        data = _data(resp)
        if not isinstance(data, dict):
            return [], resp.status == 404
        if data.get('name') != identifier:
            return [], True
        version = _mapping(data.get("dist-tags")).get("latest", "") if historical else data.get("version", "")
        version=version if isinstance(version,str) else ''
        meta = _mapping(_mapping(data.get("versions")).get(version)) if historical else data
        field_history=metadata_history(plan);allowed=True;scope={};context=identifier
        if field_history:
            versions=_mapping(data.get('versions'));times=_mapping(data.get('time'))
            records={v:[published_day(times.get(v))] for v in (set(versions)|set(times))-{'created','modified'}}
            if version and version not in records:records[version]=[]
            chosen=choose_release(plan,records,'npm') if not resp.truncated else None
            allowed=bool(chosen)
            if chosen:
                version,day=chosen;meta=_mapping(versions.get(version))
                allowed=(meta.get('name')==identifier and meta.get('version')==version
                    and urlsplit(resp.url).scheme=='https' and urlsplit(resp.url).hostname=='registry.npmjs.org'
                    and unquote(urlsplit(resp.url).path).strip('/')==identifier)
                if allowed:
                    context=f"{identifier} version {version} published {day}"
                    scope={'registry_release':{'version':version,'date':day}}
        page = Page(resp.url, title=f"npm {identifier}", identity={'registry': 'npm', 'name': identifier})
        if not plan.as_of and not plan.year:
            _field(page, "current stable version", version, identifier)
        for k in ["license", "description", "homepage"]:
            if allowed:_field(page,k,meta.get(k) if field_history else meta.get(k) or data.get(k),context,scope)
        author = meta.get("author") if field_history else meta.get("author") or data.get("author")
        if allowed:_field(page,"author",author.get("name") if isinstance(author,dict) else author,context,scope)
        if plan.as_of or plan.year:
            for v, date in _mapping(data.get("time")).items():
                if v in {"created", "modified"} or not isinstance(date, str):
                    continue
                if iso_date(date[:10])!=date[:10]:continue
                if (not plan.as_of or date[:10] <= plan.as_of) and (not plan.year or date.startswith(plan.year)):
                    _field(page, "stable version", v, f"{identifier} release date {date[:10]}")
        return [page], True
    if family == "github":
        from .github_history import request as historical_request, resolve as historical_resolve
        if historical_request(plan)[0]:return await historical_resolve(plan,fetcher),False
        endpoint = f"https://api.github.com/repos/{identifier}"
        if plan.kind in {"version", "date"} and re.search(r"release|version", plan.question, re.I):
            resp = await fetcher.fetch(endpoint + "/releases?per_page=30")
            data = _data(resp)
            if isinstance(data, list):
                page = Page(resp.url, title=identifier)
                for release in data:
                    if not isinstance(release, dict) or release.get("draft") or (plan.stable and release.get("prerelease")):
                        continue
                    if plan.versions:
                        tag=str(release.get('tag_name','')).lstrip('vV')
                        if not any(tag==v or tag.startswith(v+'.') for v in plan.versions):
                            continue
                    date = str(release.get("published_at") or "")[:10]
                    valid_date=bool(date and iso_date(date)==date)
                    if (plan.as_of or plan.year) and not valid_date:continue
                    if (plan.as_of and date > plan.as_of) or (plan.year and not date.startswith(plan.year)):
                        continue
                    _field(page, "release version", release.get("tag_name"), f"{identifier} published {date}")
                    if valid_date:_field(page, "release date", date, f"{identifier} version {release.get('tag_name')}")
                return ([page] if page.passages else []), bool(page.passages)
        resp = await fetcher.fetch(endpoint)
        data = _data(resp)
        if not isinstance(data, dict):
            return [], False
        page = Page(resp.url, title=identifier)
        license = _mapping(data.get("license"))
        _field(page, "license", license.get("spdx_id") if license.get("spdx_id") != "NOASSERTION" else license.get("name"), identifier)
        for k in ["description", "language", "default_branch", "homepage", "created_at", "updated_at", "stargazers_count"]:
            _field(page, k.replace("_", " "), data.get(k), identifier)
        return [page], False
    if family == "crates":
        if metadata_history(plan):
            from .crates_history import resolve as historical_crate
            pages=await historical_crate(plan,fetcher,identifier)
            return pages,not bool(pages)
        resp = await fetcher.fetch(f"https://crates.io/api/v1/crates/{quote(identifier, safe='')}",max_bytes=8_000_000,timeout=8)
        data = _data(resp)
        if isinstance(data, dict):
            page = Page(resp.url, title=identifier)
            crate = _mapping(data.get("crate"))
            for k, label in [("max_stable_version", "current stable version"), ("description", "description"), ("homepage", "homepage")]:
                if k == "max_stable_version" and (plan.as_of or plan.year):
                    continue
                _field(page, label, crate.get(k), identifier)
            if plan.as_of or plan.year:
                for release in _records(data.get("versions"))[:3500]:
                    date=str(release.get("created_at", ""))[:10]
                    if not date or iso_date(date)!=date:continue
                    if release.get("yanked") or (plan.as_of and date > plan.as_of) or (plan.year and not date.startswith(plan.year)):
                        continue
                    _field(page,"stable version",release.get("num"),f"{identifier} release date {date}")
            return [page], False
    if family in {"arxiv", "pep"}:
        target = f"https://arxiv.org/abs/{identifier}" if family == "arxiv" else f"https://peps.python.org/pep-{int(identifier):04d}/"
        return [parse_response(await fetcher.fetch(target))], False
    if family == "rfc":
        target = f"https://datatracker.ietf.org/api/v1/doc/document/rfc{int(identifier)}/"
        return [parse_response(await fetcher.fetch(target))], False
    return [], False
