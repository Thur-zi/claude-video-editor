"""Monocular depth (Depth Anything V2 small, ONNX/CPU) → depth map PNG for 2.5D parallax.

    python helpers/depth.py frame.png -o depth.png [--size 518]
    python helpers/depth.py video.mp4 --at 12.0 -o depth.png

Output: 16-bit grayscale PNG, same size as the input, NEAR = white (255*257), FAR = black.
Feed it with the frame to motion3d (spec "page": "parallax.html") to turn a still into a 3D camera move,
or use it to separate planes (e.g. put text between background and subject).

Model: models/depth_anything_v2_small_q.onnx (quantized, ~27 MB, huggingface.co/onnx-community/depth-anything-v2-small).
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

REPO = Path(__file__).resolve().parent.parent
MODEL = REPO / "models" / "depth_anything_v2_small_q.onnx"
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


def depth(img: Image.Image, size: int = 518) -> np.ndarray:
    import onnxruntime as ort

    sess = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
    w, h = img.size
    s = size / min(w, h)
    nw, nh = round(w * s / 14) * 14, round(h * s / 14) * 14
    x = np.asarray(img.convert("RGB").resize((nw, nh), Image.BICUBIC)).astype(np.float32) / 255.0
    x = ((x - MEAN) / STD).transpose(2, 0, 1)[None]
    d = sess.run(None, {"pixel_values": x})[0][0]           # relative inverse depth: larger = nearer
    d = (d - d.min()) / max(1e-6, d.max() - d.min())
    out = Image.fromarray((d * 65535).astype(np.uint16)).resize((w, h), Image.BICUBIC)
    return np.asarray(out).astype(np.float32) / 65535.0


def main() -> None:
    ap = argparse.ArgumentParser(description="Monocular depth map")
    ap.add_argument("input", type=Path)
    ap.add_argument("--at", type=float, default=None, help="frame time when the input is a video")
    ap.add_argument("--size", type=int, default=518)
    ap.add_argument("--blur", type=float, default=2.0, help="smooth the map (px) to avoid tearing")
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args()
    if args.at is not None or args.input.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm"):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{args.at or 0:.3f}", "-i", str(args.input),
                              "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
                             capture_output=True, check=True).stdout
        import io
        img = Image.open(io.BytesIO(raw))
    else:
        img = Image.open(args.input)
    d = depth(img, args.size)
    im = Image.fromarray((d * 65535).astype(np.uint16))
    if args.blur > 0:
        im8 = Image.fromarray((d * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(args.blur))
        im = Image.fromarray((np.asarray(im8).astype(np.float32) / 255 * 65535).astype(np.uint16))
    im.save(args.output)
    print(f"depth -> {args.output}  {img.size}")


if __name__ == "__main__":
    main()
