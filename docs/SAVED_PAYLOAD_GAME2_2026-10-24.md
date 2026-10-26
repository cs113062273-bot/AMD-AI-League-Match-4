# Localize an exposed score question before adding another rule

After the capacity-recovery fix, inspect the actual sources already obtained
for the exposed `simpleqa-1076` question, rather than assuming its original
certificate failure means no subsequent source was available.

`eval/audit_saved_payload.py` reads the existing discovery receipt
`benchmarks/named-year-20261023-live-v1.json`, verifies the original capture's
SHA-256, and applies current document parsing, passage ranking and selection
payload construction. It reads the original question and starting URL, not
gold answers or source aliases. Its focus phrase, `Game 2`, must occur in the
original question. The receipt refuses overwrite.

Primary result: `benchmarks/saved-payload-20261024-game2-v1.json`.
The saved discovery has two readable HTML source documents. Current ranking
produces 180 eligible unique passages; two passages mentioning the requested
game are actually sent in the first eight contexts, at ranks zero and three.
Their visible excerpts retain the relevant game-result sentences. Thus adding
a special source route or a sport/team-specific ranking rule is not justified
by this source replay. No such production change was made.

The complete compact selection payload has 6,465 characters. This is not a
token count, a claim that it fits the resident model, or evidence of a correct
real-model answer. Capacity, model selection and independent verification
remain the next relevant checks for this retrieved-source case. The old
source-assisted first assessment, later source discovery, this raw-source
replay, and a future model run must remain separate measurements.

The first broad exploratory capture scan also parsed browser script responses
as if they were documents. That creates irrelevant high-ranking JavaScript
passages, but `agent/browser.py` only parses the rendered main DOM for the
engine; scripts fetched through its guarded route are not independent evidence
pages. The audit therefore excludes discovery responses and non-document
content types. It does not infer a production script-evidence bug from the
presence of browser assets in a network capture. It also does not reconstruct
the browser DOM or execute scripts. JSON/API replay is outside this HTML/PDF
audit's scope and must use its actual adapter separately.

One exploratory public web search also located alternative historical source
pages. None was fetched through the project, added to production, or used for
this receipt. Its evidence comes entirely from the hash-verified existing
capture. No GPU, real model/tokenizer, browser, new assessment rows, answer or
scoring changes, build, push or submission was used. Latest independent real
first-attempt accuracy remains 0/12 exact/joint; readiness is still unproven.
