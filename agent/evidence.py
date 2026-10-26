"""Evidence eligibility and table binding, using actual parsed source fields."""
import re
from .normalize import clean, literal_span, calendar_years
from .planner import tokens, STOP
from .qualifiers import key_name
from .registry_history import metadata_supported
from .github_history import supported as github_supported

_BIRTH_KEYS={'birthdate','dateofbirth','birthyear','yearofbirth','born','dob'}


def explicit_field(plan, passage):
    leaf=re.split(r'[./]',passage.locator)[-1]
    query=plan.question
    if not re.search(r'\b(?:field|key|setting|parameter|default)\b',query,re.I):return False
    return bool(leaf and (re.search(r'(?<!\w)'+re.escape(leaf)+r'(?!\w)',query,re.I)
        or any(key_name(value)==key_name(leaf) for value in re.findall(r'[`"\x27]([^`"\x27]+)[`"\x27]',query))))


def eligible(plan, page, passage):
    if not github_supported(plan,page,passage):return False
    if not metadata_supported(plan,page,passage):return False
    if (passage.qualifiers.get('named_field_group') and dated_event(plan)=='birth'
            and not any(key_name(key) in _BIRTH_KEYS for key in passage.qualifiers.get('bindings',{}))):
        # Preserve ordinary biography passages when a new group has no typed
        # birth date and cannot itself supply this question's witness.
        return False
    if first_line_requested(plan):
        if passage.qualifiers.get('source_line')!=1 or not passage.qualifiers.get('complete_line'):return False
    elif passage.kind=='line':return False
    if not record_supported(plan,page,passage):return False
    if passage.kind not in {'json','jsonld','embedded'}:return True
    leaf=re.split(r'[./]',passage.locator)[-1]
    technical=explicit_field(plan,passage)
    schema_requested=bool(re.search(r'json.?ld|\bschema\b|@(?:type|context|id)\b',plan.question,re.I))
    if leaf in {'@type','@context','@id'} and not schema_requested:return False
    if passage.qualifiers.get('value_type') in {'boolean','null'} and not technical and (
        re.search(r'\bwho\b|\b(?:author|founder|director|president)\b',plan.question,re.I)):
        return False
    if passage.kind=='jsonld' and not technical and not schema_requested:
        scaffold={'WebPage','WebSite','BreadcrumbList','ListItem','SearchAction','SiteNavigationElement'}
        types=set(passage.qualifiers.get('schema_types',[]))
        if scaffold.intersection(types):
            # Page metadata can contain genuine authors/titles. Keep requested
            # content fields, while rejecting navigation/schema/config records.
            content_fields={'author':r'\bwho\b|\bauthor\b|\bwrote\b',
                'name':r'\btitle\b|\b(?:page|website) name\b',
                'headline':r'\btitle\b|\bheadline\b',
                'description':r'\bdescription\b|\bsummary\b',
                'datePublished':r'\bpublished\b|\bpublication\b',
                'dateModified':r'\bmodified\b|\bupdated\b'}
            pattern=content_fields.get(leaf)
            if not types.issubset({'WebPage','WebSite'}) or not pattern or not re.search(pattern,plan.question,re.I):return False
    if passage.kind=='embedded' and not technical:
        identities=passage.qualifiers.get('identity',[])
        query=set(tokens(plan.question))
        if not any(set(tokens(identity))-STOP and (set(tokens(identity))-STOP).issubset(query) for identity in identities):
            return False
    return True


def _words(value):
    words=set(tokens(value))-STOP-{'value','field','setting','parameter','default'}
    return {word[:-3]+'y' if word.endswith('ies') else word[:-1] if word.endswith('s') and len(word)>3 else word
            for word in words}


def field_words(value):
    aliases={'hour':'time','opening':'time','closing':'time','date':'day'}
    return {aliases.get(word,word) for word in _words(value)-{'during'}}


def first_line_requested(plan):
    return bool(re.search(r'\bfirst line\b',plan.question,re.I) and re.search(
        r'\b(?:song|poem|lyrics?|text|file|document|passage|message|script|code|report|novel|book|speech|readme)\b',plan.question,re.I))


