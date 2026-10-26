# Bounded recovery from resident-service admission refusals

The resident HTTP server already refuses concurrent inference with HTTP 503
and `{"error":"busy"}`. Previously the client discarded every non-200
response without inspecting it. A request arriving just before the active
worker released its lock therefore failed immediately, even with remaining
query time and readable evidence.

`agent/model_client.py` now retries only a 503 whose complete, bounded JSON
body equals that admission-refusal object. There are at most three total
attempts, separated by 100 ms and 200 ms. Each attempt retains the same
request ID, payload and expiry; all share the original monotonic call
deadline. Neither the query budget nor the per-call cap is restarted. A
retry requires at least 150 ms remaining after its pause. Exhaustion returns
`model_busy`, making an explicit busy response distinguishable in the trace
from an unidentified `http_503`.

Generic 503 errors, HTML, oversized/unrecognized error bodies, 429, 500,
invalid successful replies, and a 200 model error are not retried. The 503
body is bounded to 2,048 bytes and the original request timeout. A transport
timeout is not resubmitted: it retains the existing bounded cancellation
request. Cancelling during a pause also cancels only this request ID; it
cannot cancel the different worker responsible for the admission refusal.
The server's nonblocking single-inference lock and admission policy are
unchanged. This only covers brief contention, not sustained overload or
runtime exceptions.

## Evidence and limits

`eval/diagnose_model_busy.py` uses actual loopback HTTP, authored response
stubs, and the production server with a cooperative deterministic CPU
worker. It never constructs `Runtime`, loads a tokenizer/model, or imports
torch. The final same-diagnostic pair is:

- Baseline `756399d`: **13/30** protocol/behavior assertions.
- Current client: **30/30**, 17 improved assertions and no losses.
- Artifacts: `benchmarks/model-busy-20261023-{before,after}-v3.json`, with
  diagnostic and production source hashes. Earlier attempts are retained.

The checks include unchanged identity/expiry/payload, attempt caps, call and
query time limits, explicit caller caps, malformed and nonbusy responses,
selection/verification/expansion, cancellation during backoff, recovery
against the actual admission lock, and cancellation without stopping its
unrelated owner. An authored end-to-end phone question now recovers after
busy admission responses in both selection and verification. Semantic
rejection, abstention and continued busy responses still produce no answer.
These are related development controls, not 30 independent questions or a
competition accuracy estimate.

Existing CPU checks retain P0 16/16, reader 15/15, proof 27/27, selector
boundary 10/10, and HTTP cancellation lifecycle 8/8. The lifecycle run calls
only `http_probe`; its separate tiny-model generation probe was not run.
Historical baseline improvements printed by the older regression scripts
are not new wins of this change.

The exposed `simpleqa-415` capture already contains related geography, but
the first actual model run recorded three `http_503` states without response
bodies. Those cannot retrospectively be identified as busy responses. This
change does not establish that the old failure is fixed, that its answer
would be correct, or that the current service is available. No actual model
was started or queried. The latest retained external first-attempt score
remains 0/12.

## Separate source investigation

For exposed `simpleqa-1013`, the readable saved biography describes the son
with the same name rather than the requested father; it does not establish
the requested number of children. Four manually discovered public-source
reads were attempted using the actual project client, with ordinary TLS
verification and no account, key, card or payment:

- `benchmarks/family-count-20261023-sources-v1.json`: one HTTP 403 and two
  certificate-verification errors; all empty response bodies.
- `benchmarks/family-count-20261023-book-v1.json`: a free Gutenberg book HTML
  request timed out, also with an empty body.

Each receipt records the requested/final URL and hashes of the ignored raw
response envelope/body. No failed source was retried or TLS checks bypassed.
Separate research-tool access does not prove project-client reachability.
No family-count answer, number-word conversion, or source adapter was added
on the strength of these empty responses. Source finding remains unresolved;
these manual development probes are not question-only discovery successes.

Frozen questions, gold, aliases and first attempts remain unchanged. No GPU,
model load, browser, paid API, bulk assessment, build, push or submission was
used.
