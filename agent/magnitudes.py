"""Bounded, exact decimal arithmetic for complete scaled integer counts."""
from decimal import Decimal, InvalidOperation, localcontext
import re

from .number_atoms import NUMBER, SCALES

_DECIMAL=re.compile(r'(?:(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?')
_TOKENS=re.compile(NUMBER+r'|[A-Za-z]+')
LIMIT=10**15


def _number(token):
    if len(token)>50 or not _DECIMAL.fullmatch(token):return None
    exponent=re.search(r'[eE]([-+]?[0-9]+)$',token)
    if exponent and abs(int(exponent[1]))>18:return None
    try:return Decimal(token.replace(',',''))
    except InvalidOperation:return None


def _coefficient(words,word_integer):
    if not words:return None
    if len(words)==1:
        number=_number(words[0])
        if number is not None:return number
    if 'hundred' in words:
        if words.count('hundred')!=1:return None
        index=words.index('hundred')
        head=_coefficient(words[:index],word_integer)
        if head is None or head<=0:return None
        tail=words[index+1:]
        if tail and tail[0]=='and':tail=tail[1:]
        if not tail:return head*100
        rest=_coefficient(tail,word_integer)
        return head*100+rest if rest is not None and 0<rest<100 else None
    value=word_integer(' '.join(words))
    return Decimal(value) if value is not None else None


def integer(raw,word_integer):
    if not raw or len(raw)>350 or not re.search(r'[0-9]',raw):return None
    matches=list(_TOKENS.finditer(raw))
    if len(matches)>40:return None
    # Retain only an arithmetic grammar. Commas inside coefficients remain
    # part of their token; source commas between scale groups are separators.
    position=0;words=[]
    for match in matches:
        if raw[position:match.start()].strip(' ,\t\r\n'):return None
        words.append(match[0].casefold());position=match.end()
    if raw[position:].strip() or not any(w in SCALES or w=='hundred' for w in words):return None
    with localcontext() as context:
        context.prec=80
        total=Decimal(0);previous=LIMIT;start=0
        for i,word in enumerate(words):
            if word not in SCALES:continue
            scale=SCALES[word]
            part=words[start:i]
            if start and part and part[0]=='and':part=part[1:]
            coefficient=_coefficient(part,word_integer)
            if coefficient is None or coefficient<0 or scale>=previous:return None
            contribution=coefficient*scale
            if start and contribution>=previous:return None
            total+=contribution;previous=scale;start=i+1
        tail=words[start:]
        if tail:
            if start:
                if tail[0]!='and':return None
                tail=tail[1:]
            rest=_coefficient(tail,word_integer)
            if rest is None or rest<0 or start and rest>=min(previous,1000):return None
            total+=rest
        elif not start:return None
        if not 0<=total<LIMIT or total!=total.to_integral_value():return None
        return int(total)
