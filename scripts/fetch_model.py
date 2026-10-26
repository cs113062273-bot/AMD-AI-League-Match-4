"""Fetch pinned safetensors locally before serving; never called from a query."""
import argparse
import json
from pathlib import Path

MODEL = "Qwen/Qwen3-4B-Instruct-2507"
REVISION = "cdbee75f17c01a7cc42f958dc650907174af0554"


def main():
    from huggingface_hub import snapshot_download
    ap = argparse.ArgumentParser()
    ap.add_argument("--directory", default="models/qwen")
    args = ap.parse_args()
    snapshot_download(MODEL, revision=REVISION, local_dir=args.directory,
        allow_patterns=["*.json", "*.safetensors", "*.txt", "*.jinja", "LICENSE", "README.md"], max_workers=3)
    from huggingface_hub import HfApi
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from agent.model_assets import record
    # Raw primary metadata retains Git blob IDs as well as LFS object hashes.
    import urllib.request
    with urllib.request.urlopen(f'https://huggingface.co/api/models/{MODEL}/revision/{REVISION}?blobs=true',timeout=30) as r:
        record(args.directory,json.load(r))


if __name__ == "__main__":
    main()