def line_supported(plan,passage,answer):
    return not first_line_requested(plan) or (passage.qualifiers.get('source_line')==1
        and passage.qualifiers.get('complete_line') and clean(answer)==clean(passage.text))


_EVENTS={
    'marriage':r'\b(?:marri(?:ed|es|age|ages)|weddings?|wed)\b',
    'birth':r'\b(?:born|births?)\b',
    'death':r'\b(?:died|deaths?)\b',
    'foundation':r'\b(?:founded|founding|established|establishment|incorporated|incorporation)\b',
    'release':r'\b(?:released|releases?|launched|launch|published|publication)\b',
    'award':r'\b(?:won|wins?|winners?|awarded|awards?|prizes?|medals?|troph(?:y|ies))\b',
}
_YEAR=r'(?<![\w.])\d{4}(?!\w|\.\w)'


def dated_event(plan):
    """An explicit calendar-year constraint on a recognized event, not an as-of."""
    if not plan.year or plan.as_of:return ''
    # Multiple event meanings or distinct years require semantic temporal
    # reasoning; do not guess which one the plan's first year belongs to.
    years=set(re.findall(_YEAR,plan.question))
    if years!={plan.year}:return ''
    kinds=[kind for kind,pattern in _EVENTS.items() if re.search(pattern,plan.question,re.I)]
    return kinds[0] if len(kinds)==1 else ''


def event_year_supported(plan,page,passage,answer):
    """Necessary local witness for a dated event; full identity still needs semantics."""
    requested=dated_event(plan)
    if not requested:return True
    text=clean(passage.text);answer=clean(answer)
    heading=passage.section+' '+passage.label
    answers=list(re.finditer(re.escape(answer),text,re.I)) if answer else []
    if not answers:return False
    if requested=='birth' and passage.qualifiers.get('structured'):
        dates=[clean(value) for key,value in passage.qualifiers.get('bindings',{}).items() if key_name(key) in _BIRTH_KEYS]
        if dates:
            # Explicit source fields take precedence over a nearby update year.
            # The bound date must also be visible in this literal passage.
            return all(set(calendar_years(value))=={plan.year} and literal_span(value,text) for value in dates)
        if passage.qualifiers.get('named_field_group'):
            # Country/place of birth and an update year are not a birth date.
            return False
        if passage.kind in {'json','jsonld','embedded'}:
            # The displayed JSON context may also mention a differently named
            # ancestor. Bindings already drop that ancestor at an identity
            # boundary; do not re-import its birth through the prose fallback.
            local=[f'{key}: {value}' for key,value in passage.qualifiers.get('bindings',{}).items()
                   if clean(value) and literal_span(clean(value),text)]
            if passage.value and literal_span(passage.value,text):local.append(passage.value)
            text=clean(' | '.join(local))
            heading=passage.label
            answers=list(re.finditer(re.escape(answer),text,re.I)) if answer else []
            if not answers:return False
    cuts=[m for m in re.finditer(r'[.!?;](?:\s+|$)|\b(?:while|whereas|but)\b',text,re.I)
        if not any(m.start()<a.end() and a.start()<m.end() for a in answers)]
    blocks=[];start=0
    for cut in cuts:
        blocks.append((start,cut.start()));start=cut.end()
    blocks.append((start,len(text)))
    scoped=bool(re.search(_EVENTS[requested],heading,re.I))
    structured=passage.kind in {'table','cell','field','record','json','jsonld','xml','embedded'}
    for i,(start,end) in enumerate(blocks):
        if not any(start<=a.start() and a.end()<=end for a in answers):continue
        block=text[start:end]
        events=[(kind,m) for kind,pattern in _EVENTS.items() for m in re.finditer(pattern,block,re.I)]
        years=list(re.finditer(_YEAR,block))
        if not events and structured:
            scoped=scoped or bool(re.search(_EVENTS[requested],page.title,re.I))
        # A source record can declare its event/year in the heading. A generic
        # page title or an unrelated dated paragraph cannot supply that year.
        if scoped and (structured or any(kind==requested for kind,m in events)):
            heading_years=set(re.findall(_YEAR,heading))
            if not years and heading_years=={plan.year}:return True
        for year in years:
            if year[0]!=plan.year:continue
            if events:
                gap=lambda event:max(event[1].start()-year.end(),year.start()-event[1].end(),0)
                distance=min(map(gap,events))
                if {kind for kind,m in events if gap((kind,m))==distance}=={requested}:return True
            elif scoped and structured:return True
        # Explicit adjacent coreference can state the date after the named
        # event ("They married ... . Their wedding took place in 1998.").
        # Keep this within the same parsed passage and the very next sentence.
        if not years and any(kind==requested for kind,m in events) and i+1<len(blocks):
            following=text[slice(*blocks[i+1])].strip()
            if re.match(r'^(?:their|the|this|that)\s+(?:'+_EVENTS[requested]+r')',following,re.I):
                following_years=set(re.findall(_YEAR,following))
                if following_years=={plan.year}:return True
    return False


