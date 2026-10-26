# Measurements and provenance

Latest local validation, 2026-10-25: [full test report](docs/FULLTEST_2026-10-25.md),
[machine-readable results and receipt hashes](benchmarks/fulltest-20261025-summary-v1.json).
Frozen production `73b0f02`: fixed reading/proof/transfer 30/30; larger local regression
326/330. A **new question-only uniform disjoint12 first run scored 0/12 answer and
0/12 strict joint**, at 1536 tokens/12 seconds/browser disabled. The same exposed
sample repeated at 3072 tokens with an experimental process memory limit scored
4/12 answer and 2/12 strict joint; this is development evidence, not a new independent
score. Unbounded 3072 inference stalled; the bounded mixed run later hit the device
headroom guard and required a separate resident for remaining groups. AMD acceptance
and competition readiness remain unverified. Historical results below are retained.

Earlier fresh external sample: [second disjoint twelve](docs/DISJOINT12B_2026-10-23.md), exact answer 0/12, exact source 1/12, strict joint 0/12. The model remained busy across later cases (15 rejections); retain this failed execution separately from normal-service capability and historical samples. All twelve captures were verified; no cases were omitted or replaced.

For the newer local rerun, see [2026-10-21 results](docs/RETEST_2026-10-21.md) and its [machine-readable ledger](benchmarks/retest-20261021-summary.json). The historical measurements below remain unchanged.

These are local measurements, not official Match 4 scores. Exact joint success requires both an accepted answer and an exact predeclared source URL. Multiple predeclared URLs are alternatives; original reports under the earlier first-URL-only scorer remain unchanged. Empty answers require empty sources. No datasets are pooled into a headline accuracy.

## First frozen assessments

| Result | Cases | Answer | Source | Joint | p50 / p95 / max seconds | Exceptions / malformed / internal deadlines |
|---|---:|---:|---:|---:|---|---|
| [Original 20-family rules](benchmarks/holdout-rule.json) | 100 | 80.0% | 90.0% | 80.0% | 0.002 / 0.005 / 0.006 | 0 / 0 / 0 |
| [Original 20-family hybrid](benchmarks/holdout-model.json) | 100 | 85.0% | 87.0% | 85.0% | 1.196 / 1.756 / 4.385 | 0 / 0 / 0 |
| [Separate 30-page hybrid](benchmarks/final-holdout-model.json) | 30 | 76.7% | 80.0% | 76.7% | 1.187 / 1.602 / 1.699 | 0 / 0 / 0 |
| [Separate 20-page transfer hybrid](benchmarks/transfer-frozen-first-model.json) | 20 | 95.0% | 95.0% | 95.0% | 1.136 / 1.334 / 1.600 | 0 / 0 / 0 |
| [First external 20; now development](benchmarks/external-simpleqa20-first.json) | 20 | 15.0% | 15.0% | 15.0% | 0.318 / 17.854 / 23.065 | 0 / 0 / 0 |
| [First external 100; now development](benchmarks/external-simpleqa100-first.json) | 100 | 10.0% | 20.0% | 5.0% | 9.839 / 22.406 / 28.924 | 0 / 0 / 0 |
| [New disjoint external 100; first run](benchmarks/external-transfer100-first.json) | 100 | 9.0% | 19.0% | 4.0% | 10.430 / 23.710 / 35.071 | 0 / 0 / 1 |

The 100-case synthetic assessment has 20 families with five related variants, not 100 independent website designs. The 30-page and 20-page sets were independently written later by the same author, so author bias remains. The external 100 excludes every previously exposed external row and applies no host/topic/difficulty/availability filter. It is an adaptation of Google SimpleQA Verified, not its official autorater.

## Current regression and live measurements

| Result | Cases | Answer | Source | Joint | p50 / p95 / max seconds | Exceptions / malformed / internal deadlines |
|---|---:|---:|---:|---:|---|---|
| [Development families (finaloffline)](benchmarks/dev-model-finaloffline.json) | 180 | 100.0% | 100.0% | 100.0% | 1.609 / 4.216 / 5.438 | 0 / 0 / 0 |
| [Original holdout, now regression (finaloffline)](benchmarks/holdout-model-finaloffline.json) | 100 | 100.0% | 100.0% | 100.0% | 1.510 / 4.697 / 9.787 | 0 / 0 / 0 |
| [30-page set, now regression (finaloffline)](benchmarks/final-holdout-model-finaloffline.json) | 30 | 100.0% | 100.0% | 100.0% | 1.612 / 2.163 / 2.722 | 0 / 0 / 0 |
| [20-page transfer, now regression (finaloffline)](benchmarks/transfer-frozen-model-finaloffline.json) | 20 | 100.0% | 100.0% | 100.0% | 1.393 / 2.487 / 3.755 | 0 / 0 / 0 |
| [Narrow primary-source live development (hardened)](benchmarks/live-model-hardened.json) | 16 | 75.0% | 75.0% | 75.0% | 5.018 / 23.622 / 23.715 | 0 / 0 / 1 |
| [Broader live transfer, now development (hardened)](benchmarks/live-transfer-model-hardened.json) | 14 | 64.3% | 57.1% | 57.1% | 17.249 / 23.714 / 23.716 | 0 / 0 / 3 |

Repeated or tuned sets are regression evidence. The hardened run competed with a large Docker base download: its fresh-CLI checks failed and its live scores deteriorated. That report remains failed. Offline fixture validation deliberately omits public-web claims; final online runs occur after large downloads. Fresh CLI checks and model lifecycle measurements are separate from in-process engine latency. The recovery attempt interrupted by a Unicode logging error has no completed aggregate score; see its retained log and failure analysis.

## Published competitor scoring

Aperture passes **12/15** under the [published Pinpoint answer-only scorer](benchmarks/public-pinpoint-comparison-hardened.json). Its author reports 11/15 on an AMD W7900D, mean 7.9s and max 16.1s. Our hardware/network differ. The scorer uses loose substring matching and does not check source correctness, so this is neither a strict joint score nor a controlled superiority claim.

## Runtime and clean-room evidence

[local-gpu-validation-finaloffline](benchmarks/local-gpu-validation-finaloffline.json): actual RTX 4070 SUPER execution, 4,022,468,096 parameters; cold start 22.996s; Torch peak 11,360,367,616 bytes; peak total device memory 11948 MiB; resident PID stable: True. These are CUDA measurements, not AMD measurements.
Report scope: offline fixtures and loopback HTTP. Overall error: none.

The complete host test report, actual Linux Docker test/browser/CLI logs, production image size/lower-layer/inventory/archive receipts and actual AMD status are tracked in [AUDIT.md](AUDIT.md). `scripts/render_benchmark_summary.py` regenerates this ledger from the linked raw files.

See [methodology](docs/benchmark_methodology.md), [external provenance](docs/external_benchmark.md) and [failure analysis](docs/failure_analysis.md) for data freezes, scoring limits, ablations, first failures and remaining weaknesses.
