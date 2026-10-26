"""Whole cutoff literals with explicit uncertainty; never silently use the current value."""
import calendar
from datetime import date
import re

_MONTHS={name.casefold():i for i in range(1,13)
    for name in (calendar.month_name[i],calendar.month_abbr[i])}
_MONTHS['sept']=9
_MONTH='(?:'+'|'.join(sorted(_MONTHS,key=len,reverse=True))+')'
_END=r'(?!\w|[./\-\u2013\u2014]\w)'
_NEXT_DATE=r'(?:\d{4}\b|\d{1,2}[./-]\d{1,2}[./-]\d{4}\b|'+_MONTH+r'\b|(?:now|today)\b)'
_TEXT=[
    re.compile(r'(?P<month>'+_MONTH+r')\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:,\s*|\s+)(?P<year>\d{4})'+_END,re.I),
    re.compile(r'(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?P<month>'+_MONTH+r')\.?\s+(?P<year>\d{4})'+_END,re.I),
    re.compile(r'(?P<month>'+_MONTH+r')\.?\s+(?P<year>\d{4})'+_END,re.I),
]


def _one(tail):
    prefix=re.match(r'\s*(?:the\s+)?(?:year\s+)?',tail,re.I)
    text=tail[prefix.end():]
    current=re.match(r'(?:now|today|currently)\b',text,re.I)
    if current:return 'CURRENT','',current[0],prefix.end()+current.end()
    for pattern in _TEXT:
        match=pattern.match(text)
        if match:
            year=int(match['year']);month=_MONTHS[match['month'].casefold()]
            try:
                day=int(match.groupdict().get('day') or calendar.monthrange(year,month)[1])
                value=date(year,month,day).isoformat()
                return value,'',match[0],prefix.end()+match.end()
            except ValueError:return '','invalid_cutoff',match[0],prefix.end()+match.end()
    match=re.match(r'\d[^\s,;!?()\[\]{}<>]*',text)
    if not match:return '','unresolved_cutoff',text[:160],len(tail)
    raw=match[0].rstrip('.')
    end=prefix.end()+match.end()
    try:
        if re.fullmatch(r'\d{4}',raw):return date(int(raw),12,31).isoformat(),'',raw,end
        iso=re.fullmatch(r'(\d{4})([./-])(\d{1,2})\2(\d{1,2})',raw)
        if iso:return date(int(iso[1]),int(iso[3]),int(iso[4])).isoformat(),'',raw,end
        month=re.fullmatch(r'(\d{4})-(\d{1,2})',raw)
        if month:
            year,num=int(month[1]),int(month[2])
            return date(year,num,calendar.monthrange(year,num)[1]).isoformat(),'',raw,end
        local=re.fullmatch(r'(\d{1,2})([./-])(\d{1,2})\2(\d{4})',raw)
        if local:
            first,second,year=int(local[1]),int(local[3]),int(local[4])
            if 1<=first<=12 and 1<=second<=12 and first!=second:
                return '','ambiguous_cutoff',raw,end
            month,day=(second,first) if first>12 or first==second else (first,second)
            return date(year,month,day).isoformat(),'',raw,end
    except ValueError:return '','invalid_cutoff',raw,end
    return '','unresolved_cutoff',raw,end


def cutoff(question,census_value=''):
    """Return (ISO date, issue, unresolved raw literals, is-current).

    Year/month cutoffs mean their last calendar day, extending the existing
    end-of-year convention. Unsupported/ambiguous requirements remain explicit.
    Named census observations are handled by the census planner instead.
    """
    question=re.sub(r'https?://\S+',' ',question)
    quoted=[m.span() for m in re.finditer(r'"[^"\r\n]*"|`[^`\r\n]*`|\u201c[^\u201d\r\n]*\u201d',question)]
    values=[];issues=[];raws=[]
    for marker in re.finditer(r'\bas\s+of\b',question,re.I):
        if any(a<=marker.start()<b for a,b in quoted):continue
        if re.search(r'\b(?:not|except(?:\s+for)?|excluding|rather than|other than)\s*$',question[:marker.start()],re.I):continue
        tail=question[marker.end():]
        value,issue,raw,end=_one(tail)
        if re.fullmatch(r'\d{4}',raw) and re.match(r'\s+(?:national\s+)?census\b',tail[end:],re.I):
            if census_value==raw:continue
            issue='ambiguous_cutoff';value=''
        if re.match(r'\s*(?:,\s*)?(?:(?:to|through|until|and|or)\s+|[-\u2013\u2014]\s*)'+_NEXT_DATE,tail[end:],re.I):
            issue='ambiguous_cutoff';value=''
            raw=tail.strip()[:160]
        if re.match(r'\s+(?:at\s+)?(?:\d{1,2}:\d{2}|\d{1,2}\s*[ap]m\b|noon\b|midnight\b)',tail[end:],re.I):
            # Date-only history cannot enforce an hour-level cutoff.
            issue='unresolved_cutoff';value=''
            raw=tail.strip()[:160]
        raws.append(raw)
        if issue:issues.append(issue)
        elif value:values.append(value)
    if issues:return '',issues[0],raws,False
    if len(set(values))>1:return '','ambiguous_cutoff',raws,False
    if values and values[0]=='CURRENT':return '','',[],True
    return (values[0] if values else ''),'',[],False
