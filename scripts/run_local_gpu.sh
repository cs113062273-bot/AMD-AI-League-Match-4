#!/usr/bin/env bash
set -euo pipefail
export APERTURE_MODEL="${APERTURE_MODEL:-$PWD/models/qwen}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
exec .venv/bin/python app.py --serve
