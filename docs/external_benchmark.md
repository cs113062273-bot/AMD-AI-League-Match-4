# External assessment provenance

Source: [Google SimpleQA Verified](https://huggingface.co/datasets/google/simpleqa-verified), authored by Google DeepMind and Google Research, building on OpenAI's SimpleQA. The pinned dataset card declares the MIT license. The original card and CSV are retained in `research/external-simpleqa/`; the derived cases retain their original questions, answers and supporting URLs. Attribution and upstream licensing remain applicable.

Revision: `0dc97e0d28d8233463e005cdc4475cc2a13ba2dc`.

`scripts/freeze_external_assessment.py` samples 20 of all 1000 rows with seed 940217. It does not filter hosts, topics, difficulty, answer length, availability or outcomes. Its manifest freezes dataset and production hashes before the first run. The first run is preserved: 3/20 exact joint. It exposed missing search recovery after starting-URL failure; subsequent fixes make this sample development/regression evidence. A disjoint sample will assess the resulting frozen engine.

This adapts a parametric factuality dataset into a web retrieval assessment: the first gold URL becomes the starting URL. The harness uses exact answers and exact supporting URLs, with ISO-date and integer grouping aliases declared before evaluation. This is **not the official SimpleQA Verified autorater or leaderboard score**. The broader questions, old URLs and source formatting may differ from Match 4.

`eval/external_provenance.py` additionally reports a separate score allowing a fetched final URL when an observed redirect chain begins at a gold URL. It preserves the original strict result, answers and gold source URLs. It does not accept an arbitrary page merely because it shares a domain.

The first disjoint 100-case assessment uses seed 940218 and excludes every row in the initial 20. Both the selection freeze and the execution freeze are retained. Optional upstream-schema repairs and a scorer correction accepting every predeclared exact supporting URL occurred before the first execution. Its cases and gold were not filtered or changed. Runtime results attest production hashes before and after execution. Its first result is 10% answer / 20% source / 5% joint; after generic fixes it is development evidence. The complete upstream dataset card is also shipped as `benchmarks/SIMPLEQA_UPSTREAM_CARD.md`.

The next 100-case assessment uses seed 940219, excludes all prior 120 rows and retains the same uniform selection rule. Before any execution, the supporting-URL tokenizer was corrected to recognize individually quoted URLs within the upstream comma-separated field. The initial freeze is marked superseded and retained; `external-transfer100-v2.json` and its freeze are the execution inputs. The row positions and resulting URL lists for this new sample were unchanged. Matching serialization quotes are removed; URL path punctuation is preserved, including upstream punctuation that may represent a broken source. No questions or gold answers are edited.
