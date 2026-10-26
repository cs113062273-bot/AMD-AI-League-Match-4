# AMD deployment

The implementation separates local CUDA verification, actual Linux Docker verification, ROCm container CPU/import verification and AMD GPU verification. Consult the generated validation report and retained logs; one category does not substitute for another.

## Prepare and build

The Dockerfile pins the organizer base and digest. Runtime/browser dependencies are fully version-pinned and accelerator-neutral. `--no-deps`, base-package constraints and before/after checks prevent pip from replacing ROCm PyTorch. A dependency conflict fails the build. There is no bitsandbytes, flash-attn, vLLM or custom CUDA kernel requirement.

```bash
python3 scripts/fetch_model_ranges.py
python3 -m agent.model_assets models/qwen
bash scripts/build_rocm.sh YOUR_IMAGE_REFERENCE
```

Weights can instead be copied from the supplied verified `models/qwen` directory. Do not download weights in a query. Keep the operational submission reference out of public source.

The local clean-room harness boots an isolated Linux VM because Windows has no configured Docker/WSL. It mounts no host directories, uses a newly labeled workspace disk, installs real Docker and builds real Linux containers. Public artifact caches preserve upstream digests/signatures. They accelerate downloads; they do not replace Docker execution with a mock.

The CPU container runs Python 3.14 tests, actual Chromium/JavaScript, fixture benchmarks and a fresh CLI public-source query. The production ROCm build additionally checks HIP PyTorch import, tiny randomly initialized Qwen API compatibility on CPU, production-image CLI/browser behavior, lower-layer identity and uncompressed size. These checks can run without an AMD GPU. A random tiny model is an API compatibility check, not an answer-quality test.

The archive was fully exported. Its additional empty-daemon reload was cancelled to avoid another full copy after the user raised storage concerns; no successful reload is claimed. The downloaded base cache and scratch VM disk were removed after export. `--verify-archive-reload` now makes that additional copy an explicit optional step. The image itself had already passed actual container import/API/browser/CLI checks.

## Actual AMD acceptance

**NOT YET VERIFIED ON AMD** applies to real HIP kernels, full-model inference, startup/latency, VRAM sampling and the private Match 4 evaluator.

On an AMD machine:

```bash
bash scripts/container_contract_test.sh YOUR_IMAGE_REFERENCE
```

This starts a fresh production container with `/dev/kfd` and `/dev/dri`, completes resident-model warmup, executes a real HIP tensor operation, runs a separate query process, checks output and inspects the image. No developer home or model-cache mount is used.

Run the live suite and measure peak total VRAM with `amd-smi`/`rocm-smi` in addition to Torch allocation. Check the 1-48 GiB requirement, 1% upper tolerance and 60 GiB uncompressed image limit. Record the GPU, driver, ROCm/PyTorch versions, cold-start time, p95 latency and all failures.

Reconcile the isolated adapter with the official Match 4 task brief/private validator when available. Do not change retrieval to accommodate superficial I/O differences.

## Transfer and publish

The common notebook allows about 25GB persistent storage and three hours of GPU time each day. The source plus 8GB model fits that preparation budget. A complete local image archive can exceed 25GB: load/pull it through Docker's appropriate ephemeral image storage rather than placing it in `/persistent` or `/workspace`.

Publish the exact tested image using an authenticated registry account, then verify an unauthenticated pull from a clean environment. Do not rebuild after acceptance and submit a different image. Submit only through the organizer's designated channel. Local artifacts do not imply that publication or official submission has happened.
