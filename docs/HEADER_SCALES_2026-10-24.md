# Source-bound table-header count scales

The frozen `40dd82c` probe found that a complete row with cell `4.2` under
`Chairs (millions)` could not yield 4200000. That integer is derived rather
than a contiguous source string, so the literal selector correctly refused
it. Copying only 4.2 was also correctly rejected by the CPU semantic verifier.
The new implementation adds a proof operation instead of relaxing literal
selection or inventing a source phrase containing the expanded number.

## Implementation

`agent/table_scales.py` recognizes explicit thousand/million/billion/trillion
word scales in column labels, with singular/plural and `(in millions)` / `in
millions` forms. It only applies to supported single-count requests. Questions
explicitly requesting scaled output retain the ordinary reader path; a scale
word in an entity's name does not itself request scaled output. As-of requests
do not gain an inferred historical table state.

Header fields must match the requested count field. Literal question-named
cells bind the row at its actual column indices, including unknown identity
labels; this does not depend on a list of entity names or a `Hall` special
case. Multiple identity dimensions are enforced together. Different requested
values in the same identity column cannot become a single-entity answer when
the question asks for a combined count. Existing observation-year, version,
eligibility and source checks still run.

The executor uses Decimal with 80-digit precision, a maximum 50-character
coefficient and nonnegative integral results below 10^15. Zero is supported.
Plain decimal coefficients and comma-separated groups of three digits are
accepted. Ranges, approximations, negatives, fractional results, overflow,
footnote suffixes, ambiguous commas and unknown arithmetic are not coerced.
This is a declared numeric syntax, not universal locale detection.

`scale_table_count` carries three literal premises: column header, scalar cell
and row identity, with actual source, row locator and column keys. Validation
resolves complete original parsed evidence and re-executes the operation. It
also checks all other eligible scaled and ordinary table values on retrieved
pages. Agreeing representations can share the same result; conflicting or
incomplete applicable facts block the proof and bare-coefficient fallback.
This scan is linear and does not stop at the first 64 ordinary rows.

Table captions are retained as actual source metadata, at most 1,100 characters
with an explicit continuation flag. An incomplete caption prevents this proof;
recognized conflicting global scale declarations in captions/headings also
prevent it. Captions do not supply a missing column scale. They are sent once
per source/table only on the new proof path, rather than adding repeated
caption text to every existing reader request.

Semantic verification remains mandatory. The new operation retains all eight
original question-ranked contexts, with the existing 1,100-character passage
cap, and sends literal structured premises and all relevant row identifiers.
It does not evict an eighth contradictory source to show a favored result.
Structured fields let a wide row retain its real identity/header/cell relation
when a long notes column separates them; they are not a fabricated contiguous
quotation. Complete row spans remain in local proof validation, and are not
duplicated three times in the model request. Missing source context is an
evidence failure, not a model-service outage. The resident verification prompt
explains the new operation; actual model behavior has not been measured.

## Verification

Primary receipt: `benchmarks/header-scales-20261024-paired-final-v13.json`.
The same final harness runs against isolated `40dd82c` and the worktree:
**35/88 -> 88/88**, 53 related assertion wins, zero losses. It contains 49
authored Engine/HTTP flows, 34 arithmetic/source guards and five direct HTTP
verification controls. These are not 88 independent questions or ML accuracy.

Controls cover four scales, zero, grouped coefficients, column reordering,
ordinary integers, equivalent/conflicting duplicates, observation years,
versions, explicit scaled output, malformed/incomplete/qualified values,
caption conflicts/continuation, long rows, multiple row constraints, multiple
subjects, different pages, 70-row conflicts, forged sources/columns/roles/
identities/spans, rejected/invalid/unavailable verification and model-disabled
fallback. A verifier that decides from the eighth contradictory context
rejects the proof. The historical two-premise serializer raises ValueError
for the new operation in direct helper controls; the receipt records that
unsupported-operation exception, rather than claiming historical support.
Earlier v1-v12 pilot receipts remain; assertion counts changed during
development, so only the final identical paired harness is the primary result.

CPU regressions pass: reader 15, existing proofs 27, source excerpts 60,
P0 16, members 28 plus 12 source guards, licenses 31 plus 72 expression guards,
table years 86, population roles 90, cardinal counts 101, magnitude counts 103,
grouped numbers 165, field groups 42, first lines 22, selector boundary 10 and
cooperative HTTP lifecycle 8. Syntax compilation and diff checks pass.
Regression drivers with older baselines print their earlier feature wins;
those are not additional wins for this change.

## Actual saved-source coverage and limits

`eval/audit_header_scale_sources.py` verifies all 24 original capture hashes
against the two exposed first-attempt manifests. It inspects 152 distinct
nonempty content bodies, parsing 78 HTML bodies with 328 table rows. It finds
**zero** headers with these scale words. The receipt is
`benchmarks/header-scales-20261024-saved-source-audit-v1.json`.
Therefore this feature does not establish a gain on those already exposed
questions. The latest independent first attempt remains 0/12 exact/joint.

This is explicit column-scale arithmetic, not general unit inheritance,
arbitrary table reconstruction, aggregation or semantic proof of an entire
page. Unknown caption/header conventions still require other work. Context
limits may prevent the real model from using a large request; CPU stubs do not
measure that. The next priority is an actual exposed failure lacking its
answer source, rather than treating these synthetic wins as real-score gains.

No GPU, model/tokenizer load, browser, external request, paid API, gold/alias
edit, new assessment question, build, push or submission was used. Both primary
receipts record `torch_imported: false`. The frozen initial header probe and
all original assessment artifacts remain unchanged.
