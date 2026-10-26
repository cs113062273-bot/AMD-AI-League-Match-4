"""Anonymous published records for already discovered official ancestor profiles.

Render literal fields and relationship arrays, never a manufactured count.
"""
import json
import re
from urllib.parse import urlsplit

from .normalize import clean
from .types import Page,Passage

PID=r'[A-Z0-9]{4}-[A-Z0-9]{3}'
BASE='https://www.familysearch.org/service/tree/tree-data/published/persons/'
_PARTIAL={'partial','truncated','hasMore','next','nextPage','nextPageToken','cursor','pagination','continuation'}


def _url(url):
    try:
        p=urlsplit(url)
        return p if (p.scheme=='https' and not p.username and not p.password
                     and p.port in {None,443} and not p.query and not p.fragment) else None
    except (ValueError,TypeError):return None


def profile_key(url):
    p=_url(url)
    if not p or p.hostname!='ancestors.familysearch.org':return None
    m=re.fullmatch(r'/([a-z]{2,3}(?:-[a-z]{2,8})?)/('+PID+r')/[^/]{1,200}/?',p.path)
    return (m[1],m[2]) if m else None


def published_key(url):
    p=_url(url)
    if not p or p.hostname!='www.familysearch.org':return None
    m=re.fullmatch(r'/service/tree/tree-data/published/persons/('+PID+r')/?',p.path)
    return m[1] if m else None


