# Keep omitted HTML paragraph boundaries out of evidence

In the saved `simpleqa-4145` pages, omitted `</p>` tags caused the installed
BeautifulSoup `html.parser` tree to nest later paragraphs inside earlier
ones. The first article paragraph in the Eureka page contained 16 later
paragraphs, including a long list of links to other cities. The reader
received overlapping whole-page suffixes; a different city's architectural
description ranked ahead of the requested building's evidence.

This is valid evidence of a parser/context problem, not proof of the cause
of the original wrong result. The original model run returned unidentified
503 responses. The correct source witness was already present in its first
eight passages. No real model has been run for this change.

## Change

`agent/html_paragraphs.py` uses the standard-library HTML tokenizer to make
omitted paragraph ends explicit before BeautifulSoup extraction. It inserts
only `</p>` at block starts; original text, attributes, entities, links and
script bodies are retained. Comments and quoted attributes are tokenized,
not rewritten with a regular expression. Opaque text/foreign content is
left alone; paragraph scope respects table cells, buttons and templates.
Stack tracking is bounded. This implements a narrow paragraph repair, not
a complete HTML5 tree builder or general correction of malformed markup.

The basis is the HTML standard's [paragraph end-tag omission rules](https://html.spec.whatwg.org/multipage/grouping-content.html#the-p-element).
The standard-library [parser documentation](https://docs.python.org/3/library/html.parser.html)
also explains that it does not generate end-tag callbacks for implicitly
closed elements. No new parser dependency, browser or network service is
required.

Atomic paragraphs remain separate source passages. On repaired documents,
the parser also retains bounded context from at most three consecutive
sibling paragraphs, within 1,100 characters. Windows stop at headings,
nonparagraph elements, nonwhitespace intervening text and empty/image-only
paragraphs. They exclude table, list-item, preformatted and blockquote
scopes. The original paragraphs remain available. Each window has an actual
source locator and explicit paragraph-window metadata.

These windows retain `kind='prose'`, so existing population/year and other
prose guards still apply. They do not become trusted fields or records, and
selection still requires literal evidence and independent semantic
verification. No requested entity, city, style or answer is embedded in the
production repair.

Simply splitting the saved paragraphs without retaining bounded context
was also inspected locally: the short style sentence then fell to rank 19
because it no longer carried the building description. That incomplete
approach was not promoted. With bounded adjacent context, the actual
Eureka description and its source style sentence appear together at reader
position 0, without the navigation suffix. The witness previously appeared
at position 2 in the serialized request (zero-based); this is an evidence
presentation improvement, not a new correct-answer measurement.

## Verification

`eval/diagnose_paragraph_boundaries.py` uses authored structural controls and
the immutable original four readable NoeHill response bodies. The capture
SHA and per-body hashes are recorded. The final pair
`benchmarks/paragraph-boundaries-20261024-{before,after}-v4.json` shares the
same diagnostic SHA:

- Baseline `8aa920e`: **4/24** assertions.
- Current parser: **24/24**, no losses.
- Controls include omitted/explicit/mixed and uppercase paragraph tags,
  inline formatting, comments, attribute literals, block and heading
  boundaries, navigation/footer removal, script/JSON preservation, escaped
  tags, BR lines, tables, lists and blockquotes.
- Window bounds and heading separation are checked. Four additional checks
  ensure a population window accepts its census population but rejects the
  family count, census year and later population. Baseline has no windows;
  these are availability/guard checks, not four answer improvements.
- The saved-source witness no longer shares a passage with the city-link
  navigation and remains in the first reader payload.

Early diagnostic artifacts are retained. The first diagnostic counted the
new, explicitly marked context windows as merged atomic paragraphs; the
final harness distinguishes those and adds separate window/role checks.
Both final baseline and current were rerun with the identical harness.

Existing CPU checks pass: P0 16/16, reader 15/15, proofs 27/27, population
roles 90/90, table years 86/86, inline fields 19/19, first lines 22/22, named
field groups 42/42, location/creator 16/16, named-year 12/12, literature
20/20 and month-request 14/14. Historical comparison wins printed by those
drivers belong to their earlier fixes, not this patch. The real inline-name
field moves to rank 5 and stays within the first eight; ranks need not be
unchanged when paragraph structure changes.

`paragraph-boundaries-20261024-timing.json` records three alternating parser
runs per saved page. The small observed medians are about 12–31 ms before
and 28–49 ms after. Other local checks ran concurrently; this is not an
isolated performance benchmark, a speedup, or end-to-end latency evidence.

No public source requests, GPU/model loads, browser, paid API, assessment
sweep, build, push or submission were used. Frozen questions, gold, aliases
and first attempts remain unchanged. The retained external first-attempt
score is still 0/12; unseen-question accuracy remains unmeasured.
