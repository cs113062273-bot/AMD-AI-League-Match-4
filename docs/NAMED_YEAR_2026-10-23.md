# Empty-hint recovery for actual failure 1076

The original Selkirk question yielded no source pages: the starting mirror had
a certificate error, the model expansion was empty, and the remaining long
queries produced unrelated results or challenges. TLS validation remains on.

When existing valid model hints and quoted-text fallbacks are absent, a final
short query can now use two explicit multiword capitalized names plus a single
unambiguous calendar year from the original question. Names are bounded to
2–4 words; the query to 9 words/120 characters. Leading request words are
removed and duplicate names rejected. Multiple/no years, one name, URLs,
standards identifiers and version numbers do not trigger it. Existing valid
hints, quoted fallbacks, provider budgets and the reader question are retained.

The actual original question generates `Selkirk Fishermen Memorial Cup 1920`.
The public GET probes and current real discovery run are retained in
`benchmarks/selkirk-20261023-query-probe.json` and
`benchmarks/named-year-20261023-live-v1.json`. Current code independently
retrieves Grokipedia and the Manitoba Hockey Hall of Fame. The latter supports
the aggregate result, not the requested individual game. The former provides
the actual second-game score in the first reader passage. No gold answer,
source URL or sport-specific rule was inserted into production.

`benchmarks/named-year-20261023-replay-v2.json` compares revision `f95c617` with
the fix over the same combined SHA-verified captured responses, with zero
missing responses in either run. Before has no complete witness; after has the
second-game score in the transmitted payload. A selector stub copying `4`
passes the literal guard; the score alone also passes, without a matching
footnote. This is a protocol check, not a model answer.

The first control run exposed duplicate detection counting `Did River Academy`
as a different name from `River Academy`. Removing leading request words fixes
it. The failed v1 report is retained; final 12 controls pass. Existing concise
controls (9), hint controls (20 plus six public-response replays), and discovery
controls (7) pass. No GPU, model or browser was started; no new accuracy or
strict source score is claimed. The original mirror source gold is unchanged.
