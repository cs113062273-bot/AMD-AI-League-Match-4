# Unread answer source in actual village failure 1232

The original search already returned Alchetron's Konaruiyeh article as result
six. Its actual readable body contains the village, full administrative
location, 2006 census, population 219 and 44 families. The frozen failed run
never requested that URL: after the first four results, the census portal's
four year-navigation links filled the final fetch batch. Existing pending
discovery only refilled empty slots, so the known alternative was starved.

After a search has supplied a first batch and no answer has returned, scheduling
now reserves up to two slots in the next existing four-page batch for pending
independent results. Remaining slots retain navigation, including the selected
target. A newly recovered first search batch is not reshuffled. When there are
no pending results or no navigation, existing behavior remains. Page, depth,
request, browser and model budgets are unchanged. This balances two available
routes; it does not guarantee every lower-ranked source or navigation link can
be fetched under fixed bounds.

`benchmarks/discovery-reserve-20261023-v3.json` compares revision `ed6436c` and
the patch through the complete engine over the same SHA-verified HTTP bodies.
Both replays have zero missing responses. Before visits four census archive
years and abstains; after requests the pending Alchetron article and the
selected census navigation link. The transmitted evidence includes the exact
2006 population statement. With the same explicit CPU selector/verifier stubs,
the result changes from empty to `219`, citing the actual fetched Alchetron URL.
This is an engine/protocol result, not a real model answer or a new score.

Seven real loopback HTTP controls improve from four to seven passing. They
cover a crowded landing page, a correct navigation target retained alongside
pending results, no pending results, a single pending result, initial discovery
without a starting URL, and the original page/depth caps. Content URLs stay
unique, the first batch is preserved, and chosen navigation remains visited.
Existing discovery queue (6), reader (15), P0 (16) and discovery (7) checks pass.

The v1/v2 diagnostic reports are retained. Their HTTP harness initially used a
403 start on the same host as all search results, activating the existing failed
host penalty; it was replaced with an answerless 200 landing page. It also
incorrectly asserted arrival order inside a concurrent fetch batch; final
checks validate batch membership and start order instead. No production
changes were made to satisfy those harness errors.

No GPU, actual model or browser was started. TLS validation and frozen gold
remain unchanged. The original gold source is Wikipedia, so a readable mirror
does not establish a strict source-gold improvement. Next work should check
typed population/year constraints and incorrect census-year evidence, rather
than assuming that a literal number alone proves the requested census fact.
