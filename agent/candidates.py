from __future__ import annotations

import math
import re
from dataclasses import replace
from itertools import islice
from urllib.parse import urlsplit

from packaging.version import Version, InvalidVersion

from .normalize import clean, normalize, equivalence, iso_date, iso_month, literal_span,calendar_years
from .planner import tokens
from .types import Candidate, Plan, Page
from .currencies import PATTERN as CURRENCY
from .signatures import parameter_default
from .qualifiers import key_name
from .evidence import eligible, table_supported, explicit_field, direction_supported, line_supported, event_year_supported
from .members import literal_members, join_members
from .literature import paper_title
from .population import population_role_supported
from .license_expressions import declared as declared_license, complete as complete_license
from .cardinals import count_request, spans as cardinal_spans, count_value as cardinal_integer, licensed as cardinal_licensed, answer as count_answer
from .number_atoms import NUMBER as SOURCE_NUMBER
from .source_excerpts import excerpt
from .phones import PATTERN as PHONE_PATTERN, complete as complete_phone
from .evidence_binding import bind

SCALAR=r'[-+−]?(?:\d+(?:[,.]\d+)*|\.\d+)(?:[eE][-+−]?\d+)?'
NUM = r"(?<![\w.])"+SCALAR+r'(?!\d|[.,]\d)'
RANGE = NUM+r'(?:\s*(?:[-–—]|to)\s*'+NUM+r')?'
GEO_UNIT=r'(?:feet|foot|ft|metres?|meters?|m)'
MAG = r'(?:\s*(?:thousand|million|billion|trillion|[kmbt])\b)?'
PATTERNS = {
    "email": r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "phone": PHONE_PATTERN,
    "version": r"(?<![\w.])[vV]?\d+\.\d+(?:\.\d+){0,2}(?:[-.]?(?:alpha|beta|rc|a|b|pre|dev)\d*(?:\.\d+)?)?(?![\w.])",
    "date": r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan\w*|Feb\w*|Mar\w*|Apr\w*|May|Jun\w*|Jul\w*|Aug\w*|Sep\w*|Oct\w*|Nov\w*|Dec\w*)\s+\d{4}\b|\b(?:Jan\w*|Feb\w*|Mar\w*|Apr\w*|May|Jun\w*|Jul\w*|Aug\w*|Sep\w*|Oct\w*|Nov\w*|Dec\w*)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b",
    "year": r"(?<![\w.])\d{4}(?![\w.])",
    "price": r'(?:(?:US\$|NT\$|[$€£¥]|'+CURRENCY+r'\s*)\s*'+SCALAR+MAG+r'(?:\s*'+CURRENCY+r')?|'+NUM+MAG+r'\s*'+CURRENCY+r')(?!\w|[.,]\d)',
    "percentage": NUM + r"\s*(?:%|percent\b)",
    "number": RANGE+r'(?:\s*:\s*'+NUM+r')?'+MAG+r'(?!\w|[.,]\d)',
    "measurement": RANGE + r"\s*(?:GiB|GB|MB|TB|MiB|KiB|bytes|bits|mAh|Ah|kWh|Wh|kW|W|kg|mg|[µμ]g|g|km|cm|mm|[µμ]m|m|metres?|meters?|GHz|MHz|Hz|inches|inch|ft|feet|foot|liters|mL|L|characters|cores|lbs?|pounds|oz|kPa|MPa|Pa|psi|bar|mV|V|mA|A|dpi|ppi|°C|°F)\b",
    "duration": RANGE + r"(?:\s*[-–]\s*|\s*)(?:business days?|working days?|days?|hours?|minutes?|seconds?|weeks?|months?|years?|ms|s)\b",
    "time": r'(?<![\w:])(?:(?:0?[1-9]|1[0-2])(?::[0-5]\d(?::[0-5]\d)?)?\s*[ap]\.?m\.?|(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?!\s*[ap]\.?m))(?![\w:])',
    "url": r"https?://[^\s<>\"|]+",
}
PATTERNS['date']+=r'|\b\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}\b|\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}\b|\d{4}年\s*\d{1,2}月\s*\d{1,2}日?'
PATTERNS['month']=r'\b(?:Jan\w*|Feb\w*|Mar\w*|Apr\w*|May|Jun\w*|Jul\w*|Aug\w*|Sep\w*|Oct\w*|Nov\w*|Dec\w*)\s+\d{4}\b|\b\d{4}-(?:0[1-9]|1[0-2])\b(?![-/.]\d)'


