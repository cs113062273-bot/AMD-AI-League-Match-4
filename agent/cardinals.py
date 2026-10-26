"""Exact integer arithmetic licensed by a complete fetched count span.

Supports English cardinals and explicit decimal coefficients with magnitude
words. The vocabulary is numeral grammar, not an entity/answer catalog.
Fractions, ordinals, approximations and ranges do not become derived integers.
"""
import re

from .normalize import clean, literal_span
from .number_atoms import SMALL,TENS,SCALES,SCALED_PATTERN,scaled_runs
from .magnitudes import integer as magnitude_integer

_WORDS = sorted(set(SMALL) | set(TENS) | set(SCALES) | {'hundred'}, key=lambda word:(-len(word),word))
_VOCAB = frozenset(_WORDS)|{'and','a'}
_ATOM = r'(?:'+'|'.join(_WORDS)+r'|a(?=\s+(?:hundred|thousand|million|billion|trillion)\b))'
_TOKEN = r'(?:'+_ATOM+r'|and)\b'
# Maximal runs prevent selecting a smaller numeral inside a larger phrase.
WORD_PATTERN = r'(?<![\w\-\u2010\u2011])'+_ATOM+r'\b(?:(?:[\s\-\u2010\u2011]+|,\s*)'+_TOKEN+r')*'
_RUN = re.compile(WORD_PATTERN, re.I)
COUNT_PATTERN=r'(?:'+SCALED_PATTERN+'|'+WORD_PATTERN+r')'
_ORDINAL = r'(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|\w+(?:teenth|tieth)|hundredth|thousandth|millionth|billionth|trillionth)'
_FRACTIONS = r'(?:half|halves|quarters?|thirds|fourths|fifths|sixths|sevenths|eighths|ninths|tenths|elevenths|twelfths|\w+(?:teenths|tieths)|hundredths|thousandths|millionths|billionths|trillionths)'


def _small(words):
    if len(words)==1:
        value=SMALL.get(words[0],TENS.get(words[0]))
        return value if value else None
    if len(words)==2 and words[0] in TENS and 1<=SMALL.get(words[1],0)<=9:
        return TENS[words[0]]+SMALL[words[1]]
    return None


def _group(words):
    if len(words)>=2 and words[1]=='hundred' and 1<=SMALL.get(words[0],0)<=9:
        value=SMALL[words[0]]*100
        tail=words[2:]
        if not tail:return value
        if tail[0]=='and':tail=tail[1:]
        rest=_small(tail)
        return value+rest if rest is not None else None
    return _small(words)


def integer(value):
    value=clean(value).casefold()
    if value=='zero':return 0
    if not value or len(value)>350:return None
    # A comma is accepted only after a scale, not as an arbitrary list join.
    parts=value.split(',')
    if any(not part.strip() for part in parts):return None
    if any(part.strip().split()[-1] not in SCALES for part in parts[:-1]):return None
    for match in re.finditer(r'([a-z]+)[\-\u2010\u2011]([a-z]+)',value):
        if match[1] not in TENS or not 1<=SMALL.get(match[2],0)<=9:return None
    words=re.split(r'[\s,\-\u2010\u2011]+',value)
    if len(words)>40 or any(w not in _VOCAB for w in words):return None
    # The indefinite article has numeric meaning only immediately before a scale.
    for i,word in enumerate(words):
        if word=='a':
            if i+1==len(words) or words[i+1] not in set(SCALES)|{'hundred'}:return None
            words[i]='one'
    total=0;previous=10**15;start=0
    for i,word in enumerate(words):
        if word not in SCALES:continue
        scale=SCALES[word]
        part=words[start:i]
        if start and part and part[0]=='and':part=part[1:]
        group=_group(part)
        if group is None or scale>=previous:return None
        total+=group*scale;previous=scale;start=i+1
    tail=words[start:]
    if start and tail and tail[0]=='and':
        tail=tail[1:]
        if not tail:return None
    if not tail:return total if start else None
    group=_group(tail)
    return total+group if group is not None else None


