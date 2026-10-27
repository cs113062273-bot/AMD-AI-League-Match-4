# Local validation, 2026-10-27

The production `agent/` files in public snapshot `591206b` match local development
commit `b9fb1fe` exactly. The public submission snapshot and local development
repository were created with separate Git histories; this comparison concerns file
contents, not commit ancestry.

Targeted checks completed locally before reconnecting the working copy to the
public repository:

- GPU memory budget and cleanup controls: 25/25 passed (CPU mocks).
- Chunked Qwen3 prefill: 8/8 passed, including real tiny CPU model equivalence and
  cancellation between chunks.
- Saved Yahoo discovery replay and search-page source guards: passed.
- Python syntax, JSON parsing, and Git whitespace checks for the 66 changed or new
  development files: passed.

Raw check receipts remain in the ignored local research directory:
`research/commit-20261027-gpu-memory.json`,
`research/commit-20261027-chunk-prefill.json`, and
`research/commit-20261027-search-access.json`.

These checks do not measure factual retrieval accuracy, AMD GPU execution, or
official evaluator acceptance. This documentation update does not rebuild or
republish the submission image.