def overlap(terms, text):
    found = set(tokens(text))
    return sum(1 for t in set(terms) if t in found or (len(t) > 3 and any(t == w.rstrip("s") for w in found)))


def authority(url, plan):
    host = urlsplit(url).hostname or ""
    if plan.domain and (host == plan.domain or host.endswith("." + plan.domain)):
        return 2.0
    if host in {"pypi.org", "registry.npmjs.org", "api.github.com", "crates.io", "arxiv.org", "peps.python.org", "docs.python.org"}:
        return 1.8
    if host.endswith((".gov", ".edu")):
        return 0.8
    return 0.0


def creator_pattern(plan):
    if plan.kind!='text' or plan.operation!='single':return ''
    roles={
        'sculptor':r'(?:sculpted|carved|created)',
        'architect':r'designed',
        'artist':r'(?:painted|created)',
        'painter':r'painted',
        'author':r'(?:written|authored)',
        'creator':r'created',
        'designer':r'designed',
    }
    requested=re.search(r'\b(?:what|which)\s+(?:(?:is|was)\s+)?(?:the\s+)?'
        r'(?:name\s+of\s+(?:the\s+)?)?('+ '|'.join(roles)+r')\b',plan.question,re.I)
    if requested:return r'\b'+roles[requested[1].casefold()]+r'\s+by\b'
    who=re.match(r'\s*who\s+(created|designed|sculpted|carved|painted|wrote|authored)\b',plan.focus,re.I)
    if who:return r'\b'+('written' if who[1].casefold()=='wrote' else who[1])+r'\s+by\b'
    return ''


