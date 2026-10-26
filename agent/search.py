"""Public no-key providers. Search snippets are discovery only, never answer evidence."""
import asyncio
import json
import re
import base64
import unicodedata
from urllib.parse import quote, quote_plus, urlsplit, parse_qs, unquote
from bs4 import BeautifulSoup

from .urls import canonical_url,discovery_url,unique_links,relevance_url,answer_lookup_url
from .planner import tokens, STOP
from .literature import title_links
from .normalize import calendar_years


def source_title_query(plan):
    """Recover an unmentioned subject from the user's Wikipedia starting URL.

    This is a discovery hint only. It never supplies an answer or changes the
    question/evidence checks, and is used only after that source failed.
    """
    try:
        parts=urlsplit(plan.url)
        host=parts.hostname or ''
        if (parts.scheme not in {'http','https'}
                or not re.fullmatch(r'[a-z]{2,3}(?:-[a-z]+)*(?:\.m)?\.wikipedia\.org',host)
                or host.startswith('www.') or parts.username or parts.password
                or parts.port not in {None,80,443} or not parts.path.startswith('/wiki/')):
            return ''
        title=unquote(parts.path[6:],errors='strict').replace('_',' ')
    except (ValueError,UnicodeError):return ''
    if not 2<=len(title)<=120 or re.search(r'[\x00-\x1f\x7f"<>\[\]{}|\\:]',title):return ''
    title=' '.join(title.split())
    words=set(tokens(title))-STOP
    if not words or len(title.split())>12 or words.intersection(plan.entity_terms):return ''
    return '"'+title+'"'


def rewrites(plan,hints=()):
    q = re.sub(r"https?://\S+", "", plan.question).strip()[:450]
    # Search forms are more reliable with content words than conversational lead-ins.
    compact=' '.join(dict.fromkeys(plan.terms))[:300]
    identifiers=re.findall(r'`([^`]{2,80})`|\b([A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+)\b',plan.question)
    exact=list(dict.fromkeys(a or b for a,b in identifiers))[:3]
    targeted=' '.join('"'+term+'"' for term in exact)+' '+compact if exact else compact
    out = [targeted[:400] or q,q]
    if plan.domain:
        out.insert(0, f"site:{plan.domain} {q}")
    useful=[hint for hint in hints if isinstance(hint,str) and 1<len(hint)<=60 and not re.search(r'https?://|\d|[\r\n]',hint)]
    if useful:
        # Hints enrich the user's entity/field query; they must never replace it.
        out.insert(0,(targeted[:320]+' '+' '.join(useful[:4])[:120]).strip())
    if plan.entity_terms:
        out.append(" ".join(plan.entity_terms[:5] + plan.attributes[:2]))
    return list(dict.fromkeys(out))[:3]


def location_hint(plan,hint):
    """Keep one explicit, unambiguous named location in a valid short hint."""
    question=re.sub(r'["`]([^"`\r\n]+)["`]',lambda m:' '*len(m[0]),plan.question)
    names=[]
    for match in re.finditer(r"(?i:\b(?:in|at|near|within)\s+(?:the\s+)?)([A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)+)\b",question):
        if re.search(r'\b(?:not|except|excluding|outside)\s*$',question[:match.start()],re.I):continue
        phrase=match[1];words=set(tokens(phrase))-STOP
        if not 2<=len(phrase.split())<=4 or len(words.intersection(plan.entity_terms))<2:continue
        if phrase.casefold() not in {name.casefold() for name in names}:names.append(phrase)
    if len(names)!=1:return hint
    words=set(tokens(hint))
    missing=[word for word in names[0].split() if word.casefold() not in words and word.casefold() not in STOP]
    query=hint+(' '+' '.join(missing) if missing else '')
    return query if len(query)<=120 and len(query.split())<=8 else hint


