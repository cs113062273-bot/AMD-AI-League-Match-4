"""Constrain every installed torch distribution; validate HIP before and after dependency installation."""
import argparse
import importlib.metadata
from pathlib import Path


def main():
    import torch
    ap=argparse.ArgumentParser()
    ap.add_argument("--constraints")
    ap.add_argument("--require-rocm",action="store_true")
    args=ap.parse_args()
    if args.require_rocm or args.constraints:
        if not torch.version.hip:
            raise RuntimeError("Expected the organizer ROCm/HIP torch; refusing CUDA/CPU replacement")
    if args.constraints:
        packages=[]
        for name in ["torch","torchvision","torchaudio"]:
            try:packages.append(f"{name}=={importlib.metadata.version(name)}")
            except importlib.metadata.PackageNotFoundError:continue
        Path(args.constraints).write_text("\n".join(packages)+"\n",encoding="utf-8")
    print({"torch":torch.__version__,"hip":torch.version.hip})


if __name__=="__main__":main()
