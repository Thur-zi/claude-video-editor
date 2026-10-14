"""Download the optional AI models used by the depth-layer / 3D toolkit into models/.

    python helpers/get_models.py            # all (~60 MB)
    python helpers/get_models.py matte      # only one: matte | depth | hands

matte  MODNet portrait matting (person cutout)        ~26 MB  huggingface.co/Xenova/modnet
depth  Depth Anything V2 small, quantized (2.5D)      ~27 MB  huggingface.co/onnx-community/depth-anything-v2-small
hands  MediaPipe Hand Landmarker (hand anchors)       ~8 MB   storage.googleapis.com/mediapipe-models
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

MODELS = {
    "matte": ("modnet.onnx", "https://huggingface.co/Xenova/modnet/resolve/main/onnx/model.onnx"),
    "depth": ("depth_anything_v2_small_q.onnx",
              "https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model_quantized.onnx"),
    "hands": ("hand_landmarker.task",
              "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"),
}


def main() -> None:
    want = sys.argv[1:] or list(MODELS)
    out = Path(__file__).resolve().parent.parent / "models"
    out.mkdir(exist_ok=True)
    for key in want:
        name, url = MODELS[key]
        dest = out / name
        if dest.exists() and dest.stat().st_size > 0:
            print(f"ok (cached)  {dest.name}")
            continue
        print(f"downloading {key}: {url}")
        urllib.request.urlretrieve(url, dest)
        print(f"ok  {dest.name}  {dest.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
