# Generalization audit: development fixes are not independent validation

Production snapshot: `b1b45bd6d879f1a4605924db75195b6f43447544`.
The audit and assessment-input change do not change `app.py` or `agent/*.py`.

There is no observed recent-case answer lookup in production. A targeted search
of `agent/*.py` found no occurrences of `219`, `Konaruiyeh`, `Selkirk`, `Cibber`,
`Hermogenes`, `Belvoir`, `7905350`, `33643018`, `618408` or `Füssli`. A static AST
check of `app.py` and `agent/*.py` found no imports from `eval`, `benchmarks`,
`fixtures`, `tests` or `research`. These are limited checks, not proof against
every form of leakage or an audit of model pretraining contamination.

The changes are shared mechanisms, but were selected and tuned after looking
at failures. That is development-set fitting even without literal answer
hardcoding. It does not establish that they improve unseen questions.

| Recent mechanism | What has been checked | Remaining generalization risk |
|---|---|---|
| Reserve two pending discovery results in a four-page navigation batch | Frozen failed-source replay and seven controlled HTTP cases | A different task may need the navigation links displaced by the reservation |
| Preserve one explicit location; prefer creator statements | Recorded hints, fetched source paragraph and authored positive/negative controls | English capitalization and relation patterns; the `+6` ranking bonus lacks independent validation |
| Recover short queries from two named subjects and one year | Observed failure plus authored controls | Capitalization, first-two-name selection and word limits may miss other wording |
| Discover an explicitly titled open paper; prefer requested age evidence | Actual exact-paper retrieval, identity negatives and saved-source replay | Narrow title/field patterns; the `+8` age bonus was added after inspecting the failed paper |
| Recover a subject from a failed supplied Wikipedia URL | Failed URL replay and URL/identity guards | Depends on having a useful supplied URL, which this assessment obtained from gold |
| Recognize imperative month/year questions and cleaned empty JS shells | Parsing/routing controls | Covers selected forms; no new model or broad web accuracy measurement |

Authored controls check intended behavior and guard known regressions. A CPU
selector stub that copies the expected literal checks retrieval, payload and
protocol behavior; it is not evidence that the real model can select that
answer. Saved-page replay also removes live search and network uncertainty.

## Gold-source assistance in the existing external assessment

`scripts/freeze_external_assessment.py` historically writes the first upstream
gold source into each case's `url`. `eval/run.py` passes the question and this
URL to `Engine.run`; answers and source expectations remain in the scoring
harness. The existing manifests explicitly record this adaptation.

This is a **source-assisted** assessment. It is useful for a task supplied with
a starting URL, but does not measure question-only discovery. It is distinct
from feeding the answer string to the engine. In particular, recovering a
subject from that URL cannot demonstrate finding the subject without it.
The real competition's starting-URL distribution remains unknown; see the
[contract ledger](competition_contract.md).

The freezer now supports `--starting-url none`. This sets only the input URL
to an empty string: sample selection, question, answer aliases and scoring
source lists stay identical for the same seed/exclusions. Its manifest records
`starting_url_mode`. The default remains `first-gold` for reproduction; old
frozen files and results are unchanged. An absent mode in an old manifest must
not be interpreted as question-only; consult its `adaptation` field.

Seven CPU checks in `eval/diagnose_assessment_inputs.py` cover the historical
default, unchanged rows/truth/aliases, actual runner arguments through a spy
engine, exclusion of exposed rows, overwrite refusal, invalid-mode refusal,
and static production import boundaries. They use three invented CSV rows in
temporary directories. No new real assessment questions or answers were opened,
no web requests were made, and no model, GPU or browser was started.

```powershell
.\.venv\Scripts\python.exe eval/diagnose_assessment_inputs.py
```

## Evidence required before claiming generalization

The most recent first new-sample live assessment remains **0/12 exact answers
and 0/12 strict joint**. Its exposed development repeat completed ten cases,
with **0/10 exact answers and 0/10 strict joint**; two cases were not run.
The CPU fixes do not supersede those results. See
[the retained first run and repeat](DISJOINT12B_2026-10-23.md).

All 244 rows across the following five external assessments are exposed and
must be excluded from any next independent first-sample claim:

- `external-simpleqa20.json`
- `external-simpleqa100.json`
- `external-transfer100-v2.json`
- `external-disjoint12-20261023.json`
- `external-disjoint12b-20261023.json`

Before a future validation, freeze code, input mode, exclusions, sample size,
scoring rule, budgets and backend. Do not inspect remaining questions/gold to
choose rules or samples. Score the whole preselected sample without changing
rules between cases; retain abstentions, network failures and failed first
runs. Once failures are examined for fixes, mark the sample development data.
Reusing these rows without their URLs would still be development, not holdout.

Report question-only and source-assisted results separately. Also name the
source scoring rule: `eval/run.py` historically accepts any matching source,
whereas the disjoint12 reports require every returned source to match. Neither
uses the official SimpleQA autorater. Do not pool these scores or silently
change aliases to turn a development answer into a hit. Unseen sampled rows
would provide transfer evidence under the declared setup, not a guarantee of
hidden-competition accuracy or full marks.

The next independent model/web assessment is pending. The user's no-GPU
restriction remains active; no new score is claimed by this audit.
