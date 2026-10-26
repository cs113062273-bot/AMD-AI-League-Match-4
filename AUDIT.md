# Aperture acceptance ledger

This ledger distinguishes completed evidence from acceptance that still requires a build, AMD hardware or the organizer's private interface. It is not an official certification or a claim of winning performance. Raw failed runs are retained alongside successful runs.

Latest validation, 2026-10-25: [full local report](docs/FULLTEST_2026-10-25.md) and
[results/receipt hashes](benchmarks/fulltest-20261025-summary-v1.json). Frozen production
`73b0f02` has fixed regression 30/30 and larger local regression 326/330, but a new
question-only first sample scored 0/12 under its declared 1536-token/12-second setup.
A 3072-token memory-bounded development repeat scored 4/12 answer and 2/12 strict
joint. The original 3072 service stalled, and the bounded mixed workload later hit
the device headroom guard. Remaining groups ran in a separate resident, not a single
continuous pass. Model cancellation/deadline recovery 6/6 and fresh CLI 3/3 pass;
the experimental memory policy is not integrated into production. Historical checks
below do not supersede these failures or establish actual AMD/private acceptance.

## Contract and implementation review

| Area | Finding and evidence | Status |
|---|---|---|
| A. Official versus inferred requirements | The common organizer PDF and pinned base digest are recorded in [competition_contract](docs/competition_contract.md). Task-specific CLI/schema and roughly 30-second timing are **CONFIRMED_OBSERVED**, cross-checked against public Match 4 implementations. | Explicitly separated |
| B. Architecture | Adapter, retrieval engine and resident inference service have independent modules. [Architecture](docs/architecture.md) follows a request from early output through provenance checks and atomic finalization. | Implemented |
| C. Query planning | Deterministic type, entity, field, currency, date/version and negation constraints; unknown semantics stay in the original question. | Tested; semantic limits remain |
| D. Search | Real keyless Bing/DDG/Google paths, alternate RSS/Lite paths and guarded discovery; snippets only supply links. Failed starting URLs trigger recovery. | Tested locally; provider access varies |
| E. Navigation | Bounded rounds/pages, anchor/URL relevance and optional model lexical hints; hints cannot become evidence. | Tested |
| F. Fetching | Actual connecting DNS addresses, redirects, compressed/decompressed bytes, headers, retries and deadlines are bounded. Private destinations are blocked by default. | HTTP fault and security tests |
| G. Parsing | HTML tables/definition lists, JSON/JSON-LD/state, XML, CSV, text PDFs, metadata and isolated Chromium. Numeric spelling and truncation status are preserved. Image-only facts remain unsupported. | Tests and real Chromium |
| H. Typed extraction | Phones, emails, numbers, prices, dates, versions, durations, measurements and exact parameter bindings preserve literal evidence and units. Python signatures are parsed as syntax and never executed. | Tested |
| I. Temporal/version reasoning | Stable semantic versions, complete dated histories, as-of dates, requested document identity and current/archived context are checked. | Tested; general semantic reasoning remains empirical |
| J. Semantic verification | Resident extractive selection and a separate semantic check precede literal/source/type checks. Both use the same small model and can share blind spots. | CUDA exercised; not a truth guarantee |
| K. Normalization | NFC/whitespace, explicit version-prefix handling and limited document/name canonicalization. No invented currency conversion or OCR-style uppercase stripping. | Tested |
| L. Abstention | Unsupported/rejected selections, conflicts and missing evidence yield empty answer/sources. Explicit model refusal does not silently select another candidate. | Tested; precision/recall reported per set |
| M. Runtime | Atomic output, external worker watchdog, Windows Job objects and Linux process groups. One resident model; bounded inference concurrency; explicit busy/protocol failures. | Process-tree and runtime tests |
| N. Model | Qwen/Qwen3-4B-Instruct-2507, pinned revision, Apache-2.0; 4,022,468,096 actual parameters, three fully hashed weight shards and bundled tokenizer assets. | Full assets verified |
| O. Backend portability | Ordinary PyTorch SDPA and the CUDA/HIP-compatible torch namespace; accelerator-neutral pinned production dependencies. Base torch is constrained and HIP-checked before/after installation. | CUDA executed; actual AMD pending |
| P. Unit/integration tests | [Core source extraction:460 passed](benchmarks/tests-extracted-corecheck.txt), core-only environment; [Linux Docker:460 passed](benchmarks/linux-cpu-final.txt). Later edits concern VM orchestration and documentation; the suite was not repeated. | Recorded executions |
| Q. Adversarial/holdout data | Related synthetic families are disclosed. First frozen results remain separate from tuned regressions. First external100 joint score is5%; it is now development. A new uniform100 excludes prior120 rows and was frozen before execution. | [Methodology](docs/benchmark_methodology.md) |
| R. Live and competitor measurements | Exact answer/source and published loose answer-only scoring are kept separate. Hardware/network differences prevent a controlled competitor superiority claim. | [BENCHMARKS](BENCHMARKS.md) |
| S. Latency and failures | p50/p95/max, malformed output, exceptions, internal deadlines and abstention are retained. An emoji-related incomplete external run is a recorded harness failure, not a scored completed run. | Raw reports and [failure analysis](docs/failure_analysis.md) |
| T. CUDA measurements | Actual RTX 4070 SUPER 12GB, torch 2.9.1+cu128; [final offline report](benchmarks/local-gpu-validation-finaloffline.json): cold startup 22.996s, one load for three racing startup clients, stable resident PID, all three loopback fresh-process answer/source contracts pass, Torch peak11,360,367,616 bytes and total-device peak11,948 MiB. All four fixture suites attest unchanged production code and matching resident backend hashes:330/330 joint. | Actual offline execution; final online measurements separate |
| U. Linux clean-room | Real Linux Docker/Python3.14:460 tests, actual Chromium with empty unexpected stderr and exact public-source CLI pass. | CPU/browser verified |
| V. Production image | [Actual image](benchmarks/production-image.json):40,103,014,862 bytes (37.35GiB), all11 mandated lower layers retained. HIP torch import, tiny CPU Qwen API, production browser/CLI and export pass. Empty-daemon reload was cancelled after the user raised storage concerns. | Built/exported; fresh reload NOT completed |
| W. AMD acceptance | Actual HIP kernels, full model on AMD, startup/latency, device VRAM sampling and official/private evaluator acceptance. | **NOT YET VERIFIED ON AMD** |
| X. Release integrity | The core source ZIP was independently extracted and passed460 tests. The final source package adds measured results/documents and updated VM tools; no duplicate full-model ZIP or extra full-suite rerun is produced. The image already contains the model. | Final source/image artifacts |
| Y. Submission readiness | Honest documentation and runnable local artifacts are distinct from a public registry pull and official submission. No registry account or private evaluator is assumed. | Publication/submission not claimed |

