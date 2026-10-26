# Aperture

**One value. Traceable evidence.** A local-GPU web retrieval agent for AMD AI League Match 4.

Submission snapshot: see [current scope](SUBMISSION_STATUS.md).

Latest measured state, 2026-10-25: [full local test report](docs/FULLTEST_2026-10-25.md)
and [results with receipt hashes](benchmarks/fulltest-20261025-summary-v1.json).
Frozen production `73b0f02` passes fixed regression 30/30 and larger local regression
326/330. A new question-only independent sample scored **0/12 answer and strict joint**
at 1536 tokens/12 seconds/browser disabled. A 3072-token experimental memory-bounded
repeat scored 4/12 answer and 2/12 strict joint on the same now-exposed sample;
this is not independent improvement. The original 3072 runtime stalled and a bounded
mixed run hit a device headroom guard; formal memory-lifecycle repair and actual AMD
acceptance remain outstanding. This build is not demonstrated competition-ready.

Earlier validation boundary: [generalization audit](docs/GENERALIZATION_AUDIT_2026-10-23.md).
That audit added the question-only freeze option and seven CPU checks before this
new live measurement. Older source-assisted assessments and authored controls below
remain historical/development evidence.

Latest CPU-only verification fix: [bind table values to their actual year columns/rows](docs/TABLE_YEARS_2026-10-23.md), paired structural checks41/86 to86/86 with no losses. A complete model-disabled HTTP fallback now selects the requested year's value; a semantic stub cannot authorize the other year's value. No new live or generalization score.

Latest CPU-only prose fix: [distinguish population counts from households and census years](docs/POPULATION_ROLES_2026-10-23.md), authored controls32/90 to90/90; four planning changes among244 exposed cases. The saved actual population remains accepted while its household count and census year are rejected. Unknown syntax still requires semantics; no new live accuracy score.

Latest CPU-only literal fix: [reject partial comma-grouped numbers](docs/GROUPED_NUMBERS_2026-10-23.md), helper/HTTP assertions101/165 to165/165. `10` no longer counts as numeric evidence from `10,000`; the full value and later standalone occurrences remain valid. No answer normalization or live accuracy claim.

Latest CPU-only temporal fix: [preserve named census observations](docs/CENSUS_REFERENCES_2026-10-23.md), paired controls25/59 to59/59. Five complete model-disabled HTTP cases select the correct year instead of an earlier row; ordinary date cutoffs are retained. Three plans change among244 exposed cases, with no new live/generalization score.

Latest CPU-only cutoff fix: [parse complete dates and retain unresolved requirements](docs/CUTOFFS_2026-10-23.md), paired controls10/52 to52/52 and three fresh CLI checks. Month/date cutoffs use calendar bounds; malformed, ambiguous or unsupported cutoffs cannot fall through to current registry answers. All244 exposed plans retain their existing field values; no new live accuracy score.

Latest CPU-only historical field fix: [read dated PyPI/npm release metadata](docs/REGISTRY_HISTORY_2026-10-23.md), paired HTTP controls6/43 to43/43. Current fields cannot fill a missing historical value. Two actual free-API compatibility reads and same-body CPU replays retain exact release fields; these are not a new holdout/generalization score.

Latest small live check: [three original failures with rendered case citations](docs/CASE_CITATION_2026-10-23.md), exact answers 1/3 and strict joint 1/3; the two-team case now has the correct original gold source. Same-source full4B citation controls 7/9 to 9/9, zero losses.

Latest whole12 live regression: [same12 exposed cases](docs/CONCISE_DISCOVERY_2026-10-23.md), exact answers remain4/12 and joint2/12; two unsupported outputs now abstain. The newer three-case check is not pooled into a new twelve-case score.

Latest new-sample assessment: [second disjoint 12 live cases](docs/DISJOINT12B_2026-10-23.md), exact answers 0/12 and joint 0/12. A request remained active and caused 15 busy rejections; the failed first run is retained. An idle-checked development repeat completed ten cases (0/10 exact, 2/10 source) before the VRAM guard stopped it; no new full12 score is available.

Latest CPU-only source fix: [recognize observed challenge documents](docs/CHALLENGES_2026-10-23.md), fixed parsing/HTTP controls 16/25 to 25/25; no GPU, browser launch, or new answer-accuracy claim.

Latest CPU-only field fix: [preserve explicit inline labels](docs/INLINE_FIELDS_2026-10-23.md), 19/19 controls; an actual full-name passage moves from rank11 to rank4 in the serialized top8. Temporal verification remains required; no model accuracy gain measured.

Latest CPU-only search fix: [select the concise hint retaining more user content](docs/HINT_SELECTION_2026-10-23.md), controls17/20 to20/20, two changed choices among11 recorded sets. Six public responses retained, including a rejected field-first proposal; no new answer-accuracy score.