def passage_score(plan, page, passage):
    ctx = f"{passage.label} {passage.section} {passage.text}"
    label = passage.label.casefold()
    terms=plan.terms
    title=paper_title(plan.question)
    title_matched=bool(title and any(clean(part).casefold().removesuffix('.')==title.casefold().removesuffix('.')
        for part in re.split(r'\s+[|—-]\s+',page.title)))
    if title_matched:
        # Once the document identifies the exact requested paper, repeated
        # title words must not outrank the field the user actually asks for.
        topic=set(tokens(title));focus=set(tokens(plan.focus))
        terms=[term for term in terms if term not in topic or term in focus]
    attr_overlap = overlap(terms, label)
    n = overlap(terms, ctx)
    attrs = overlap(plan.attributes, label + " " + passage.section)
    entity = overlap(plan.entity_terms, ctx + " " + page.title)
    length_penalty = math.log1p(max(0, len(passage.text)-200)) * 0.1
    score = n * 1.1 + attr_overlap * 2.3 + min(attrs, 3) * 0.6 + min(entity, 4) * 0.5
    relation=creator_pattern(plan)
    if relation and passage.kind in {'prose','record'}:
        for match in re.finditer(relation,passage.text,re.I):
            if not re.search(r'\b(?:not|never)\s+(?:\w+\s+){0,2}$',passage.text[max(0,match.start()-40):match.start()],re.I):
                score+=6
                break
    if (title_matched and re.search(r'\bage\b',plan.focus,re.I)
            and re.search(r'\bage(?:d|s)?\s*(?:range\s*)?(?:[:=]\s*|of\s+|between\s+)?\d',passage.text,re.I)):
        score+=8
    default=re.search(r'default (?:value )?(?:of|for) (?:the )?[`\x27]?([\w_]+)',plan.question,re.I)
    if default and overlap(tokens(default[1]),label):score+=8
    identifiers=[t for t in plan.terms if '_' in t or '-' in t and re.search(r'\bfield\b|\bparameter\b|\bsetting\b|\bkey\b',plan.question,re.I)
        or re.fullmatch(r'\d+\.\d+\.\d+(?:\.\d+)*',t)]
    score += min(2,overlap(identifiers,ctx))*4
    qwords = set(tokens(plan.question))
    if "title" in qwords and "title" in tokens(label):
        score += 6
        value_words = set(tokens(passage.value))
        if value_words:
            score += 3 * len(value_words.intersection(tokens(page.title))) / len(value_words)
        if label.startswith("twitter"):
            score -= 3
    if "author" in qwords and "author" in tokens(label) and "email" not in tokens(label):
        score += 6
        if label.startswith("citation"):
            score -= 2  # Bibliography may use "surname, given" rather than the visible author spelling.
    if passage.kind in {"field", "cell", "json", "xml"}:
        score += 1.0
    if passage.kind in {"jsonld", "embedded", "meta"}:
        score -= 0.25
    if plan.year:
        dates = calendar_years(ctx)
        if dates and plan.year not in dates:
            score -= 7
        elif plan.year in dates:
            score += 3
    if plan.as_of:
        dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", ctx)
        if dates and min(dates) > plan.as_of:
            score -= 15
    if plan.versions:
        explicit = re.findall(r"\b(?:version|v|release)\s*(\d+(?:\.\d+)*)", ctx, re.I)
        if explicit and not any(v == e or e.startswith(v + ".") for v in plan.versions for e in explicit):
            score -= 10
    lower = ctx.casefold()
    if plan.latest and any(t in lower for t in ["archived", "obsolete", "superseded", "deprecated", "previous version"]):
        score -= 6
    if plan.kind == "phone":
        if "fax" in label or ("fax" in lower and "phone" not in label and "support" not in label):
            score -= 14
        if "sales" in lower and "support" in plan.question.casefold() and "support" not in lower:
            score -= 9
    if plan.kind == "price" and not re.search(r"msrp|list price|original|member|financ", plan.question, re.I):
        if re.search(r"msrp|list price|original|financ|out.of.stock", label + " " + passage.section, re.I):
            score -= 9
    if "headquarters" in plan.question.casefold() and re.search(r"warehouse|shipping", label):
        score -= 12
    if re.search(r"\bwho\b|\bauthor\b|\bmaintainer\b", plan.question, re.I) and plan.kind == "text":
        if "email" in label or "e-mail" in label:
            score -= 8
    if any(re.search(r"\b" + re.escape(t) + r"\b", lower) for t in plan.negations):
        score -= 8
    return score + authority(page.url, plan) - length_penalty


