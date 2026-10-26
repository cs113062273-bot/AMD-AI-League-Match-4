"""Explicit population-count intent and incompatible literal roles, not semantic proof."""
import re

from .normalize import calendar_years,clean
from .cardinals import COUNT_PATTERN, count_value as cardinal_integer

_YEAR=r'(?<![\w.])\d{4}(?!\w|\.\w)'
_COUNT=r'(?<![\w.,+\-\u2212])(?:\d{1,3}(?:,\d{3})+|\d+)(?!\w|[.,]\d)'
_VALUE=r'(?:'+COUNT_PATTERN+'|'+_COUNT+r')'
_UNITS=r'(?:families|households|people|persons|residents|inhabitants|homes|percent|thousand|million|billion)'
_YEAR_REFERENCES=[
    re.compile(r'\b(?:in|during|for)\s+(?:the\s+year\s+)?(?P<year>'+_YEAR+r')(?!\s*'+_UNITS+r'\b)',re.I),
    re.compile(r'(?P<year>'+_YEAR+r')\s+(?:national\s+)?census\b',re.I),
    re.compile(r'\bcensus\s+(?:of|in|for)\s+(?P<year>'+_YEAR+r')',re.I),
    re.compile(r'\bpopulation\s*\(\s*(?P<year>'+_YEAR+r')\s*\)',re.I),
]
_POPULATION=[
    re.compile(r'\bpopulation\b\s*(?:\(\s*'+_YEAR+r'\s*\)\s*)?[:=]?\s*'
        r'(?:(?:was|is|of|numbered|reached|totalled|totaled|stood\s+at)\s+)?(?P<value>'+_VALUE+r')',re.I),
    re.compile(r'\bpopulation\s+of\s+'
        r'(?:(?!\b(?:and|but|while|whereas|was|is|were|are|has|had|have|not)\b)[^\d.!?;|,:])+?'
        r'\s+(?:was|is|numbered|reached|totalled|totaled|stood\s+at)\s+(?P<value>'+_VALUE+r')',re.I),
    re.compile(r'(?P<value>'+_VALUE+r')\s+(?:people|persons|residents|inhabitants)\b',re.I),
]
_HOUSEHOLDS=[
    re.compile(r'(?P<value>'+_VALUE+r')\s+(?:families|households)\b',re.I),
    re.compile(r'\b(?:families|households)\b\s*'
        r'(?:(?:was|were|is|are|numbered|totalled|totaled)\s+)?[:=]?\s*(?P<value>'+_VALUE+r')',re.I),
]
_BREAKS=re.compile(r'[;!?]|\.(?:\s+|$)|\b(?:but|whereas|while)\b|'
    r'(?:,\s*(?:and\s+)?|\band\s+)(?=(?:in|during|at)\s+(?:the\s+)?\d{4}\b)',re.I)


def population_request(focus):
    focus=re.sub(r',?\s+(?:not|except|excluding|rather than|other than)\s*$','',focus,flags=re.I)
    return bool(re.fullmatch(r"what(?:\s+(?:is|was)|['\u2019]s)\s+(?:the\s+)?(?:total\s+)?population|"
        r'how many\s+(?:people|persons|residents|inhabitants)(?:\s+(?:lived|resided|were there))?',
        focus.strip(),re.I))


def census_year(question):
    """One non-negated explicitly supplied census year, never a URL or guessed date."""
    question=re.sub(r'https?://\S+',' ',question)
    years=set(calendar_years(question))
    if len(years)!=1:return ''
    quoted=[m.span() for m in re.finditer(r'"[^"\r\n]*"|`[^`\r\n]*`|\u201c[^\u201d\r\n]*\u201d',question)]
    for match in re.finditer(r'\b(?:in|during|at|as of|according to|from|per)\s+(?:the\s+)?('
            +_YEAR+r')\s+(?:national\s+)?census\b',question,re.I):
        if any(start<=match.start()<end for start,end in quoted):continue
        if not re.search(r'\b(?:not|except|excluding|rather than|other than)\s*$',question[:match.start()],re.I):
            return match[1]
    return ''


def _roles(text):
    """Annotate only explicit roles; an unresolved local year stays unknown."""
    result=[];start=0
    bounds=[(m.start(),m.end()) for m in _BREAKS.finditer(text)]+[(len(text),len(text))]
    for end,next_start in bounds:
        block=text[start:end]
        dates=[match for pattern in _YEAR_REFERENCES for match in pattern.finditer(block)]
        years={match['year'] for match in dates}
        year=next(iter(years)) if len(years)==1 else ''
        for match in dates:
            a,b=match.span('year');result.append((start+a,start+b,'year',match['year']))
        for role,patterns in [('population',_POPULATION),('households',_HOUSEHOLDS)]:
            for pattern in patterns:
                for match in pattern.finditer(block):
                    a,b=match.span('value');result.append((start+a,start+b,role,year))
        start=next_start
    return result


def population_role_supported(plan,passage,answer):
    """Reject only when every occurrence has an explicitly incompatible role.

    Unknown syntax/year associations keep semantic verification. Passing this
    necessary check does not establish the answer or the subject's identity.
    Structured tables already have their separate row/column constraints.
    """
    if (not population_request(plan.focus) or plan.operation!='single' or not plan.year or plan.as_of
            or set(calendar_years(re.sub(r'https?://\S+',' ',plan.question)))!={plan.year} or passage.kind!='prose'
            or not (re.fullmatch(_COUNT,answer) or cardinal_integer(answer) is not None)):
        return True
    text=clean(passage.text)
    occurrences=[m.span() for m in re.finditer(_VALUE,text,re.I) if m[0]==answer]
    if not occurrences:return True  # Ordinary literal/type guards decide this.
    roles=_roles(text)
    for start,end in occurrences:
        matches=[(role,year) for a,b,role,year in roles if (a,b)==(start,end)]
        if not matches:return True
        if any(role=='population' and (not year or year==plan.year) for role,year in matches):return True
    return False
