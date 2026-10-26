# Public ancestor records and source-bound relationship counts

The actual source recovered in `53217fc` was available anonymously but had not
been integrated. Generic JSON flattening used its 3,500-passage budget on
translations before reaching the useful person/relationship record. This
change connects discovered official profile URLs to the observed published
record and adds executable counting of the returned relationship list.

## Retrieval and parsing

`agent/familysearch.py` accepts exact HTTPS official ancestor profile paths
with a locale, person identifier and slug, or exact official published-person
URLs. It derives the API path from the discovered profile identifier; it
contains no person's name, identifier, expected answer or case-specific URL.
The initial profile must have succeeded with matching final identity. The
additional guarded GET consumes an ordinary page slot, uses the original
deadline/cache/body limits and does not start without time or a page slot.
Both direct API starts and profile links found on another page are covered.

Response status, truncation, final host/path, redirects, document shape,
version, main person identifier, official profile URL and schema type/context
are checked before evidence is exposed. Duplicate JSON keys, nonfinite JSON,
private/living/error/removed/forwarded markers and explicit pagination/partial
indicators are rejected. Counts declared beside an array must agree with its
length; nested continuation metadata is not ignored. Relationship links, when
present, must identify their own record rather than another profile.

The adapter renders actual main-person fields, spouse fields and bounded
relationship chunks, plus one requested-locale life summary with English
fallback. Script/hidden HTML filtering is reused on the summary. Translations
do not precede and crowd out the main record. Local parsing allows at most 32
spouses and 128 children; this is a bounded returned snapshot, not a claim of
complete biological history. Invalid collections never yield a valid count.

The actual API URL remains the citation. The original frontend has not rendered
these facts, so it is not relabeled as the evidence source. No key, cookie,
account, browser, billing service or paid wrapper is used. This is the already
observed anonymous public read route, not a claim of unlimited API quotas.

## Count proof

`count_relationships` binds subject, requested partner and every actual
children chunk to source URLs, original parsed evidence and locators. It
counts distinct returned identifiers, filtering `otherParentId` for a uniquely
requested spouse when needed. Duplicate/missing child identifiers, ambiguous
partners, missing other-parent links in a spouse-filtered count, incomplete
chunks and conflicting returned counts block the proof. A total-list question
does not require another-parent identity for every item. Child records from a
different named partner are excluded from the filtered count.

The question's subject must be bound by its literal full name or an exact
starting-profile identity. Unsupported historical, ordinal and qualified
subsets cannot become the unfiltered list size. Wife/husband requests also
require the returned partner's matching gender. The executor counts one source
collection and does not implement aggregation across subjects. Additional
semantic constraints and interpretations still require the model.

The numeric result is computed; no synthetic `childrenCount: 18` or rewritten
source quotation is created. `published: false` alone does not remove an item
that is actually present in this anonymous source. Explicit private/living
markers are handled separately. The actual English prose's **at least**
qualification is preserved; the executor does not erase it or add 7 and 11
from that prose to assert a biological total.

Semantic verification is mandatory, including when arithmetic is valid. It
receives all original ranked contexts and references the full actually sent
collection chunks; subject and selected partner fields must also be present
without clipping. Every relationship remains visible once rather than being
duplicated in proof and context. A missing chunk/context fails before HTTP.
An eighth contradictory context stays in the request. If the resident service
cannot fit this request, it returns `context_limit` before its usual passage
pruning, so proof references cannot survive after their evidence is removed.
The focused count prompt explains the computed operation and its limitations.

## Validation and actual-source replay

Primary receipt: `benchmarks/familysearch-20261024-familysearch-final-v11.json`.
The identical final harness compares isolated `53217fc` and the worktree:
**61/93 -> 93/93**, 32 related assertion wins, zero losses. It contains 60
Engine/HTTP flows, 28 source/packing guards and five direct verification checks.
These are authored and related controls, not 93 independent questions.

Coverage includes profile discovery, direct API, page limits, locale flooding,
zero/one/many/60 records, partner filtering, matching declared counts, invalid
identities/URLs, private/partial/truncated/paginated records, duplicate fields,
forged proof atoms, missing chunks, different source snapshots, wrong question
subsets, unavailable/invalid/rejecting verification and disabled models.
The actual `Runtime.infer` packing path is exercised with an authored string
counter and an uninitialized runtime; no real tokenizer, torch, model or
generation is loaded. Oversized proof requests remain unmodified and fail.
Earlier v1-v10 receipts are retained; only the final identical paired harness
supplies the reported comparison.

One flow replays the exact 169,942-byte frozen published-person body recovered
in the previous turn, with capture and body hashes rechecked. The record is
the father (1706–1782), its spouse identifier matches Elisabeth, and all 18
different returned child identifiers bind to that other-parent identifier.
The production flow now automatically fetches the API from the profile URL,
proposes the collection proof, passes the CPU verifier and returns **18** with
the actual API citation. Previously it abstained. The unchanged qualified
English summary is verified to remain in the model request.

The generic parser formerly produced 3,500 translation passages. The actual
new verification request has five source passages and 3,300 JSON characters;
this is a character measurement, not a tokenizer/context-fit result. The real
model has not been run. This replay starts from the already discovered profile,
not the original Wikipedia start and full question-only discovery. The API
source also differs from that original gold source. Therefore it establishes
an actual-source integration repair, **not** a new competition or joint-score
point. The latest independent first-attempt result remains 0/12 exact/joint.

Regressions pass: reader 15, existing proofs 27, P0 16, header scales 88, shared
excerpts 60, members 28 plus 12 guards, licenses 31, table years 86, population
roles 90, record bindings 11, Oyez 24 plus four HTTP flows, HTTP lifecycle 8.
All 68 original captured HTML responses remain identical under old/current
parsers; two loopback render-spy checks retain existing shell fallback without
launching a browser. Older baselines printed by those drivers are historical
feature comparisons, not additional wins for this feature.

No GPU, real tokenizer/model, browser, new external request, bulk assessment,
gold/alias edit, build, push or submission was used. All primary CPU receipts
record `torch_imported: false`. Original source captures and first assessments
remain unchanged.

## Remaining work

This is a bounded count of returned source relationships, not independently
verified biological history. Unknown relationship schemas, large requests
that cannot fit the full evidence, and arbitrary child subsets remain outside
this operation. Real-model semantics and original-start retrieval still need
measurement when model use is authorized. The general resident packing path
can still prune other operation types; its effect on verification conflicts
and source fidelity needs a separate CPU audit next.
