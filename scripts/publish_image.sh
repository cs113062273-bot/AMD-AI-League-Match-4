#!/usr/bin/env bash
set -euo pipefail
reference="${1:?Provide the submission registry reference; keep it outside public source}"
local_image="${2:-aperture-rocm-clean:local}"
python3 scripts/check_image.py "$local_image"
docker tag "$local_image" "$reference"
docker push "$reference"
printf 'Verify an unauthenticated pull and submit the tested digest through the organizer channel.\n'
