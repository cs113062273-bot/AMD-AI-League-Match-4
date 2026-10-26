# Requested month and year in actual failure 483

The original question starts `Specify the month, and year`. Planning recognized
only `What/Which month and year`, so it used ordinary text and omitted month
precision. The planner now recognizes explicit Specify/State/Give/Provide/Tell
me requests, both field orders, and the optional comma before `and`.

The same captured GamesBeat article contains `October 22, 2015` and states the
company announced the division that morning. Its June 2025 update remains a
different date; semantic selection is still required. The official investor
announcement, its PDF, and the SEC filing returned 403 in the actual project
client. Their failures and the readable article are retained in
`benchmarks/announcement-20261023-sources.json` with capture hashes.

In `benchmarks/month-request-20261023.json`, the same literal selector stub and
actual captured article yield `October 22, 2015` before and `October 2015`
after. The latter is the existing source-checked month projection. The 14
request controls change from 7 passing to 14; all 27 existing calendar/record
controls remain passing. These are CPU protocol checks, not real model answers.

No gold, source aliases or scoring rules were changed. The frozen exact gold
has different punctuation (`October, 2015`), so this result is not claimed as an
exact-match benchmark win. Production retrieval and semantic model selection
have not yet been rerun under the user's no-GPU constraint.