def extract(plan: Plan, page: Page):
    if page.error:
        return []
    out = []
    first_author_seen = False
    default_match = re.search(r"default (?:value )?(?:of|for) (?:the )?[`']?([\w_]+)", plan.question, re.I)
    function_match = re.search(r"(?:parameter|argument) (?:in|of) [`']?([\w.]+)", plan.question, re.I)
    for p in page.passages:
        if len(out)>=6000:break
        if not eligible(plan,page,p):continue
        if default_match and p.kind == "field" and "(" in p.label:
            # A documentation definition list's dd is explanatory prose, not a parameter default.
            continue
        base = passage_score(plan, page, p)
        values = []
        if plan.kind in PATTERNS:
            source_text = p.value if p.value else p.text
            pattern=PATTERNS[plan.kind]+('|'+PATTERNS['month'] if plan.kind=='date' and plan.date_precision=='month' else '')
            for m in islice(re.finditer(pattern, source_text, re.I),64):
                values.append(m[0])
            if count_request(plan.question,plan.kind,plan.operation):
                values.extend(raw for raw,value in islice(cardinal_spans(source_text,p.qualifiers.get('source_continues',False)),64))
            if plan.kind=='price' and p.value and re.fullmatch(SCALAR,clean(p.value)) and re.search(r'\b(?:price|cost|amount)\b',p.label,re.I):
                values.append(clean(p.value))
            if plan.kind == "phone" and p.value and "phone" in p.label.lower():
                if len(re.sub(r"\D", "", p.value)) >= 7:
                    values.append(p.value)
        else:
            if default_match and p.kind == "signature":
                if function_match and function_match[1].split(".")[-1].casefold() not in p.text.casefold():
                    continue
                param = default_match[1]
                value=parameter_default(p.text,param)
                if value is not None:
                    values.append(value.strip())
                    base += 8
            if p.value and overlap(plan.terms + plan.attributes, p.label) > 0:
                values.append(p.value)
            if plan.first and re.search(r"author", plan.question, re.I) and "author" in p.label.lower():
                if first_author_seen and p.label.lower() != "first author":
                    continue
                first_author_seen = True
                base += 3
            # Label/value prose is common in contact/specification pages.
            if ":" in p.text and len(p.text) < 350:
                left, right = p.text.split(":", 1)
                if overlap(plan.terms + plan.attributes, left):
                    values.append(right.strip())
            full=declared_license(plan,p)
            if full:values.append(full)
            if plan.kind == "license":
                values.extend(re.findall(r"\b(?:MIT|Apache(?:[- ](?:License )?)?2\.0|BSD-[23]-Clause|GPL-[23]\.0(?:-only|-or-later)?|ISC|MPL-2\.0|Unlicense)\b", p.text, re.I))
            if plan.kind == "boolean" and p.value.lower() in {"yes", "no", "true", "false"}:
                values.append(p.value)
        for raw in dict.fromkeys(values):
            raw = clean(raw)
            if not raw or len(raw) > 350 or equivalence(raw) not in equivalence(p.text):
                continue
            score = base
            if p.value and raw == clean(p.value):
                score += 1.3
            if plan.kind == "version":
                if re.search(r"(?:^|[ ._])(?:size|uploaded|requires python|requires-python|dependency|dependencies)(?:$|[ ._])", p.label, re.I):
                    continue
                raw_pos = p.text.find(raw)
                if raw_pos >= 0 and re.match(r"\s*(?:kB|MB|GB|KiB|MiB|GiB)\b", p.text[raw_pos+len(raw):], re.I):
                    continue
                try:
                    v = Version(raw.lstrip("vV"))
                    if plan.stable and (v.is_prerelease or v.is_devrelease):
                        continue
                except InvalidVersion:
                    continue
                if raw in page.title or (p.kind in {"heading", "field"} and p.label == "title"):
                    score += 4
            if plan.currency and plan.kind == "price":
                if plan.currency.casefold() not in p.text.casefold():
                    # USD and EUR symbols are unambiguous only with an explicit symbol/currency mapping.
                    symbol = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "TWD": "NT$"}.get(plan.currency)
                    if not symbol or symbol not in raw:
                        continue
            if plan.as_of:
                ds = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", p.text + " " + p.section)
                if ds and min(ds) > plan.as_of:
                    continue
            normalized=(count_answer(raw,plan.question,plan.kind,plan.operation) if plan.kind=='number'
                        else normalize(raw,plan.kind,plan.date_precision))
            out.append(Candidate(raw, normalized, page.url, p.text, p.label, p.section,
                                 plan.kind, score, {"locator": p.locator, "page_title": page.title, "structure": p.kind,
                                     'qualifiers':p.qualifiers,'field_value':p.value}))
    dedup = {}
    for c in out:
        key = (equivalence(c.answer), c.source)
        if key not in dedup or c.score > dedup[key].score:
            dedup[key] = c
    return list(dedup.values())


def rank(candidates, plan):
    by_value = {}
    for c in candidates:
        by_value.setdefault(equivalence(c.answer), set()).add(c.source)
    for c in candidates:
        # Same-site duplicates are not independent corroboration.
        hosts = {urlsplit(u).hostname for u in by_value[equivalence(c.answer)]}
        c.signals["agreement_domains"] = len(hosts)
        c.score += min(1.0, (len(hosts)-1) * 0.4)
    candidates.sort(key=lambda c: c.score, reverse=True)
    if candidates and plan.kind == "version" and plan.latest:
        top_score = candidates[0].score
        strong = [c for c in candidates if c.score >= top_score - 1.0]
        if strong:
            strong.sort(key=lambda c: Version(c.answer), reverse=True)
            best = strong[0]
            candidates.remove(best)
            candidates.insert(0, best)
    return candidates


