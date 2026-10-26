# Preserve the boundaries of comma-grouped numbers

`literal_span` previously accepted `10` inside `10,000`, `617` inside `1,617`,
and `1,234` inside `1,234,567`. A semantic endpoint saying supported could turn
these partial numeric spans into final answers. Literal occurrence alone was
not enough to establish a complete numeric value.

The fix identifies standard comma-grouped scalar spans and rejects an answer
boundary that falls inside one. It applies to the existing numeric kinds:
number, percentage, measurement, duration, price, year and time. It retains
signs, decimal suffixes, units and currency punctuation without normalizing
the answer or adding scoring aliases. A later standalone occurrence can still
support the same value. Text, versions, phone and date kinds retain their
existing rules.

This is lexical validation, not locale or semantic inference. It recognizes
one to three initial digits followed by comma-separated groups of three,
optionally with a decimal suffix. Whitespace-separated lists (`10, 20`) and a
four-digit date year after a comma (`March 1,2014`) remain usable. Other locale
formats, comma decimals, malformed groupings and contextually ambiguous
unspaced lists are not universally resolved by this patch.

The paired `eval/diagnose_grouped_numbers.py` reports use the same diagnostic
SHA, baseline `d2f489c`:

- `benchmarks/grouped-numbers-20261023-before-v1.json`: **101/165** assertions.
- `benchmarks/grouped-numbers-20261023-after-v1.json`: **165/165** assertions.

All 101 prior passing assertions are retained; 64 change from failing to
passing. Most assertions repeat the same lexical requirements under different
numeric-kind flags. They test the literal helper independently of full type
validation and are not 165 independent questions or an accuracy percentage.

Two complete-engine loopback HTTP checks use an explicit CPU semantic stub
which always says supported. Correct `10,000` remains accepted; selecting `10`
from the only `10,000` source changes from an erroneous answer to abstention.
This does not establish real-model accuracy or teach the model to choose the
correct span after rejection.

Existing CPU regression artifacts use the same prefix: population roles90,
table years86, reader15, proofs27, birth bindings51, event years41,
calendar/record structure27 and P0 16 all pass. Their older-baseline gains
belong to the earlier patches, not this change.

```powershell
.\.venv\Scripts\python.exe eval/diagnose_grouped_numbers.py --baseline d2f489c --out benchmarks/grouped-new-before.json
.\.venv\Scripts\python.exe eval/diagnose_grouped_numbers.py --out benchmarks/grouped-new-after.json
```

Use fresh output paths. The baseline command intentionally exits with failed
assertions. No GPU, model weights, browser, public HTTP or paid API is used.
Original answers and gold sources are unchanged; no new external sample was
opened. The retained first-new-sample result remains **0/12**. Shared lexical
correctness checks do not replace the pending independent validation described
in the [generalization audit](GENERALIZATION_AUDIT_2026-10-23.md).
