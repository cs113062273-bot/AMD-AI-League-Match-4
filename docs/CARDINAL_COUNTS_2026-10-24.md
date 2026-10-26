# Derive integer counts from complete English source numerals

Numeric questions previously rejected literal English numerals at the type
guard. A copied `four` could not pass, and a model-produced `4` could not be
bound to source text containing only `four`. The saved Layton biography
really contains “first of four children”; the project had fetched its body
successfully. That source, rather than an unavailable answer page or a gold
value, supplies the real-source development premise for this change.

## Behavior

`agent/cardinals.py` implements bounded English integer grammar: zero through
nineteen, tens and compound units, hundreds, and descending thousand,
million, billion and trillion groups. It supports conventional conjunctions,
tens-unit hyphens, scale commas and `a hundred`/`a thousand` forms. The
largest representable value is 999,999,999,999,999. This is arithmetic
vocabulary, not a mapping from entities or questions to answers.

For explicit single-count requests, extraction and selection retain the
actual source words as `Candidate.raw`, while `Candidate.answer` contains
their computed decimal integer. The mechanical verifier independently
recomputes that value, requires exact equality and a complete licensed
source span, and ignores forged projection signals. Structured field values
must license the words themselves; a different JSON child's parent context
cannot supply them. Existing row/column, year, source and role constraints
remain in effect. Population role matching now recognizes source word spans
with their original offsets, without rewriting the evidence into digits.

Both the resident reply validator and client selector can bind a model's
decimal integer to one uniquely matching visible word span. Multiple matches
cause abstention rather than an arbitrary binding. Requested count nouns
may be removed only with actual matching source text. A complete numeral is
not mistaken for a removable unit. Ordinary text/version copying remains
unchanged, and the old generic normalizer has not gained word aliases.

Trace data records the selected span, source words and computed value.
Independent semantic verification receives the integer proposal, the actual
source and explicit `english_cardinal` normalization metadata. Arithmetic
does not establish which entity, field, year or quantity the question asks
for; semantic rejection or service failure still yields an empty answer.
The new helper is included in resident-backend source hashes.

The grammar does not derive fractions, ordinals, signed values, arithmetic
expressions, approximate quantities, ranges or mixed digit/word quantities.
Conservative context guards reject the tested forms rather than normalize
a smaller fragment of them. This is not universal English numeric-language
understanding. Unsupported syntax still needs abstention or a future
explicitly supported operation.

## Complete source boundaries

Numeral words need more than a character/word boundary: `one` is not the
count in `one hundred`. The scanner uses maximal runs and requires the
whole grammatical number. A truncated `one hundred…` also cannot establish
100. HTML paragraphs, plain-text segments and clipped JSON scalar values
now carry source-continuation metadata. Count words at an unfinished edge
are rejected; the complete count remains selectable from an overlapping
later segment where available. The fact's actual parser metadata is used,
not metadata asserted by a candidate or model.

## Verification and limits

The final identical-diagnostic pair is
`benchmarks/cardinal-counts-20261024-before-v9.json` and
`benchmarks/cardinal-counts-20261024-after-v10.json`:

- Baseline `5ed15b2`: **68/101** assertions.
- Current code: **101/101**, 33 improved assertions and no losses.
- These include grammar, source/type/field binding, forged answers, numeric
  fragments, observed qualifiers/fractions/ranges/operations, source clipping,
  population roles, protocol binding/selection, and actual loopback HTTP selection
  followed by independent CPU semantic stubs.
- HTTP positives retain literal words and emit verified integer strings,
  including zero, 21 and 1005. Rejection, unavailable verification, conflicting
  bindings and unsupported quantities still abstain. Text/version values and
  grouped Arabic counts are retained.

These are related development assertions, not 101 questions or a model
accuracy score. Some improved assertions concern protocol binding or the
ability to reach semantic verification, not different final answers. The
saved-source check uses an authored count question on the already exposed
biography; it is not a new independent sample, and it does not change the
original city question's result. Its immutable capture/body hashes are in
the report. No gold or answer aliases are consulted by production.

Earlier attempts are retained. The first omitted the existing population
count-intent form and failed its positive control; that was corrected.
Additional controls cover incomplete source segments, field-owned values,
unit handling, fractional suffixes and arithmetic/range boundaries. Final
baseline and current results use the same expanded harness and source
hashes. No earlier subset result is pooled into the final comparison.

CPU regressions retain P0 16/16, reader 15/15, proofs 27/27, selector boundary
10/10, population roles 90/90, table years 86/86, grouped numeric boundaries
165/165, paragraph boundaries 24/24, first lines 22/22, named-year 12/12 and
month-request 14/14 and HTTP cancellation lifecycle 8/8. The lifecycle run calls only its cooperative
CPU `http_probe`, not its separate tiny-model generation function. Historical
comparison wins printed by those drivers belong to earlier work.

One existing, separate limit remains reproduced in
`cardinal-counts-20261024-next-magnitudes.json`: both baseline and current
mechanical guards accept the Arabic prefix `4` from `4 hundred`/`4 million`.
Pure word-cardinal support does not fix that existing magnitude boundary;
the probe is kept as the next quantity task, outside the 101 assertions.
This observation concerns local evidence guards, not an actual model error.

The previously exposed Füssli children-count case still lacks a successfully
fetched count-bearing body. This change does not supply its answer, repair
that missing source, or prove a new competition point. The latest retained
external first-attempt score remains 0/12. Unseen-question and real-model
gains remain unmeasured.

No GPU, model/tokenizer load, browser, public source/API request, paid service,
assessment sweep, Docker build, push or submission was used. Frozen
questions, gold, aliases and original results remain unchanged.
