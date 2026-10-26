# Bind complete scaled quantities and compute exact integer counts

The previous source guard accepted the coefficient `4` from `4 million` or
`4 hundred`. A permissive semantic verifier could therefore authorize an
answer smaller by the missing multiplier. Copying `4 million` also retained
that literal representation, while a model reply of `4000000` could not bind
to a source containing only the scaled phrase.

## Change

`agent/number_atoms.py` identifies complete source runs carrying magnitude
words. The existing numeric literal guard now rejects interior/prefix/suffix
fragments of those runs, while continuing to search for a later independent
occurrence. Text and version matching retain their prior behavior. The
lexical guard also covers ambiguous or unsupported runs; finding such a run
does not make it arithmetically valid.

`agent/magnitudes.py` performs bounded exact decimal arithmetic for complete
integer counts, using spelled hundred/thousand/million/billion/trillion
multipliers. Examples include `4 hundred` to `400`, `1.25 million` to
`1250000`, and descending components such as `4 million and 200 thousand`
to `4200000`. Mixed English/numeric components reuse the existing word
grammar. Coefficients can use valid comma grouping, leading decimals or
bounded scientific notation.

Arithmetic uses an 80-digit Decimal context, bounded coefficient length and
exponent, descending nonoverlapping groups, and an exactly integral result
below 10**15. It does not round a noninteger result into an answer. Ambiguous
decimal commas, unsupported syntax, fractions and approximate/range
expressions do not gain a fabricated integer projection. Existing literal
forms can remain copyable where their prior type rules permit; an
unsupported expression is not silently interpreted as a new operation.

The English-count pipeline retains the complete source phrase as raw
evidence, emits the computed integer for supported count requests, and
independently recomputes it during verification. All count candidates must
now agree with their permitted normalization, including ordinary literal
forms. This closes the old ability to attach an arbitrary integer answer to
an otherwise literal unsupported count. Projection signals are not trusted.
Actual structured field values must license the phrase themselves.

The client and resident protocol both bind a computed reply only to a
unique visible complete source phrase. Independent semantic verification
still checks entity, relation, field, units, year and other constraints; it
receives explicit `scaled_integer` metadata rather than being told that
arithmetic proves the question. Population role matching uses the complete
source quantity and its original offsets, so a scaled household count or
another year's population cannot bypass existing role checks.

A plain numeric coefficient whose only source occurrence is at an unfinished
count-segment edge is also rejected using actual parser continuation
metadata. A later overlapping segment containing the complete scaled count
remains available. Existing complete literal ranges, grouped numbers,
dates, versions, scores and unrelated later occurrences are retained by the
focused controls.

The lexical scanner uses atomic numeric tokens to avoid repartitioning
long digit runs during failed role matches, and quickly skips text without
a relevant magnitude word. The two new modules are included in resident
backend source hashes. No dependency, source API or answer catalog was added.

## Evidence

The identical final diagnostic pair is
`benchmarks/magnitude-counts-20261024-{before,after}-v7.json`:

- Baseline `496aa9f`: **27/103** assertions.
- Current code: **103/103**, 76 improved assertions and no losses.
- Many assertions repeat the same lexical counterexample across numeric
  types. They are not 103 independent questions or 76 recovered answers.
- Actual loopback HTTP with CPU semantic stubs demonstrates prefix rejection,
  complete phrase/decimal-reply normalization, descending components,
  semantic rejection, ambiguity, and unsupported qualified/range cases.
- High-precision noninteger coefficients, malformed grouping, huge exponents,
  ascending scales, overflowed components, source clipping and forged
  normalized answers have separate controls. A complete literal range is
  retained without being converted into a scalar.

The first harness used an ASCII score hyphen for a legacy positive whose
existing literal rules treat it as a sign. It was corrected to the en-dash
form used by the existing real-score regression; no sign guard was weakened.
The first implementation also missed a second quantity after a sentence
conjunction, making reverse binding look unique. The scanner now starts at
a numeral rather than that leading conjunction. Earlier artifacts remain
preserved; the final pair uses identical harness bytes and production hashes.

The saved-source audit inspected only the **24 already exposed** first-attempt
captures, with 150 distinct readable response bodies, excluding discovery
pages and deduplicating identical bodies. It made no network requests or
new assessment. The official Census HTML actually contains a qualified
`19 million` sampling count. Its original frozen capture hash is verified;
the new guard rejects `19` while retaining the complete literal phrase.
This national sampling statistic is not the original city's population, and
does not supply an exact city answer. Two other audit hits were marketing
metadata on already captured login pages and are not used as answer evidence.

Final existing CPU checks pass: English cardinals 101/101, P0 16/16, reader
15/15, proofs 27/27, selector boundary 10/10, population roles 90/90, table
years 86/86, grouped boundaries 165/165, named-year 12/12 and HTTP
cancellation 8/8. Historical comparison wins reported by those drivers are
not new wins of this patch. A separate owned-child malformed-source regex
probe completes in about 0.15 seconds under a three-second cap; this is a
bounded robustness check, not an end-to-end speed claim.

Arithmetic/source boundaries do not resolve arbitrary prose ambiguity,
units supplied only by a separate header, or every numeric notation. The
original missing biographical source remains unresolved. No actual model
or unseen-question gain has been measured; the retained latest external
first-attempt score remains 0/12.

Frozen questions, gold, aliases and original results remain unchanged. No
GPU, model/tokenizer load, browser, paid API, new public request, bulk
assessment, Docker build, push or submission was used.
