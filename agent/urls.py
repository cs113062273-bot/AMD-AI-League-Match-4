import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit, unquote_plus, urljoin,parse_qs


def text_urls(text):
    """HTTP URLs in prose, preserving internal balanced delimiters and bytes.

    Explicit quotes/angle brackets disambiguate literal terminal punctuation.
    A nonempty bare query is also kept verbatim rather than guessing which
    part of a parameter value is sentence punctuation.
    """
    result=[];position=0
    pairs={'(':')','[':']','{':'}'}
    while match:=re.search(r'https?://',text[position:],re.I):
        start=position+match.start();end=start
        before=text[start-1] if start else ''
        closer={'<':'>','"':'"',"'":"'",'`':'`'}.get(before)
        # Delimited URLs can contain unmatched parentheses as literal data.
        stop=text.find(closer,start) if closer else -1
        if stop>=0 and not any(char.isspace() for char in text[start:stop]):
            result.append(text[start:stop]);position=stop+1;continue
        stack=[];closed=False
        for end in range(start,len(text)):
            char=text[end]
            if char.isspace() or char in '<>"`' or ord(char)<32:
                break
            if char in pairs:
                stack.append(pairs[char])
            elif char in ')]}':
                if not stack or stack[-1]!=char:
                    closed=char==pairs.get(before)
                    break
                stack.pop()
        else:end=len(text)
        url=text[start:end]
        if not closed and ('?' not in url or url.endswith('?') and url.count('?')==1):
            url=url.rstrip('.,;?')
        if url:result.append(url)
        position=max(end,start+len(match[0]))
    return result


def unique_links(links):
    """Preserve ranking while allocating one candidate slot per URL."""
    result={}
    for url,label in links:
        result.setdefault(url,(url,label))
    return list(result.values())


def relevance_url(url):
    """Ranking text only: search-query echoes do not identify a resource.

    Keep identity parameters and preserve the actual URL used for fetching.
    """
    try:
        parts=urlsplit(url)
        search_keys={'q','query','search','searchterm','searchquery','se','s','keyword','keywords','srsearch'}
        query='&'.join(part for part in parts.query.split('&') if
            re.sub(r'[^a-z0-9]','',unquote_plus(part.split('=',1)[0]).casefold()) not in search_keys)
        return urlunsplit((parts.scheme,parts.netloc,parts.path,query,''))
    except (ValueError,UnicodeError):
        return ''


def answer_lookup_url(url):
    """Known query-derived clue lookup, distinct from editorial site pages."""
    try:
        parts=urlsplit(url);host=(parts.hostname or '').lower()
        return (host=='wordplays.com' or host.endswith('.wordplays.com')) and (
            parts.path.lower().rstrip('/')=='/crossword-solver' or parts.path.lower().startswith('/crossword-solver/'))
    except (ValueError,UnicodeError):
        return False


def discovery_url(url):
    """Known search-result endpoints are discovery, never source evidence."""
    try:
        parsed=urlsplit(url);host=(parsed.hostname or '').lower();path=parsed.path.lower()
        if host=='r.search.yahoo.com':return True
        if host=='search.yahoo.com':return path.rstrip('/') in {'/search','/preferences/preferences'}
        if any(host==domain or host.endswith('.'+domain) for domain in ('google.com','bing.com')):
            return path.rstrip('/') in {'/search','/url','/complete/search'} or path.startswith('/ck/')
        if host=='duckduckgo.com' or host.endswith('.duckduckgo.com'):
            return path.startswith(('/html','/lite','/l/')) or 'q=' in parsed.query
        if any(host==domain or host.endswith('.'+domain) for domain in ('wikipedia.org','wikidata.org')):
            params=parse_qs(parsed.query,max_num_fields=128)
            return path.startswith('/wiki/special:search') or 'search' in params or 'search' in params.get('list',[]) or params.get('action',[''])[0] in {'opensearch','wbsearchentities'}
    except (ValueError,UnicodeError):return False
    return False


def canonical_url(url, base=""):
    try:
        u = urlsplit(urljoin(base, str(url).strip()))
        if u.scheme.lower() not in {"http", "https"} or not u.hostname or u.username or u.password:
            return ""
        host = u.hostname.encode("idna").decode("ascii").lower()
        if ":" in host:
            host = "[" + host + "]"
        port = u.port
        netloc = host + (f":{port}" if port and (u.scheme.lower(), port) not in {("http", 80), ("https", 443)} else "")
        # Preserve byte spelling/order of semantic parameters (signed URLs may depend on it).
        query = [part for part in u.query.split('&') if not
                 (unquote_plus(part.split('=',1)[0]).lower().startswith('utm_') or
                  unquote_plus(part.split('=',1)[0]).lower() in {'fbclid','gclid'})]
        names={unquote_plus(part.split('=',1)[0]).lower() for part in u.query.split('&')}
        if names.intersection({'signature','sig','x-amz-signature','x-goog-signature','hmac','policy'}):
            query=u.query.split('&')
        return urlunsplit((u.scheme.lower(), netloc, u.path or "/", '&'.join(query), ""))
    except (ValueError, UnicodeError):
        return ""


def public_ip(address):
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
        if isinstance(ip,ipaddress.IPv6Address):
            mapped=ip.ipv4_mapped or ip.sixtofour
            if ip in ipaddress.ip_network('64:ff9b::/96'):mapped=ipaddress.IPv4Address(int(ip)&0xffffffff)
            if mapped and not mapped.is_global:return False
        return ip.is_global and not ip.is_multicast
    except ValueError:
        return False


def same_site(a, b):
    x, y = urlsplit(a).hostname or "", urlsplit(b).hostname or ""
    return x.removeprefix("www.") == y.removeprefix("www.")


def safe_id(value):
    value = str("query" if value is None or value == "" else value)
    safe = re.sub(r"[^\w.-]", "_", value, flags=re.UNICODE).strip(". ")[:100]
    if not safe or safe.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1,10)), *(f"LPT{i}" for i in range(1,10))}:
        safe = "query_" + safe
    return safe
