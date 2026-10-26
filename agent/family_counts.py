"""Source-bound cardinality of a complete returned relationship collection."""
import json
import re

from .cardinals import count_request
from .normalize import literal_span
from .planner import tokens,STOP
from .familysearch import profile_key,published_key,PID,_dump


def requested(plan):
    return count_request(plan.question,plan.kind,plan.operation) and bool(re.search(r'\bchildren\b',plan.question,re.I))


def answer(atoms):
    if not atoms or atoms[0].role!='subject':return ''
    partners=[a.value for a in atoms if a.role=='partner']
    if len(partners)>1:return ''
    records=[];found=False
    try:
        for atom in atoms:
            if atom.role=='children':records.extend(json.loads(atom.value)['children']);found=True
    except (ValueError,TypeError,KeyError):return ''
    if not found or len(records)>128:return ''
    ids=[]
    for record in records:
        if not isinstance(record,dict) or not isinstance(record.get('identifier'),str) or not re.fullmatch(PID,record['identifier']):return ''
        if partners and (not isinstance(record.get('otherParentId'),str) or not re.fullmatch(PID,record['otherParentId'])):return ''
        ids.append(record['identifier'])
    if len(ids)!=len(set(ids)):return ''
    return str(sum(not partners or r.get('otherParentId')==partners[0] for r in records))


def _scope(plan,page,subject,partners):
    key=page.identity['person_id'];url_key=profile_key(plan.url)
    if not (literal_span(subject.qualifiers['source_fields']['name'].casefold(),plan.question.casefold())
            or url_key and url_key[1]==key or published_key(plan.url)==key):return None,False
    if (plan.year or plan.as_of or plan.versions or re.search(
        r'\b(?:grand|step|adopted|biological|surviving|living|deceased|more|fewer|difference|combined|second|first)\b',plan.question,re.I)):
        return None,True
    if not re.search(r'\b(?:how\s+many|number\s+of|count\s+of)\s+(?:total\s+)?children\b',plan.question,re.I):
        return None,True
    marker=re.search(r'\bwith\b(.+?)(?:\?|$)',plan.question,re.I)
    if not marker:
        if re.search(r'\b(?:wife|husband|spouse|partner)\b',plan.question,re.I):return None,True
        return [],True
    name=re.sub(r'^\s*(?:(?:his|her|their|the)\s+)?(?:(?:wife|husband|spouse|partner)\b\s*[,":]?\s*)?','',marker[1],flags=re.I)
    words=set(tokens(name))-STOP
    if not page.identity.get('spouses_complete'):return None,True
    gender='Female' if re.search(r'\bwife\b',marker[1],re.I) else 'Male' if re.search(r'\bhusband\b',marker[1],re.I) else ''
    matching=[p for p in partners if (not words or words.issubset(set(tokens(p.qualifiers['source_fields']['name']))))
              and (not gender or p.qualifiers['source_fields'].get('gender')==gender)]
    return [matching[0]] if len(matching)==1 else None,True


def analyze(plan,pages):
    if not requested(plan):return None,False
    candidates=[];required=False;invalid=False
    for page in pages:
        if page.identity.get('registry')!='familysearch' or page.error:continue
        subjects=[p for p in page.passages if p.qualifiers.get('familysearch_role')=='subject']
        partners=[p for p in page.passages if p.qualifiers.get('familysearch_role')=='partner']
        if len(subjects)!=1:continue
        subject=subjects[0];fields=subject.qualifiers.get('source_fields',{})
        if (published_key(page.url)!=page.identity.get('person_id')
                or subject.value!=page.identity.get('person_id') or fields.get('identifier')!=subject.value
                or subject.text!=_dump({'person':fields})
                or any(p.value!=p.qualifiers.get('source_fields',{}).get('identifier')
                       or p.text!=_dump({'person':fields,'spouse':p.qualifiers.get('source_fields',{})}) for p in partners)):
            required=True;invalid=True;continue
        selected,applicable=_scope(plan,page,subjects[0],partners)
        if not applicable:continue
        required=True
        if selected is None or page.truncated or not page.identity.get('children_complete'):
            invalid=True;continue
        chunks=[p for p in page.passages if p.qualifiers.get('familysearch_role')=='children']
        records=[];start=0;complete=True
        for p in chunks:
            q=p.qualifiers
            if (q.get('start')!=start or q.get('stop')!=start+len(q.get('records',[]))
                    or q.get('subject_id')!=page.identity['person_id']):complete=False;break
            try:
                if json.loads(p.text)!={'children':q['records']}:complete=False;break
            except (ValueError,TypeError):complete=False;break
            records.extend(q['records']);start=q['stop']
        if not chunks or not complete or start!=page.identity.get('children_length'):
            invalid=True;continue
        if selected and any(not isinstance(r.get('otherParentId'),str) or not re.fullmatch(PID,r['otherParentId']) for r in records):
            invalid=True;continue
        ids=[r['identifier'] for r in records]
        if len(ids)!=len(set(ids)) or len(ids)>128:invalid=True;continue
        count=str(sum(not selected or r.get('otherParentId')==selected[0].value for r in records))
        candidates.append((page,subjects[0],selected,chunks,records,count))
    if not required:return None,False
    if invalid or not candidates or len({c[-1] for c in candidates})!=1:return None,True
    return candidates[0],True
