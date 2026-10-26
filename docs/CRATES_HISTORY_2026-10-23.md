# Read crates.io historical fields from a dated version record

The old resolver projected the current crate description and homepage for
past-date questions. It supplied no release license field; a later generic
frontend fetch could then answer with the current license. Controlled HTTP
reproduced all three errors, including a current license when the old version
had no valid publication date.

The official [version schema](https://github.com/rust-lang/crates.io/blob/main/crates/crates_io_api_types/src/lib.rs)
stores license, description, homepage, documentation, repository and compiler
metadata on each version, alongside its creation timestamp and crate identity.
The [crate metadata controller](https://github.com/rust-lang/crates.io/blob/main/src/controllers/krate/metadata.rs)
returns the full version records by default. The [version endpoint](https://github.com/rust-lang/crates.io/blob/main/src/controllers/version/metadata.rs)
can return one exact version. Those are the source contracts used here.

For historical metadata questions (excluding version/date/year answer kinds):

- Match the named crate and any explicit version against the starting URL
  before fetching. A conflicting name/ref is unresolved, not permission to
  choose a different project or the current release.
- With an exact SemVer version, fetch its single version endpoint. Preserve
  custom prerelease and build strings; do not silently reduce them to a numeric
  prefix. Check the returned crate and version. An explicitly named yanked
  version can still supply its declared metadata.
- Otherwise, check the root crate name/ID, catalog count, version IDs, unique
  labels and per-record crate identity. Choose the uniquely highest eligible
  stable SemVer from the current catalog, or a preview only when requested.
  Current yanked entries are excluded from this default selection. Unknown
  dates on a competing higher release and equal SemVer precedence are
  unresolved. Incomplete catalogs and malformed records do not qualify.
- Require a complete, valid UTC publication timestamp and apply the cutoff
  or year constraint to that version's own date. Date-only and timezone-less
  values do not satisfy the crates.io timestamp contract.
- Project fields solely from the selected version. Do not fill absent fields
  from today's crate metadata, a different release, owners or publisher names.
  Each passage retains crate/version/date context, a registry-release scope,
  and a locator such as `versions[22].license` or `version.license`.
- Cite the actual fetched API URL. The date and field are in that same response,
  so no foreign date is inserted into a source that never contained it.
- Skip the redundant initial frontend fetch after resolving a scoped version.
  Invalid history cannot fall through to a current-only API/frontend field.
  Generic historical official pages require the validated adapter scope;
  separate dated external sources retain their normal evidence path.
- Preserve current-query behavior, including generic parsing of a timeless,
  explicitly pinned API starting URL. The new API routing is historical only.

The public compatibility probe used the direct, keyless official endpoint,
without an account, card, paid wrapper or credentials. The Rust project's
[data-access policy text](https://github.com/rust-lang/rfcs/blob/master/text/3463-crates-io-policy-update.md#data-access)
requires an identifying user agent and at most one request per second. The
existing user agent identifies the application. This adapter needs one API
request per primary attempt and stops on errors; crates.io no longer receives
the fetcher's automatic error retries. The live probe made only one request.
This patch does not add a shared rate limiter across independent worker
processes; that remains separate network work before any batch API use.

This is currently available version metadata, not a registry time machine.
Historical yank state, deleted records, tag state, earliest-release selection
and arbitrary historical usage statistics are not reconstructed. Default
selection uses the highest available stable version rather than the most
recent upload time. Different question intent can require further work.

## Verification

`eval/diagnose_crates_history.py` uses authored data, actual loopback HTTP,
blocked external transport and explicit CPU semantic stubs. Final paired
`crates-history-20261023-before-v5.json` / `after-v5.json` share the diagnostic
SHA and case IDs: **5/49 to 49/49**, 44 improved assertions, zero losses.
These are related controls, not 49 independent questions or a held-out score.
They cover positive licenses/descriptions/homepages, custom SemVer, exact
references, name/ref conflicts, missing fields/dates, catalog consistency,
malformed timestamps, HTTP failures, semantic rejection and no-model behavior.
All first attempts remain saved. The initial 36/37 run exposed a harness
limitation: its semantic stub recognized `homepage:` but not `homepage URL:`.
The stub was corrected without changing the expected answer, then both
historical baseline and current source were rerun with the same diagnostic.

`crates-history-20261023-live-v1.json` records one actual HTTP 200 API response
for `itoa`, starting from a question with no supplied URL and with model,
search and browser disabled. The complete catalog contained 37 versions.
For cutoff 2020-01-31, the selected record was **0.4.5**, published
**2020-01-24**, with literal license **MIT OR Apache-2.0**. The capture envelope
and body hashes are retained, and the raw response is under ignored research.

`eval/diagnose_crates_capture.py` verifies those hashes and replays the exact
saved body without more public requests. Final `capture-replay-v2.json`
checks both baseline and current behavior: the baseline abstains for this
question-only/model-disabled input; the updated path returns the full declared
field from the correctly dated version. This is a development compatibility
example, not an unseen model evaluation.

Existing CPU checks pass: registry metadata 43/43, GitHub history 45/45,
proofs 27/27, cutoffs 52/52, representative reader fixtures 15/15, P0 16/16
and assessment-input isolation 7/7. These preceded the final narrow rejection
of timezone-less crates timestamps; final focused 49/49 and actual-body replay
cover the final code. The assessment check uses unittest, without `--out`;
the unsupported CLI invocation was corrected before recording its 7 passes.

No GPU/model loading, browser, full benchmark sweep, answer/gold/alias edits,
paid service, build, push or competition submission occurred. Production
imports no evaluation fixture or answer table. Actual resident-model and
unseen-web accuracy remain unmeasured here; the retained latest external
first-attempt result stays 0/12.

## Next concrete issue

`crates-history-20261023-next-license-expression-probe.json` replays the same
actual API body with a deliberately partial CPU selector (`MIT`) and an
always-positive verifier. The current pipeline accepts that fragment despite
the structured field being `MIT OR Apache-2.0`. Historical source binding is
fixed, but full-field versus partial-expression intent still needs diagnosis
and general controls. This is not a claim about what the actual model selects.