_DIRECTION=r'\b(north|south|east|west)(?:ern|erly)?\b'
_BOUNDARY=r'\b(?:bound(?:ary|aries|ed|s)?|border(?:s|ed|ing)?|sides?|edges?)\b'


def boundary_direction(plan):
    """Only explicit single-cardinal boundary requests; leave other meanings alone."""
    directions=set(re.findall(_DIRECTION,plan.question,re.I))
    directions={direction.casefold() for direction in directions}
    if len(directions)!=1:return ''
    cardinal=r'(?:north|south|east|west)(?:ern|erly)?'
    relative='|'.join([r'\b'+cardinal+r'\s+(?:boundar(?:y|ies)|borders?|edges?|sides?)\b',
        r'\bborders?\s+(?:the\s+)?'+cardinal+r'\s+of\b',
        _BOUNDARY+r'[^?;.]{0,45}?\b(?:on|to)\s+(?:the\s+)?'+cardinal+r'\b'])
    return next(iter(directions)) if re.search(relative,plan.question,re.I) else ''


def direction_supported(plan,passage,answer):
    """Require a requested boundary direction at the selected name, not merely nearby.

    This is a necessary literal relation check. Entity identity, negation and the
    full meaning still need the independent semantic verifier.
    """
    requested=boundary_direction(plan)
    if not requested:return True
    text=clean(passage.text);answer=clean(answer)
    spans=list(re.finditer(re.escape(answer),text,re.I)) if answer else []
    if not spans:return False
    mentions=[m for m in re.finditer(_DIRECTION,text,re.I)
        if not any(m.start()<span.end() and span.start()<m.end() for span in spans)]
    heading=passage.section+' '+passage.label
    heading_directions={m.casefold() for m in re.findall(_DIRECTION,heading,re.I)}
    heading_support=bool(re.search(_BOUNDARY,heading,re.I) and heading_directions=={requested})
    if not mentions:return heading_support
    cuts=list(re.finditer(r'[;.!?|]|\b(?:while|whereas|but)\b|,\s*(?:and|with)\b',text,re.I))
    bound=set()
    for span in spans:
        start=max((cut.end() for cut in cuts if cut.end()<=span.start()),default=0)
        end=min((cut.start() for cut in cuts if cut.start()>=span.end()),default=len(text))
        local=[m for m in mentions if start<=m.start() and m.end()<=end]
        if not local or not (heading_support or re.search(_BOUNDARY,text[start:end],re.I)):continue
        gap=lambda m:max(m.start()-span.end(),span.start()-m.end(),0)
        distance=min(map(gap,local))
        bound.update(m[1].casefold() for m in local if gap(m)==distance)
    return bound=={requested}


