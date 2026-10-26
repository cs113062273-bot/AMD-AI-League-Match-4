"""Bounded derived answers with literal premises and executable operations.

This first implementation supports table projection, versioned scalar comparison
and explicit category/class/tier mappings. It does not evaluate arbitrary code,
invent conversions, or treat a loose keyword match as semantic verification.
"""
from dataclasses import dataclass, replace
import re
from urllib.parse import urlsplit

from .candidates import PATTERNS
from .evidence import eligible, table_supported, field_words, row_supported
from .normalize import clean, literal_span
from .planner import tokens, STOP


@dataclass(frozen=True)
class Atom:
    source: str
    locator: str
    span: str
    value: str
    role: str
    version: str = ''
    key: str = ''
    relation: str = ''


@dataclass(frozen=True)
class Proof:
    operation: str
    atoms: tuple[Atom, ...]

    @property
    def sources(self):
        return list(dict.fromkeys(atom.source for atom in self.atoms))

    @property
    def answer(self):
        if self.operation=='count_relationships':
            from .family_counts import answer
            return answer(self.atoms)
        if self.operation=='scale_table_count':
            from .table_scales import compute
            return compute(self.atoms[0].value,self.atoms[1].value) if len(self.atoms)==3 else ''
        if self.operation=='compose_fields':return ', '.join(atom.value for atom in self.atoms)
        if self.operation in {'join_category','github_license'}:return self.atoms[-1].value
        old,new=(_quantity(atom.value) for atom in self.atoms)
        if old and new and old[1]==new[1]:return f'from {old[0]} to {new[0]} {new[1]}'
        return ''


def _words(value):
    return {word[:-3]+'y' if word.endswith('ies') else word[:-1] if word.endswith('s') and len(word)>3 else word
            for word in tokens(value) if word not in STOP and not word.isdigit()}


def _field(value):
    return field_words(value)


def _quantity(value):
    match=re.fullmatch(r'([-+]?\d+(?:[.,]\d+)*)\s+([A-Za-zµμ%][A-Za-zµμ% /-]{0,90})',value)
    return match.groups() if match else None


def _record(passage):
    facts=passage.qualifiers
    labels,values=facts.get('columns',[]),facts.get('cells',[])
    return list(zip(labels,values)) if passage.kind=='table' and labels and len(labels)==len(values) else []


def _relation_label(label):
    match=re.search(r'\b(categories|category|classes|class|tiers?|groups?|bands?)\b',label,re.I)
    if not match:return ''
    word=match[0].casefold()
    return 'category' if word.startswith('categor') else 'class' if word.startswith('class') else word.rstrip('s')


def _key_columns(record):
    found=[]
    for index,(label,value) in enumerate(record):
        relation=_relation_label(label)
        if relation and value and len(value)<=80:found.append((index,relation,value))
    return found


def _field_indices(field,labels):
    target=_field(field)
    if not target:return []
    exact=[i for i,label in enumerate(labels) if _field(label)==target]
    return exact or [i for i,label in enumerate(labels) if _field(label).intersection(target)]


def _project_indices(plan,passage):
    record=_record(passage);indices=[]
    for field in plan.required_fields:
        matches=_field_indices(field,[label for label,value in record])
        if len(matches)!=1:return []
        indices.extend(matches)
    return indices if len(set(indices))==len(indices) else []


def _row_matches(plan,page,passage,excluded):
    if not row_supported(plan,page,passage,excluded):return False
    cache=getattr(page,'_row_query_bindings',None)
    return bool(cache and cache[1])


def _same_origin(pages):
    return len({(urlsplit(p.url).scheme,urlsplit(p.url).netloc) for p in pages})==1


