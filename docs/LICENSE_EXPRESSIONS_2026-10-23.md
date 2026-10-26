# Preserve complete license fields after a partial semantic selection

The historical crates.io fix supplied the correct dated release field, but a
CPU selector returning `MIT` from `MIT OR Apache-2.0` could still produce a
verified fragment. The independent verifier was deliberately always-positive
in that diagnosis. Source/date binding alone did not preserve field completeness.

The [SPDX expression specification](https://spdx.github.io/spdx-spec/v2.3.1/SPDX-license-expressions/)
defines combinations using AND, OR, WITH, a plus suffix and grouping. Those
operators and identifier suffixes cannot be discarded when reporting the
complete declared field. This change copies a bounded literal source value;
it does not evaluate legal equivalence, reorder operators, substitute aliases,
or embed a license/exception catalog.

- Recognize scalar license/expression fields and uniquely labeled table
  columns. Parse bounded SPDX-shaped identifiers/references, exceptions,
  grouping and operators. Operator case and spacing matter. Unknown identifiers
  can be copied as declared metadata; grammar recognition is not a claim that
  an identifier belongs to an official SPDX list.
- For a whole-field question, a selected operand, subexpression or literal
  identifier prefix can recover the complete field. This also preserves single
  identifiers such as `GPL-2.0-only` when the model selects `GPL-2.0`.
  Operator-only selections and non-prefix identifier fragments do not trigger
  recovery. Every recovered answer remains an exact normalized source span.
- The full value must fit the existing 350-character answer bound and appear
  within the selected passage's transmitted 1,100-character view. Overlong
  recognized fields reject incomplete candidates rather than overflowing output.
- JSON's repeated parent context sometimes makes a model select a license
  fragment from a `name` passage. Resolve only actual license sibling fields
  at the same parsed record path and source. Do not borrow a child, neighboring
  record or different page. Rebind evidence to the actual license passage,
  recording the original selection, original locator and target field locator.
  The source-field index is per page and invalidates when passages are added.
- Actual parsed facts govern the candidate check. Candidate-supplied field
  values or qualifier dictionaries cannot make a fragment complete. Both the
  raw candidate and returned answer must preserve the required field value.
  Conflicting duplicate license columns are unresolved rather than selected by
  DOM order. Literal, table, entity, time and version checks remain in place.
- The normal model path independently verifies the recovered full answer, not
  the original fragment. Rejection, service failure and reader abstention do
  not become deterministic model-path answers. The existing model-disabled
  source-bound path can still return the complete literal field.
- Explicit component/option/exception/identifier/count requests and yes/no
  questions are excluded from whole-field recovery. These and ordinary unlabeled prose retain their existing read
  path. The intent rules are bounded English patterns, not universal language
  understanding. Arrays, unsupported expression syntax and competing authority
  between different licensing fields are not resolved by this patch.

## Evidence

`eval/diagnose_license_expressions.py` uses authored sources over loopback HTTP
with explicit CPU semantic stubs. Final paired `before-v3.json` and
`after-v6.json` under `benchmarks/license-expressions-20261023-*` share the
diagnostic SHA: **9/31 to 31/31**, 22 improved controls and zero losses.
They cover JSON/nested JSON, SPDX declared/concluded keys, definition lists,
inline fields, table rows, custom references, unary/binary operators, source
grouping, complete/single identifiers, subquestions, duplicate columns,
semantic rejection/unavailability, reader abstention and no-model behavior.
These are related development controls, not 31 independent questions.

The first implementation passed the original 21 controls. Expanded testing
exposed the repeated JSON-parent context issue (28/29), then single-identifier
suffix/family loss (29/31); those attempts remain saved. The early family-prefix
control required abstention. The final policy requires the complete source
field instead: it recovers valid literal identifier prefixes under the same
whole-field intent, rather than treating abstention as the final objective.
The final paired baseline was rerun with exactly that final diagnostic.

`eval/diagnose_license_expression_guards.py` passes **72/72** separate direct
syntax/source/intent assertions. Its first run exposed an unrecognized explicit
license count (71/72); the bounded intent rule was corrected. These assertions
are not added to the HTTP control count or treated as an accuracy percentage.

`eval/diagnose_license_capture.py` verifies and replays the exact saved official
`itoa` response from the previous change, with zero new public API calls.
Final `capture-replay-v2.json` checks 16 baseline/current behaviors. The
baseline's partial-selector outputs are `MIT` or `Apache-2.0`; the updated
whole-field outputs are `MIT OR Apache-2.0`, preserving version 0.4.5 and its
2020-01-24 publication context. Option-only questions, rejected verification,
unavailable service and abstention retain their expected behavior. The 16
assertions describe replay behavior, including baseline failures; they are
not 16 correct answers or a held-out score. No actual resident model was run.

Final CPU regressions pass: crates history 49/49, PyPI/npm metadata 43/43,
GitHub history 45/45, reader fixtures 15/15, proof checks 27/27, selector ID
boundary checks 10/10, P0 checks 16/16 and assessment-input isolation 7/7.
The selector boundary comparison uses its own older baseline; its historical
wins are not wins of this license change. No gold, alias or frozen first
attempt was edited. No GPU/model load, browser, paid service, public API
request, full benchmark sweep, build, push or submission occurred this turn.
The latest retained external first-attempt accuracy remains 0/12, unrerun.

## Next diagnosis

Return to the actual exposed failures rather than treating these controls as
overall competition progress. `next-failure-triage.json` records a read-only
review of the latest first-assessment reasons and source hashes. Several of
its retrieval/intent failures already have later CPU fixes and cannot be
counted again. One actually verified answer, `simpleqa-911`, selected a school
name including the lowercase descriptor `former`. Diagnose name boundaries
generally, preserving proper titles and status-sensitive questions, before
changing that behavior. No case-specific name or scoring alias is authorized
as a production fix; any such work is exposed development, not a new holdout.