def _object(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('duplicate JSON key')
        result[k]=v
    return result


def _protected(data):
    return (any(data.get(k) for k in ['private','isPrivate','living','isLiving','removed','forwarded','error','errors'])
            or str(data.get('privacy','')).casefold() not in {'','public','false'})


def _partial(data):return any(data.get(k) for k in _PARTIAL)


def _linked_identity(record):
    if not record.get('url'):return True
    key=profile_key(record['url'])
    return bool(key and key[1]==record.get('identifier'))


def _collection_complete(person,children,kind='children'):
    aliases={'children','child'} if kind=='children' else {'spouse','spouses'}
    for key,value in person.items():
        name=re.sub('[^a-z]','',key.casefold())
        if name in {alias+suffix for alias in aliases for suffix in ['count','total']}|{'total'+alias for alias in aliases}:
            if type(value) is not int or not isinstance(children,list) or value!=len(children):return False
        if any(name.startswith(alias+suffix) for alias in aliases for suffix in ['page','pagination','continuation','cursor']) and value:return False
    return True


def _fields(person):
    return {k:person[k] for k in ['identifier','name','birthDate','deathDate','gender']
            if isinstance(person.get(k),str) and 0<len(person[k])<=350}


def _dump(data):return json.dumps(data,ensure_ascii=False,separators=(',',':'))


def parse_published(response,key,locale='en'):
    page=Page(response.url,status=response.status,redirects=response.redirects,truncated=response.truncated)
    if response.error or response.status!=200 or response.truncated:
        page.error=response.error or 'familysearch_incomplete_response';return page
    if published_key(response.url)!=key or any(published_key(u)!=key for u in response.redirects):
        page.error='familysearch_response_identity_mismatch';return page
    try:
        data=json.loads(response.text,object_pairs_hook=_object,
                        parse_constant=lambda value:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
    except (ValueError,TypeError,RecursionError):data=None
    if (not isinstance(data,dict) or _protected(data) or _partial(data)
            or not re.fullmatch(r'1\.\d{1,3}',str(data.get('version','')))
            or not isinstance(data.get('person'),dict)):
        page.error='familysearch_invalid_document';return page
    person=data['person'];profile=profile_key(person.get('url',''))
    if (person.get('@type')!='Person' or not isinstance(person.get('@context'),str)
            or person['@context'] not in {'http://schema.org','https://schema.org'}
            or person.get('identifier')!=key or not profile or profile[1]!=key
            or _protected(person) or _partial(person)
            or not isinstance(person.get('name'),str) or not 0<len(clean(person['name']))<=350):
        page.error='familysearch_person_identity_mismatch';return page
    fields=_fields(person);page.title=clean(person['name']);page.canonical=person['url']
    page.identity={'registry':'familysearch','person_id':key,'profile_url':person['url']}
    page.passages.append(Passage(_dump({'person':fields}),label='person',value=key,kind='record',locator='person',
                                 qualifiers={'familysearch_role':'subject','source_fields':fields}))
    spouses=person.get('spouse');valid_spouses=(isinstance(spouses,list) and len(spouses)<=32
        and _collection_complete(person,spouses,'spouse') and _collection_complete(data,spouses,'spouse'))
    spouse_ids=set()
    for i,spouse in enumerate(spouses[:32] if valid_spouses else []):
        if (not isinstance(spouse,dict) or spouse.get('@type')!='Person' or _protected(spouse) or _partial(spouse)
                or not _linked_identity(spouse)
                or not isinstance(spouse.get('identifier'),str) or not re.fullmatch(PID,spouse['identifier'])
                or spouse['identifier'] in spouse_ids or spouse['identifier']==key
                or not isinstance(spouse.get('name'),str) or not 0<len(clean(spouse['name']))<=350):
            valid_spouses=False;continue
        spouse_ids.add(spouse['identifier']);values=_fields(spouse)
        page.passages.append(Passage(_dump({'person':fields,'spouse':values}),label='spouse',value=spouse['identifier'],
            kind='record',locator=f'person.spouse[{i}]',qualifiers={'familysearch_role':'partner','source_fields':values}))
    page.identity['spouses_complete']=valid_spouses
    children=person.get('children');valid_children=(isinstance(children,list) and len(children)<=128
        and _collection_complete(person,children) and _collection_complete(data,children))
    records=[];ids=set()
    for child in children if valid_children else []:
        if (not isinstance(child,dict) or child.get('@type')!='Person' or _protected(child) or _partial(child)
                or not _linked_identity(child)
                or not isinstance(child.get('identifier'),str) or not re.fullmatch(PID,child['identifier'])
                or child['identifier'] in ids or child['identifier'] in {key,*spouse_ids}):
            valid_children=False;continue
        ids.add(child['identifier'])
        row={k:child[k] for k in ['identifier','otherParentId'] if k in child}
        if row.get('otherParentId') is not None and (not isinstance(row['otherParentId'],str)
                or not re.fullmatch(PID,row['otherParentId']) or row['otherParentId'] in {key,child['identifier']}):
            valid_children=False
        records.append(row)
    page.identity.update(children_complete=valid_children,children_length=len(records))
    chunks=[];chunk=[]
    for row in records:
        if chunk and len(_dump({'children':[*chunk,row]}))>950:chunks.append(chunk);chunk=[]
        chunk.append(row)
    if chunk or not records:chunks.append(chunk)
    start=0
    for chunk in chunks:
        stop=start+len(chunk);text=_dump({'children':chunk})
        page.passages.append(Passage(text,label='children',section=page.title,kind='collection',
            locator=f'person.children[{start}:{stop}]',qualifiers={'familysearch_role':'children','start':start,
                'stop':stop,'records':chunk,'subject_id':key}))
        start=stop
    translations=data.get('localizedData',{})
    translation=translations.get(locale,translations.get('en',{})) if isinstance(translations,dict) else {}
    summary=translation.get('lifeSummary') if isinstance(translation,dict) else None
    if isinstance(summary,str) and summary:
        from .parser import parse_response,segments
        from .network import Response
        if len(summary)>12000:page.truncated=True
        fragment=parse_response(Response(response.url,body=summary[:12000].encode(),content_type='text/html',status=200))
        for p in fragment.passages:
            if p.kind not in {'prose','heading'}:continue
            for offset,text in segments(p.text,width=1000):
                page.passages.append(Passage(text,label='life summary',section=page.title,kind='prose',
                    locator=f'localizedData.{locale}.lifeSummary:{p.locator}:{offset}'))
    return page


async def adapt_profile(requested,response,fetcher,attempted):
    direct=published_key(requested)
    if direct:return parse_published(response,direct)
    key=profile_key(requested)
    if not key:return None
    if (response.error or response.status!=200 or response.truncated or profile_key(response.url)!=key
            or any(profile_key(u)!=key for u in response.redirects)):return None
    target=BASE+key[1]
    if target not in attempted:
        if len(attempted)>=fetcher.settings.max_pages or fetcher.deadline.remaining<1.8:return None
        attempted.add(target)
    return parse_published(await fetcher.fetch(target),key[1],key[0])
