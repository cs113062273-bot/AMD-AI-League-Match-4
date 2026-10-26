# Preserve source evidence inside the resident packer

The client-side excerpt repair did not cover a second transformation inside
`Runtime.infer`. When a request exceeded the resident context limit, the server
removed passages from the end, then hard-cut remaining text to 650 characters.
That could remove an eighth conflicting source or split a complete quantity
again. Proof fields and their passage references could survive without all
their original context. The special relationship-count guard added in
`229bb5a` protected only that new operation.

The frozen CPU receipt `benchmarks/packing-fidelity-20261024-probe-v1.json`
reproduces both mutations through the actual pre-generation `Runtime.infer`
path. It uses an authored string counter and intercepts before tensor creation;
it does not load a tokenizer, torch, weights, GPU or model. Its counter units
are not real tokens and do not estimate actual capacity. No wrong-model-answer
or competition-score claim follows from this packing observation.

## Change

Extractive selection and semantic verification now preserve all request fields,
source strings, constraints and proof references. If the initial prompt is
too large, the server tries compact JSON separators. This removes redundant
JSON whitespace only; spaces inside source strings remain unchanged. If that
complete representation fits, it proceeds to generation with the full evidence.
If it still does not fit, it returns `context_limit` without changing the data
or starting generation. The existing context ceiling and generation limits
remain unchanged.

Navigation expansion retains its prior packing policy. `compacted_requests`
records lossless repacking separately from `pruned_requests`, which now counts
only expansion pruning. Existing statistics dictionaries remain compatible
through a default for the new counter.

## Verification

Primary receipt: `benchmarks/packing-fidelity-20261024-paired-v3.json`.
The same harness compares isolated `229bb5a` against the worktree:
**7/21 -> 21/21**, 14 related assertion wins and zero losses. Seven payload
shapes are tested at three authored packing limits: initially fitting, fitting
after lossless compaction, and genuinely too large. The real production
packer executes, while generation is intercepted before tensor construction.

The shapes cover selection and verification at a quantity boundary, an eighth
conflicting context, table-proof premises, member cardinality/selected spans,
source fields, locators, offsets, Unicode, quotes and repeated spaces inside
source strings. The parsed model payload equals the entire original request
for accepted cases; oversized cases preserve the request and fail before
generation. The same previously successful small requests remain accepted.
Earlier probe/v2 receipts remain; only the final identical paired harness
supplies this comparison.

CPU regressions pass: relationship counts 93, reader 15, existing proofs 27,
source excerpts 60, table-header scales 88, members 28 plus 12 guards, P0 16,
and cooperative HTTP lifecycle 8. These drivers include their own older
baselines; their historical wins are not new wins for this patch. Syntax and
diff checks pass. All primary receipts record `torch_imported: false`.

## Limits

Lossless JSON compaction may not save enough real tokens. No actual tokenizer
or model context-fit measurement was performed because the user continues to
prohibit model/GPU work. Requests that formerly generated after silently
losing evidence can now return `context_limit`; this can increase abstention.
The controlled positive cases prove lossless recovery when it fits, not a
general accuracy or latency improvement. A genuinely oversized full request
needs further context planning or an independently validated staged read;
this patch does not claim to solve that broader task by returning an error.

The engine currently classifies `model_context_limit` through its generic
service-failure path. That is a separate recovery-policy gap worth checking
next: insufficient evidence capacity is not proof that the endpoint is down.
Any revised recovery must retain the existing deadlines and call/page caps,
and must not hide conflicting facts merely to produce a smaller accepted
request. The latest independent real first attempt remains 0/12 exact/joint.

No browser, public request, new assessment question, gold/alias edit, real
model/tokenizer/GPU use, build, push or submission was involved.
