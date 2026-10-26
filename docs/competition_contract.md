# Competition contract ledger

Reviewed against public organizer material and public implementations. A document's example task is not automatically the Match 4 interface.

## Confirmed official common infrastructure

Source: [organizer common challenge PDF](https://storage.googleapis.com/lablab-static-eu/events/LabLab_AMD%20AI%20Challenge%20-%20Mini%20Challenge.pdf), retained under `research/official-common-rules.pdf`. SHA-256: `6eec89109e4c3e04cb32b38b80c03fdeb1cb307802373fbf00492bfc10a343c3`.

| Requirement | Status | Implementation |
|---|---|---|
| Base `rocm/pytorch:rocm10.0_ubuntu26.04_py3.14_pytorch_release_2.13.0` | CONFIRMED_OFFICIAL | Exact tag plus verified manifest digest in Dockerfile |
| Preserve lower layers; no squashing/flattening | CONFIRMED_OFFICIAL | One final stage derived from the base; actual RootFS prefix check |
| At most 60 GiB uncompressed | CONFIRMED_OFFICIAL | `scripts/check_image.py` fails above the limit |
| `/app/app.py`, `/app/requirements.txt`, optional `/models` | CONFIRMED_OFFICIAL | Adapter and complete neutral requirements; bundled model |
| Peak VRAM 1-48 GiB, upper tolerance 1%; sampled every 3 seconds | CONFIRMED_OFFICIAL | Resident GPU model; actual AMD measurement remains required |
| Open model; weights bundled or obtained during startup | CONFIRMED_OFFICIAL | Apache-2.0 Qwen, pinned and bundled; offline inference |
| Prebuilt publicly pullable submission image | CONFIRMED_OFFICIAL | Local image/export and publication commands; publication is a separate external operation |
| Submission registry reference must not appear in public source | CONFIRMED_OFFICIAL | Only placeholders and official base references in source |
| Notebook sessions 3 hours/day; about 25GB persistent storage | CONFIRMED_OFFICIAL | Prepare weights outside the GPU session; keep large local image archive out of notebook persistent storage |

The exact base manifest was fetched and verified from Docker Hub: `sha256:3174cb7061d94c427da96c0edef4adea28046fa3f3b2ff3948dc4e995665ff8c`. Digest identity is distinct from successful container execution.

## Match 4 interface observations

The [organizer event page](https://lablab.ai/ai-hackathons/amd-lablab-ai-academy-challenge) identifies Match 4 as intelligent web information retrieval, October 13-27, 2026. Public implementations provide task-interface evidence, not certification of our adapter:

| Observed behavior | Status |
|---|---|
| Natural-language question, optional starting URL | CONFIRMED_OBSERVED |
| One exact value with actual source URL | CONFIRMED_OBSERVED |
| `python3 /app/app.py`, results in `/app/output` | CONFIRMED_OBSERVED for Match 4 invocation; common paths are also official |
| Startup/resident model; approximately 30-second query budget | CONFIRMED_OBSERVED |
| Current CLI aliases and minimal/compat JSON profiles | COMPATIBILITY_IMPLEMENTED; official Match 4 acceptance UNKNOWN |
| Exact answer/source normalization, tie-breaking and hidden task mix | UNKNOWN |
| Evaluator GPU, search allowlist, private validator and deadline timezone | UNKNOWN |

The common PDF's concrete OCR flags, OCR JSON schema, scoring normalization and 10-minute startup/30-second query examples are not labeled official Match 4 specifications. They inform conservative compatibility choices only.

Public evidence includes [WebScout](https://github.com/Solar-DePIN-Hub/amd-match4-agent), [Pinpoint](https://github.com/ctmakc/pinpoint-web-agent) and [Source Trail](https://github.com/agammann/source-trail). Pinpoint's reported AMD result is stronger hardware evidence than a description, but remains its author's measurement. None establishes hidden-evaluator results for Aperture. Reference snapshots remain outside production packaging.
