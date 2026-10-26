"""Deterministic constraints. Unknown semantic distinctions remain in the question."""
import re
from urllib.parse import urlsplit
from .types import Plan
from .currencies import CODES
from .members import member_count
from .urls import text_urls
from .population import population_request,census_year
from .temporal import cutoff

STOP = set("a an the of for in on to at from with by is are was were be been what which who when where how many much does do did has have its their and or please find tell me give according expressed return website site page official current latest stable version number value get as per using use this that it only i need want".split())
ALIASES = {
    "phone": "phone telephone tel contact support hotline toll-free",
    "email": "email e-mail contact mail",
    "price": "price cost sale discount current offer amount currency",
    "version": "version release stable latest download",
    "date": "date released release submitted published updated launched",
    "license": "license licence licensing spdx",
    "author": "author authors creator maintainer written",
    "headquarters": "headquarters head office hq location address",
    "title": "title name",
    "capacity": "capacity memory storage vram size",
    "duration": "duration timeout lead time delivery days hours minutes seconds",
}


def tokens(text):
    found = re.findall(r"[\w]+(?:[.+#-][\w]+)*", text.casefold(), re.UNICODE)
    # Preserve identifiers and also expose lexical components of compound field labels.
    return found + [part for token in found if "-" in token or "_" in token or '.' in token and re.search('[A-Za-z]',token)
                    for part in re.split(r"[-_.]", token) if part and part != token]