def concise_query(plan,hints=()):
    """One short topic query, anchored to the user's entity, for a final provider.

    Hints are unverified discovery text. They never replace the question used
    by the reader, and unrelated names/answers cannot form a topic query.
    """
    generic={'first','last','given','family','name','day','month','year','line','field','value'}
    original=set(plan.entity_terms)-generic
    if not original:return ''
    minimum=min(2,len(original))
    valid=[]
    for hint in hints:
        if not isinstance(hint,str) or not 1<len(hint)<=80 or re.search(r'https?://|\d|[\r\n]',hint):continue
        words=tokens(hint)
        retained=len(original.intersection(words))
        if 2<=len(hint.split())<=8 and retained>=minimum:
            valid.append((retained,hint.strip()))
    if valid:
        # Model ordering is not a relevance guarantee. Keep the most user
        # content among already-valid hints, retaining original order on ties.
        return location_hint(plan,max(valid,key=lambda item:item[0])[1])
    # A quoted title/identifier is supplied by the user, not invented by the
    # model. Keep up to two contextual topic terms after it for disambiguation.
    for quoted in re.findall(r'["`]([^"`\r\n]{2,80})["`]',plan.question):
        if re.search(r'https?://',quoted,re.I):continue
        words=set(tokens(quoted))-generic
        if not words or not words.intersection(original):continue
        excluded=words|set(tokens(plan.focus))
        extra=[word for word in plan.terms if word not in excluded][:2]
        query='"'+quoted+'"'+(' '+' '.join(extra) if extra else '')
        if len(query)<=120 and len(query.split())<=10:return query
    # Empty/invalid model hints must not leave a long historical question as
    # the only fallback. Two explicit multiword names plus one unambiguous
    # year give a bounded topic query using only the user's own words.
    question=re.sub(r'https?://\S+',' ',plan.question)
    years=list(dict.fromkeys(calendar_years(question)))
    if len(years)==1:
        names=[]
        for phrase in re.findall(r"\b[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)+\b",question):
            parts=phrase.split()
            while parts and parts[0].casefold() in STOP|generic:parts.pop(0)
            phrase=' '.join(parts)
            if not 2<=len(phrase.split())<=4:continue
            if len((set(tokens(phrase))-STOP-generic).intersection(original))<2:continue
            if phrase.casefold() not in {name.casefold() for name in names}:names.append(phrase)
        if len(names)>=2:
            query=' '.join(names[:2]+years)
            if len(query)<=120 and len(query.split())<=9:return query
    return ''


_LEAD=set("what which who whom whose when where why how in on at for from within during did does do is are was were the a an of and to by with after before between".split())


def name_queries(question):
    """Proper-noun phrases the user wrote, for encyclopedia title search (discovery only)."""
    text=re.sub(r'https?://\S+',' ',question)
    phrases=[]
    pattern=r"[A-Z][\w'’.-]*(?:\s+(?:(?:of|the|de|del|von|van|der|and|la|le)\s+)*[A-Z][\w'’.-]*)*"
    for match in re.finditer(pattern,text):
        words=match[0].split()
        while words and words[0].casefold() in _LEAD:words.pop(0)
        phrase=' '.join(words).strip(" .'’-")
        if len(phrase)>=3 and phrase.casefold() not in {p.casefold() for p in phrases}:phrases.append(phrase)
    queries=[]
    if phrases:
        queries.append(' '.join(phrases[:6])[:200])
        if len(phrases)>2:queries.append(' '.join(phrases[:2])[:120])
    return list(dict.fromkeys(queries))


async def wikipedia_links(plan,fetcher):
    """English Wikipedia title search through its official API; the article must still be fetched and read."""
    if fetcher.deadline.remaining<=5:return []
    queries=name_queries(re.sub(r'https?://\S+','',plan.question))[:2]+[re.sub(r'https?://\S+','',plan.question).strip()[:250]]
    async def one_query(query):
        resp=await fetcher.fetch('https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=4&srsearch='+quote(query),
            timeout=4,max_bytes=200000)
        if resp.error or resp.status!=200:return []
        try:
            entries=json.loads(resp.text).get('query',{}).get('search',[])
            return [('https://en.wikipedia.org/wiki/'+quote(item['title'].replace(' ','_')),item['title'])
                    for item in entries if isinstance(item,dict) and isinstance(item.get('title'),str)][:4]
        except (ValueError,TypeError,AttributeError):return []
    results=await asyncio.gather(*(one_query(q) for q in dict.fromkeys(queries) if q))
    links=[]
    for batch in results:
        for item in batch:
            if item not in links:links.append(item)
    return links[:8]


