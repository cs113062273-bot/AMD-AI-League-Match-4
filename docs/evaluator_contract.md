# Evaluator adapter

The Match 4 task-specific interface is still unconfirmed. This is an isolated, replaceable compatibility adapter, not a declaration of official acceptance.

```
python3 /app/app.py --query-id q01 --query "QUESTION" [--url https://example.org/]
```

Aliases: `--question`, `-q`, `--id`, `--start-url`; positional question; `QUERY`, `QUERY_ID`, `START_URL`. Unknown flags fail visibly instead of being silently misinterpreted.

Default output: `/app/output/q01_output.json` on Linux; project `output/` on Windows. Without an ID the filename is `output.json`. Override with `--output-dir` or `APERTURE_OUTPUT`.

Minimal profile (default):

```json
{"answer":"exact value","sources":["https://actual-fetched.example/page"]}
```

Empty answer: `{"answer":"","sources":[]}`. `--profile compat` adds `citations`, `source_url`, `confidence`. Neither profile is yet organizer-certified. `--diagnostics` writes a separate `.trace.json`, never extra evaluator keys. Standard output contains one compact result JSON per query.

`--input tasks.json` accepts a list, a task object, or `{"tasks":[...]}` / `{"queries":[...]}`. `.jsonl` accepts one task per line. Task keys: `id`/`query_id`, `query`/`question`, `url`/`start_url`. Invalid list items receive empty `invalid_N` outputs. Malformed top-level JSON and unsupported CLI syntax are input errors, not fabricated successful queries.

`--serve` loads the model once. `--warmup` or `--index [PATH]` starts/waits for it; there is no corpus indexing for live web retrieval. If CMD is overridden and no warmup is called, queries still run deterministically without waiting for model startup. No query downloads or loads weights.

Internal retrieval budget: default 24 seconds; parent worker allowance: 25 seconds. `APERTURE_BUDGET` changes the retrieval budget, capped at 26; parent capped at 27. Startup waits up to 540 seconds, a conservative choice derived from the common OCR example, not a confirmed Match 4 allowance.

IDs are sanitized against path traversal and Windows reserved names. Concurrent different IDs are isolated. Reusing the same ID intentionally overwrites its result atomically; consumers on Windows can use the supplied retrying `read_json` when a replacement briefly causes a sharing violation.

Answer normalization preserves case, units, currencies, dates and phone punctuation. Whitespace and NFC are normalized; extracted version `v` prefixes are removed. The OCR document's uppercase/punctuation normalization is **not** assumed for web retrieval.
