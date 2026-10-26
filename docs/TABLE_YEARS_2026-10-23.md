# Bind table answers to the requested year

The previous literal guard checked whether the requested year appeared in the
evidence context. That context includes the whole row and section heading.
A heading containing both years could therefore authorize a value from the
wrong year. A wide table's `Population 2004` and `Population 2014` columns both
matched the requested field, so either value could pass.

The fix changes only `agent/evidence.py`'s existing table verification:

- For a single explicit point-year plan, a source column named `Year`,
  `Census year`, `Observation year`, `Reporting year` or `Calendar year` must
  establish that year for its row. Unknown, conflicting and multi-year values
  cannot establish it. Birth, update and fiscal years are not treated as
  interchangeable observation years.
- If matching field columns contain calendar years, require the answer to
  occur in the column for the requested year. An undated matching column can
  instead use the row's explicit observation year. Another field's dated
  column cannot veto the correct field.
- A wide table with bare-year headers can bind the answer to the requested
  year column, while identity and field checks continue to apply.

Checks use the parser's actual column/cell qualifiers. No page title alone,
candidate-supplied qualifier, nearby unrelated year, domain, entity, answer
literal or ranking bonus supplies the binding. Multi-year questions and
as-of questions keep their existing semantic handling. Planning, fetching,
budgets, ranking and model prompts are unchanged.

## Paired evidence

Baseline: `197a4c4`. The final pair is:

- `benchmarks/table-years-20261023-before-v3.json`: **41/86** checks pass.
- `benchmarks/table-years-20261023-after-v2.json`: **86/86** checks pass.

Both reports record the same diagnostic SHA. All 41 previously passing checks
are retained; 45 assertions change from failing to passing. These assertions
include related variants, not 86 independent facts or a web accuracy score.

The diagnostic varies field names (population, enrollment, director, email),
year values and column order over invented HTML. It covers vertical and wide
tables, cell contexts containing a neighbor's year, an incorrect row beneath
a correct-year heading, bare years, equal values in multiple years,
ambiguous/missing year values and unrelated year meanings. Initial authored
controls were run before the production edit; the final additional
model-disabled HTTP case was added afterwards. Earlier v1/v2 baseline and v1
after reports are retained; the final comparison uses the same 86 checks.

Three complete engine checks use actual loopback HTTP:

1. A CPU semantic stub selecting the correct-year literal still returns it.
2. The stub deliberately selects the other year's literal and always says
   supported. Before the answer is accepted; after the literal guard rejects
   it before semantic confirmation can authorize it.
3. With the model entirely disabled and wrong-year data first in DOM order,
   the deterministic fallback previously answers `839`; now it answers the
   requested year's `617`, citing the actually fetched table. These numbers
   are invented diagnostic inputs, absent from the production change.

Reproduce with fresh output paths:

```powershell
.\.venv\Scripts\python.exe eval/diagnose_table_years.py --baseline 197a4c4 --out benchmarks/table-years-new-before.json
.\.venv\Scripts\python.exe eval/diagnose_table_years.py --out benchmarks/table-years-new-after.json
```

The baseline command exits with status 1 because it intentionally exposes the
old failures. Neither command starts a real model, GPU or browser.

Existing CPU checks pass: reader 15, calendar/record structure 27, record
bindings 11, proofs 27, birth bindings 51, event years 41, P0 16, assessment
input boundary 7. Their new artifacts use the `table-years-20261023-` prefix.
Some diagnostics compare against their own older baseline; those printed
before/after gains must not be attributed to this table patch.

## Limits and next issue

This is a shared structural constraint, not evidence of unseen-question
generalization. No real assessment questions were sampled and no new live
accuracy result replaces the retained **0/12** first-new-sample result.
See the [generalization audit](GENERALIZATION_AUDIT_2026-10-23.md).

An authored prose example still exposes a separate gap: a paragraph with a
census year, population, household count and later population permits multiple
literal numbers under the existing generic guard. This table change does not
solve that prose relation or the missing planner year in `at the YEAR census`.
That requires separate diagnosis and controls; it must not be counted as fixed.
No GPU, real model, browser, public HTTP request or paid API was used.