def record_supported(plan,page,passage):
    """Reject an explicitly different named award scope, not absent synonyms."""
    if passage.kind!='record' or plan.kind not in {'year','date'}:return True
    requested=re.search(r'\b(?:receiv(?:e|ed)|wins?|won|earn(?:ed)?|awarded)\s+(?:an?\s+|the\s+)?'
        r'([^?;:.]{1,120}?\b(?:awards?|prizes?|medals?|troph(?:y|ies)|fellowships?))\b',plan.question,re.I)
    if not requested:return True
    markers={'award','awardee','prize','medal','trophy','fellowship'}
    generic=markers|{'recipient','winner','honoree','all','list','record','nomination','annual','honorary','first','second','his','her'}
    target=_words(requested[1])-generic
    if not target:return True
    for heading in [*reversed(passage.section.split(' > ')),page.title]:
        words=_words(heading);named=words-generic
        if words.intersection(markers) and named:
            return bool(target.intersection(named))
    return True


def row_supported(plan,page,passage,excluded=()):
    facts=passage.qualifiers
    headers,cells=facts.get('columns'),facts.get('cells')
    if not headers or not cells:return True
    # Field names, not physical column positions, declare the row identifiers.
    identity={'name','model','product','plan','tier','material','code','id','region','location',
              'vendor','merchant','category','type','item','service','department'}
    cache_key=(len(page.passages),plan.question,facts.get('table'),tuple(excluded))
    cached=getattr(page,'_row_query_bindings',None)
    if not cached or cached[0]!=cache_key:
        constraints={};sections=set()
        for row in page.passages:
            if row.kind!='table':continue
            if row.section:sections.add(row.section)
            if row.qualifiers.get('table')!=facts.get('table'):continue
            for i,(label,value) in enumerate(zip(row.qualifiers.get('columns',[]),row.qualifiers.get('cells',[]))):
                if i not in excluded and field_words(label).intersection(identity) and len(value)>1 and literal_span(value.casefold(),plan.question.casefold()):
                    constraints.setdefault(i,set()).add(value)
        requested_sections=set()
        if len(sections)>1:
            common=set.intersection(*(_words(section) for section in sections))
            requested_sections={section for section in sections if (_words(section)-common).intersection(_words(plan.question))}
        cached=(cache_key,constraints,requested_sections);page._row_query_bindings=cached
    for i,values in cached[1].items():
        if len(values)!=1 or i>=len(cells) or cells[i] not in values:return False
    if len(cached[2])==1 and passage.section not in cached[2]:return False
    if len(plan.versions)==1:
        for label,value in zip(headers,cells):
            if re.search(r'\b(?:version|release)\b',label,re.I):
                actual=clean(value).lstrip('vV')
                if not (actual==plan.versions[0] or actual.startswith(plan.versions[0]+'.')):return False
    return True


def table_supported(plan,page,passage,answer):
    facts=passage.qualifiers
    headers,cells=facts.get('columns'),facts.get('cells')
    if not headers or not cells:return True
    focus=field_words(plan.focus)
    matching=[i for i,label in enumerate(headers) if field_words(label).intersection(focus)]
    if plan.year and not plan.as_of and set(calendar_years(plan.question))=={plan.year}:
        # A year elsewhere in a row/heading does not date every field in it.
        # Only explicit observation-year columns bind an otherwise undated
        # field; birth/update/fiscal years have different meanings.
        row_years=[value for label,value in zip(headers,cells) if key_name(label) in
            {'year','censusyear','observationyear','reportingyear','calendaryear'}]
        if any(set(calendar_years(value))!={plan.year} for value in row_years):return False
        dated={i:set(calendar_years(headers[i])) for i in matching}
        if any(dated.values()):
            matching=[i for i,years in dated.items() if years=={plan.year} or not years and row_years]
            if not matching:return False
        elif not matching:
            # Some wide tables use bare years as column headers, declaring
            # the field in a row label or caption instead.
            years=[i for i,label in enumerate(headers) if re.fullmatch(_YEAR,clean(label))]
            if years:
                matching=[i for i in years if clean(headers[i])==plan.year]
                if not matching:return False
    if matching and not any(i<len(cells) and literal_span(answer,cells[i],plan.kind) for i in matching):return False
    return row_supported(plan,page,passage,matching)
