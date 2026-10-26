# Keep identical text when its section changes the meaning

The HTML parser deduplicated passages by `(text, label, value)`. The engine
then deduplicated ranked passages by `(source, text)`. Both keys omitted the
section, although selection/verification uses that section to distinguish
entities, dates and other question constraints. Identical facts under a later
heading could disappear before the reader saw them.

Both keys now retain section. The typed-candidate evidence bonus also includes
section, so a verified candidate's bonus is not transferred to another heading
just because its wording is identical. Ordinary duplicates within the same
section retain the existing deduplication behavior. No answer, name, source
catalog, question identifier, scoring alias or site-specific rule was added.

## Evidence from saved sources

`benchmarks/section-dedup-20261024-source-audit-final-v3.json` verifies all 24
original capture hashes from the two exposed disjoint assessments and compares
the isolated `26a18e8` parser with the same parser retaining section in its key.
It examines 77 unique nonempty HTML documents, excluding discovery responses,
browser assets and errored responses. This is saved-source coverage, not a
current live-web assessment. The audit also executes the current production
parser on those documents.

Fifteen documents contain 54 groups of identical text under different
sections. Some are navigation/boilerplate; these are not 54 bugs or score wins.
The new parser retains 58 additional scoped passage records. All original
passage records, including locators and qualifiers, remain present in all 77
documents; every production result equals the scoped diagnostic variant.

One substantive witness comes from the frozen rules article at
`https://thekindgm.com/2022/10/19/unearthed-arcana-2022-expert-classes-analysis/`.
Its identical hit-dice statement appears under two different character-class
headings, but the old parser retained only the first occurrence. Other shared
class rules likewise lost later headings. The witness body is loaded directly
from the original capture; capture and body hashes are checked before replay.

## Paired CPU integration

Primary receipt: `benchmarks/section-dedup-20261024-paired-final-v3.json`.
Identical loopback HTTP harness, isolated baseline `26a18e8`: **4/8 -> 8/8**,
four related control wins and zero losses. Controls cover a later entity, a
later year, both contexts surviving passage ranking, unchanged earlier-entity
behavior, same-section deduplication and semantic rejection.

Two additional controls serve the exact saved article bytes and ask authored
questions about each class's hit dice. The later-class query previously
abstained because its scoped fact was gone; after the fix an authored CPU
selector/verifier can use the actual later-section literal and the engine
returns it with the local replay source. The earlier-class control is retained.
These authored questions and semantic replies are not the original external
assessment query, an independent holdout, a real model read or a strict source
score gain. Intermediate probes and earlier audit versions remain intact.

CPU regressions pass: table years 86, population roles 90, field groups 42,
record bindings 11, source excerpts 60, reader 15, proofs 27, P0 16, public
relationship counts 93, paragraph boundaries 24, header scales 88 and query-local
capacity memo 23. Their older baseline wins are not new wins for this change.
Primary audit and paired receipts record `torch_imported: false`.

## Limits

Section means the heading context already extracted by the parser. This does
not reconstruct a complete heading ancestry where that was absent, nor preserve
every other possible semantic distinction between identical strings. More
distinct contexts can displace other passages within the unchanged first-eight
reader limit or increase a request's size. Real-model capacity and semantics
remain unmeasured; oversized full requests still abstain explicitly.

No GPU, real model/tokenizer, browser, external request, new independent rows,
gold/alias/scorer edit, build, push or submission was used. Latest independent
real first-attempt accuracy remains **0/12 exact/joint**. Competition readiness
is still unproven, and the full optimization goal remains active.
