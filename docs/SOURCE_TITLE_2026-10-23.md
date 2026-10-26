# Recovering the subject of actual failure 2215

The question describes an unknown ancient runner. The supplied source URL is
`https://en.wikipedia.org/wiki/Hermogenes_of_Xanthos`, but it returned 403.
Existing queries discarded that available subject and searched for “The Horse
individual known”, retrieving brands, horses and a LinkedIn query-echo page.

After an observed 403/429/certificate failure, discovery now uses the title of
the user's Wikipedia article as a quoted query when none of its subject words
are already in the question. The title also anchors result relevance. Known
subjects such as Activision Blizzard retain their existing queries. Ordinary
source success does not activate this fallback. Query/provider/page/depth
limits remain unchanged. The title is never inserted into answer evidence.

The extraction accepts bounded, public Wikipedia article paths, including
language/mobile hosts, and rejects credentials, unusual ports, non-HTTP,
lookalikes, control characters, namespaces, malformed encoding and long titles.
The original question and downstream literal/semantic checks remain intact.

Actual guarded HTTP discovery and four source requests are saved in
`benchmarks/source-title-20261023-live.json`. Three pages returned 403, but
Grokipedia returned a full article. Its actual paragraph now ranks first in the
reader payload and includes the name, Horse nickname, eight Olympic crowns,
three consecutive Games and 81–89 CE. The [Dicolympique article](https://www.dicolympique.fr/hermogenes-xanthos/)
was also independently retrieved during the earlier unquoted-title probe; it
is not silently substituted into the production search result.

`benchmarks/source-title-20261023-replay.json` reruns before/after discovery over
the exact same combined, SHA-verified old/new HTTP captures. Both replays have
zero missing captures. Before has no complete witness in the reader payload;
after has one. Fifteen URL/subject guards pass, and a reachable source leaves
the old search result unchanged. Existing hint controls (20), six captured
query replays, discovery controls (7), and reader controls (15) pass.

This establishes repaired retrieval, not a final model answer or strict joint
score: no model, browser or GPU was started, and the new source URL is not the
frozen gold Wikipedia URL. No gold or evaluator matching rules were changed.
