# Failure analysis

All results are local evidence. They do not establish AMD hardware performance, official acceptance or a hidden-set score.

## Retained failures and systemic repairs

The initial test run had 167 passes and two failures: a registry query selected a preposition as a package name, and concurrent Windows atomic replacement encountered sharing violations. Entity parsing and bounded file retries were corrected. Early live results began at 7/15 joint success.

The first frozen 100-case synthetic assessment scored 80% with rules and 85% with the early hybrid system. Its 20 families contain five related variants each. Failures included former versus current officeholders, prose names, nonexistent offices and package versus product weight. Later 100% results are regression evidence after changes, not untouched holdout results. The separate 30-page first hybrid assessment scored 23/30. A later 20-page transfer assessment scored 19/20 on its first hybrid run, then 20/20 as regression evidence. Same-author fixture bias remains.

Independent flow reviews found and repaired:

- Model-selected spans bypassing temporal/type constraints; rejected selections enabling another candidate; and empty model answers mistaken for transport errors.
- Candidate priming, ID-zero handling, partial numeric/version matches, author ordering, wrong-document titles and defaults bound to another parameter.
- Context exceeding physical RTX VRAM. Structured pruning now caps input at 3072 tokens on the 12GB development GPU; the failed over-allocation report remains available.
- Repeated full-page evidence scans. Indexed membership avoids quadratic verification on large tables.
- Truncated histories falsely appearing complete; huge table spans creating misleading associations; and JSON float conversion changing numeric spelling.
- Starting-URL failures bypassing search; large legitimate security headers rejected; inline JavaScript shells missed; and legacy HTML body text omitted.
- Currency negation and symbol ownership, localized dates, structured numeric prices, and Unicode under legacy Windows stdout encodings.
- Null or malformed optional API records interrupting fallback. Optional metadata is now schema-checked.
- Simultaneous default startup and warmup launching separate models. All shipping entry points now share a process startup lock; actual concurrent clients verify one load and one resident PID.
- Signed URL percent escapes being rewritten by the HTTP library, and local health calls trusting environment proxies. Actual loopback HTTP tests now verify wire bytes and proxy independence.
- Nested structured records losing product identity, inherited currency or release-date ownership. Bounded ancestry and nearest-record qualifiers now bind evidence to the actual parsed passage. Conflicting local currency fields require abstention.
- Browser callbacks surviving teardown. Actual delayed-XHR tests capture stderr and verify orderly unroute/close behavior.

Tests exercise actual HTTP servers, process descendants and real browser JavaScript where appropriate. Static checks supplement tests and manual review; a marker scan alone is not an audit.

## Live and public comparison limits

Live success varied with network conditions. A narrow tuned run reached 16/16; another retained run reached 14/16. The shipping CUDA run reached 16/16 on that development set and 10/14 on the broader live transfer set. Exact source scoring rejects correct answers read from alternate official pages or unlisted redirects. Image-only specifications, inaccessible sites and semantic field alignment remain difficult.

The visible Pinpoint comparison reached 14/15 under its published loose answer-only scorer, versus the author's reported 11/15 on different AMD hardware and network. This is a public development baseline, not a controlled head-to-head result. The remaining introduction-versus-later-revision question exposes semantic limits. The scorer's substring behavior is disclosed; exact source scoring is separate.

## Independent external assessment

The first uniformly sampled 20 Google SimpleQA Verified cases scored 3/20 exact answer-and-source. Seventeen were unanswered; most starting URLs returned 403/404, and search recovery was missing on that path. A recovery run exposed a benchmark logging crash on an emoji. Its incomplete log is preserved and is not counted as a completed run. The stdout issue and recovery path were fixed.

The evaluator also incorrectly used only the first of multiple predeclared supporting URLs. It now accepts any exact URL already listed in the case, with tests against near-match and wrong-domain URLs. Original results remain unchanged. The disjoint 100-case sample (seed 940218) scored **10% answer, 20% source and 5% exact joint**, with 58 empty answers. p50/p95/max were 9.839/22.406/28.924 seconds; no harness crash, malformed output or internal deadline was recorded. Nonfatal browser callback warnings did occur in its raw log and were subsequently repaired. Observed signals included source fetch failures on 74 cases, 32 nonempty answer/format mismatches and five correct-answer/source mismatches. These overlap and do not prove mutually exclusive causes.

That 100 is now development evidence after generic fixes. A fresh 100 uses seed 940219 and excludes all prior 120 rows. Its first generated freeze was superseded before execution to repair individually quoted upstream URL tokenization; the same 100 row positions were retained, and their resulting URL lists happened to be unchanged. Original first-run reports and malformed upstream punctuation remain preserved. No outcome was used to select replacement cases.

The fresh 100 first execution scored **9% answer, 19% source and 4% exact joint**. Fifty answers were empty, 41 were nonempty answer/format mismatches, and five had a correct answer with a source mismatch. p50/p95/max were 10.430/23.710/35.071 seconds. The direct-engine harness recorded zero crashes/malformed outputs and one internal deadline; two cases exceeded 30 seconds. This is a real latency limitation of direct-engine execution. The shipping CLI has a separate process watchdog, which may instead yield an empty answer on such a case. Do not call this run zero-timeout or claim the direct-engine latency is a verified evaluator latency. Production files remained unchanged and resident backend hashes matched. Heavy WAN downloads were complete, while local image assembly/export ran concurrently. The raw log contains no traceback. This assessment does not meet the requested accuracy target, and reliable confidence calibration remains unestablished.

This is an exact-scoring adaptation, not Google's official autorater. Gold answers sometimes contain explanatory alternatives or ranges; a correct literal answer may fail strict formatting. Original supporting pages may have disappeared. These limitations do not justify editing gold after evaluation. See [external provenance](external_benchmark.md).

## Taxonomy and diagnosis

The scorer records symptoms: CTR contract/harness exception, CIT correct answer with a source mismatch, ABS unanswered, and RANK nonempty answer mismatch. eval/analyze_failures.py separately identifies observed network, search-provider, parser, browser and deadline signals from traces. Signals can coexist and are not automatically proven root causes. Inspect evidence before attributing abstention to model quality.

## Remaining limits

Keyless providers can throttle, return irrelevant results or block access. The agent does not bypass access controls or promote snippets to evidence. Small-model semantic verification can share the selector's blind spots. OCR of image-only specifications, authenticated pages, arbitrary multistep reasoning and comprehensive open-web coverage are not established. Confidence is a heuristic, not a calibrated probability.

Linux Docker CPU/browser checks, the pinned ROCm production build and image export are separate evidence categories. Actual HIP kernels, full-model latency/VRAM on AMD and the official private evaluator remain NOT YET VERIFIED ON AMD. Consult [AUDIT.md](../AUDIT.md) for completed checks and artifact status.
