# Aperture — One value. Traceable evidence.

## Project description

Aperture retrieves one exact answer and the page it actually read. It combines asynchronous web navigation, structure-preserving parsing and a resident Qwen3 4B model with independent semantic checking. Deterministic checks enforce literal evidence, source provenance, parameter bindings, answer types, dates, versions, units and currencies. When the evidence does not establish an answer, Aperture abstains.

The evaluator adapter, retrieval engine and inference service are separate. A newly published Match 4 interface can therefore be accommodated without rebuilding the retrieval system. The agent uses no paid search service or remote inference API. Its production Dockerfile preserves the mandated ROCm base and bundles verified, openly licensed model weights.

## Evidence for review

Read [BENCHMARKS.md](BENCHMARKS.md) and [AUDIT.md](AUDIT.md) with their linked raw reports. Measurements distinguish first frozen assessments from tuned regression tests, exact answer-and-source scoring from a competitor's looser answer-only scorer, and CUDA execution from actual AMD execution. Public-source availability and broader factual questions remain difficult; development success is not a hidden-evaluator claim.

Readiness verdict: this is a runnable engineering candidate, **not a demonstrated first-place build**.
The [2026-10-25 validation](docs/FULLTEST_2026-10-25.md) measured frozen production
`73b0f02`: local fixed regression 30/30 and larger local regression 326/330, but a new
question-only independent first sample scored 0/12 answer and strict joint under the
declared 1536-token/12-second/browser-disabled setup. A 3072-token memory-bounded
development repeat scored 4/12 answer and 2/12 strict joint; it does not replace that
first score. Unbounded 3072 runtime stalled and the bounded mixed workload hit the
device headroom guard; the experimental memory policy has not been integrated into
production startup. These results do not support the requested championship quality.
Actual target AMD/private-interface acceptance remains outstanding.

## Reproducible demonstration

After starting the resident model with `python3 /app/app.py --warmup`, run these in separate processes:

```bash
python3 /app/app.py --query-id package --query "What is the license of the httpx package on PyPI?" --diagnostics
python3 /app/app.py --query-id standard --url https://peps.python.org/pep-0440/ --query "What is the title of PEP 440?" --diagnostics
python3 /app/app.py --query-id paper --url https://arxiv.org/abs/1810.04805 --query "Who is the first author of arXiv paper 1810.04805?" --diagnostics
```

Inspect `/app/output/*_output.json` and the separate trace files. The examples are visible demonstrations; their facts are fetched at run time and do not establish independent holdout performance.

## Submission state

Local engineering artifacts are prepared in this workspace. This document does not claim that an image has been published or that an entry has been submitted. The operational registry reference belongs in the organizer's designated submission channel, outside public source. Actual AMD kernels, full-model performance and official/private evaluator acceptance remain **NOT YET VERIFIED ON AMD** until those checks are performed on the intended platform.
