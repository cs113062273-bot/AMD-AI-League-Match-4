# Share crates.io API pacing between query processes

Independent query workers previously had separate fetchers and could send
API requests simultaneously. In the authored three-process HTTP control,
two of the three requests received a rate-limit response. Application-local
semaphores could not coordinate these processes.

The fetcher now obtains a shared OS file lock for each crates.io API hop,
including redirects into the API and between its bare and `www` hostnames.
The lock stays held until the response has been consumed or closed. The
next admission waits until 1.05 seconds after completion. This deliberately
conservative policy trades some throughput for predictable spacing; it is
consistent with the maximum one-request-per-second rule in the Rust
project's [data-access policy text](https://github.com/rust-lang/rfcs/blob/master/text/3463-crates-io-policy-update.md#data-access).

The gate uses `APERTURE_STATE/crates-api.pacing`, with the same default state
directory as resident-model startup (`.state` on Windows, `/tmp/aperture` on
Linux). Workers must share this directory. It coordinates processes on the
same host/filesystem, not independent containers with separate storage or
machines. The descriptor is closed on cancellation and automatically on
process exit; no PID lock needs to be stolen or deleted. Never delete or
replace the gate file while workers are running.

Waiting is asynchronous and covered by the existing request/query timeout.
Timeout or cancellation while waiting sends no HTTP request. Cache hits,
ordinary frontend pages and unrelated origins need no slot. Existing API
error behavior is retained: a 429 is not automatically retried and still
consumes its interval. Inaccessible state storage fails the fetch instead
of making an unpaced request. No new dependency or external service is used.

The bounded record includes a format marker, active/completed status,
monotonic timestamp and checksum. A corrupt, partial, old-format or
clock-inconsistent record costs a full cooldown. Admission is recorded
before HTTP; normal cleanup records completion. If an owner dies in flight,
the next owner waits a fresh interval after recovery, irrespective of how
old the admission timestamp is. OS locks remain held throughout the actual
HTTP response.

## Verification

`eval/diagnose_crates_pacing.py` redirects logical crates.io URLs to actual
loopback HTTP. Three independent Python processes share a temporary state
directory; the local server returns 429 if successive requests are less
than one second apart. All transport destinations are restricted to this
server. No public API calls, model weights or browser are involved.

The final identical-diagnostic pair is
`benchmarks/crates-pacing-20261024-{before,after}-v2.json`:

- Baseline `365a162`: **3/19** assertions.
- Current transport: **19/19**, 16 improved assertions, no losses.
- Three simultaneous workers: baseline one 200 and two 429 responses;
  current three 200 responses with measured arrival gaps of about 1.05 s.
- Checks cover separate fetchers, complete responses, cache, query and
  request timeout, cancellation both during cooldown and while contending
  with an active owner, two redirect paths, 429 handling, inaccessible and
  corrupt state, and termination of the diagnostic's own child process.

These are related transport assertions, not 19 independent questions or a
model/competition accuracy estimate. The initial 16-control version passed,
but a stronger crash case exposed a shortcoming: a long-running owner could
die with only an old admission timestamp. That intermediate implementation
passed 18/19 (`before-crash-v2.json`). Active/completed state fixes that case;
all earlier artifacts remain preserved.

Final Windows CPU regressions retain crates history 49/49, immutable actual
crates-response replay 2/2, P0 16/16, reader 15/15 and proof 27/27. The earlier
historical replay's baseline improvement is not a new win of this change.
Only the Windows `msvcrt` branch has been executed here; Linux `flock` is
implemented but not runtime-verified because no Linux environment is
available. No VM installation, Docker build or deployment was attempted.

The shared file lock, timing and cancellation controls do not prove improved
unseen answers. Frozen questions, gold, aliases and first-attempt results
are unchanged; the latest external first-attempt score remains 0/12. No GPU,
model, browser or paid API was used.
