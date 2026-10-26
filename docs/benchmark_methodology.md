# Measurement boundaries

All reported numbers must identify the dataset, first-run status, scoring rule, source hashes, backend and network conditions. Fixture accuracy, live accuracy and a competitor's public score are distinct measurements.

The [2026-10-23 generalization audit](GENERALIZATION_AUDIT_2026-10-23.md) distinguishes failure-driven shared rules from independently validated improvements. Existing external SimpleQA assessments supplied the first gold source as a starting URL; they are source-assisted, not question-only retrieval results. The freezer now supports `--starting-url none`, recording the input mode without changing sampled rows or truth. This option has CPU boundary checks but no new live accuracy result. Previously exposed rows remain development data even if their starting URLs are removed.

## Dataset history

| Dataset | Composition | Interpretation |
|---|---|---|
| `dev.json` | 180 related synthetic cases, 15 families | Development and regression only |
| `holdout.json` | 100 cases, 20 families with five related variants | First frozen rules result 80/100; first hybrid 85/100. Subsequent engineering used observed failures, so later runs are regression evidence |
| `final-holdout.json` | 30 separately written pages | First rules 20/30; first hybrid 23/30. Later runs are development/regression |
| `transfer-frozen.json` | 20 new pages, no template variants | Frozen before first run; first hybrid 19/20, with all unanswerable cases refused. Later changes make repeats regression, not new untouched evidence |
| `live.json` | 16 primary-source questions | Visible development, timestamped truth and explicit source expectations |
| `live-holdout.json` | 14 live transfer questions across nine domains | Reclassified development after first observation; network failures retained |
| `published-pinpoint.jsonl` | 15 publicly visible competitor questions | Visible comparison using its published answer-only substring scorer |
| `external-simpleqa20.json` | Uniform20 from Google SimpleQA Verified | First exact joint3/20; now development |
| `external-simpleqa100.json` | Uniform100 excluding prior20, seed940218 | First exact joint5/100; now development after generic fixes |
| `external-transfer100-v2.json` | Uniform100 excluding prior120, seed940219 | Frozen before first execution; same selected rows as superseded pre-execution tokenizer freeze |

All synthetic sets were authored by the implementation author. They are not independent third-party validation, representative hidden data or proof of a universal accuracy percentage. Related variants do not count as independent facts. Production code never imports fixtures, test answers or competitor code.

The early `dev-model-strict-protocol` run encountered selector schema failures and frequent deterministic recovery; it must not be presented as a clean semantic-model success. The first full GPU run also exceeded a 12GB device's physical memory on long prompts. Both observations remain in the evidence; later context limits address them.

The [2026-10-23 disjoint12 first live assessment](DISJOINT12_2026-10-23.md) uniformly sampled from the remaining780 rows, excluding prior220. Exact answers4/12, exact answer+source2/12. Its predeclared source rule requires every returned source to match, which is stricter than the older any-source scorer. It is now exposed development data.

## Scoring

`eval/run.py` uses exact answer and any matching accepted source for joint success. The newer disjoint12 reports use the stricter requirement that every returned source match; name this difference when comparing results. Accepted alternate answers/source URLs are explicit in the frozen case. Empty truth requires both an empty answer and empty source list. Whitespace/NFC normalization is conservative; no OCR uppercase/punctuation oracle is assumed.

The harness reports abstention precision/recall, crashes, malformed outputs, internal deadlines, recovered errors, latency percentiles, page counts and model attempts. It records source hashes before and after a run and reports concurrent edits. Model health records identify the actual resident backend. Direct-engine runs are supplemented by fresh CLI, watchdog, concurrent-output and real-container tests.

The public Pinpoint scorer permits answer substrings and does not validate citations. It can count an email containing a person's name as a correct person answer. Such cases are flagged, not silently rescored or merged into strict joint accuracy. Its author's 11/15 AMD result used a different GPU/network; a local comparison is not an official head-to-head result.

An early live-transfer harness did not support plural accepted `sources`. The harness was corrected and old answers rescored with provenance in `eval/rescore.py`; the expected answers were not changed. Source-format corrections are distinct from model improvements.

## Reproduction

Use fresh output paths. For example:

```bash
python -m pytest -q
python eval/run.py benchmarks/holdout.json --fixtures fixtures/holdout.json --out benchmarks/repeat-rules
python app.py --warmup
python eval/run.py benchmarks/holdout.json --fixtures fixtures/holdout.json --model --budget 24 --out benchmarks/repeat-model
python eval/run_public_baseline.py --out benchmarks/repeat-public
```

Live pages, search blocking and network congestion can change results. Preserve every attempt and its failures. Torch allocation, total device memory, cold start and image size are measured separately. CUDA results do not certify AMD kernels, and a ROCm import on CPU does not certify HIP inference.

The `hardened` GPU run overlapped a large base-image download and failed fresh CLI checks. Its lower live scores and timeout traces remain retained. `finaloffline` measures resident CUDA lifecycle, synthetic fixtures and actual loopback HTTP CLI output without public-network traffic. New final online measurements run after the download/build; offline and online scopes are named explicitly.

[Confidence diagnostics](confidence.md) additionally report answered-only Brier error, calibration error and fixed threshold risk/coverage curves. They do not label the heuristic confidence as a calibrated probability or retune thresholds using held-out outcomes.
