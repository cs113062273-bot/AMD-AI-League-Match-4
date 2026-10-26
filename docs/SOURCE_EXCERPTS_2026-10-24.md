# Shared source excerpts

The frozen `c02cacf` probe showed an actual evidence-fidelity defect under
authored CPU HTTP readers: the complete source says Elm Hall has 4 million
chairs, but both model requests end at `Elm Hall has 4`. A legitimate earlier
Oak Hall count of 4 allows the mechanical literal check to pass. The resulting
answer was 4 with `model_verified`; this is not a real-model accuracy result.
The original probe, its receipt and original assessments remain unchanged.

## Production change

`agent/source_excerpts.py` chooses a contiguous slice from the actual parsed
passage. Short passages remain unchanged. Longer ones use word and complete
numeral-run boundaries, including invalid scaled runs as negative boundaries.
Candidate windows include the beginning, end and positions near question terms.
Distinct query terms with following context receive relevance weight; repeated
source terms receive less weight. Following context is 96 characters or all
remaining source text, whichever is shorter. Length and earlier position break
ties. This is a bounded relevance heuristic, not full semantic understanding.

The policy sees the question and source, never the proposed answer. It inserts
no facts or ellipses. Each payload includes source character offsets, retains
the actual URL and locator, and keeps the existing maximum of eight passages
and 1,100 characters per passage. Deadlines and model settings are unchanged.

Selection and semantic verification use the same policy. Selection binds only
to the transmitted slice; the candidate retains the complete actual parsed
passage for independent source/type checks. Multi-member verification uses that
same slice instead of the old prefix. License projection receives the exact
visible text, so it cannot expand an operand using an unseen full field.

Verification resolves the candidate back to an actual parsed source passage;
an invented candidate cannot create a fallback prefix. It retains distinct
sources even when they have identical text. A selected passage may be moved
first, but no distinct original context is removed. Same-record license and
first-author projections keep the original reader contexts rather than evicting
the eighth context to insert the projected field. The complete license was
already required to be visible; surname/given-name ordering remains supported.

## Evidence

Primary receipt: `benchmarks/source-excerpts-20261024-paired-v6.json`.
`eval/diagnose_source_excerpts.py` runs the identical final harness against
isolated production `c02cacf` and the current worktree, through real loopback
HTTP. **20/60 -> 60/60**, 40 assertion wins and zero losses. These are related,
authored controls, not 60 independent questions or a competition score. Source
and diagnostic hashes and the seven Engine request traces are retained.

Controls include:

- Elm Hall returns 4000000 while the earlier Oak Hall still returns 4.
- Complete contradictory quantities remain visible and cause abstention.
- Word and decimal coefficients survive the old cut.
- Seven kinds of assertion (including ranges, approximation and negation) at
  four offsets retain their whole wording, with ordinary padding and different
  names. This checks fidelity, not expansion of unsupported arithmetic.
- A source literal excluded from the transmitted window cannot be selected.
- Invented verification evidence is rejected before HTTP.
- Later multi-member answers and complete license projection pass mechanical
  source checks. First-author canonicalization is retained.
- Eight original contexts survive license/name projections, including the
  eighth conflicting source note; identical text at different URLs survives.

Earlier v1-v5 receipts are retained pilots. Some earlier harness versions had
different assertion counts; only the paired v6 harness supplies the final
before/after comparison. The initial v1 direct-source setup was corrected to
put its selected passage in the actual page's parsed passage list.

CPU regressions pass: reader 15, proof 27, selector boundary 10, cardinal counts
101, magnitude counts 103, license expressions 31 and guards 72, members 28
and source guards 12, first lines 22, field groups 42, inline fields 19,
population roles 90, table years 86, grouped numbers 165, P0 16, paragraph
boundaries 24, named year 12, creator/location 16 and month requests 14.
The cooperative CPU-only HTTP lifecycle probe also passes 8/8; its generation
probe was not invoked and `torch_imported` remains false.
Some regression drivers compare against their own older baselines; their
printed historical wins are not additional wins for this change.

No GPU, model/tokenizer loading, browser, external request, paid API, new
assessment question, gold/alias edit, build, push or submission was used.
`torch_imported` is false in the paired receipt. The latest independent real
first attempt remains 0/12 exact/joint; these controls do not update it.

## Limits and next work

A bounded window cannot guarantee that every relevant fact or contradiction
anywhere on a long page is visible. This change prevents the demonstrated
quantity split and preserves the selected verification context; it does not
prove universal retrieval or numeric semantics. Source parser truncation is a
separate boundary, and table-header scale/unit inheritance remains unsupported.
Proof verification still transmits complete atom spans in its premise objects;
its separate legacy passage prefixes need an audit of the entire request before
any change. Do not treat that prefix alone as evidence of missing proof facts.
