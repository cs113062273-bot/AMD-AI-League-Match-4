# Actual exposed-case source recovery: published ancestor data

This follows the original exposed 1013 question, not a new assessment. It does
not modify production, questions, gold, aliases or the frozen first attempt.
Header-scale production is already committed as `3f74e3c` and is unrelated to
the following source recovery.

The original FamilySearch HTML contains no child records or count. Its actual
script references identify a main bundle and a shared bundle. Public static
asset reads through the project client obtained the 206,657-byte main bundle
and the 2,399,593-byte shared bundle. The shared bundle first exceeded the
default body cap; a second development read used the fetcher's existing 8 MB
hard override based on that deterministic `body_limit`. Production settings
were unchanged. No previous 403, certificate error or timeout was retried.

Receipts are `benchmarks/family-source-assets-20261024-v1.json` and `-v2.json`.
Raw envelopes are retained at their recorded ignored research paths. Scripts
were inspected as text, never executed. Page keys, cookies and tokens were
not used. Only public routing configuration was read.

The main bundle declares `/service/tree/tree-data` and actually constructs
`${base}/published/persons/${personId}`. The original HTML's `SERVER_DATA.baseUrl`
is `https://www.familysearch.org`; the profile identifier comes from its already
discovered official profile URL. This provides an observed read path rather
than an invented API endpoint or a gold-derived source URL.

One anonymous project-client GET of
[the published person record](https://www.familysearch.org/service/tree/tree-data/published/persons/9MF8-T95)
returned HTTP 200, 169,942 bytes, no truncation or error. No API key, account,
payment details, paid wrapper, login or challenge bypass was used. This is an
observed public page read path; no general pricing, quota or unlimited-use
policy is claimed.

`benchmarks/family-published-20261024-probe-v1.json` records the raw envelope
and body hashes and the discovery bundle hash. The envelope is
`research/family-published-20261024-probe-v1/0.json` (ignored). The source body
SHA256 is `d1f7fe4b187dd89db72cfba70164ab378a60a42b17da2384930f456fb9175aeb`.

## What the actual body establishes

`benchmarks/family-published-20261024-audit-v1.json` verifies the capture and
bundle hashes and records the relevant structure:

- Root keys are `localizedData`, `person`, `version`.
- The main person identifier is `9MF8-T95`, name Johann Caspar Füssli,
  birth `+1706-01-03`, death `+1782-05-06`, with the matching official profile
  URL. This identifies the requested father, not the previously fetched son.
- The spouse is Anna Elisabeth Waser, identifier `LY1P-YNW`.
- The actual children array has 18 distinct nonempty identifiers. All 18
  `otherParentId` values equal that spouse identifier.
- Eight child records have `published: true` and ten have `published: false`.
  Both sets are present in the anonymous response. Do not infer that this flag
  means a record should be removed from the source's listed relationship count.
  Its broader meaning has not been established.
- The English life summary says **at least** 7 sons and 11 daughters. That is
  qualified prose, not an exact contiguous literal answer of 18. Do not erase
  `at least` or claim an exact biological total on its basis. Counting the
  complete listed records for a particular spouse is a separate proof task.

The published list is a source record, not independently verified biological
history. These observations establish source availability and provenance, not
a real-model answer or a score improvement.

## Confirmed remaining runtime gaps

The current generic parser reaches its 3,500-passage cap on this actual body.
Its top eight ranked passages are `localizedData.*.lifeSummary` in different
languages; the main relationship collection is not usable as a bound count.
The audit retains the actual current serialized payload. Recovering this
response manually therefore has not integrated the missing facts into the
question-only production pipeline.

Next work should adapt only validated official profile URLs and matching
published-person JSON, inside existing fetch/deadline/page limits. Reject
wrong identifiers, cross-origin redirects, error/private/partial/truncated
data and unrelated shapes. Keep the actual API URL as the source; the original
HTML has not rendered these facts, so do not relabel the citation as frontend.
Select the actual main record and relevant locale without translation flooding.

A count needs executable source-bound collection semantics: distinct actual
child identifiers, a complete bounded array, correct parent/spouse identity
and `otherParentId` binding. Missing/duplicate/ambiguous relationships cannot
be guessed. Any numeric count is computed, not a fabricated literal source
quote. Generic authored variants and a frozen real-body replay need independent
semantic verification. Do not hardcode this person's name, identifier, answer
or source into production. Do not claim gold-source equality or a new holdout.

No GPU, model/tokenizer load, browser, bulk assessment, build, push or submission
was used. Raw responses, first assessment captures and expected answers were
not overwritten. The automatic adapter and count proof remain unimplemented.