def plan_query(question, url=""):
    question = str(question or "")[:8000]
    urls = text_urls(question)
    url = str(url or (urls[0] if urls else ""))
    q = re.sub(r"https?://\S+", " ", question.casefold())
    requests=list(re.finditer(r'(?:^|[?!.;,\n]\s*)(?:what|which|how|when|who)\b',q))
    intent=q[requests[-1].start():].lstrip(' ?!.;,\n').split('?',1)[0] if requests else q
    focus=re.split(r'\b(?:of|for|from|according to|in|on|at|under|within)\b',intent,maxsplit=1)[0] or intent
    kind = "text"
    for name, pattern in [
        ("phone", r"(?<![a-z])(?:phone|telephone|hotline|cellphone)(?![a-z])|電話"),
        ("email", r"(?<![a-z])e-?mail(?:address)?(?![a-z])|電子郵件"),
        ("url", r"(?:website|homepage|repository|download) (?:url|address)|official website|網址"),
        ("price", r"price|cost|pricing|\bfees?\b|\bfares?\b|價格|售價"),
        ("license", r"licen[sc]e|授權"),
        ("date", r"\bdate\b|\bwhen\b|日期|何時"),
        ("year", r"\b(?:what|which)\s+(?:is\s+)?(?:the\s+)?(?:\w+\s+){0,2}year\b|哪一年"),
        ("version", r"(?:latest|current|newest|stable|lts)\s+(?:\w+\s+){0,3}(?:version|release)|(?:what|which) version|版本"),
        ("percentage", r"percent|percentage|比例|百分"),
        ("duration", r"how long|duration|lead time|timeout|多久"),
        ("measurement", r"how (?:tall|high|wide|heavy)|capacity|memory|weight|mass|voltage|current draw|battery|height|width|\belevation\b|\baltitude\b|\blength\b|dimensions|容量|重量"),
        ("number", r"how many|\bcount\b|\bnumber\b|maximum|minimum|多少"),
        ("boolean", r"^(?:is|are|does|do|can|has)\b"),
    ]:
        if re.search(pattern, focus):
            kind = name
            break
    if re.search(r'^who\b',intent):kind='text'
    elif re.search(r'^(?:what|which) year\b',intent):kind='year'
    elif re.search(r'^when\b',intent):kind='date'
    elif re.search(r'^how many\b',intent):kind='number'
    elif re.search(r'^how old\b',intent):kind='number'  # an age, even when the clause says "when she married"
    elif re.search(r'^(?:is|are|was|were|does|do|can|has|have)\b',intent):kind='boolean'
    if population_request(focus):kind='number'
    scheduled_clock=bool(re.search(r'^when\s+(?:does|do|is)\b.*\b(?:leave|depart|arrive|open|close)\b',intent)
        and re.search(r'\b(?:first|last|weekday|weekend|daily|every|each|morning|evening)\b',intent)
        and not re.search(r'\b(?:date|month|year)\b',intent))
    if re.search(r'\b(?:what|which|at what)\s+time\b',intent) or scheduled_clock:
        kind='time'
    if all(re.search(r'\b'+part+r'\b',focus) for part in ('day','month','year')):kind='date'
    month_year=bool(re.search(r'\b(?:what|which|specify|state|give|provide|tell me)\s+'
        r'(?:(?:is|was|are|were)\s+)?(?:the\s+)?'
        r'(?:month\s*,?\s+and\s+year|year\s*,?\s+and\s+month)\b',intent))
    date_precision='month' if month_year else ''
    if month_year:kind='date'
    if re.search(r"default (?:value|setting)|default (?:of|for)", q):
        kind = "text"
    if re.search(r'\b(?:which|what)\s+(?:pep|rfc)\b',q) and not re.search(r'\btitle\b',q):
        kind='number'
    choices=[]
    alternative=re.search(r'\b(enabled|disabled|active|inactive|open|closed|true|false|yes|no)\s+or\s+'
                          r'(enabled|disabled|active|inactive|open|closed|true|false|yes|no)\b',intent)
    if alternative and alternative[1]!=alternative[2]:
        choices=list(alternative.groups());kind='text'
    attributes = []
    for key, aliases in ALIASES.items():
        if any(t in tokens(q) for t in [key] + aliases.split()[:2]):
            attributes.extend(aliases.split())
    words = [t for t in tokens(q) if t not in STOP]
    attrs = set(attributes)
    entities = [t for t in words if t not in attrs and not re.fullmatch(r"\d{4}", t)]
    versions = re.findall(r"\b(?:version|v|release)\s*(\d+(?:\.\d+){0,3})\b", q)
    operation='single';required_fields=[]
    if len(list(dict.fromkeys(versions)))==2 and re.search(r'\b(?:change|changed|compare|comparison|increase|decrease)\b',q):
        operation='compare_versions'
    else:
        requested=re.search(r'\b(?:what|which)\s+(?:(?:is|are)\s+)?(.+)',intent)
        if requested and not month_year:
            head=re.split(r'\b(?:of|for|from|in|on|does|do)\b',requested[1],maxsplit=1)[0].rstrip(' ?')
            fields=[re.sub(r'\b(?:during|which|what|the|at)\b','',part).strip() for part in head.split(' and ')]
            # Coordinated parts of a person's name ask for one complete name,
            # not two independent table fields. Explicit field/column requests
            # and genuinely different outputs still use bounded composition.
            whole_name=bool(re.fullmatch(r'(?:the\s+)?(?:first|given)(?:\s+names?)?\s+and\s+'
                r'(?:(?:last|family)\s+names?|surnames?)',head))
            if len(fields)==2 and all(0<len(part.split())<=3 for part in fields) and not whole_name:
                operation='compose_fields';required_fields=fields
    year_match = re.search(r"\b(?:in|during|for)\s+(\d{4})\b", q)
    census_value=census_year(q)
    year_value=year_match[1] if year_match else census_value
    asof_value,temporal_issue,temporal_raw,current_cutoff=cutoff(q,census_value)
    currency=''
    code_pattern='(?:'+'|'.join(CODES)+')'
    explicit=list(re.finditer(r'\b(?:in|currency|denominated in|expressed in)\s*[:=]?\s*('+code_pattern+r')\b',q,re.I))
    mentions=explicit+list(re.finditer(r'\b('+code_pattern+r')\b',q,re.I))
    for match in mentions:
        prefix=q[max(0,match.start()-40):match.start()]
        if not re.search(r'\b(?:not|except|excluding|without|rather than)(?:\s+(?:in|use|using|denominated|expressed)){0,2}\s*$',prefix):
            currency=match[1].upper();break
    negations = re.findall(r"(?:not|excluding|except|without)\s+(?:in\s+)?([\w.-]+)", q)
    cardinal = re.search(r"\b(?:first|top|list)\s+(\d+)\b", q)
    try:domain = urlsplit(url).hostname or ""
    except ValueError:domain = ''  # Fetcher rejects malformed URLs without crashing planning.
    site = re.search(r"\bsite:([\w.-]+)", q)
    latest = bool(asof_value or current_cutoff or re.search(r"latest|current|newest|現在|最新", q))
    stable = bool(re.search(r"stable|lts|穩定", q))
    if kind == "version" and latest and not re.search(r"beta|preview|alpha|release candidate|\brc\b|prerelease", q):
        stable = True
    return Plan(question, url, kind, list(dict.fromkeys(words)), list(dict.fromkeys(attributes)),
                list(dict.fromkeys(entities)), versions, year_value if not asof_value else "",
                asof_value, latest,
                stable, bool(re.search(r"first|original|earliest|最初", q)),
                currency, member_count(question,kind,operation) or (min(10, int(cardinal[1])) if cardinal else 1), negations,
                site[1] if site else domain,focus,choices,operation,required_fields,date_precision,
                temporal_issue=temporal_issue,temporal_raw=temporal_raw)
