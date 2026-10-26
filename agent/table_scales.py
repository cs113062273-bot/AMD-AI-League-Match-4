"""Exact counts from an explicit column scale and its actual scalar cell.

No source text is rewritten. This module describes literal premises for the
proof executor; it never licenses a model's arbitrary computed reply.
"""
from decimal import Decimal, InvalidOperation, localcontext
from dataclasses import replace
import re

from .cardinals import count_request
from .evidence import eligible, field_words, row_supported, table_supported
from .normalize import clean, literal_span
from .number_atoms import SCALES

_SCALE=r'(?:thousand|million|billion|trillion)s?'
_HEADER=re.compile(r'(.+?)(?:\s*\(\s*(?:in\s+)?('+_SCALE+r')\s*\)|\s+in\s+('+_SCALE+r'))',re.I)
_HINT=re.compile(r'\b'+_SCALE+r'\b',re.I)
_DECIMAL=re.compile(r'(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?|\.[0-9]+')
_GLOBAL=re.compile(r'\b(?:all\s+)?(?:figures|values|counts|numbers)\s+(?:are\s+)?(?:(?:shown|expressed)\s+)?in\s+('+_SCALE+r')\b',re.I)
_OUTPUT=re.compile(r'\b(?:in(?:\s+units\s+of)?|how\s+many)\s+'+_SCALE+r'\b|\(\s*(?:in\s+)?'+_SCALE+r'\s*\)\s*\??$',re.I)


def header(label):
    match=_HEADER.fullmatch(clean(label))
    return (match[1].strip(),(match[2] or match[3]).lower().rstrip('s')) if match else None


def compute(label, raw):
    """A bounded, exact nonnegative integral result; commas use grouped syntax."""
    unit=header(label)
    if not unit or len(raw)>50 or not _DECIMAL.fullmatch(raw):return ''
    try:
        with localcontext() as context:
            context.prec=80
            value=Decimal(raw.replace(',',''))*SCALES[unit[1]]
            if value<0 or value>=10**15 or value!=value.to_integral_value():return ''
            return str(int(value))
    except (InvalidOperation,ValueError):return ''


def _field_matches(plan, value, excluded=()):
    words=field_words(value)-{'total','count','number'}
    requested=re.search(r'\b(?:how\s+many|number\s+of|count\s+of)\s+(.+?)'
        r'(?=\s+(?:does|do|did|is|are|was|were|has|have|in|at|of|for|from|on)\b|[?]|$)',plan.question,re.I)
    query=field_words(requested[1]) if requested else field_words(plan.question)-set(excluded)
    query.update(re.findall(r'\b[0-9]{4}\b',plan.question))
    # These are count-field synonyms, not entity or answer lookups.
    population={'population','resident','inhabitant'}
    words={'population' if w in population else w for w in words}
    query={'population' if w in population else w for w in query}
    return bool(words) and any(re.search(r'[A-Za-z]',w) for w in words) and words.issubset(query)


def identities(plan, passage, excluded=()):
    """Actual nonnumeric row identifiers named literally in the question."""
    found=[]
    for i,(label,value) in enumerate(zip(passage.qualifiers.get('columns',[]),passage.qualifiers.get('cells',[]))):
        if i in excluded or field_words(label).intersection({'year','version','release','date','day','time'}):continue
        if (re.search(r'[A-Za-z]',value) and field_words(value)
                and literal_span(value.casefold(),plan.question.casefold())):found.append(value)
    return found


def _columns(plan, passage):
    found=[]
    entity_words=set().union(*(field_words(v) for v in identities(plan,passage)))
    for i,label in enumerate(passage.qualifiers.get('columns',[])):
        parsed=header(label)
        # An explicit but ambiguous scale cannot become a bare scalar fallback.
        hinted=bool(_HINT.search(label))
        base=parsed[0] if parsed else re.split(r'\s*\(|\s+in\s+',label,maxsplit=1,flags=re.I)[0] if hinted else label
        if _field_matches(plan,base,entity_words):found.append((i,label,parsed,hinted))
    return found


def _bindings(plan,page,passage,excluded):
    """Bind all question-named cells at this table's actual column indices."""
    constraints={}
    for row in page.passages:
        if row.kind!='table' or row.qualifiers.get('table')!=passage.qualifiers.get('table'):continue
        names=set(identities(plan,row,excluded))
        for i,value in enumerate(row.qualifiers.get('cells',[])):
            if value in names:constraints.setdefault(i,set()).add(value.casefold())
    return constraints


def analyze(plan,pages):
    """Return a unique complete scaled fact and whether a derivation is required.

Facts include eligible unscaled rows too, so disagreeing ordinary values on
other retrieved pages cannot silently be ignored in favor of a scaled row.
"""
    if (not count_request(plan.question,plan.kind,plan.operation) or plan.as_of
            or _OUTPUT.search(plan.question)):return None,False
    selected=None;required=False;invalid=False;answers=set();bindings={}
    for page in pages:
        if page.error:continue
        for passage in page.passages:
            if passage.kind!='table' or not eligible(plan,page,passage):continue
            columns=_columns(plan,passage)
            indices=[i for i,label,parsed,hinted in columns]
            if not columns or not identities(plan,passage,indices):continue
            key=(id(page),passage.qualifiers.get('table'),tuple(indices))
            if key not in bindings:bindings[key]=_bindings(plan,page,passage,indices)
            constraints=bindings[key];cells=passage.qualifiers.get('cells',[])
            if any(len(v)!=1 for v in constraints.values()):
                required |= any(hinted for i,label,parsed,hinted in columns)
                invalid=True
                continue
            if any(i>=len(cells) or cells[i].casefold() not in v for i,v in constraints.items()):continue
            if not row_supported(plan,page,passage,indices):continue
            for i,label,parsed,hinted in columns:
                cells=passage.qualifiers.get('cells',[])
                raw=cells[i] if i<len(cells) else ''
                # table_supported also checks observation years and versions.
                focused=replace(plan,focus=parsed[0] if parsed else label)
                if raw and not table_supported(focused,page,passage,raw):continue
                required |= hinted
                complete=(len(cells)==len(passage.qualifiers['columns'])
                    and type(passage.qualifiers.get('table')) is int and type(passage.qualifiers.get('row')) is int
                    and bool(passage.locator) and not page.truncated and not passage.qualifiers.get('source_continues')
                    and literal_span(label+': '+raw,passage.text) and len(passage.text)<=6000
                    and not passage.qualifiers.get('caption_continues'))
                declarations={m[1].lower().rstrip('s') for m in _GLOBAL.finditer(
                    passage.section+' '+passage.qualifiers.get('table_caption',''))}
                if parsed and declarations-{parsed[1]}:complete=False
                value=compute(label,raw) if parsed else raw if re.fullmatch(r'0|[1-9][0-9]{0,14}',raw) and not hinted else ''
                if not complete:value=''
                invalid |= not bool(value)
                if value:answers.add(value)
                if parsed and selected is None:selected=(page,passage,i,label,raw,value,True)
    if not required:return None,False
    if invalid or len(answers)!=1:return None,True
    return selected,True
