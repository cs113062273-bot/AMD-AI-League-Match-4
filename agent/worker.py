"""Single query subprocess; no accelerator libraries are imported here."""
import asyncio
import json
import sys

from .engine import Engine


def main():
    if sys.platform.startswith("linux"):
        import resource
        # The CPU retrieval worker is isolated from the resident GPU model. Bound decompression,
        # hostile PDF/parser allocations, and accidental file descriptor growth.
        import os
        # Chromium reserves a large PROT_NONE V8 arena. Bound committed writable data
        # for that optional child path; a small AS limit would prevent browser startup.
        memory_limit=resource.RLIMIT_DATA if os.getenv('APERTURE_BROWSER')=='1' else resource.RLIMIT_AS
        resource.setrlimit(memory_limit, (3 * 1024**3, 3 * 1024**3))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    data = json.loads(sys.stdin.buffer.read(100_000))
    result = asyncio.run(Engine().run(data.get("query", ""), data.get("url", "")))
    sys.stdout.write(json.dumps(result.internal(), ensure_ascii=False))


if __name__ == "__main__":
    main()
