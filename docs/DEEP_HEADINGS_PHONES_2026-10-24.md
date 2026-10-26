# Deep contact headings and complete literal telephone numbers

The saved-source heading audit found that the HTML parser handles headings only
through `h4`. An existing captured retailer page uses `h5` and `h6` for regions
and store names. Its telephone paragraphs therefore inherited the generic
contact-section title and could not be bound to the requested store by the
reader. The fix recognizes all six heading levels in ordinary extraction,
compact-record scopes, table scopes, first-line extraction and repaired
paragraph windows. Hidden elements are still removed before heading extraction.

This actual-source replay exposed a second failure: `(02)2951-6736` reaches the
reader, but the phone grammar requires a separator after a parenthesized area
code. It rejects the complete displayed number while lexical extraction can
instead find the subscriber-number suffix. `agent/phones.py` now supports that
display format and centralizes complete literal-span checks. Candidate
verification, the resident reply validator and the alternate-endpoint selector
all require a whole source telephone span. Dropping an area code, country code,
leading plus sign or displayed extension cannot be licensed by copying a suffix
of the longer source number. A separate later complete occurrence can still
license the same digits. Existing digit-length, ISO-date and IP-address guards
remain. No country code or formatting is inferred or rewritten.

## Evidence

The diagnostic heading-path exploration is retained in
`benchmarks/heading-paths-20261024-source-probe-v2.json`: 24 hash-verified
original captures, 77 unique HTML sources, two identical-leaf-heading collision
groups and twelve groups of differently scoped facts. Several groups are
navigation/boilerplate, not answer failures. The diagnostic path decorator was
not promoted: this change fixes the observed unsupported heading levels without
adding ancestor dates to deterministic year guards or a new payload schema.
General heading ancestry remains separate work.

The complete local-HTTP paired harness is
`benchmarks/deep-headings-20261024-paired-final-v5.json`. Identical baseline
`858be7c`: **6/15 -> 15/15**, nine related control wins and zero losses. It checks
all six heading levels, deep tables and compact records, first-line requests,
repaired paragraph windows, hidden-heading removal, semantic rejection and
rejection of deliberately truncated telephone replies even when an authored
semantic endpoint would approve them.

One control serves the exact saved body from
`https://www.daynday.com.tw/dayday`, verified against its original capture/body
hashes, and asks an authored store-phone question. After the heading-only pilot,
the requested store's literal telephone paragraph ranks first but fails phone
validation. With both fixes it is selected, independently verified by the CPU
stub and returned with the local replay source. The source was captured while
working on another external question; this authored replay is not that original
question, an independent assessment, or a new external-score point.

`benchmarks/phone-spans-20261024-paired-final-v4.json` separately compares the
same baseline: **6/20 -> 20/20**, fourteen related controls, zero losses. It covers
old/new display formats, complete extraction, partial-area/country/extension
replies in both copied-span and candidate-ID modes, invalid lengths, ISO dates/IPs
and a later separate complete occurrence.
These are overlapping phone controls, not twenty independent factual questions.

The final saved-source audit is
`benchmarks/deep-headings-20261024-source-audit-final-v3.json`. Of the same 77
HTML sources, 76 produce identical complete page records. The retailer page
retains every original `(text, label, value)` field, gains 26 heading atoms and
updates 26 existing scope records. Eight product-name passages move from prose
to heading; this is reclassification, not lost text. Element-index locators on
that page change consistently when deep headings enter the extraction walk.
Original capture bytes remain unchanged.

Earlier probes/pilots remain. The early compact-record fixture had only nine
combined characters and did not meet the existing ten-character record rule;
the final identical paired fixture uses a longer explicit label. The production
record-size rule was not relaxed. Final comparisons alone supply the results
above; pilot counts are not pooled.

CPU regressions pass: reader 15, P0 16, proofs 27, existing section scopes 8,
table years 86, population roles 90, field groups 42, paragraph boundaries 24,
source excerpts 60, public relationship counts 93 and query-local capacity memo
23. Seven assessment-input/import-boundary checks also pass. Those drivers'
older baseline wins are not additional wins for this change. Primary paired
and source-audit receipts record no `torch` import.

## Remaining limits

Phone syntax and complete source spans do not prove ownership, current service,
or which of several listed numbers the question requests. Those remain semantic
and source-identity decisions. Arbitrary international display formats are not
universally supported. The current legacy seven-to-fifteen-digit bound excludes
short emergency/extension-only numbers. Deep headings can affect passage ranking
and request size; real-model fit and semantics have not been remeasured.

No GPU, real model/tokenizer, browser, external request, new independent rows,
gold/alias/scorer edit, build, push or submission was used. Latest independent
real first-attempt accuracy remains **0/12 exact/joint**. The competition-readiness
goal remains active.

The next CPU probe, `benchmarks/source-binding-20261024-probe-v1.json`, confirms
a separate verifier-binding gap. Two explicit award records have identical
text/labels and different years/locators. The candidate selects the actual
2024 record, but `candidates.verify` chooses the first matching label from its
text index, evaluates the 2023 record and rejects it. The next repair must bind
the selected locator and scope before applying the existing year/field guards;
removing those guards would not resolve the underlying source-identity error.
