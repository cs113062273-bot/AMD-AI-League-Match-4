# Pending: counts whose scale is in a table column header

Production `a0796d5` fixes the earlier shared-excerpt defect. A separate CPU
HTTP probe now confirms a missing derivation even when the complete source
row and header are visible. No production implementation for this new case
has been added.

`eval/diagnose_header_scale_probe.py` serves a real HTML table with two rows.
The requested Elm Hall row has cell `4.2` under `Chairs (millions)`; the other
Oak Hall row has cell `4`. The CPU reader computes only from the requested
visible row/header using Decimal. It returns 4200000. The current pipeline
rejects that nonliteral answer before verification (`model_invalid_reply`).

When the reader instead copies 4.2, the independent verifier uses the visible
million scale and rejects the coefficient as an answer to the full count.
That rejection is correct; this is an unsupported derivation, not evidence
that the current pipeline wrongly accepts 4.2. A thousands header similarly
exposes the missing 4200 derivation. An ordinary unscaled integer cell still
returns 4 with `model_verified`.

Receipt: `benchmarks/header-scale-20261024-probe-v1.json`. All four requests
contain the complete requested row and header, and complete source HTML,
production/diagnostic hashes and HTTP request traces are retained. No actual
model, new competition question, external request or new accuracy score is
involved; `torch_imported` is false.

The intended improvement must preserve actual literal premises: the exact
column header and scalar cell, tied to the same actual row, column, page and
locator. The resulting full count is a computed answer, not a fabricated
contiguous source phrase. Existing proof operations are the natural place to
evaluate this, rather than allowing arbitrary nonliteral reader replies.

Required controls before promotion include correct row/entity and column
binding, observation years and versions, duplicate/conflicting headers or
values, another eligible unscaled source, truncated/missing metadata,
approximation and ranges, negatives, nonintegral/overflow results, ambiguous
number formatting and unsupported unit/scale notation. A question explicitly
requesting values in millions must not be multiplied into a different output
unit. Unknown header/caption inheritance must not be guessed.

An independent semantic check still needs the real premises and relevant
conflicting contexts. Existing proof requests carry full atom spans in their
premise objects as well as separate passage prefixes; inspect the entire
request before changing those fields or claiming proof evidence was clipped.
Do not solve this by suppressing the case when its complete, unambiguous
header/cell derivation fits the existing budgets.
