"""Recover a complete literal license field from a selected expression operand.

This recognizes bounded SPDX-shaped syntax, not identifier-list membership or
legal equivalence. It never changes operator order, spelling, case or grouping.
"""
from functools import lru_cache
import re

from .normalize import clean, literal_span
from .qualifiers import key_name

_REF=r'(?:DocumentRef-[A-Za-z0-9.-]+:)?LicenseRef-[A-Za-z0-9.-]+'
_ID=r'[A-Za-z0-9.-]+'
_TOKEN=re.compile(_REF+r'|'+_ID+r'\+?|[()]')
_OPERATORS={'AND','OR','WITH'}
_FIELDS={'license','licence','licenseexpression','licenceexpression','spdxlicenseexpression',
    'spdxexpression','licensedeclared','licenseconcluded'}


def whole_question(plan):
    if plan.operation!='single' or plan.cardinality!=1 or plan.choices:return False
    focus=plan.focus or plan.question
    if not (plan.kind=='license' or plan.kind=='text' and re.search(r'\bspdx\s+(?:license\s+)?expression\b',focus,re.I)):return False
    if not re.search(r'licen[sc]e|\bspdx\b',focus,re.I):return False
    question=re.sub(r'https?://\S+',' ',plan.question)
    question=re.sub(r'\b(?:crate|package|project|repository|module)\s+(?:(?:named|called)\s+)?[`"\x27]?'
        r'[\w.-]+(?:/[\w.-]+)?',' ',question,flags=re.I)
    if re.match(r'\s*(?:is|are|was|were|does|do|did|can|could|may|must|has|have|who|when|where|why|how)\b',question,re.I):return False
    if re.search(r'\b(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+licen[sc]es?\b',question,re.I):return False
    return not re.search(r'\b(?:options?|choices?|alternatives?|exceptions?|identifiers?|operators?|clauses?|'
        r'first|last|only|excluding|except|without|apart|parts?|components?|whether|either|both)\b|\bwhich of\b',question,re.I)


@lru_cache(maxsize=128)
def expression_nodes(value):
    """Return literal operand/subexpression spans, or None for unsupported syntax.

    Known license/exception catalogs are deliberately not embedded. This parser
    checks structure solely to preserve an already fetched field's full value.
    """
    if not isinstance(value,str) or not 0<len(value)<=2000:return None
    matches=list(_TOKEN.finditer(value))
    if not matches or len(matches)>256:return None
    end=0
    for token in matches:
        if value[end:token.start()].strip():return None
        if token[0] in {'AND','OR'}:
            left=value[token.start()-1] if token.start() else ''
            right=value[token.end()] if token.end()<len(value) else ''
            if not (left.isspace() or left==')') or not (right.isspace() or right=='('):return None
        end=token.end()
    if value[end:].strip():return None
    index=0;nodes=set()

    def peek():return matches[index][0] if index<len(matches) else ''

    def identifier(token,exception=False):
        text=token[0]
        if text in _OPERATORS or text in {'(',')','NONE','NOASSERTION'}:return False
        if text.startswith(('LicenseRef-','DocumentRef-')):
            return not exception and bool(re.fullmatch(_REF,text))
        return bool(re.fullmatch(_ID+(r'' if exception else r'\+?'),text))

    def primary(depth):
        nonlocal index
        if depth>16 or index>=len(matches):raise ValueError('expression bound')
        token=matches[index];index+=1
        if token[0]=='(':
            start,_=either(depth+1)
            if peek()!=')':raise ValueError('unclosed group')
            finish=matches[index].end();index+=1
            nodes.add(value[token.start():finish])
            return token.start(),finish
        if not identifier(token):raise ValueError('operand expected')
        start,finish=token.span();nodes.add(value[start:finish])
        if token[0].endswith('+'):
            nodes.add(value[start:finish-1])
        if peek()=='WITH':
            operator=matches[index];index+=1
            if index>=len(matches) or not identifier(matches[index],exception=True):raise ValueError('exception expected')
            right=matches[index];index+=1
            if not value[finish:operator.start()].isspace() or not value[operator.end():right.start()].isspace():raise ValueError('WITH spacing')
            finish=right.end();nodes.add(value[start:finish])
        return start,finish

    def conjunction(depth):
        nonlocal index
        start,finish=primary(depth)
        while peek()=='AND':
            index+=1;_,finish=primary(depth);nodes.add(value[start:finish])
        return start,finish

    def either(depth):
        nonlocal index
        start,finish=conjunction(depth)
        while peek()=='OR':
            index+=1;_,finish=conjunction(depth);nodes.add(value[start:finish])
        return start,finish

    try:either(0)
    except ValueError:return None
    if index!=len(matches):return None
    return frozenset(nodes)


def _license_label(label):
    leaf=re.split(r'[./]',label)[-1]
    return key_name(leaf) in _FIELDS


def _values(plan,passage):
    if not whole_question(plan):return set()
    values=[]
    labels=passage.qualifiers.get('columns',[]);cells=passage.qualifiers.get('cells',[])
    row_values=[v for label,v in zip(labels,cells) if _license_label(label)] if len(labels)==len(cells) else []
    if passage.kind in {'field','cell','json','jsonld','embedded','xml','meta'} and _license_label(passage.label):
        values=row_values if passage.kind=='cell' and len(row_values)>1 else [passage.value]
    elif passage.kind=='table':
        values=row_values
    return {clean(v) for v in values if isinstance(v,str) and v}


def declared(plan,passage):
    values=_values(plan,passage)
    if len(values)!=1:return ''
    value=next(iter(values))
    return value if expression_nodes(value) and literal_span(value,passage.text) else ''


def _targets(plan,page,passage):
    own=_values(plan,passage)
    if own:return [(passage,own)]
    if not whole_question(plan) or passage.kind not in {'json','jsonld','embedded'} or not passage.locator:return []
    # Flattened JSON repeats its parent record beside each scalar. Recover only
    # actual sibling fields at that same path, never arbitrary nearby records.
    parent=passage.locator.rpartition('.')[0]
    cached=getattr(page,'_license_field_index',None)
    if not cached or cached[0]!=len(page.passages):
        index={}
        for p in page.passages:
            if p.kind in {'json','jsonld','embedded'} and p.locator and _license_label(p.label):
                index.setdefault((p.kind,p.locator.rpartition('.')[0]),[]).append(p)
        cached=(len(page.passages),index);page._license_field_index=cached
    return [(p,_values(plan,p)) for p in cached[1].get((passage.kind,parent),[])]


def project(plan,page,passage,answer,visible=None):
    targets=_targets(plan,page,passage)
    values=set().union(*(v for p,v in targets)) if targets else set()
    if len(values)!=1:return None
    value=next(iter(values));nodes=expression_nodes(value)
    operand=bool(nodes) and (answer in nodes or any(
        bool(re.fullmatch(_REF+'|'+_ID+r'\+?',node)) and node.startswith(answer)
        and literal_span(answer,node) for node in nodes))
    if (not operand or answer in _OPERATORS or len(value)>350
            or not literal_span(value,passage.text[:1100] if visible is None else visible)):return None
    matching=[p for p,v in targets if value in v and declared(plan,p)==value]
    return (matching[0],value) if matching else None


def complete(plan,page,passage,answer):
    targets=_targets(plan,page,passage)
    values=set().union(*(v for p,v in targets)) if targets else set()
    if len(values)>1 and any(expression_nodes(v) for v in values):return False
    value=next(iter(values)) if len(values)==1 and expression_nodes(next(iter(values))) else ''
    return not value or clean(answer)==value
