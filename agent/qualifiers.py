"""Typed qualifiers from actual structured fields; nearer records override ancestors."""
import re
from .currencies import CODES
from .normalize import iso_date


def key_name(value):
    return re.sub(r'[^a-z0-9]','',str(value).casefold())


def record_qualifiers(fields,parent=None,path=''):
    normalized={key_name(key):value for key,value in fields.items()}
    inherited=dict(parent or {})
    # A newly named entity does not inherit another entity's release date/tag.
    identities={str(value) for key,value in normalized.items() if key in {'name','id','sku','model','productname','partnumber'}}
    if identities and inherited.get('identity') and identities.isdisjoint(inherited['identity']):
        for key in list(inherited):
            if key.startswith(('release_','version_')) or key=='bindings':inherited.pop(key)
    if identities:inherited['identity']=sorted(identities)[:8]
    result={**inherited,'structured':True}
    bindings={**fields,**{key:value for key,value in inherited.get('bindings',{}).items() if key not in fields}}
    result['bindings']=dict(list(bindings.items())[:64])
    for key in ('currency_distance','release_date_distance','version_distance'):
        if key in result:result[key]+=1
    currency=[(key,value) for key,value in fields.items() if key_name(key) in {'currency','pricecurrency'}]
    if currency:
        codes={str(value).upper() for key,value in currency if str(value).upper() in CODES}
        ambiguous=len(codes)!=1 or any(str(value).upper() not in CODES for key,value in currency)
        result.update(currency=next(iter(codes)) if not ambiguous else '',currency_ambiguous=ambiguous,
            currency_distance=0,currency_raw=str(currency[0][1]),currency_key=currency[0][0])
    version=[str(value) for key,value in fields.items() if key_name(key) in
        {'version','tagname','releaseversion','stableversion','currentversion','currentstableversion'}]
    if version:result.update(version_values=list(dict.fromkeys(version)),version_distance=0)
    priorities={**{key:0 for key in ('released','releasedat','releasedate','currentreleasedate','releasetime')},
        **{key:1 for key in ('published','publishedat','publicationdate','publishdate')},
        **{key:2 for key in ('uploadtime','uploadtimeiso8601','uploadedat')}}
    if version or re.search(r'releases?|versions?|history',path,re.I):priorities['date']=3
    dates=[(priorities[key_name(key)],key,str(value)) for key,value in fields.items() if key_name(key) in priorities]
    if dates:
        rank=min(item[0] for item in dates);selected=[item for item in dates if item[0]==rank]
        values={iso_date(item[2]) for item in selected}
        ambiguous='' in values or len(values)!=1
        result.update(release_date=next(iter(values)) if not ambiguous else '',release_date_ambiguous=ambiguous,
            release_date_distance=0,release_date_key=selected[0][1],release_date_raw=selected[0][2])
    return result
