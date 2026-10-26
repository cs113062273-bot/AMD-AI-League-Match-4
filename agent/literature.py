"""Free official Europe PMC title discovery; metadata is never answer evidence."""
import json
import re
from urllib.parse import parse_qs,quote,urlsplit

from .normalize import clean

BASE='https://www.ebi.ac.uk/europepmc/webservices/rest/search'


def paper_title(question):
    # Require an explicit publication title, not a short nickname or an
    # arbitrary quoted instruction. Ambiguous multiple titles stay generic.
    matches=list(re.finditer(r'\b(?:paper|article|study)\s+(?:titled|entitled)\s+"([^"\r\n]{20,240})"',question,re.I))
    if len(matches)!=1:return ''
    if re.search(r'[\x00-\x1f\x7f]',matches[0][1]):return ''
    title=clean(matches[0][1])
    return title if 5<=len(title.split())<=35 and not re.search(r'https?://|[\x00-\x1f\x7f]',title) else ''


def title_query(question):
    title=paper_title(question)
    return 'TITLE:"'+title+'"' if title else ''


def matching_links(response,question):
    title=paper_title(question);query=title_query(question)
    if not title or response.error or response.truncated or response.status!=200:return []
    try:
        parts=urlsplit(response.url)
        if (parts.scheme!='https' or parts.netloc!='www.ebi.ac.uk'
                or parts.path!='/europepmc/webservices/rest/search'
                or parse_qs(parts.query).get('query')!=[query]):return []
        data=json.loads(response.text)
        if not isinstance(data,dict) or not isinstance(data.get('request'),dict) or data['request'].get('queryString')!=query:return []
        results=data.get('resultList',{}).get('result')
        if not isinstance(results,list) or len(results)>3:return []
        wanted=clean(title).casefold().removesuffix('.')
        years=re.findall(r'\b(\d{4})\s+(?:research\s+)?(?:paper|article|study)\s+(?:titled|entitled)\b',question,re.I)
        matches={}
        for item in results:
            if not isinstance(item,dict) or not isinstance(item.get('title'),str):continue
            if clean(item['title']).casefold().removesuffix('.')!=wanted:continue
            if item.get('source') not in {'MED','PMC'} or item.get('isOpenAccess')!='Y':continue
            pmcid=item.get('pmcid','')
            if not isinstance(pmcid,str) or not re.fullmatch(r'PMC[1-9]\d{0,11}',pmcid):continue
            if years and (len(set(years))!=1 or str(item.get('pubYear'))!=years[0]):continue
            matches[pmcid]=item['title']
        # A title collision must not choose an arbitrary article or revision.
        if len(matches)!=1:return []
        pmcid,label=next(iter(matches.items()))
        return [('https://pmc.ncbi.nlm.nih.gov/articles/'+pmcid+'/',label)]
    except (ValueError,TypeError,AttributeError,RecursionError):return []


async def title_links(plan,fetcher):
    query=title_query(plan.question)
    if not query or fetcher.deadline.remaining<=4:return []
    response=await fetcher.fetch(BASE+'?query='+quote(query)+'&format=json&pageSize=3&resultType=core',
        timeout=3,max_bytes=250000)
    return matching_links(response,plan.question)
