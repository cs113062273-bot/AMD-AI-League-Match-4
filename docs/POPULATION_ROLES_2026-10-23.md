# Distinguish population, households and census years in prose

The previous planner classified `What was the population ... at the YEAR
census?` as free text without a year constraint. In an authored paragraph,
population, household count, census year and a later population all passed
literal verification. This is a planning and evidence-role gap, not an answer
spelling problem.

The shared fix has three parts:

- Explicit population-count questions, including `what's` and selected
  `how many inhabitants` forms, use number extraction. Density, growth,
  percentages and questions asking which population of cells are preserved.
- One explicitly supplied census year after `at`, `according to`, `from` or
  `per` can supply the existing year constraint. Negated census constraints,
  multiple years, URL contents and version-like decimals do not supply it.
- For a single point-year population request, a prose literal is rejected
  when **all its numeric occurrences** have an explicitly incompatible role:
  households, a census/calendar year, or a population locally assigned to a
  different year. A value also used as a supported population is retained,
  including a population numerically equal to the census year.

The last check is deliberately a rejection check, not a positive semantic
proof. An unclassified occurrence, unknown wording or unresolved multi-year
clause still requires the ordinary semantic verifier. The subject's identity,
negation, units, estimates and relations are not proven merely by passing it.
As-of and multi-year reasoning are not replaced. Tables retain their separate
[row/column year constraints](TABLE_YEARS_2026-10-23.md).

There are no entity names, village IDs, expected counts, source URLs or new
ranking bonuses in the production change. `agent/population.py` parses source
roles; planning and candidate verification call it.

## Evidence and boundaries

Final paired diagnostic: baseline `f68287f`, same diagnostic SHA in
`benchmarks/population-roles-20261023-before-v3.json` and
`benchmarks/population-roles-20261023-after-v3.json`: **32/90 to 90/90**, all 32
prior passing assertions retained. Related substitutions are authored controls,
not 90 independent facts or a generalization score.

The five actual loopback HTTP checks retain a correct selection, reject a
household count, reject a census year and reject the other year's population
despite a semantic stub that always says supported. With the model entirely
disabled, the complete HTTP engine changes from empty to the authored
paragraph's correct `617`, citing the fetched page. No real model is simulated
as an accuracy result.

The saved actual Konaruiyeh paragraph, with its input capture hashes retained
in `population-roles-20261023-exposed-audit.json`, still accepts literal `219`.
It now rejects `2006` (census year) and `44` (families); before all three passed.
The existing full captured discovery replay still reaches the readable source
and returns `219` through the same explicit CPU stubs. That replay already
returned `219` before this patch, so it is **not a new end-to-end accuracy win**.
The readable mirror also remains different from the original gold source.

The final planning audit (`population-roles-20261023-exposed-audit-v2.json`)
checks all 244 already exposed cases. Four plans change: population requests
2934 and 262 become numeric; 1726 and 1232 become numeric and retain their
explicit census years (2021 and 2006). Other plan fields and other cases stay
unchanged. These are development data; no new external questions were sampled.

Earlier diagnostic attempts remain retained. The first after report was
82/83 because the negated census phrasing exposed a trailing focus fragment.
That was corrected, ambiguous population-type and URL/version negatives were
added, and contractions were checked. Final before/after use the same 90
assertions; none of these are independent held-out tuning evidence.

CPU regressions pass: table years 86, reader 15, proofs 27, event years 41,
birth bindings 51, calendar/record structure 27, P0 16, assessment boundary 7,
and the captured discovery replay with seven controlled HTTP checks. Older
diagnostics' gains against their historical baselines belong to earlier work.

```powershell
.\.venv\Scripts\python.exe eval/diagnose_population_roles.py --baseline f68287f --out benchmarks/population-new-before.json
.\.venv\Scripts\python.exe eval/diagnose_population_roles.py --out benchmarks/population-new-after.json
```

Use new output names; the baseline command intentionally fails its assertions.
No GPU, model weights, browser, public HTTP request or paid API was used.
The retained first-new-sample result is still **0/12**, not superseded by these
CPU checks. See the [generalization audit](GENERALIZATION_AUDIT_2026-10-23.md).

A separate literal-boundary probe found that `10` can currently pass as a span
of `10,000`, and `617` as a span of `1,617`. That general numeric-token defect
is not fixed or counted as fixed by the population patch. The subsequent
[grouped-number boundary fix](GROUPED_NUMBERS_2026-10-23.md) addresses standard
comma-grouped scalars separately.