def verify(c: Candidate, plan: Plan, pages):
    if getattr(plan,'temporal_issue',''):return False
    bound=bind(c,pages)
    if bound is None:return False
    page,fact=bound
    # Use only actual source context, including for legacy candidates that
    # omitted scope. Never let a blank candidate scope bypass a source year.
    c=replace(c,evidence=fact.text,label=fact.label,section=fact.section)
    if 'literal_spans' in c.signals:
        values = literal_members(plan.question, c.signals['literal_spans'], excerpt(plan,fact)[0], plan.kind, plan.operation)
        if not values or c.raw != join_members(values) or c.answer != c.raw:
            return False
        signals = {key:value for key,value in c.signals.items() if key != 'literal_spans'}
        # Every member still passes ordinary source binding, table, time and
        # direction checks. Whole-question semantics is checked afterwards.
        return all(verify(replace(c, raw=value, answer=value, signals=signals), plan, pages) for value in values)
    if not c.raw or not literal_span(c.raw,c.evidence,plan.kind):
        return False
    context = c.evidence + " " + c.section
    counting=count_request(plan.question,plan.kind,plan.operation)
    cardinal=cardinal_integer(c.raw) if counting else None
    if counting and c.answer!=(str(cardinal) if cardinal is not None else normalize(c.raw,plan.kind,plan.date_precision)):return False
    if counting and fact.qualifiers.get('source_continues') and re.fullmatch(SOURCE_NUMBER,c.raw):
        source=clean(fact.value or fact.text)
        if source.endswith(c.raw) and not literal_span(c.raw,source[:-len(c.raw)],plan.kind):return False
    if cardinal is not None:
        if not cardinal_licensed(c.raw,fact.text,fact.qualifiers.get('source_continues',False)) or c.answer!=str(cardinal):return False
        if fact.value and not cardinal_licensed(c.raw,fact.value,fact.qualifiers.get('source_continues',False)):return False
    if not eligible(plan,page,fact) or not table_supported(plan,page,fact,c.raw):return False
    if not complete_license(plan,page,fact,c.raw) or not complete_license(plan,page,fact,c.answer):return False
    if not direction_supported(plan,fact,c.raw):return False
    if not line_supported(plan,fact,c.raw):return False
    if not event_year_supported(plan,page,fact,c.raw):return False
    if not population_role_supported(plan,fact,c.raw):return False
    if fact.kind in {'json','jsonld','embedded'} and fact.value and not explicit_field(plan,fact) and re.search(
        r'\bwho\b|\b(?:author|founder|director|president)\b',plan.question,re.I):
        partial=bool(re.search(r'\b(?:given|first name|surname|last name)\b',plan.question,re.I))
        if not (literal_span(c.raw,fact.value,plan.kind) if partial else clean(c.raw)==clean(fact.value)):return False
    qualified=fact.qualifiers
    direct_field=bool(re.search(r'\b(?:what|which)\s+(?:is|are)\b|\bvalue\s+(?:of|for)\b',plan.question,re.I))
    quoted=set(re.findall(r'[`\"]([A-Za-z][\w.-]+)[`\"]',plan.question))
    targets=re.findall(r'[`\"]?([A-Za-z][\w.-]+)[`\"]?\s+(?:(?:metadata|configuration)\s+)?(?:field|setting|parameter|key)\b',plan.question,re.I)
    targets+=re.findall(r'\b(?:field|setting|parameter|key)\s+(?:named\s+|called\s+)?[`\"]?([A-Za-z][\w.-]+)',plan.question,re.I)
    technical=[name for name in targets if '_' in name or '-' in name or re.search(r'[a-z][A-Z]',name) or name in quoted]
    if direct_field and technical and fact.kind in {'json','jsonld','embedded','field','cell','meta','xml'}:
        for target in technical:
            bindings=qualified.get('bindings',{})
            expected=[bindings[target]] if target in bindings else [value for key,value in bindings.items() if key.casefold()==target.casefold()]
            if not expected:expected=[value for key,value in bindings.items() if key_name(key)==key_name(target)]
            if not expected and key_name(re.split(r'[.\[\]/]',fact.label)[-1])==key_name(target):expected=[fact.value]
            if expected:
                expected=list(dict.fromkeys(clean(value) for value in expected))
                partial=bool(re.search(r'\b(?:first|given|surname|last name|minimum|maximum|shortest|longest)\b',plan.question,re.I))
                if len(expected)!=1 or not (literal_span(c.raw,expected[0],plan.kind) if partial else normalize(c.raw,plan.kind)==normalize(expected[0],plan.kind)):return False
    if plan.kind=='boolean' and c.raw.casefold() not in {'yes','no','true','false'}:return False
    if plan.kind in {'date','year'} and re.search(r'\bversion\b',c.label,re.I) and not re.search(r'\b(?:date|year|published|created)\b',c.label,re.I):return False
    metadata_key=re.sub(r'[^a-z0-9]','',c.label.casefold())
    requested=plan.focus or plan.question
    question_key=re.sub(r'[^a-z0-9]','',requested.casefold())
    navigation_meta=re.match(r'^(?:appleitunesapp|googleplayapp|msapplication|twitterapp|viewport|robots|generator)',metadata_key)
    if navigation_meta and metadata_key not in question_key:
        explicit_app_id=re.search(r'\bapp(?:lication)?\s*[-_ ]?\s*(?:store\s+)?(?:id|identifier)\b|itunes|google play',requested,re.I)
        explicit_other=re.search(r'\b(?:viewport|robots|generator)\b|theme color|tile color',requested,re.I)
        if not explicit_app_id and not explicit_other:return False
    if plan.kind=='number' and re.search(r'\b(?:which|what)\s+(?:PEP|RFC)\b',plan.question,re.I) and not re.fullmatch(r'\d+',c.raw):return False
    if re.search(r'\b(?:which|what)\s+(?:PEP|RFC)\b.*\bintroduced\b',plan.question,re.I):
        if not re.search(r'introduc|propos|added|first specified|originally',c.evidence,re.I):return False
    default=re.search(r'default (?:value )?(?:of|for) (?:the )?[`\x27]?([\w_]+)',plan.question,re.I)
    if default:
        signature=c.label if '(' in c.label and '=' in c.label else c.evidence if re.match(r'^[\w .]+\(',c.evidence) and '=' in c.evidence else ''
        if c.signals.get('locator','').startswith('signature'):signature=c.evidence
        if signature:
            binding=parameter_default(signature,default[1])
            if binding is None or clean(binding)!=c.raw:return False
            function=re.search(r'(?:parameter|argument) (?:in|of) [`\x27]?([\w.]+)',plan.question,re.I)
            if function and not re.search(r'\b'+re.escape(function[1].split('.')[-1])+r'\s*\(',signature,re.I):return False
        else:
            name=re.sub(r'([a-z])([A-Z])',r'\1 \2',default[1]).replace('_',' ')
            name_pattern=r'\b'+r'[\s_]*'.join(re.escape(w) for w in name.split())+r'\b'
            if c.label and not re.search(name_pattern,c.label,re.I) and clean(c.label).casefold() not in {'default','value','default value','setting','parameter'}:
                return False
            identity=page.title+' '+next((p.text for p in page.passages if p.kind=='heading'),'')
            if not re.search(name_pattern,context+' '+identity,re.I):return False
    # An index entry's topical similarity cannot establish a named API field.
    identifiers=(re.findall(r'\b[A-Za-z][A-Za-z0-9]*[_-][A-Za-z0-9_-]+\b',plan.question)
        if re.search(r'\bfield\b|\bparameter\b|\bsetting\b|\bkey\b|\bfunction\b|\bmodule\b',plan.question,re.I) else [])
    if identifiers:
        cached=getattr(page,'_lexical_cache',None)
        if not cached or cached[0]!=len(page.passages):
            cached=(len(page.passages),' '.join(p.text for p in page.passages).casefold())
            page._lexical_cache=cached
        for identifier in identifiers:
            if identifier.casefold() not in cached[1] and identifier.replace('_',' ').replace('-',' ').casefold() not in cached[1]:
                return False
            own_context=context+' '+c.label+' '+page.title
            forms=(identifier.casefold(),identifier.replace('_',' ').replace('-',' ').casefold())
            if not any(form in own_context.casefold() for form in forms):
                # A document's own title may identify the specification while a
                # separate definition heading names its field. An index/history
                # mention cannot use this exception: both title and path must
                # identify the exact standalone document being returned.
                spec=re.search(r'\b(?:which|what)\s+(PEP|RFC)\b.*\b(?:describes?|defines?|specifies?)\b',plan.question,re.I)
                identifier_title=re.search(r'\b(PEP|RFC)\s*[-:]?\s*0*(\d+)\b',page.title,re.I)
                own_spec=bool(spec and identifier_title and spec[1].casefold()==identifier_title[1].casefold()
                    and c.raw.isdigit() and int(c.raw)==int(identifier_title[2])
                    and re.search(r'/'+spec[1]+r'[-/]?0*'+str(int(c.raw))+r'(?:/|\.html|$)',urlsplit(page.url).path,re.I)
                    and fact.kind in {'heading','title'} and len(c.evidence)<300)
                definition=any(p.kind=='heading' and any(form==clean(p.label or p.text).casefold() for form in forms) for p in page.passages)
                if not own_spec or not definition:return False
    if re.search(r'\bwho\b|\b(?:author|founder|director|president|maintainer)\s+name\b',plan.question,re.I):
        if '@' in c.raw or re.match(r'https?://',c.raw) or c.raw.casefold() in {'null','none','unknown'}:
            return False
    identity_context=context+' '+page.title+' '+page.url
    document=re.search(r'\b(PEP|RFC)\s*[- ]?\s*(\d+)\b',plan.question,re.I)
    if document:
        pattern=r'\b'+document[1]+r'[- /#]*0*'+str(int(document[2]))+r'(?!\d)'
        in_index=re.search(r'\b'+document[1]+r's?\b',page.title,re.I) and re.search(r'(?<![\w.])0*'+str(int(document[2]))+r'(?![\w.])',context)
        if not re.search(pattern,identity_context,re.I) and not in_index:
            # A generic index title is not the requested document's title. A matching
            # index table row remains usable because it contains the document identifier.
            return False
    paper=re.search(r'\barxiv(?:\s+paper)?\s*[: ]\s*(\d{4}\.\d{4,5})',plan.question,re.I)
    if paper and paper[1] not in identity_context:return False
    if page.truncated and plan.kind=='version' and plan.latest:
        if plan.as_of or not re.search(r'latest|current|most recent',context,re.I):
            return False  # An incomplete history cannot establish the maximum version.
    if plan.year:
        years = calendar_years(context)
        if years and plan.year not in years:
            return False
    if plan.as_of:
        if plan.kind=='version' and qualified.get('structured'):
            if qualified.get('release_date_ambiguous') or not qualified.get('release_date') or qualified['release_date']>plan.as_of:return False
        dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", context)
        if dates and min(dates) > plan.as_of:
            return False
    if plan.versions:
        explicit = re.findall(r"\b(?:version|v|release)\s*(\d+(?:\.\d+)*)", context, re.I)
        if explicit and not any(e == v or e.startswith(v + ".") for e in explicit for v in plan.versions):
            return False
        url_versions=re.findall(r'/(?:v|version/)?(\d+\.\d+(?:\.\d+)*)(?=/|$)',urlsplit(page.url).path)
        if url_versions and not any(e==v or e.startswith(v+'.') for e in url_versions for v in plan.versions):return False
    if plan.kind in {"email", "year", "percentage", "price", "date", "measurement", "duration", "number", "time"}:
        typed=re.fullmatch(PATTERNS[plan.kind], c.raw, re.I)
        if plan.kind=='measurement':
            geo=re.fullmatch(RANGE+r'\s*('+GEO_UNIT+r')(?:\s+MSL)?',c.raw,re.I)
            geographic=bool(re.search(r'\b(?:height|elevation|altitude)\b|^how (?:high|tall)\b',plan.focus,re.I))
            if geo and geographic:typed=True
            requested=re.search(r'\bin\s+('+GEO_UNIT+r')\b',plan.question,re.I)
            if geo and requested:
                family=lambda unit:'ft' if unit.casefold() in {'ft','feet','foot'} else 'm'
                if family(geo[1])!=family(requested[1]):return False
        if plan.kind=='date' and plan.date_precision=='month':typed=typed or re.fullmatch(PATTERNS['month'],c.raw,re.I)
        numeric_price=(plan.kind=='price' and re.fullmatch(SCALAR,c.raw) and (re.search(
            r'\b(?:price|cost|amount)\s*[:=]\s*'+re.escape(c.raw)+r'(?=\s*(?:\||[}]|$))',c.evidence,re.I)
            or qualified.get('structured') and c.raw==c.signals.get('field_value') and re.search(r'\b(?:price|cost|amount)\b',c.label,re.I)))
        if numeric_price:typed=True
        when_year=plan.kind=='date' and re.search(r'\bwhen\b',plan.question,re.I) and not re.search(r'\bdate\b',plan.question,re.I) and re.fullmatch(PATTERNS['year'],c.raw) and int(c.raw)>0
        if when_year:typed=True
        if plan.kind=='number':typed=typed or cardinal is not None or re.fullmatch(PATTERNS['measurement'],c.raw,re.I) or re.fullmatch(PATTERNS['duration'],c.raw,re.I)
        if not typed:
            return False
    if plan.kind=='date':
        if plan.date_precision=='month':
            if not iso_month(c.raw) or c.answer!=normalize(c.raw,'date','month'):return False
        elif not iso_date(c.raw) and not when_year:return False
    if plan.kind=='year' and not 1<=int(c.raw)<=9999:return False
    if plan.kind == "phone":
        if not complete_phone(c.raw,c.evidence):return False
    if plan.kind=='price':
        if qualified.get('currency_ambiguous'):return False
        currency_pattern=r'(?<![A-Za-z])'+CURRENCY+r'(?![A-Za-z])'
        raw_codes=set(re.findall(currency_pattern,c.raw,re.I))
        contextual={code.upper() for code in re.findall(currency_pattern,context,re.I)}
        explicit={code.upper() for code in re.findall(r'\b(?:price[_ ]?currency|currency)\s*[:=]\s*('+CURRENCY+r')\b',context,re.I)}
        symbols=({'TWD'} if c.raw.startswith('NT$') else {'USD'} if c.raw.startswith('US$') else {'EUR'} if '€' in c.raw
            else {'GBP'} if '£' in c.raw else {'JPY','CNY'} if '¥' in c.raw else
            {'USD','CAD','AUD','HKD','SGD','NZD','MXN','BRL','TWD'} if '$' in c.raw else set())
        codes={code.upper() for code in raw_codes}
        known_currency=qualified.get('currency')
        if known_currency:
            if codes and known_currency not in codes and qualified.get('currency_distance')==0:return False
            if symbols and known_currency not in symbols and qualified.get('currency_distance')==0:return False
            explicit={known_currency}
            if not raw_codes and len(symbols)!=1:contextual={known_currency}
        if not codes:
            if len(symbols)>1:codes=(symbols & (explicit or contextual)) or symbols
            else:codes=symbols or explicit or contextual
        excluded={term.upper() for term in plan.negations}
        if plan.currency:
            if plan.currency in excluded or codes and plan.currency not in codes:return False
            if numeric_price and not codes:return False  # A bare amount cannot establish an unspecified currency.
        elif codes.intersection(excluded):return False
    if plan.stable and plan.kind == "version":
        try:
            if Version(c.answer).is_prerelease or Version(c.answer).is_devrelease:
                return False
        except InvalidVersion:
            return False
    if plan.kind == "phone" and "fax" in c.label.lower():
        return False
    return True


def conflicts(candidates):
    if len(candidates) < 2:
        return []
    top = candidates[0]
    return [{"a": top.answer, "b": c.answer, "sources": [top.source, c.source], "margin": round(top.score-c.score, 3)}
            for c in candidates[1:8] if equivalence(c.answer) != equivalence(top.answer) and abs(top.score-c.score) < 0.65]
