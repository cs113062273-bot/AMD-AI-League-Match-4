"""Validate uncompressed size and lower-layer identity, independently of Dockerfile text."""
import argparse
import json
import subprocess

BASE="rocm/pytorch:rocm10.0_ubuntu26.04_py3.14_pytorch_release_2.13.0@sha256:3174cb7061d94c427da96c0edef4adea28046fa3f3b2ff3948dc4e995665ff8c"


def inspect(image):
    return json.loads(subprocess.check_output(["docker","image","inspect",image],text=True))[0]


def main():
    ap=argparse.ArgumentParser();ap.add_argument("image");args=ap.parse_args()
    base,image=inspect(BASE),inspect(args.image)
    layers=base["RootFS"]["Layers"]
    if image["RootFS"]["Layers"][:len(layers)]!=layers:
        raise RuntimeError("Mandated lower layers differ")
    if image["Size"]>60*1024**3:
        raise RuntimeError("Image exceeds 60 GiB uncompressed")
    print(json.dumps({"size_bytes":image["Size"],"base_layers":len(layers),"layer_identity":True,"image_id":image["Id"]},indent=2))


if __name__=="__main__":main()
