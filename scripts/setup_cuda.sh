#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv
.venv/bin/python -m pip install torch==2.9.1 --index-url https://download.pytorch.org/whl/cu128
.venv/bin/python -m pip install --no-deps -r requirements-runtime.lock
.venv/bin/python -m pip install pytest==9.1.1
.venv/bin/python scripts/fetch_model.py
.venv/bin/python scripts/gpu_smoke_test.py
