"""Lexical source boundaries for numbers carrying spelled magnitude words.

No arithmetic or source rewriting here. Invalid scaled runs still prevent
substrings from being treated as independent numeric evidence.
"""
import re

SMALL = dict(zip(('zero one two three four five six seven eight nine ten eleven twelve thirteen '
                  'fourteen fifteen sixteen seventeen eighteen nineteen').split(), range(20)))
TENS = dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(), range(20,100,10)))
SCALES = {'thousand':1000,'million':10**6,'billion':10**9,'trillion':10**12}
MULTIPLIERS = {'hundred':100,**SCALES}
NUMBER = r'[-+\u2212]?(?:[0-9]+(?:[,.][0-9]+)*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?'
_GUARD_SCALES={word+suffix for word in MULTIPLIERS for suffix in ['s','th','ths']}
_VOCAB = sorted(set(SMALL)|set(TENS)|set(MULTIPLIERS)|_GUARD_SCALES|{'and','to','or','through','plus','minus','point','dot','half','quarter'},
                key=lambda word:(-len(word),word))
_WORDS = r'(?:'+'|'.join(_VOCAB)+r'|a(?=\s+(?:hundred|thousand|million|billion|trillion)\b))\b'
_FIRST = r'(?:'+'|'.join(word for word in _VOCAB if word not in {'and','to','or','through','plus','minus','point','dot','half','quarter'})+r'|a(?=\s+(?:hundred|thousand|million|billion|trillion)\b))\b'
# Atomic numeric tokens cannot be repartitioned into exponentially many digit
# groups when a role regex subsequently fails to find its requested unit.
TOKEN = r'(?:(?>'+NUMBER+')|'+_WORDS+r')'
_START = r'(?:(?>'+NUMBER+')|'+_FIRST+r')'
_LINK = r'(?:[\s,\-\u2010-\u2014/+*\u00d7\u00f7]+|(?<=[0-9])(?=[A-Za-z]))'
SCALED_PATTERN = r'(?<![\w.])'+_START+r'(?:'+_LINK+TOKEN+r')*'
_RUN = re.compile(SCALED_PATTERN,re.I)
_SCALE = re.compile(r'(?<![A-Za-z_])(?:hundred|thousand|million|billion|trillion)(?:s|ths?)?\b',re.I)


def scaled_runs(text):
    if not _SCALE.search(text):return
    for match in _RUN.finditer(text):
        raw=match[0]
        if not re.search(r'[0-9]',raw) or not _SCALE.search(raw):continue
        start,end=match.span()
        # A sentence conjunction before nonnumeric prose is not part of a count.
        tail=re.search(r'\s+(?:and|to|or|through)$',raw,re.I)
        if tail and text[end:].strip():end=start+tail.start()
        yield start,end
