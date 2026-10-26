"""Tokenize upstream comma-separated supporting URLs without changing URL paths."""
import re

from agent.urls import canonical_url


def supporting_urls(value):
    # Some upstream rows quote an individual URL inside the CSV field. The
    # closing quote belongs to the list serialization, not to the URL path.
    parts=re.split(r',\s*(?=[\x27\"]?https?://)',value)
    result=[]
    for part in parts:
        part=part.strip()
        if len(part)>1 and part[0] in "\x27\"" and part[-1]==part[0]:part=part[1:-1]
        url=canonical_url(part)
        if not url:raise ValueError('Invalid upstream supporting URL')
        if url not in result:result.append(url)
    if not result:raise ValueError('No upstream supporting URLs')
    return result
