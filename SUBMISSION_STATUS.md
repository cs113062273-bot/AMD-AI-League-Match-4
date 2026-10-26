# Submission snapshot - 2026-10-26

This snapshot preserves the current workspace implementation, including the CPU-checked memory and search repairs made after the frozen 2026-10-25 assessment. Historical benchmark scores apply only to the recorded code hashes and conditions; they are not new scores for this snapshot.

Four fresh CLI/worker checks passed on 2026-10-26 with model, browser and external search disabled. They exercise URL preservation, literal title extraction, private-address rejection and malformed-URL handling. See `benchmarks/submission-20261026-cli-v1.json`.

The hosted build workflow fetches pinned model weights, builds the mandated ROCm image, validates image size and lower layers, exercises a tiny random Qwen model on CPU, then pushes the container. It does not validate AMD GPU performance. After a push, make the package public and verify anonymous pulling before sending its operational reference to the organizer. Keep that reference outside this repository.

Formal event submission and certificate issuance are separate organizer actions. Neither is claimed by this repository.
