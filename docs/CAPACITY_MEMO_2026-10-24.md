# Avoid resubmitting identical capacity-rejected evidence

The previous recovery fix allowed navigation after `context_limit`, but a
newly fetched irrelevant page could leave the first eight reader contexts
unchanged. The engine then submitted exactly the same oversized selection
payload again. This spends another HTTP admission and resident packing pass
without providing new evidence.

The model client now records exact capacity refusals on the query's `Deadline`.
The memo key includes the configured endpoint, operation path and SHA-256 of
the complete serialized request. Serialization occurs once, and those frozen
bytes are sent, preserving source whitespace and JSON key order. Only an HTTP
200 reply exactly equal to `{"error":"context_limit"}` is recorded, for
`/select` and `/verify`. Other errors, timeouts, cancellation, abstention and
semantic rejection are not memoized. At most sixteen keys are retained; no
source text, answers or model decisions are cached.

Each `Engine.run` creates a new deadline, so another question starts empty.
Changed text, sources, locators, constraints, proposed answers, proof data,
context order, endpoint or operation produces a new request. Existing query
and call budgets take precedence over a memo hit. The resident capacity is
fixed at runtime startup; this bounded query-local memo assumes that capacity
does not change in the middle of one query. A reconfigured/restarted service
can be tried on the next query.

The trace adds `model_capacity_skips` when a duplicate refusal is reused.
Existing `llm_calls` remains a count of logical reader/navigation attempts;
it is not changed into a physical HTTP count. The paired diagnostic measures
physical requests directly at its local HTTP endpoint.

## Verification

Primary receipt: `benchmarks/capacity-memo-20261024-paired-final-v4.json`.
Identical harness, isolated baseline `bec782c`: **18/23 -> 23/23**, five related
control wins and zero losses. These are protocol controls, not independent
factual questions or new answer-score points.

The complete engine case fetches the initial page and an irrelevant linked
page under the original page/depth limits. Its unchanged oversized reader
request is sent twice before the fix and once afterward; both versions
correctly abstain. A second complete case continues to a third page with new
evidence, then selects and independently verifies its literal answer: four
physical model requests before, three afterward, with the same answer/source.
Thus the observed change saves redundant admission work; it does not establish
an accuracy gain or a real-model latency measurement.

Other controls retain requests after changing the deadline, endpoint, path,
JSON order, source spacing, source locator, a same-size source string, proof
data or a conflicting context. Exact selection and verification refusals are
reused. The sixteen-key bound, budget precedence, cancellation and timeout
behavior are also checked. Intermediate probe/pilot receipts are retained but
are not pooled into the final comparison.

CPU regressions pass: capacity navigation 13, busy/admission 30, proofs 27,
P0 16, reader 15, public relationship counts 93, source excerpts 60, resident
packing fidelity 21 and cooperative HTTP lifecycle 8. Their historical
before/after comparisons are not new wins for this patch. Primary and
lifecycle receipts record `torch_imported: false`; no real model is loaded.

## Remaining work

The full evidence still must fit before a genuine model read can succeed.
This optimization does not shorten evidence, stage a long read, improve source
discovery or establish model semantics. The saved game-source payload audit
remains source-coverage evidence only. Latest independent real first-attempt
accuracy remains 0/12 exact/joint, and competition readiness is unproven.

No GPU, real model/tokenizer, browser, external request, new assessment rows,
gold/alias/scorer edit, build, push or submission was used.
