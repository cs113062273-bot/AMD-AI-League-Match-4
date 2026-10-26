# Exact-paper discovery and requested-field ranking for failure 516

The saved failed run read a different PMC article (`PMC8970926`) and never
obtained the requested paper's participant paragraph. A public exact-title
Lite probe also returned a challenge, so no generic query rewrite was promoted
on that evidence alone. The failed probe is retained.

The new discovery path extracts one explicitly quoted paper/article/study title
from the original user question. It calls the official Europe PMC search API
once, concurrently with existing search providers, under a three-second and
250 kB limit. It only accepts an exact normalized title, matching echoed query,
one unambiguous PMCID, MED/PMC record, open-access flag and an explicitly
requested publication year when present. Invalid, truncated, ambiguous,
closed-access, mismatched and redirected-lookalike responses provide no links.

API metadata is discovery only: it generates the official PMC article URL,
which is independently fetched and parsed before any answer evidence exists.
No answer, age, PMCID, author, DOI or article-specific rule was hardcoded in
production. Custom search providers and low remaining budgets skip the API.

The [Europe PMC team explicitly states the API is completely free](https://groups.google.com/a/ebi.ac.uk/g/epmc-webservices/c/cZLnV1JhCj8).
The integration uses only the public keyless EMBL-EBI endpoint, with no account,
card, billing or third-party wrapper. The [official service reference](https://europepmc.org/RestfulWebService)
describes title search and result metadata. Article reuse remains subject to
its license; this actual paper is open access under CC BY.

Actual current HTTP discovery in `benchmarks/literature-20261023-live-v1.json`
finds `PMC7905350` and retrieves its full readable article. However, the first
payload still misses the answer: the participant paragraph ranks **65th**,
while repeated words from the long paper title dominate the first eight slots.
That initial result is retained rather than overwritten.

Ranking now discounts repeated paper-title words after the actual document
title matches the explicitly requested paper. Requested focus words remain.
An age request additionally favors a local explicit numeric age statement in
that identified document. This changes ranking only; it does not establish
semantic correctness or relax literal source verification. Scores for other
document titles and questions without an explicit paper title stay unchanged.

`benchmarks/literature-20261023-replay.json` compares revision `186f268` and the
new code over the same combined SHA-verified public responses, with zero
missing captures. Before finds no participant evidence; after retrieves the
correct article. On that same article, its literal `aged 23 to 27 years`
paragraph moves from rank 65 to **rank 1**. A selector stub copying `23 to 27`
passes the ordinary literal guard. Twenty identity/input negatives pass,
including wrong title/year/PMCID, collision, access flag and query binding.

Existing reader (15), proof (27), hint (20 plus six response replays) and
source-title recovery (15 guards plus paired replay) checks pass. The separate
68-body saved-corpus audit checks passage-score stability for the old sources.

No GPU, model or browser was started. This proves recovered retrieval and
payload evidence, not an actual model answer or a new accuracy score. Frozen
gold is unchanged (`23-27` differs from the stub's literal spelling); no source
or answer aliases were added. The actual primary publisher and PMC bodies are
also retained in `benchmarks/paper-20261023-access.json`.