def count_request(question,kind,operation='single'):
    return (kind=='number' and operation=='single' and bool(re.search(
        r'\bhow many\b|\b(?:what|which)(?:\s+(?:is|was|are|were))?\s+(?:the\s+)?'
        r'(?:total\s+)?(?:number\s+of|count(?=\s+(?:of|for|in|at|on|as)\b|\s*[?.,]|$))|'
        r'\bwhat(?:\s+(?:is|was)|[\x27\u2019]s)\s+(?:the\s+)?(?:total\s+)?population\b',question,re.I)))


def count_value(raw):
    """A word numeral or a complete, exactly integral scaled quantity."""
    value=integer(raw)
    return value if value is not None else magnitude_integer(clean(raw),integer)


def spans(text,continues=False):
    """Yield actual source phrases and computed integers, never rewritten evidence."""
    text=clean(text)
    bounds=sorted(set([m.span() for m in _RUN.finditer(text)]+list(scaled_runs(text))))
    for start,end in bounds:
        # An ordinary sentence conjunction can follow an otherwise complete count.
        raw=re.sub(r'\s+and$','',text[start:end],flags=re.I)
        end=start+len(raw)
        value=count_value(raw)
        if value is None or not literal_span(raw,text,'number'):continue
        before=text[:start];after=text[end:]
        if re.fullmatch(r'\s+and\s*[,;:.!?]?',after,re.I):continue
        if continues and re.fullmatch(r'\s*(?:and\s*)?[,;:\-]?',after,re.I):continue
        if re.search(r'[\-\u2010-\u2014\u2212]\s*$',before) or re.match(r'\s*[\-\u2010-\u2014\u2212]',after):continue
        if re.search(r'[<>\u2264\u2265/+*\u2044\u00d7\u00f7]\s*$',before) or re.match(r'\s*[/+*\u2044\u00d7\u00f7]',after):continue
        if re.search(r'(?:\d|[+\-\u2212])\s*$',before) or re.match(r'\s*\d',after):continue
        if re.search(r'\b(?:point|dot|minus|plus|times|divided by|multiplied by|half|quarter|half of|quarter of|negative|about|around|approximately|roughly|nearly|over|under|'
                     r'between|from|to|through|or|at least|at most|more than|less than|fewer than)\s*$',before,re.I):continue
        if re.match(r'\s+(?:to\b|through\b|or\b|point\b|dot\b|plus\b|minus\b|times\b|divided\b|multiplied\b|'
                    +_ORDINAL+r'\b|'+_FRACTIONS+r'\b|'
                    r'(?:dozens?|score|hundreds|thousands|millions|billions|trillions|'
                    r'quadrillions?|quintillions?|sextillions?|septillions?|octillions?|nonillions?|decillions?|lakhs?|crores?)\b|'
                    r'and\s+(?:a|one)\s+(?:half|quarter|third)\b)',after,re.I):continue
        yield raw,value


def licensed(raw,text,continues=False):
    raw=clean(raw)
    return any(source==raw for source,value in spans(text,continues))


def answer(raw,question,kind,operation='single'):
    value=count_value(raw) if count_request(question,kind,operation) else None
    return str(value) if value is not None else clean(raw)


def lexical_runs(text):
    """Whole numeral runs, including invalid quantities, for safe excerpt edges."""
    return sorted(set([m.span() for m in _RUN.finditer(text)]+list(scaled_runs(text))))


def source_span(selected,text,question,kind,operation='single'):
    """A literal span, or one unique word-span with exactly the selected value."""
    selected=clean(selected)
    counts=count_request(question,kind,operation)
    unit=None
    if counts and count_value(selected) is None:
        match=re.fullmatch(r'(.+)\s+([A-Za-z]+)',selected)
        if (match and re.search(r'(?<!\w)'+re.escape(match[2])+r'(?!\w)',question,re.I)
                and (count_value(match[1]) is not None or re.fullmatch(r'[-+]?\d+(?:[,.]\d+)*',match[1]))):
            selected,unit=match[1],match[2]
    if literal_span(selected,text,kind):
        if counts and count_value(selected) is not None and not licensed(selected,text):return None
        if unit and not literal_span(selected+' '+unit,text,kind):return None
        return selected
    if not counts or not re.fullmatch(r'0|[1-9]\d{0,14}',selected):return None
    matches=[raw for raw,value in spans(text) if str(value)==selected
             and (not unit or literal_span(raw+' '+unit,text,kind))]
    return matches[0] if len(matches)==1 else None
