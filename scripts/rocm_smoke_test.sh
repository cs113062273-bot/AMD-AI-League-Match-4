#!/usr/bin/env bash
set -euo pipefail
python3 scripts/protect_torch.py --require-rocm
python3 scripts/gpu_smoke_test.py --rocm
python3 app.py --warmup
python3 scripts/gpu_smoke_test.py --rocm --server
python3 app.py --query-id smoke --query 'What is the license of the httpx package on PyPI?' --diagnostics
python3 -c 'import json; x=json.load(open("/app/output/smoke_output.json")); assert x["answer"] and x["sources"]'
