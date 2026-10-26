"""Wikidata-assisted discovery. Website claims are seeds, not evidence for other facts."""
import json
import re
from urllib.parse import quote

from .urls import canonical_url


def entity_phrase(question):
    # Retain the original natural-language search when no clean relationship phrase exists.
    m=re.search(r"(?:CEO|chief executive|capital|headquarters|founder|official website)\s+(?:of|for)\s+(.+?)(?:\?|\s+according to|$)",question,re.I)
    return (m[1] if m else question).strip(' .?"')[:160]


async def lookup(plan,fetcher):
    phrase=entity_phrase(plan.question)
    endpoint="https://www.wikidata.org/w/api.php?action=wbsearchentities&language=en&format=json&maxlag=5&limit=3&search="+quote(phrase)
    response=await fetcher.fetch(endpoint)
    try:
        data=json.loads(response.text)
        results=data.get('search',[]) if isinstance(data,dict) else []
    except (ValueError,TypeError):
        return []
    if not isinstance(results,list) or not results:
        return []
    results=[result for result in results if isinstance(result,dict)]
    # Exact label or alias alignment avoids silently choosing a similarly named company.
    chosen=next((r for r in results if str(r.get("label","")).casefold()==phrase.casefold()
                 or isinstance(r.get('match'),dict) and str(r['match'].get("text","")).casefold()==phrase.casefold()),None)
    if not chosen:
        return []
    qid=chosen.get("id","")
    if not isinstance(qid,str) or not re.fullmatch(r"Q\d+",qid):
        return []
    resp=await fetcher.fetch(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
    try:
        entity=json.loads(resp.text)["entities"][qid]
    except (ValueError,TypeError,KeyError):
        return []
    if not isinstance(entity,dict):return []
    claims=entity.get("claims",{})
    if not isinstance(claims,dict) or not isinstance(claims.get('P856',[]),list):return []
    seeds=[]
    for claim in claims.get("P856",[]):
        if not isinstance(claim,dict):continue
        if claim.get("rank")=="deprecated":continue
        snak=claim.get('mainsnak')
        if not isinstance(snak,dict) or not isinstance(snak.get('datavalue'),dict):continue
        value=snak['datavalue'].get('value','')
        if isinstance(value,str) and canonical_url(value):
            seeds.append((canonical_url(value),chosen.get("label",phrase)+" official website"))
    return seeds
