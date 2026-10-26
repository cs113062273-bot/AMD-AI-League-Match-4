import argparse
import json
import time
import urllib.request


def main():
    import torch
    ap=argparse.ArgumentParser()
    ap.add_argument("--rocm",action="store_true")
    ap.add_argument("--server",action="store_true")
    args=ap.parse_args()
    if args.rocm and not torch.version.hip:raise RuntimeError("HIP missing")
    if not torch.cuda.is_available():raise RuntimeError("GPU unavailable")
    start=time.monotonic()
    a=torch.arange(1024,device="cuda",dtype=torch.float32)
    out=(a*a).sum()
    assert out.item()==sum(i*i for i in range(1024))
    torch.cuda.synchronize()
    data={"device":torch.cuda.get_device_name(),"torch":torch.__version__,"hip":torch.version.hip,
          "kernel_seconds":time.monotonic()-start,"peak_vram_bytes":torch.cuda.max_memory_allocated()}
    if args.server:
        with urllib.request.urlopen("http://127.0.0.1:8765/health",timeout=3) as r:data["server"]=json.load(r)
    print(json.dumps(data,indent=2))


if __name__=="__main__":main()