async def search(plan, fetcher, providers=None,hints=()):
    standard_providers=providers is None
    queries = rewrites(plan,hints)
    failed_hosts={urlsplit(event['url']).hostname for event in fetcher.events if event.get('error') in {'http_403','http_429'} or 'Certificate' in event.get('error','')}
    if plan.domain in failed_hosts:
        queries=[query for query in queries if not query.startswith('site:'+plan.domain+' ')] or queries
    source_query=source_title_query(plan) if plan.domain in failed_hosts else ''
    if source_query:
        queries=list(dict.fromkeys([source_query]+queries))[:3]
    source_words=set(tokens(source_query))-STOP
    providers = providers or [
        ("https://www.google.com/search?q=", "google"),
        ("https://www.bing.com/search?setlang=en-US&cc=US&q=", "bing"),
        ("https://html.duckduckgo.com/html/?q=", "duckduckgo"),
    ]
    found = [];batches=[];yahoo_targets=set()
    # Official Wikipedia title-search hits come from the question's own proper nouns; a title
    # rarely repeats class words like "EP", so overlap scoring alone would drop the right article.
    trusted=set()
    def lexical(text):
        # Search matching tolerates diacritics; answer/source literals do not change.
        return set(tokens(''.join(c for c in unicodedata.normalize('NFKD', text)
                                  if not unicodedata.combining(c))))
    named=set()
    generic={'specify','provide','state','name','list','identify','give','find','tell','show'}
    for match in re.finditer(r"\b[^\W\d_][\w'-]*\b",plan.question,re.UNICODE):
        word=match[0]
        if word[0].isupper() and word.casefold() not in STOP|generic:
            named.update(lexical(word))
    named.intersection_update(lexical(' '.join(plan.entity_terms)))
    if plan.url and not failed_hosts:
        named.clear()
    puzzle_question=bool(re.search(r'\b(?:crosswords?|clues?|puzzles?)\b',plan.question,re.I))
    def source_link(target):
        return target and not discovery_url(target) and (puzzle_question or not answer_lookup_url(target))
    def retain(links):
        batches.append(links)
        found.extend(links)
    def relevance(item):
        target,label=item
        ranking_url=relevance_url(target)
        words=set(tokens(label+' '+ranking_url))
        identifiers=[t for t in plan.terms if '_' in t]
        entity=set(plan.entity_terms)|source_words
        if target in yahoo_targets:
            words=lexical(label+' '+unquote(ranking_url))
            entity=lexical(' '.join([*plan.entity_terms,*source_words]))
        overlap=len(entity.intersection(words))
        # Matching only one generic question word ("first", "day", etc.)
        # must not make a multi-term query's unrelated batch stop fallback.
        # Keep single-term subjects and exact technical identifiers usable.
        anchored=max(0,overlap-min(2,len(entity))+1) if entity else 0
        named_match=target in yahoo_targets and bool(named) and len(named.intersection(words))>=min(2,len(named))
        score=anchored+2*named_match+4*sum(t in label+' '+ranking_url for t in identifiers)-(5 if urlsplit(target).hostname in failed_hosts else 0)
        return max(score,1) if target in trusted else score
    def usable():
        # A URL alone is not evidence that discovery succeeded. Try another
        # provider while time permits rather than trusting weak topic matches.
        return bool(found) and max(map(relevance,found))>0
    # Two concurrent independent providers; third is a real fallback.
    async def one(prefix, name, query):
        resp = await fetcher.fetch(prefix + quote_plus(query),timeout=3,max_bytes=400000)
        if resp.error:
            return []
        if name=='bing_rss':
            import xml.etree.ElementTree as ET
            try:
                root=ET.fromstring(resp.body)
                return [(target,(item.findtext('title') or '').strip()[:250]) for item in root.findall('.//item')
                    if source_link(target:=canonical_url(item.findtext('link') or ''))][:8]
            except ET.ParseError:return []
        soup = BeautifulSoup(resp.text, "html.parser")
        links = []
        selector = "a.result__a" if name == "duckduckgo" else 'a.result-link' if name=='duckduckgo_lite' else "li.b_algo h2 a" if name == "bing" else 'h3' if name=='yahoo' else "a"
        for a in soup.select(selector):
            if name=='yahoo':
                a=a.find('a',href=True) or a.find_parent('a',href=True)
                if a is None:continue
            href = str(a.get("href", ""))
            if name == "google" and urlsplit(href).path=='/url':
                params=parse_qs(urlsplit(href).query)
                href = (params.get('q') or params.get('url') or [''])[0]
            if name == 'bing' and (urlsplit(href).hostname or '').endswith('bing.com') and urlsplit(href).path.startswith('/ck/'):
                wrapped=parse_qs(urlsplit(href).query).get('u',[''])[0]
                if wrapped.startswith('a1'):
                    try:href=base64.urlsafe_b64decode(wrapped[2:]+'='*(-len(wrapped[2:])%4)).decode('utf-8')
                    except (ValueError,UnicodeError):continue
            if "uddg=" in href:
                href = parse_qs(urlsplit(href).query).get("uddg", [""])[0]
            target = canonical_url(href)
            host = urlsplit(target).hostname or ""
            if source_link(target):
                label = a.get_text(" ", strip=True)
                if label:
                    if name=='yahoo':yahoo_targets.add(target)
                    links.append((target, label[:250]))
        return links[:8]
    selected = providers[1:] if len(providers) > 1 else providers
    requests=[one(p,n,q) for p,n in selected for q in queries[:2]]
    if standard_providers:
        requests.append(title_links(plan,fetcher))
        async def trusted_wikipedia():
            links=await wikipedia_links(plan,fetcher)
            trusted.update(target for target,label in links)
            return links
        requests.append(trusted_wikipedia())
    results = await asyncio.gather(*requests)
    for links in results:
        retain(links)
    if not usable() and standard_providers and fetcher.deadline.remaining>7:
        # Actual public endpoints, separately probed; no snippets become evidence.
        broad=next((q for q in queries if not q.startswith('site:')),queries[0])
        requests=[one('https://www.bing.com/search?format=rss&q=','bing_rss',broad),
            one('https://lite.duckduckgo.com/lite/?q=','duckduckgo_lite',broad),
            one('https://search.yahoo.com/search?p=','yahoo',broad)]
        concise=concise_query(plan,hints)
        if concise and concise not in queries[:2]:
            requests.append(one('https://lite.duckduckgo.com/lite/?q=','duckduckgo_lite',concise))
        extra=await asyncio.gather(*requests)
        for links in extra:retain(links)
    if not usable() and fetcher.deadline.remaining > 8:
        broad=next((q for q in queries if not q.startswith('site:')),queries[0])
        retain(await one(*providers[0], broad))
    if not usable() and len(queries) > 1 and fetcher.deadline.remaining > 8 and queries[-1] not in queries[:2]:
        retain(await one(*providers[-1], queries[-1]))
    # General encyclopedia search is a final discovery fallback; the article still must be fetched.
    if not usable() and fetcher.deadline.remaining > 4:
        import json
        resp = await fetcher.fetch("https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srsearch=" + quote(plan.question[:250]))
        try:
            data=json.loads(resp.text)
            query=data.get('query') if isinstance(data,dict) else None
            entries=query.get('search') if isinstance(query,dict) else None
            wiki=[]
            for item in entries[:3] if isinstance(entries,list) else []:
                if isinstance(item,dict) and isinstance(item.get('title'),str):
                    wiki.append(("https://en.wikipedia.org/wiki/" + quote(item["title"].replace(" ", "_")), item["title"]))
            trusted.update(target for target,label in wiki)
            retain(wiki)
        except (ValueError, TypeError, KeyError):
            pass
    # An unrelated-only response is not a last-resort source. Keep generic
    # links only inside batches with an anchored result, including when every
    # provider was tried and none answered the actual topic.
    found=[item for batch in batches if any(relevance(item)>0 for item in batch) for item in batch]
    return unique_links(sorted((item for item in found if not discovery_url(item[0])),key=relevance,reverse=True))[:12]
