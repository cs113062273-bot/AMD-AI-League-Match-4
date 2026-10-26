"""Bounded, query-dependent slices of actual evidence, shared by both readers.

Window choice never sees a proposed answer. Offsets refer to the original
parsed passage; no facts or ellipses are inserted into its text.
"""
import re
from collections import Counter

from .cardinals import lexical_runs
from .planner import STOP

LIMIT = 1100


def excerpt(plan, passage):
    text=passage.text
    if len(text)<=LIMIT:return text,0,len(text)
    # Never make a new apparent word/quantity at either edge of a slice.
    atoms=list(lexical_runs(text))
    tokens=list(re.finditer(r'\S+',text))
    starts=[m.start() for m in tokens if not any(a<m.start()<b for a,b in atoms)]
    ends=[m.end() for m in tokens if not any(a<m.end()<b for a,b in atoms)]
    words=list(re.finditer(r'\w+(?:[.+#-]\w+)*',text,re.UNICODE))
    terms={m[0].casefold() for m in re.finditer(r'\w+(?:[.+#-]\w+)*',plan.question)
           if m[0].casefold() not in STOP}
    hits=[m for m in words if m[0].casefold() in terms]
    frequency=Counter(m[0].casefold() for m in hits)
    desired={0,max(0,len(text)-LIMIT)}|{max(0,m.start()-LIMIT//3) for m in hits}
    windows=set()
    for offset in desired:
        start=next((s for s in starts if s>=offset),None)
        if start is None:continue
        end=max((e for e in ends if start<e<=start+LIMIT),default=start)
        if end>start:windows.add((start,end))
    if not windows:return '',0,0

    def score(window):
        start,end=window
        # A matching entity at a clipped edge is insufficient. Reward hits
        # with their following context, or all text through the source end.
        visible={m[0].casefold() for m in hits if start<=m.start()
                 and m.end()+min(96,len(text)-m.end())<=end}
        return sum(1+1/frequency[t] for t in visible),end-start,-start

    start,end=max(windows,key=score)
    return text[start:end],start,end
