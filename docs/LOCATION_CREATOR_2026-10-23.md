# Preserving location and reading creator evidence in actual failure 2010

The old concise query `sculptor of ceres sculpture` discarded the requested
Belvoir Castle location, retrieving other sculptures of Ceres and Pajou.
The first public probe verifies that adding the original location terms finds
the exact Historic England listing and its mirrors. Other tested proposals
and failed requests remain in the probe/variant reports; none supply answers.

After choosing an already-valid model hint, discovery now preserves a single
explicit multiword location introduced by in/at/near/within. It adds only
missing original words, bounded by eight words/120 characters. Multiple
different locations, quoted text, negated places, one-word names and overflow
retain the existing hint. No year or artist name is added. On the eleven saved
hint sets, only this case changes relative to revision `3f3a4b9`.

Actual current discovery finds the exact record. Historic England and the
original source return 403; WRENN initially timed out in an independent probe,
but the subsequent current discovery run obtains HTTP 200 and a full paragraph
naming Ceres, Belvoir Castle, around 1680 and Caius Gabriel Cibber. The earlier
failures are retained. The Geograph photo caption disagrees on the year (1660)
and is not treated as complete evidence for the original question. Independent
public council PDF and Lincolnshire heritage records support the artist/1680
association; these manually discovered URLs were not injected into search.

The first current payload still missed the answer: WRENN's paragraph ranked
28th behind landmark metadata and location fields. Ranking now favors a
visible explicit creator relation for an explicit creator question. For
example, a sculptor request can favor `created/sculpted/carved by`; an architect
request favors `designed by`, and an author request `written/authored by`.
This is a ranking bonus, not semantic proof. It does not change source text,
delete metadata, or relax verification. Numeric/composed requests, JSON parent
contexts, a different requested output, and negated attribution get no bonus.

`benchmarks/location-creator-20261023-replay-v2.json` compares exact same,
SHA-verified old/new HTTP captures, with zero missing responses. Before never
retrieves the creator paragraph; after does. On the same new article, the
paragraph moves from rank 28 to rank 1 and is fully transmitted. A literal
selector stub copying the artist name passes the ordinary source guard.

The first control run exposed an embedded `who created` clause inside a
material question receiving an inappropriate boost. The `who` request now has
to start the planner's actual request focus. That failed v1 report remains;
the final sixteen controls pass. Named-year recovery, reader (15), proof (27),
hint (20 plus six captured responses), discovery (7) and literature retrieval
with the rank-65-to-1 age evidence retain their passing checks.

No GPU, model or browser was started. This establishes corrected discovery and
reader input, not a final model answer or strict joint-score improvement. The
gold answer/source and all scoring rules remain unchanged. New live source
availability, including WRENN, is not guaranteed by a frozen replay.
