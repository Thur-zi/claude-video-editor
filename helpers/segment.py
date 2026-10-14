"""Person matting (MODNet, CPU/ONNX) → per-frame alpha mattes for depth-layer compositing.

    python helpers/segment.py <video> -o <edit>/matte/            # every frame → matte_00000.png …
    python helpers/segment.py <video> -o out.png --at 12.9         # one frame (e.g. a freeze-frame)
    python helpers/segment.py <video> -o <dir> --fps 12            # sample, then interpolate

What you get: 8-bit grayscale PNGs, same size as the video frames, 255 = person.
Use them to put elements BEHIND the person (overlay alpha × (1 − matte)), cut the person out
for end cards / stickers, or replace/blur the background.

Model: MODNet portrait matting (models/modnet.onnx, ~26 MB, from huggingface.co/Xenova/modnet).
Input is resized so the short side is 512 (multiples of 32), normalised to [-1, 1].
Temporal smoothing: exponential moving average across frames (--ema, default 0.35) kills flicker.
Speed on a 2-core laptop: ~0.6–1.2 s per frame at 512 px.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
MODEL = REPO / "models" / "modnet.onnx"
_SESSION = None


def session():
    global _SESSION
    if _SESSION is None:
        import onnxruntime as ort
        _SESSION = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
    return _SESSION


def matte(rgb: np.ndarray, ref: int = 512) -> np.ndarray:
    """rgb uint8 HxWx3 → float32 HxW in [0, 1]."""
    h, w = rgb.shape[:2]
    s = ref / min(h, w)
    nh, nw = max(32, round(h * s / 32) * 32), max(32, round(w * s / 32) * 32)
    x = np.asarray(Image.fromarray(rgb).resize((nw, nh), Image.BILINEAR)).astype(np.float32)
    x = (x / 255.0 - 0.5) / 0.5
    x = x.transpose(2, 0, 1)[None]
    out = session().run(None, {"input": x})[0][0, 0]
    m = Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)
    return np.asarray(m).astype(np.float32) / 255.0


def refine(m: np.ndarray, lo: float = 0.08, hi: float = 0.92) -> np.ndarray:
    """Tighten the soft edge a little (MODNet halos are wide on low-res input)."""
    return np.clip((m - lo) / (hi - lo), 0, 1)


def probe(video: Path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,avg_frame_rate", "-of", "csv=p=0", str(video)],
                         capture_output=True, text=True, check=True).stdout.strip().split(",")
    num, den = out[2].split("/")
    return int(out[0]), int(out[1]), float(num) / float(den or 1)


def frames(video: Path, fps: float | None = None, at: float | None = None):
    w, h, src_fps = probe(video)
    cmd = ["ffmpeg", "-v", "error"]
    if at is not None:
        cmd += ["-ss", f"{at:.3f}"]
    cmd += ["-i", str(video)]
    if at is not None:
        cmd += ["-frames:v", "1"]
    elif fps:
        cmd += ["-vf", f"fps={fps}"]
    cmd += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = w * h * 3
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    p.wait()


def main() -> None:
    ap = argparse.ArgumentParser(description="Person matting → alpha PNGs")
    ap.add_argument("video", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True, help="directory, or a .png with --at")
    ap.add_argument("--at", type=float, default=None, help="single frame at this time (s)")
    ap.add_argument("--fps", type=float, default=None, help="sample rate (default: every frame)")
    ap.add_argument("--ema", type=float, default=0.35, help="temporal smoothing weight of the previous matte")
    ap.add_argument("--ref", type=int, default=512)
    args = ap.parse_args()

    if args.at is not None:
        rgb = next(frames(args.video, at=args.at))
        m = refine(matte(rgb, args.ref))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray((m * 255).astype(np.uint8)).save(args.output)
        print(f"matte -> {args.output}  coverage {m.mean():.1%}")
        return

    args.output.mkdir(parents=True, exist_ok=True)
    prev = None
    i = 0
    for rgb in frames(args.video, fps=args.fps):
        m = refine(matte(rgb, args.ref))
        if prev is not None and args.ema > 0:
            m = (1 - args.ema) * m + args.ema * prev
        prev = m
        Image.fromarray((m * 255).astype(np.uint8)).save(args.output / f"matte_{i:05d}.png")
        i += 1
        if i % 24 == 0:
            print(f"  {i} frames", flush=True)
    print(f"mattes -> {args.output}  ({i} frames)")


if __name__ == "__main__":
    main()