def _scope(plan,pages):
    if not _same_origin(pages):return set()
    generic=STOP|{'guide','reference','documentation','current','quota','request','fee','fees','daily','permit',
                  'version','release','category','categories','vendor','vendors','stable','the'}
    names=[]
    query=set(tokens(plan.question))
    for page in pages:
        names.append({name.casefold() for name in re.findall(r'\b[A-Z][A-Za-z0-9-]*\b',page.title)
                      if name.casefold() in query and name.casefold() not in generic})
    return set.intersection(*names) if names else set()


def _target_words(plan,excluded=()):
    return _words(plan.question)-set(excluded)-{'change','changed','compare','comparison','increase','decrease','between',
        'did','how','much','per','to','from','version','release'}


def _predicate(passage):
    if passage.kind!='prose':return None
    if re.search(r'\b(?:not|never|no|except|excluding|may|might|could|unless|if)\b',passage.text,re.I):return None
    match=re.fullmatch(r'(.*?)\b(?:is|are|was|were|equals?|(?:allows?|permits?)(?=\s+[-+\d$€£¥]))\s+(.+?)[.!?]?',passage.text)
    return (clean(match[1]),clean(match[2])) if match else None


def _version_value(plan,page,passage):
    if re.search(r'\b(?:alpha|beta|preview|prerelease|release candidate)\b|\bv\d+(?:\.\d+)*(?:alpha|beta|rc)\d*\b',
                 page.title+' '+passage.section,re.I):return None
    record=_record(passage)
    if record:
        versions=[clean(value).lstrip('vV') for label,value in record if re.search(r'\b(?:version|release)\b',label,re.I)]
        if len(versions)!=1 or versions[0] not in plan.versions:return None
        target=_target_words(plan,_scope(plan,[page]))
        quantities=[(len(_field(label).intersection(target)),label,value) for label,value in record if _quantity(value)]
        if not quantities:return None
        score=max(q[0] for q in quantities);best=[q for q in quantities if q[0]==score]
        if score<1 or len(best)!=1:return None
        _,label,value=best[0]
        return versions[0],f'{label} version {versions[0]} {passage.section}',value
    predicate=_predicate(passage)
    if not predicate or not _quantity(predicate[1]):return None
    versions=set(re.findall(r'\b(?:version\s+|v)(\d+(?:\.\d+)*)\b',
                            predicate[0]+' '+passage.section+' '+page.title,re.I))
    if len(versions)!=1:return None
    version=next(iter(versions))
    if version not in plan.versions:return None
    return version,predicate[0],predicate[1]


def _classification(passage,plan=None):
    record=_record(passage)
    if record:
        keys=_key_columns(record)
        if len(keys)!=1:return None
        index,relation,key=keys[0]
        subjects=[value for i,(label,value) in enumerate(record) if i!=index and _words(value)
                  and not _quantity(value) and not re.fullmatch(PATTERNS['price'],value,re.I)
                  and (plan is None or _words(value).issubset(_words(plan.question)))]
        return (subjects[0],relation,key) if len(set(subjects))==1 else None
    if passage.kind!='prose' or re.search(r'\b(?:not|never|no|except|excluding|may|might|could|unless|if)\b',passage.text,re.I):return None
    match=re.fullmatch(r'(.+?)\s+(?:(?:is|are|was|were)\s+(?:assigned(?: to)?|classified(?: as)?|in|under)|belong(?:s)? to|fall(?:s)? under)\s+'
        r'(category|class|tier|group|band)\s+([\w-]+)[.!]?',passage.text,re.I)
    return match.groups() if match else None


