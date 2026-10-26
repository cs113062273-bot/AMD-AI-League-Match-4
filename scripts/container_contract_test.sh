#!/usr/bin/env bash
set -euo pipefail
image="${1:?Provide image reference}"
name="aperture-clean-$RANDOM"
mkdir -p release/clean-room
docker run -d --name "$name" --device=/dev/kfd --device=/dev/dri --group-add video \
    --ipc=host --shm-size=8g "$image"
trap 'docker logs "$name" > release/clean-room/container.log 2>&1; docker rm -f "$name" >/dev/null' EXIT
docker exec "$name" python3 /app/app.py --warmup
docker exec "$name" python3 /app/scripts/gpu_smoke_test.py --rocm --server > release/clean-room/gpu.json
docker exec "$name" python3 /app/app.py --query-id clean01 --query 'What is the license of the httpx package on PyPI?' --diagnostics
docker cp "$name:/app/output" release/clean-room/output
python3 -c 'import json; x=json.load(open("release/clean-room/output/clean01_output.json")); assert set(x)=={"answer","sources"}; assert x["answer"]=="BSD-3-Clause"; assert x["sources"]==["https://pypi.org/pypi/httpx/json"]'
python3 scripts/check_image.py "$image" > release/clean-room/image.json
