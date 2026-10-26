# Pending: preserve count information at the reader excerpt boundary

`eval/diagnose_excerpt_probe.py` reproduces a separate display-integrity
problem in production `2dfd43e`, using actual loopback HTTP and an authored
CPU reader/verifier. No real model or external source is involved.

The complete source paragraph states that Oak Hall has 4 chairs and Elm Hall
has 4 million chairs. Its padding places the Elm Hall coefficient at
character 1099. Both selection and verification receive `p.text[:1100]`,
which ends with `Elm Hall has 4`, hiding the magnitude and final unit.

The CPU reader selects the value actually displayed after Elm Hall; the
CPU verifier approves the value displayed for that subject. The pipeline
returns **4**, with reason `model_verified`. The full source instead states
4 million. A separate earlier, legitimate 4 in the same paragraph satisfies
the mechanical literal check, so whole-quantity boundaries alone cannot
disambiguate the intended occurrence.

The receipt is `benchmarks/excerpt-truncation-20261024-probe-v1.json`, with
complete request/response trace, exact source and production hashes. This
is a controlled evidence-loss demonstration, not proof that the resident
model would make this error or a new competition score. Production has not
yet been changed for this probe; it is not included among the magnitude
feature's passing assertions.

The next change needs consistent source excerpt formation for selection and
verification, not only a wider literal/type exception. The Elm Hall query
should retain its complete quantity when it fits the unchanged context
budget; the Oak Hall query must retain its earlier legitimate count. Both
must bind only to text actually transmitted. A new window must not hide
contradictions or gain facts from model memory, and verification must not
reintroduce the old raw prefix. Existing eight-passage, character, deadline,
source-binding and independent-verification bounds remain relevant.

No GPU/model/tokenizer, browser, public request, paid API, gold/alias change,
bulk assessment, build, push or submission was used.
