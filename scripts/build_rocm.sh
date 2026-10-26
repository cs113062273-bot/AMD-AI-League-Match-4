#!/usr/bin/env bash
set -euo pipefail
image="${1:?Provide the submission registry reference; keep it outside public source}"
test -s models/qwen/aperture-model.json
docker build --pull -t "$image" .
python3 scripts/check_image.py "$image"