## Two whole-repository reviews

The first review followed the full request and evidence path: `app.py`, worker/process cleanup, network/URL guards, parser bounds, resolvers, extraction/ranking, model protocol, selector and runtime. It found provenance/temporal bypasses, silent alternate-candidate fallback, partial spans, context overflow and quadratic verification. Repairs have explicit regression tests and retained failed measurements.

The second review reread those paths after repairs, then inspected evaluator scoring, dependency locks, Docker context/layers, model acquisition, clean-room orchestration and release packaging. It found failed-starting-URL search omission, HTTP header limits, sparse upstream schemas, Unicode stdout, multiple-gold-source scoring and guest-template environment corruption. The fixes were made in the responsible layers rather than by adding benchmark facts or changing expected answers.

The final pass reproduced additional concrete failures: simultaneous startup paths loading separate models, delayed browser callbacks after closure, signed URL wire-byte changes, proxied local health calls and structured ancestry losing entity/currency/release-date ownership. These have actual process/HTTP/browser or adversarial parser regressions. Technical-field binding reads qualifiers from actual source passages rather than accepting candidate-supplied metadata. A standalone document's identity can support a field definition on the same document without accepting unrelated history/index mentions. The retained hardened live run failed while sharing WAN bandwidth with the base-image download; it is not promoted to a passing final run.

`scripts/audit_source.py` parses and compiles production/test/tool Python, checks forbidden production imports, direct eval/exec calls, unfinished markers and common secret patterns. Its [static report](benchmarks/source-audit-final.json) supplements these flow reviews. It does not prove the absence of every defect. No final hardware claims are inferred from Dockerfile text or from a CUDA run.

## Reproduction

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/audit_source.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/validate_local_gpu.py --tag audited2 --keep-server --browser
.\.venv\Scripts\python.exe eval/run.py benchmarks/external-simpleqa100.json --model --browser --budget 24 --out benchmarks/external-simpleqa100-first
.\.venv\Scripts\python.exe scripts/linux_cleanroom.py --rocm-build
```

The CUDA validator requires an unused model-service port so its cold-start measurement is real. Choose a new tag/output path for an additional run; do not overwrite the first-run evidence. The Linux harness needs the separately verified QEMU/Alpine assets and configured artifact bridge described in [deployment](docs/amd_deployment.md); normal AMD deployment uses Docker directly.

## Practical limits

The tuned synthetic and package/documentation demonstrations do not establish 95% accuracy on arbitrary websites. Broken URLs, provider blocking, dynamic/image-only content, strict answer/source formatting and small-model semantic errors remain measurable weaknesses. [Confidence diagnostics](docs/confidence.md) show that heuristic confidence is substantially overconfident on the first external100; reliable general-web probability calibration is unestablished. The independent external adaptation deliberately exposes these limits rather than filtering difficult cases away. The operational registry reference and official submission channel are user/account-specific and remain outside public source.

## Final quality verdict

The final disjoint external100 first run scored9% answer,19% source and4% exact joint;50 abstentions,41 nonempty mismatches and5 citation mismatches. p50/p95/max10.430/23.710/35.071s; zero harness crashes/malformed outputs, one internal deadline and two direct-engine cases over30s. These numbers do not meet the requested championship target. I would not present this exact build as first-place-ready. Actual AMD/private evaluator acceptance and reliable general-web confidence calibration remain unestablished.

The user requested reduced validation work and raised storage concerns. Extra archive reload was cancelled after complete export. The18.59GiB downloaded base cache and110.8GiB task-created scratch VM were removed, restoring about161GiB free space. Source, model and image were retained. No new unit suites or repeated benchmark runs were added after that request.