def _keyed_value(passage):
    record=_record(passage)
    if record:
        keys=_key_columns(record)
        prices=[value for label,value in record if re.search(r'\b(?:fee|price|cost|fare|amount)\b',label,re.I)
                and re.fullmatch(PATTERNS['price'],value,re.I)]
        if len(keys)!=1 or len(set(prices))!=1:return None
        _,relation,key=keys[0]
        return passage.section+' '+' '.join(label for label,value in record),relation,key,prices[0]
    predicate=_predicate(passage)
    if (not predicate or not re.fullmatch(PATTERNS['price'],predicate[1],re.I)) and passage.kind=='prose' and not re.search(
        r'\b(?:not|never|no|except|excluding|may|might|could|unless|if)\b',passage.text,re.I):
        prices=list(re.finditer(PATTERNS['price'],passage.text,re.I))
        if len(prices)==1 and not passage.text[prices[0].end():].strip(' .!?'):
            prefix=passage.text[:prices[0].start()].strip()
            phrase=re.fullmatch(r'(.+?)\s+(?:carries|incurs|requires)\s+(.+?)(?:\s+of)?',prefix,re.I)
            if phrase and re.search(r'\b(?:fee|price|cost|fare)\b',phrase[2],re.I):
                predicate=(phrase[1]+' '+phrase[2],prices[0][0])
    if not predicate or not re.fullmatch(PATTERNS['price'],predicate[1],re.I):return None
    key=re.search(r'\b(category|class|tier|group|band)\s+([\w-]+)\b',predicate[0],re.I)
    return (predicate[0],key[1].casefold(),key[2],predicate[1]) if key else None


def _atom(page,passage,value,role,**kwargs):
    return Atom(page.url,passage.locator,passage.text,value,role,**kwargs)


def _resolve(atom,pages):
    for page in pages:
        if page.url!=atom.source:continue
        for passage in page.passages:
            if passage.locator==atom.locator and passage.text==atom.span:return page,passage
    return None


