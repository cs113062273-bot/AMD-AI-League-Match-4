# Read release-scoped metadata for historical registry questions

A valid cutoff did not make a current registry field historical. A controlled
PyPI response with only today's license could still answer a past-date
question when the semantic verifier blindly supported the literal. npm also
selected metadata through today's `latest` tag and could fill a missing old
field with the current top-level value.

The [PyPI JSON documentation](https://docs.pypi.org/api/json/) distinguishes
latest-project metadata from a version endpoint and describes stored
first-upload release metadata. npm's [package metadata format](https://github.com/npm/registry/blob/main/docs/responses/package-metadata.md)
defines version records and publication times; its [registry API description](https://github.com/npm/registry/blob/main/docs/REGISTRY-API.md)
identifies fields declared in the version's package manifest. These are the
source contracts used here, not evidence of a complete historical registry
archive.

For PyPI/npm non-version/date/year fields with a cutoff or year constraint:

- Select a uniquely highest eligible stable release in the currently available
  catalog, or honor one explicitly requested version. A year-only constraint
  uses releases dated in that year. Preview releases require an explicit
  preview request. Missing dates on a competing higher version and equal
  precedence are unresolved, rather than permission to choose an older value.
- PyPI reuses a matching, dated current record when sufficient. Otherwise it
  makes at most one extra version-metadata request. The fetched record must
  match the official endpoint, package name, exact version and its own file
  dates. A short remaining budget skips that extra request, not the date rule.
- npm reads the selected `versions` entry and its publication time. It does
  not backfill missing historical fields from current top-level metadata.
  Selection follows [SemVer precedence](https://semver.org/): numeric release
  and prerelease components are compared numerically, build metadata does
  not break a tie, and conflicting equal-precedence records remain unresolved.
- Validate complete publication timestamps before taking their calendar date.
  Generated field evidence retains the source's version and publication/file
  upload date witness, without labeling a later file upload as the first release.
  It carries a
  verified release qualifier. Selected PyPI description passages retain this
  scope too, so an author found only in the release description can still be
  read. Raw current API/frontend fields cannot bypass the scope check on a
  later fetch.

The new `agent/registry_history.py` supplies selection and eligibility checks;
`agent/resolvers.py` obtains and projects the actual metadata. Names, expected
licenses, authors and versions from diagnostics are not lookup data in
production. Frozen gold, answer aliases, TLS rules and overall deadlines are
unchanged. Timeless metadata keeps its existing behavior.

## Paired HTTP evidence

The final diagnostic SHA matches between baseline `6a31e8f` in
`benchmarks/registry-history-20261023-before-v7.json` and
`benchmarks/registry-history-20261023-after-v11.json`: **6/43 to 43/43**, with all
six prior passing controls retained. These are authored, related engine/HTTP
controls, not 43 independent facts or a generalization score.

Controls cover both registries, an explicitly requested old/future release,
current queries, already-sufficient current records, absent history, unknown
higher releases, missing fields, incorrect identity/version, bad timestamps,
future own-record dates, lookalike redirects, truncation, a short budget,
frontend bypass, authors in descriptions, version ties and preview ordering.
Package identifiers are excluded from preview-intent recognition: a package
named `beta` does not request a preview channel merely by its name.
An external dated source still passes. With the model disabled, both fixture
registries change from the current `MIT` to their old release's literal
`BSD-3-Clause`; ordinary current queries still return `MIT`.

Earlier reports are retained. The initial frontend fixture was clarified to
have no usable API history; npm fixtures were changed from abbreviated toy
versions to three-component versions. The description, SemVer and malformed
timestamp controls exposed implementation failures that were fixed before
the final same-diagnostic comparison. They are development refinements, not
held-out validation.

CPU regressions pass: cutoff52, P0 16, reader15, proofs27, table years86,
population90, calendar/record structure27 and assessment boundary7. The
latest core reruns use the `registry-history-20261023-final-` prefix; older
diagnostics' baseline gains belong to earlier changes.

```powershell
.\.venv\Scripts\python.exe eval/diagnose_registry_history.py --baseline 6a31e8f --out benchmarks/registry-history-new-before.json
.\.venv\Scripts\python.exe eval/diagnose_registry_history.py --out benchmarks/registry-history-new-after.json
```

Use new output names; the baseline command intentionally fails assertions.
The diagnostic contacts only loopback HTTP, even where logical API URLs appear
in its results. Its semantic service is an explicit CPU stub.

## Actual free-API compatibility reads

Two additional queries used actual public API responses, no starting URL,
model, browser or search. Three unique response bodies are saved unchanged
with SHA hashes under the paths in
`benchmarks/registry-history-20261023-live.json`.

| Registry/package | Cutoff | Selected version/date | Literal declared license |
|---|---|---|---|
| PyPI httpx | 2020-01-31 | 0.11.1 / 2020-01-17 | [BSD](https://pypi.org/pypi/httpx/0.11.1/json) |
| npm chalk | 2020-01-31 | 3.0.0 / 2019-11-09 | [MIT](https://registry.npmjs.org/chalk) |

The same actual bodies are replayed against old/current code in
`registry-history-20261023-real-replay.json`, with no missing captures. PyPI
changes from the current record's `BSD-3-Clause` to the selected release's
literal `BSD`, citing the actual version endpoint. No SPDX alias is inserted.
npm's answer remains `MIT`; only its release/date binding changes. That is
not an additional correct-answer win. These are declared record fields and
compatibility checks, not a new sampled assessment or a legal interpretation.

Only existing keyless, free public registry reads were used; no paid service,
account, billing, model weights or GPU was involved. The first-new-sample
result remains 0/12. See the [generalization audit](GENERALIZATION_AUDIT_2026-10-23.md).

## Limits and next issue

This selects release metadata from the available catalog. It does not recreate
past deletion/yank/tag state, prove every active version had the same field,
or provide timestamp-level comparisons. Generic official package HTML needs
a verified adapter release scope; separate extraction of historical HTML
records remains limited. Other dated external sources retain their existing
checks. A valid snapshot may require a different source URL from frozen gold;
no strict-source improvement is claimed.

GitHub/crates historical fields are not repaired by this PyPI/npm change.
`registry-history-20261023-next-github-probe.json` reproduces the analogous
GitHub issue: a current-only repository license still passes a past-date
request with an always-supporting CPU verifier. That is the next unresolved
source-scope problem, not a fixed control in the 43-case comparison.