Latest CPU-only evidence fix: [bind birth years to actual source fields](docs/BIRTH_BINDINGS_2026-10-23.md), same51 controls30/51 to51/51; explicit birth dates restored, update years and another named parent's birth rejected. No new model score.

Latest CPU-only parsing fix: [preserve named HTML field groups](docs/FIELD_GROUPS_2026-10-23.md), same42 controls23/42 to42/42; actual full name and birth date now share the first payload passage. Paired68 saved HTML responses retain their original passages; no new model or live accuracy score.

Latest CPU-only URL fix: [preserve question URLs through planning and routing](docs/QUESTION_URLS_2026-10-23.md), same49 controls19/49 to49/49 and4 fresh CLI checks. Existing244 explicit-start plans unchanged; no claim of a competition-score increase.

Earlier assessment: [first disjoint 12 live cases](docs/DISJOINT12_2026-10-23.md), exact answers 4/12 and exact answer+source 2/12; small sample, now exposed. These are different samples and are not pooled.

Latest discovery change: [ranking query echoes and clue lookup pages](docs/SEARCH_SIGNALS_2026-10-23.md), controlled HTTP 3/9 to 9/9 with 12 additional URL/navigation checks. The proposal to append a year to concise queries was not promoted.

Latest source/reader improvement: [official Oyez and bounded multi-span members](docs/CASE_MEMBERS_2026-10-23.md), same full4B/frozen sources 6/12 to 12/12 with all six prior correct outcomes retained. The real two-team answer is recovered from the API; its URL is not in the original strict gold-source list. This is source-replay development evidence, not a new live score.

Latest code changes: [browser content budget and main redirects](docs/BROWSER_BUDGET_2026-10-23.md) (fresh Chromium controls3/5 to5/5, six existing browser checks retained; actual Oyez content still unresolved), [dated-event source evidence](docs/EVENT_YEARS_2026-10-23.md) (same full4B source controls5/11 to11/11, five prior positive answers retained), [shorter model discovery hints](docs/EXPANSION_2026-10-23.md) (same full4B HTTP comparison completed anchored hints3/8 to8/8; three exposed live cases exactanswer1/3, joint0/3 with a temporal-evidence gap), [bounded concise discovery](docs/CONCISE_DISCOVERY_2026-10-23.md) (fixed-response topic candidates recovered on two queries; no new end-to-end correct answers), [explicit first-line evidence](docs/FIRST_LINES_2026-10-23.md) (same full4B authored controls 5/8 to8/8; original five correct answers retained), [directional boundary evidence](docs/DIRECTIONS_2026-10-23.md) (same full4B local-page controls 5/8 to8/8; all four positive answers retained), [exact table-field projection](docs/PROJECTION_FIELDS_2026-10-23.md) (same full4B proof controls 2/4 to4/4), [complete-name request routing](docs/FULLNAME_2026-10-23.md) (same full4B reader service 3/7 to6/7; one compound-field case still fails), [search topic anchors](docs/SEARCH_ANCHORS_2026-10-23.md) (24 unrelated candidates removed in fixed real-response replay; no new answer claim), [selector request-ID boundary](docs/SELECTOR_BOUNDARY_2026-10-23.md) (10/10 controlled HTTP checks), [2026-10-23 actual public-web diagnosis](docs/LIVE_PIPELINE_2026-10-23.md) (two erroneous abstentions recovered; original strict score remains 0/3), [2026-10-23 record field/scope binding](docs/RECORD_BINDINGS_2026-10-23.md) (same eight full-4B reader development cases, two staged comparisons 4/8 → 6/8 → 8/8), [search response filtering](docs/SEARCH_BATCHES_2026-10-23.md) (three frozen real-response replays), [real-page date precision](docs/REAL_PAGE_READER_2026-10-23.md), [discovery candidate queues](docs/DISCOVERY_QUEUE_2026-10-23.md) and [discovery recovery](docs/DISCOVERY_FIXES_2026-10-23.md); preceded by [table/wording transfer fixes](docs/TRANSFER_FIXES_2026-10-23.md), [multi-source proofs](docs/PROOF_FIXES_2026-10-23.md), [reader/type fixes](docs/READER_FIXES_2026-10-23.md) and [service/fallback fixes](docs/P0_FIXES_2026-10-22.md). The [2026-10-21 full rerun](docs/RETEST_2026-10-21.md) measures the earlier code. These development results are not claims of general-web accuracy or an official Match 4 ranking.

Aperture answers a natural-language question, optionally starting at a supplied URL. It retrieves actual pages, preserves their structure, selects a literal value or derives a bounded answer from literal premises, checks its evidence and returns the fetched source URLs. Unsupported questions receive an empty answer and no sources.