def validate(proof,plan,pages):
    if proof.operation=='count_relationships':
        from .family_counts import analyze
        fact,required=analyze(plan,pages)
        if not fact or not required:return False
        page,subject,partners,chunks,records,count=fact
        expected=tuple(_atom(page,p,p.value if role!='children' else p.text,role,key=p.locator)
            for p,role in [(subject,'subject'),*((p,'partner') for p in partners),*((p,'children') for p in chunks)])
        return proof.atoms==expected and proof.answer==count
    if proof.operation not in {'compose_fields','compare_versions','join_category','github_license','scale_table_count'}:return False
    if len(proof.atoms)!=(3 if proof.operation=='scale_table_count' else 2):return False
    resolved=[_resolve(atom,pages) for atom in proof.atoms]
    if not all(resolved):return False
    for atom,(page,passage) in zip(proof.atoms,resolved):
        if not eligible(plan,page,passage) or not literal_span(atom.value,passage.text):return False
    if not proof.answer or len(proof.answer)>350:return False
    if proof.operation=='scale_table_count':
        from .table_scales import analyze,identities
        fact,required=analyze(plan,pages)
        if not fact or not required:return False
        page,passage,column,label,raw,value,scaled=fact
        identity=proof.atoms[2]
        cells=passage.qualifiers['cells']
        return (tuple(a.role for a in proof.atoms)==('column_header','coefficient','row_identity')
            and all(a.source==page.url and a.locator==passage.locator and a.span==passage.text
                    for a in proof.atoms)
            and all(a.key==str(column) for a in proof.atoms[:2])
            and tuple(a.value for a in proof.atoms[:2])==(label,raw) and proof.answer==value
            and identity.key.isdigit() and int(identity.key)<len(cells) and int(identity.key)!=column
            and identity.value==cells[int(identity.key)] and identity.value in identities(plan,passage,[column]))
    if proof.operation=='github_license':
        from .github_history import pair
        first,last=resolved
        return (tuple(a.role for a in proof.atoms)==('commit_date','license')
            and proof.atoms[0].value==first[1].value
            and (first,last) in pair(plan,pages)
            and (last[1].qualifiers.get('github_role')!='license' or proof.atoms[1].value==last[1].value))
    if proof.operation=='compose_fields':
        if plan.operation!='compose_fields' or len(plan.required_fields)!=2:return False
        first_page,first=resolved[0]
        if any(page.url!=first_page.url or p.qualifiers.get('table')!=first.qualifiers.get('table')
               or p.qualifiers.get('row')!=first.qualifiers.get('row') for page,p in resolved):return False
        if first.kind!='table' or first.qualifiers.get('table') is None:return False
        if not table_supported(replace(plan,focus='',kind='text'),first_page,first,proof.atoms[0].value):return False
        projection=_project_indices(plan,first)
        if not projection or not _row_matches(plan,first_page,first,projection):return False
        columns,cells=first.qualifiers['columns'],first.qualifiers['cells']
        indices=[]
        for field,atom in zip(plan.required_fields,proof.atoms):
            matches=_field_indices(field,columns)
            if len(matches)!=1 or matches[0]>=len(cells) or cells[matches[0]]!=atom.value:return False
            indices.extend(matches)
            if 'time' in _field(field):
                clock=PATTERNS['time']
                if not re.fullmatch('(?:'+clock+r')(?:\s*(?:[-–—]|to)\s*(?:'+clock+'))?',atom.value,re.I):return False
        return len(set(indices))==2
    scope=_scope(plan,[page for page,p in resolved])
    if not scope:return False
    if proof.operation=='compare_versions':
        if plan.operation!='compare_versions' or tuple(a.version for a in proof.atoms)!=tuple(dict.fromkeys(plan.versions)):return False
        for atom,(page,passage) in zip(proof.atoms,resolved):
            fact=_version_value(plan,page,passage)
            if not fact or fact[0]!=atom.version or fact[2]!=atom.value:return False
            if not _target_words(plan,scope).issubset(_words(fact[1]+' '+page.title)):return False
            alternatives=set()
            for other in pages:
                if not _scope(plan,[page,other]):continue
                for candidate in other.passages:
                    value=_version_value(plan,other,candidate)
                    if value and value[0]==atom.version and _target_words(plan,scope).issubset(_words(value[1]+' '+other.title)):
                        alternatives.add(value[2])
                        if len(alternatives)>1:return False
        return _quantity(proof.atoms[0].value)[1]==_quantity(proof.atoms[1].value)[1]
    if plan.kind!='price' or plan.operation!='single':return False
    mapping=_classification(resolved[0][1],plan);value=_keyed_value(resolved[1][1])
    if not mapping or not value:return False
    if mapping[1].casefold()!=value[1] or mapping[2]!=value[2]:return False
    if proof.atoms[0].value!=mapping[2] or proof.atoms[1].value!=value[3]:return False
    if any(a.key!=mapping[2] or a.relation!=value[1] for a in proof.atoms):return False
    if not _words(mapping[0]).issubset(_words(plan.question)):return False
    target=_target_words(plan,scope|_words(mapping[0]))
    if not target.issubset(_words(value[0]+' '+resolved[1][0].title)):return False
    keys=set();values=set()
    for page in pages:
        if not _scope(plan,[resolved[0][0],page]):continue
        for passage in page.passages:
            classified=_classification(passage,plan)
            if classified and classified[1].casefold()==value[1] and _words(classified[0]).issubset(_words(plan.question)):
                keys.add(classified[2])
            fee=_keyed_value(passage)
            if fee and fee[1:3]==value[1:3] and target.issubset(_words(fee[0]+' '+page.title)):values.add(fee[3])
            if len(keys)>1 or len(values)>1:return False
    return True


