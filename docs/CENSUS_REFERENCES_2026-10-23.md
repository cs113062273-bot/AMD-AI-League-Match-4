# Preserve named census years without inventing a year-end cutoff

`In the 2020 census` and `As of the 2020 Census` previously supplied no
machine-readable year. Without the article, `As of 2020 Census` instead
supplied `2020-12-31`. That is a calendar cutoff, not the named census
observation. A table containing multiple years could therefore authorize the
wrong row even though the question supplied a census year.

The existing census helper now recognizes `in`, `during` and `as of`, optional
`the`, and `YEAR national census`, alongside its prior forms. It still requires
one supplied calendar year, rejects directly negated references and ignores
URL contents. Quoted titles do not add a constraint through this helper.

When a positive census reference immediately follows a bare `as of YEAR`,
planning uses the observation year rather than deriving December 31. Ordinary
`as of YEAR` and `as of YYYY-MM-DD` retain their cutoff behavior. A separate
cutoff elsewhere in the question remains a cutoff; the census word appearing
elsewhere does not erase it. No observation date is invented.

Only `agent/population.py`'s census grammar and `agent/planner.py`'s distinction
change. There are no village names, answer counts, URLs, new rankings or new
source adapters in this patch. The year also applies to household questions;
it is not conditional on an expected population value.

## Paired CPU evidence

Final `eval/diagnose_census_references.py` reports:

- Baseline `fd8d4b3`, `benchmarks/census-references-20261023-before-v2.json`:
  **25/59** assertions pass.
- `benchmarks/census-references-20261023-after-v2.json`: **59/59** pass.

The diagnostic SHA matches. All 25 prior passing assertions remain passing;
34 improve. These are authored grammar variants and transport controls, not
59 independent factual questions or a generalization percentage. The initial
57-assertion pair is also retained; household controls were added after the
244-case planning audit and are included in both final runs.

Thirteen complete-engine checks use actual loopback HTTP. Four population
question forms retain a correct semantic-stub selection, reject the other
year's selection despite an always-positive verification stub, and choose the
right row with the model entirely disabled. A model-disabled household case
does the same. All five model-disabled cases change from the wrong-year
literal `361` to the requested-year literal `617`, citing the fetched table.
These are invented table values; no real model is involved.

The planning-only audit of all 244 exposed external cases changes exactly
three plans: 2934 and 262 gain year `2020`; household case 3207 gains `2000`.
Every other plan field/case is unchanged. Original case hashes are retained in
`benchmarks/census-references-20261023-exposed-audit.json`; no new external
questions or gold labels were sampled or modified.

CPU regressions pass: population90, table years86, grouped numbers165,
calendar/record structure27, reader15, proofs27 and P0 16. Their retained
artifacts use the same `census-references-20261023-` prefix. Older-baseline
improvements in those diagnostics belong to earlier changes.

```powershell
.\.venv\Scripts\python.exe eval/diagnose_census_references.py --baseline fd8d4b3 --out benchmarks/census-new-before.json
.\.venv\Scripts\python.exe eval/diagnose_census_references.py --out benchmarks/census-new-after.json
```

Use fresh output names. The baseline command intentionally fails assertions.
No GPU, model weights, browser, public HTTP or paid API is used. There is no
new live accuracy score; the retained first-new-sample result remains 0/12.
See the [generalization audit](GENERALIZATION_AUDIT_2026-10-23.md).

## Remaining temporal gap

This is not a replacement for generic temporal parsing, including all its
negation/quotation and combined-constraint cases. The next planning probe
(`census-references-20261023-next-cutoff-probe.json`) confirms that existing
generic cutoffs accept `2020.2` and `2020-02` as `2020-12-31`, and retain invalid
`2020-99-99`. None of those is fixed here. Repair must preserve the user's
unresolved temporal requirement, rather than silently dropping it and allowing
a current-value deterministic fallback.