The evaluator adapter is independent of retrieval and inference. Match 4 CLI/schema assumptions are **CONFIRMED_OBSERVED**, cross-checked against public implementations. Common organizer infrastructure requirements are **CONFIRMED_OFFICIAL**. See the [contract ledger](docs/competition_contract.md).

## Run a query

Python 3.13 or 3.14, from the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-deps -r requirements-core.lock
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe app.py --query-id demo --query "What is the license of the httpx package on PyPI?" --diagnostics
```

The example writes `output/demo_output.json` on Windows. Linux defaults to `/app/output`; override with `--output-dir`. Example shape:

```json
{"answer":"BSD-3-Clause","sources":["https://pypi.org/pypi/httpx/json"]}
```

The quoted value is an example, not a bundled answer. Every request fetches evidence. `--diagnostics` writes a separate trace containing constraints, passages, decisions, fetch failures and timing.

## Resident GPU model

Project cost constraint: use only free APIs; do not enable billing, paid plans, or automatic paid overages. The user authorized the keyless official `api.oyez.org` public endpoint; no third-party Oyez wrapper is used. Requests retain the existing time/size/retry bounds. An unpublished quota is not a promise of unlimited usage. Skip other integrations while their free-use status is unconfirmed.

The pinned model is `Qwen/Qwen3-4B-Instruct-2507`, revision `cdbee75f17c01a7cc42f958dc650907174af0554`, Apache-2.0. Three weight shards and all assets are checked against SHA-256 receipts. No per-query download, remote inference API or API key is required.

On the local RTX development host:

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.9.1 --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe -m pip install --no-deps -r requirements-runtime.lock -r requirements-test.lock
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/fetch_model_ranges.py
.\.venv\Scripts\python.exe app.py --warmup
.\.venv\Scripts\python.exe app.py --query-id q01 --url https://peps.python.org/pep-0440/ --query "What is the title of PEP 440?" --diagnostics
```

`--serve` keeps the model resident; `--warmup` starts it under a startup lock and waits for a completed generation. A 12GB GPU uses a 3072-token input cap. Larger devices use up to 5800 tokens. Attention uses ordinary PyTorch SDPA; there is no CUDA-only production dependency.

To enable the same selective JavaScript fallback on Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-deps -r requirements-browser.lock
.\.venv\Scripts\python.exe -m playwright install --only-shell chromium
$env:APERTURE_BROWSER = "1"
.\.venv\Scripts\python.exe scripts/browser_smoke_test.py
```

The production Docker build includes this browser by default. Browser executables are versioned separately from the Python package; an older cached Chromium does not satisfy a newer Playwright lock.

## Build for AMD

The Dockerfile pins the organizer's exact ROCm image and digest, retains its lower layers and protects its installed PyTorch. Models are bundled under `/models/qwen`. The default image also includes isolated Chromium rendering.

```bash
bash scripts/build_rocm.sh YOUR_IMAGE_REFERENCE
bash scripts/container_contract_test.sh YOUR_IMAGE_REFERENCE
```

Keep the operational registry reference outside public source. [Deployment and verification](docs/amd_deployment.md) distinguishes local CPU/CUDA evidence, ROCm container evidence and **NOT YET VERIFIED ON AMD** hardware checks.

## Verify and reproduce

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe eval/run.py benchmarks/dev.json --fixtures fixtures/dev.json --out benchmarks/repeat-dev
.\.venv\Scripts\python.exe eval/run.py benchmarks/holdout.json --fixtures fixtures/holdout.json --model --budget 24 --out benchmarks/repeat-model
```

Use new output names to preserve the first-run evidence. The [measurement methodology](docs/benchmark_methodology.md) identifies development sets, first frozen evaluations and subsequent regression runs. Public competitor comparisons use their published scoring separately from exact answer-and-source scoring. No result is an official hidden-evaluator score.

## Inside the agent

- Primary-source adapters for package registries, repositories, papers and standards, plus keyless search and bounded link navigation.
- HTML tables/definition lists, JSON/JSON-LD, embedded state, XML, CSV, text PDFs and selective JavaScript rendering.
- Typed candidates, field and parameter binding, dates/versions, currency and unit preservation, conflicts and abstention.
- Resident extractive selection followed by independent semantic checking and deterministic literal/source/type checks.
- Guarded DNS and redirects, byte limits, deadlines, isolated browser requests and whole-process-tree cleanup.
- Early atomic output, a replaceable evaluator adapter and detailed failure traces.

See [architecture](docs/architecture.md), [adapter](docs/evaluator_contract.md), [failure analysis](docs/failure_analysis.md) and [audit](AUDIT.md). The source is MIT licensed; the model retains its own Apache-2.0 license.
