# Reprioritize pending sources after repeated content refusals

Search already lowers the rank of hosts that failed before discovery. It
cannot see refusals that happen after its result list has been returned.
The engine could therefore spend both remaining fetch batches on eight
refused URLs from one origin, leaving an available alternate source pending
until the page/depth limits ended the query.

After navigation, discovery reserve and queue refill, the engine now uses the
actual content fetch events to reconsider that pending order:

- An origin needs HTTP 403 responses for at least two distinct canonical
  content URLs, and no successful HTTP 200 content response in this query.
  A single protected resource does not establish a source-wide problem.
- Standard search requests and configured provider requests do not count as
  content refusals. Observe the final origin after redirects. Scheme/host/
  port retain normal URL-origin semantics, including default-port handling.
- Keep an explicit model navigation target first, then preserve the existing
  order among other unrefused origins, then among refused origins. Retain
  every deferred URL and its original label and bytes, including signed URLs.
- Keep the same batch size, attempted-URL deduplication, page cap, depth cap
  and deadline. No new query, source, API, citation or answer is manufactured.
  The source still must be fetched, parsed and verified normally.
- This is a per-query ordering preference, not a permanent domain blacklist.
  A known readable origin keeps its original priority. When only same-origin
  candidates remain, they remain usable. HTTP 404 and 429 receive no new policy
  from this helper; it does not claim to implement rate-limit cooldowns.

The heuristic changes which source can fit inside a fixed budget. It cannot
guarantee every later same-origin resource will fail, nor that every alternative
will answer. Requiring multiple distinct refusals and retaining successful
origins and navigation choices limits that tradeoff; real-web accuracy still
needs independent evaluation.

## Evidence

`eval/diagnose_origin_recovery.py` uses actual loopback HTTP with three distinct
origins and an explicit CPU semantic endpoint. Final paired `before-v3.json`
and `after-v5.json` under `benchmarks/origin-recovery-20261023-*` share the
diagnostic SHA: **7/8 to 8/8**, one recovered control, zero losses. These are
related development controls, not eight independent web questions.

In the recovered case both runs make nine content requests. Before, all eight
post-root attempts return 403; the answer source is never fetched. After,
the second batch includes the alternate source, and the literal phone field
passes the independent CPU-stub verification. Same-origin public-resource
recovery, resource-specific 404, page/depth caps, missing alternatives and
semantic rejection remain covered.

The initial harness placed a ninth candidate in one provider response, beyond
the search parser's eight-link cap. That did not actually test a pending
alternative and both first runs remained 6/7. The corrected harness has a
second query contribute the alternate result. Both baseline and current were
rerun; all original attempts remain recorded.

The first one-refusal policy passed those seven controls but failed an added
counterexample (7/8): one protected URL displaced a readable same-origin
answer under the fixed budget. The final policy requires two distinct
refusals and excludes origins with a successful content read. It preserves
that answer and passes all eight controls. This is why the initial policy
was not promoted unchanged.

`eval/diagnose_origin_policy.py` passes **20/20** separate direct invariants:
source retention, batch bounds, explicit navigation targets, one/duplicate
refusals, successful reads before/after refusals, provider exclusion, final
redirect origins, scheme/port identity, signed URL preservation, malformed
events and empty frontiers. These are not additional accuracy questions.

Final existing discovery checks pass: queue 6/6, discovery/navigation 7/7,
reserve 7/7, and the existing exact saved-body village replay retains answer
219 with zero missing captures. That replay compares its own older baseline
`ed6436c`; its previous improvement is not a new win of this change. Core CPU
checks (P0 16/16, reader 15/15, proofs 27/27, assessment isolation 7/7) also pass.

## Investigations not promoted

The [name-boundary proposal](NAME_BOUNDARY_PROPOSAL_2026-10-23.md) had green
authored controls but no strict real-replay gain. Its production changes were
removed; name handling, frozen gold, aliases and scoring remain unchanged.

Two actual public, keyless Wikimedia read probes returned HTTP 403 in this
project client; see `benchmarks/wikimedia-rest-20261023-probe-v1.json`. Both
responses were recorded, without retries, credentials or accounts. No new
Wikimedia fallback was installed. The official [MediaWiki REST reference](https://www.mediawiki.org/wiki/API:REST_API/Reference)
documents page HTML access, while the [API Portal migration notice](https://wikitech.wikimedia.org/wiki/API_Portal/Deprecation)
describes the Core API's transition. Documentation and a separate browsing
tool's access do not establish reachability from this runtime.

No GPU/model load, browser, paid API, full assessment sweep, build, push or
submission was used. The only public project-client requests this turn were
those two denied read probes. No new real-model or unseen score is claimed;
the latest retained external first-attempt result remains 0/12.