def propose(plan,pages,chosen=None):
    """Return (complete proof or None, whether a single span would be incomplete)."""
    from .family_counts import analyze as family_count
    family,needed=family_count(plan,pages)
    if needed:
        if not family:return None,True
        page,subject,partners,chunks,records,count=family
        proof=Proof('count_relationships',tuple(_atom(page,p,p.value if role!='children' else p.text,role,key=p.locator)
            for p,role in [(subject,'subject'),*((p,'partner') for p in partners),*((p,'children') for p in chunks)]))
        return proof,True
    from .table_scales import analyze,identities
    scaled,required=analyze(plan,pages)
    if required:
        if not scaled:return None,True
        page,passage,column,label,raw,value,scaled=scaled
        name=identities(plan,passage,[column])[0]
        identity_column=passage.qualifiers['cells'].index(name)
        return Proof('scale_table_count',(_atom(page,passage,label,'column_header',key=str(column)),
            _atom(page,passage,raw,'coefficient',key=str(column)),
            _atom(page,passage,name,'row_identity',key=str(identity_column)))),True
    from .github_history import request, premises
    if request(plan)[0]:
        facts=premises(plan,pages,chosen)
        if not facts:return None,True
        proof=Proof('github_license',tuple(_atom(page,p,value,role)
            for (page,p,value),role in zip(facts,('commit_date','license'))))
        return (proof if validate(proof,plan,pages) else None),True
    proposals=[]
    if plan.operation=='compose_fields':
        for page in pages:
            rows=[p for p in page.passages if p.kind=='table' and p.qualifiers.get('columns')]
            for p in rows:
                indices=_project_indices(plan,p)
                if not indices or not _row_matches(plan,page,p,indices):continue
                atoms=[_atom(page,p,p.qualifiers['cells'][i],field) for i,field in zip(indices,plan.required_fields)]
                if len(atoms)==2:proposals.append(Proof('compose_fields',tuple(atoms)))
    elif plan.operation=='compare_versions':
        values={v:[] for v in dict.fromkeys(plan.versions)}
        for page in pages:
            for p in page.passages:
                fact=_version_value(plan,page,p)
                if fact and _target_words(plan).issubset(_words(fact[1]+' '+page.title)):
                    values[fact[0]].append(_atom(page,p,fact[2],fact[0],version=fact[0]))
                    if sum(map(len,values.values()))>64:return None,True
        if len(values)==2 and all(len({a.value for a in atoms})==1 for atoms in values.values()):
            proposals.append(Proof('compare_versions',tuple(atoms[0] for atoms in values.values())))
    keyed=[];mappings=[];schema_keys=[];direct_record=False
    if plan.kind=='price':
        for page in pages:
            for p in page.passages:
                record=_record(p)
                if record:
                    schema_keys.extend(value for label,value in record if _relation_label(label))
                    amounts=[i for i,(label,value) in enumerate(record) if re.fullmatch(PATTERNS['price'],value,re.I)]
                    if amounts and _row_matches(plan,page,p,amounts):direct_record=True
                fact=_classification(p,plan)
                if fact and _words(fact[0]).issubset(_words(plan.question)):mappings.append((page,p,fact))
                value=_keyed_value(p)
                if value:keyed.append((page,p,value))
                if len(mappings)>64 or len(keyed)>64:return None,True
        if len({(f[1].casefold(),f[2]) for page,p,f in mappings})==1:
            for mp,m,classification in mappings:
                for vp,v,value in keyed:
                    if classification[1].casefold()==value[1] and classification[2]==value[2]:
                        proposals.append(Proof('join_category',(
                            _atom(mp,m,classification[2],'mapping',key=value[2],relation=value[1]),
                            _atom(vp,v,value[3],'value',key=value[2],relation=value[1]))))
                        if len(proposals)>64:return None,True
    valid=[proof for proof in proposals if validate(proof,plan,pages)]
    # Conflicting complete derivations are not resolved by DOM order.
    answers={proof.answer for proof in valid}
    proof=valid[0] if len(answers)==1 else None
    # A named product and its price can already be bound in a single record;
    # an incidental Category column does not force a redundant category join.
    if direct_record and plan.operation=='single':return None,False
    explicit_key=any(value and literal_span(value,plan.question) for value in schema_keys+[value[2] for page,p,value in keyed])
    required=plan.operation!='single' or bool(mappings) or bool((keyed or schema_keys) and not explicit_key)
    return proof,required
