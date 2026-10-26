# Architecture

`app.py` contains evaluator compatibility and process lifecycle, with no accelerator imports. `agent/engine.py` orchestrates retrieval. `agent/model_server.py` owns one resident model. Changing an official CLI or JSON schema therefore does not require rebuilding the retrieval engine.

```text
CLI / JSON(L) tasks
  -> early atomic empty output
  -> bounded retrieval subprocess
     -> explicit constraints and primary-source adapters
     -> starting URL / keyless search / website discovery
     -> guarded asynchronous HTTP and optional isolated Chromium
     -> structured passages and typed candidates
     -> exact parameter bindings / dated release tables when applicable
     -> extractive local-model reading of numbered passages
     -> independent semantic check
     -> literal span + source + type + temporal checks + conflict gate
     -> bounded navigation, or abstention
  -> atomic answer and actual source URL
```

Each passage retains its source, section, field and locator. Table rows preserve headers and scope. JSON keeps numeric spelling and boolean/null literals. Parsed evidence is indexed once per page so verification of many table candidates does not repeatedly scan the entire document. Typed evidence receives a retrieval ranking boost without presenting proposed answers to the model.

Table passages also retain row/column/cell bindings; verification checks explicit requested columns, row keys and section roles. JSON passages carry scalar and schema record types. Shared eligibility filters extraction, model context and final verification, separating scaffold/config from facts while preserving requested technical false/zero and factual JSON-LD. Query focus supplies the answer type before background versions; clock time and hyphenated durations preserve their literal spelling. [Reader validation and remaining multi-source limits](READER_FIXES_2026-10-23.md).

The selector returns a passage ID and literal span. It cannot generate the citation. The checker reviews the proposed value against the requested entity, field, location and time. Neither model stage establishes truth on its own: deterministic checks reject invented spans, wrong numeric boundaries, invalid types, conflicting fields, wrong document identity and incompatible dates or versions. Semantic entailment remains empirical; a literal match alone is insufficient.

For declared two-field composition, specified-version quantity comparison and explicit classification mapping, `proofs.py` instead assembles literal premises and applies a bounded operation. It checks actual row/column/version/key/source scope and contradictions, then sends the real premises for semantic checking. The final answer may combine spans; citations include every required premise source. Incomplete/rejected/unavailable proofs do not fall back to a partial single-span answer. [Measured scope and limitations](PROOF_FIXES_2026-10-23.md).

For large link collections, model-generated lexical hints influence navigation only. A hint is never evidence or a final answer. Search snippets likewise only discover URLs. Citations use the actual final fetched URL, rather than an unverified canonical link.

The resident service verifies all model assets, loads directly onto the selected device and performs actual warmup before readiness. CUDA and HIP both use PyTorch's `cuda` namespace. Input pruning preserves structured JSON; requests that cannot fit fail explicitly. Localhost service concurrency is bounded, with one inference at a time and immediate busy responses. Health records backend source hashes, token counts, startup, outcomes and Torch peak allocation.

The network resolver validates the addresses used by the actual connector. Every redirect is checked, environment proxies/netrc are disabled, and compressed/decompressed bodies are bounded. Selective Chromium uses fresh contexts and a rejecting proxy; all allowed HTTP requests pass through the same guarded fetcher. POST, service workers, WebSockets, downloads, images/fonts and private destinations are blocked. Browser tests execute real JavaScript.

The parent query process enforces a default 25-second worker allowance around a 24-second internal budget. Windows Job objects bound aggregate process memory and kill descendants. Linux uses process groups and resource limits; browser-enabled workers use a data-segment cap so V8 can reserve virtual address space. The adapter leaves valid empty output even when a worker is killed.

With the model enabled, missing/busy/unavailable, malformed, timed-out or rejecting model calls cannot authorize general lexical candidates. Independently bound registry fields, exact signatures and dated release tables have separate deterministic paths. Explicit CPU-only mode retains the legacy rule path and does not satisfy the organizer's GPU requirement. See the [2026-10-22 changes and validation limits](P0_FIXES_2026-10-22.md).

All model clients send request IDs and expiration times. Client cancellation/timeout sends a bounded cancellation request; the server checks cancellation and deadlines around preparation and at generation token boundaries. This is cooperative and cannot interrupt a device kernel mid-execution. HTTP replies are sent after the inference lock is released.
