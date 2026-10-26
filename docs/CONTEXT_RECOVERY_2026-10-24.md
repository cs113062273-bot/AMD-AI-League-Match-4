# Evidence capacity and navigation recovery

The reader packer now preserves complete evidence and returns `context_limit`
when it cannot fit. The engine previously classified that response as a service
outage. This disabled model-assisted navigation even though a much smaller
link-selection request could still run. The original packing request is not
retried by the model client; its failure is specific to its evidence payload.

`Engine._reader_state` now maps `model_context_limit` to `context_limit` for
selection, answer verification and computed-proof verification. Existing
navigation and search-hint paths can proceed under their original deadline,
page and depth limits. A page-budget guard also stops navigation when no more
pages can be fetched. No server, evidence window, context ceiling, generation
limit, source ranking or answer-validation rule was changed.

## Evidence

Primary receipt: `benchmarks/context-recovery-20261024-paired-final-v4.json`.
The identical CPU loopback HTTP harness compares isolated `031d8be` with the
worktree: **5/13 -> 13/13**, eight related assertion wins and zero losses. These
are authored protocol controls, not thirteen independent factual questions.

In the positive recovery case, the first compact request has 7,171 characters
and is refused by an authored 5,000-character capacity boundary. The navigation
request has 854 characters, chooses an existing source link, fetches that page,
and submits shorter selection/verification requests (2,329/2,355 characters).
The engine returns the selected literal answer with the page it actually read.
The old engine disables model navigation, fetches an irrelevant archive link
and resubmits the unchanged oversized evidence. Character counts are not real
token counts or measurements of model context fit.

Controls establish that page/depth limits stop further work; terminal selection,
answer-verification and proof-verification failures retain the capacity reason;
semantic rejection still abstains; another oversized source request still
abstains; genuine HTTP/service/invalid/deadline failures gain no model navigation
calls; ordinary abstention retains its successful navigation. The harness checks
HTTP paths, source citations, payloads and exact call counts. Only the positive
capacity-recovery control establishes a new returned answer under authored
semantics. Most wins concern classification and bounded recovery, not answer
accuracy.

The initial probe used overly strict expectations that true service failures
would prevent even existing lexical traversal. It is retained as a development
artifact. The final paired harness corrects those expectations and keeps lexical
traversal unchanged. Only the final identical paired harness supplies the result
above; intermediate receipts are not pooled as additional wins.

CPU regressions pass: reader 15, proofs 27, P0 16, lossless resident packing 21,
public relationship counts 93, source excerpts 60, and cooperative HTTP lifecycle
8. Historical before/after wins printed by those drivers belong to their older
features. Primary and lifecycle receipts record no `torch` import.

## Remaining limits

This restores bounded navigation after a request-capacity refusal. It does not
make an intrinsically oversized evidence request fit, establish a general staged
reader, or guarantee a more relevant source exists. Existing passage ranking can
still yield an unchanged oversized payload after an irrelevant page. Search and
link traversal still consume the original finite query budget. Actual tokenizer
fit, model semantics and independent answer accuracy have not been remeasured.
The latest independent real first attempt remains **0/12 exact/joint**.

No real model/tokenizer, GPU, browser, external request, answer/gold/scorer edit,
build, push or submission was used. The competition-readiness goal remains open.
