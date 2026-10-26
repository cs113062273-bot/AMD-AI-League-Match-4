# Empty JavaScript body in actual failure 1013

The saved FamilySearch response has an empty `body` after removing scripts,
noscript notices and hidden compatibility warnings. The old dynamic-page
heuristic counted the notices before cleanup (over 250 characters), and five
generic metadata passages prevented the renderer fallback.

The parser now promotes a completely empty cleaned HTML body with active
scripts to `dynamic`. It does not promote truncated responses or pages with
embedded JSON data. No source facts, links or passages are replaced.

`benchmarks/empty-shell-20261023.json` compares revision `a4f3460` with the fix:
68 distinct captured HTML responses retain all original extraction, errors and
links; only the two saved versions of the affected FamilySearch URL change
classification. Actual loopback HTTP with a render spy changes fallback calls
from zero to one when enabled, and keeps zero when disabled. Five controls
cover readable articles, embedded data, truncation and absence of active JS.
No browser, model or GPU was started.

Public source investigation is retained in the children probe, sources and
access reports. Three question-only Lite queries found alternate URLs, but
their actual bodies were blocked, login pages or lacked the requested count.
Wikipedia's three official read endpoints also returned 403. These failed
probes are not evidence of a repaired answer.

An independent web lookup reads the [FamilySearch profile](https://ancestors.familysearch.org/en/9MF8-T95/johann-caspar-f%C3%BCssli-1706-1782)
and shows `Children (18)`. The project HTTP client still obtains only its JS
shell. The browser fallback is repaired, but no end-to-end answer or score gain
has been verified. Frozen benchmark gold is unchanged.
