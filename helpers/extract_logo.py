"""Lift a flat-colour logo off a solid background in a reference video, as clean RGBA.

    python helpers/extract_logo.py <video> --start 89.0 --end 89.9 --bg 0,77,157 \
        --colors 255,255,255 237,202,5 0,156,59 -o logo_full.png [--scale 3] [--crop x0,y0,x1,y1]

How it works
  1. Temporal mean of every frame in [start, end] (the logo must be static there) —
     averages away codec noise.
  2. Per-pixel matting against the known flat background B and a small palette of
     flat logo colours F_i:  P = a·F + (1−a)·B  →  a = (P−B)·(F−B) / |F−B|²,
     choosing the F_i with the smallest residual. Colour is snapped to that F_i.
  3. "Re-vectorise" the edges: upscale alpha by --scale (bicubic), then a steep
     smoothstep around 0.5 rebuilds crisp, smooth contours (like tracing a vector),
     so the result stays sharp when used larger than the source resolution.

Also writes <out>_parts/ with each connected component group (lines of the lockup)
cropped separately (`--split`), sorted top→bottom.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image


def mean_frame(video: Path, start: float, end: float) -> np.ndarray:
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", str(video)],
                           capture_output=True, text=True, check=True).stdout.strip().split(",")
    w, h = int(probe[0]), int(probe[1])
    proc = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start}", "-to", f"{end}", "-i", str(video),
                           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    n = len(proc.stdout) // (w * h * 3)
    frames = np.frombuffer(proc.stdout[: n * w * h * 3], np.uint8).reshape(n, h, w, 3).astype(np.float32)
    print(f"averaged {n} frames ({w}x{h})")
    return frames.mean(axis=0)


def matte(img: np.ndarray, bg: np.ndarray, palette: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    d = img - bg
    best_a = np.zeros(img.shape[:2], np.float32)
    best_r = np.full(img.shape[:2], np.inf, np.float32)
    best_i = np.zeros(img.shape[:2], np.int32)
    for i, f in enumerate(palette):
        fb = f - bg
        a = np.clip((d @ fb) / float(fb @ fb), 0, 1)
        r = np.linalg.norm(d - a[..., None] * fb, axis=2)
        better = r < best_r
        best_a[better], best_r[better], best_i[better] = a[better], r[better], i
    best_a[best_r > 60] = 0          # not explained by any logo colour → background noise
    return best_a, best_i


def settle_colours(alpha: np.ndarray, idx: np.ndarray, conf: float = 0.7, iters: int = 6) -> np.ndarray:
    """Edge pixels (part background) get mis-assigned to the wrong palette colour; give every
    low-alpha pixel the colour of its nearest confident (solid) neighbour instead."""
    from scipy import ndimage

    solid = alpha >= conf
    if not solid.any():
        return idx
    _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
    return np.where(solid, idx, idx[iy, ix])


def revectorise(alpha: np.ndarray, idx: np.ndarray, palette, scale: int) -> Image.Image:
    idx = settle_colours(alpha, idx)
    h, w = alpha.shape
    A = Image.fromarray((alpha * 255).astype(np.uint8)).resize((w * scale, h * scale), Image.BICUBIC)
    # a light blur before the threshold irons out the low-res wobble in the contour
    from PIL import ImageFilter
    A = A.filter(ImageFilter.GaussianBlur(scale * float(__import__("os").environ.get("LOGO_SMOOTH", "0.45"))))
    a = np.asarray(A).astype(np.float32) / 255
    k = 0.10                                     # transition half-width → crisp but anti-aliased
    t = np.clip((a - (0.5 - k)) / (2 * k), 0, 1)
    a = t * t * (3 - 2 * t)
    I = np.asarray(Image.fromarray(idx.astype(np.uint8)).resize((w * scale, h * scale), Image.NEAREST))
    rgb = np.zeros((h * scale, w * scale, 3), np.float32)
    for i, f in enumerate(palette):
        rgb[I == i] = f
    out = np.dstack([rgb, a * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def split_rows(img: Image.Image, min_gap: int) -> list[Image.Image]:
    """Split into horizontal bands separated by ≥ min_gap fully transparent rows."""
    a = np.asarray(img.getchannel("A")) > 20
    rows = a.any(axis=1)
    parts, start, gap = [], None, 0
    for y, on in enumerate(rows):
        if on and start is None:
            start, gap = y, 0
        elif not on and start is not None:
            gap += 1
            if gap >= min_gap:
                parts.append((start, y - gap + 1))
                start, gap = None, 0
        elif on:
            gap = 0
    if start is not None:
        parts.append((start, len(rows)))
    out = []
    for y0, y1 in parts:
        band = img.crop((0, y0, img.width, y1))
        bb = band.getchannel("A").getbbox()
        if bb:
            out.append(band.crop(bb))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--bg", required=True, help="r,g,b of the flat background")
    ap.add_argument("--colors", nargs="+", required=True, help="r,g,b of each flat logo colour")
    ap.add_argument("--crop", default=None, help="x0,y0,x1,y1 in source pixels")
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--split", type=int, default=0, help="split into row bands separated by N px gaps")
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args()

    img = mean_frame(args.video, args.start, args.end)
    if args.crop:
        x0, y0, x1, y1 = map(int, args.crop.split(","))
        img = img[y0:y1, x0:x1]
    bg = np.array(list(map(float, args.bg.split(","))), np.float32)
    pal = [np.array(list(map(float, c.split(","))), np.float32) for c in args.colors]
    alpha, idx = matte(img, bg, pal)
    out = revectorise(alpha, idx, pal, args.scale)
    bb = out.getchannel("A").getbbox()
    out = out.crop(bb) if bb else out
    out.save(args.output)
    print(f"logo -> {args.output}  {out.size}")
    if args.split:
        d = args.output.with_name(args.output.stem + "_parts")
        d.mkdir(exist_ok=True)
        for i, p in enumerate(split_rows(out, args.split * args.scale)):
            p.save(d / f"part_{i:02d}.png")
            print(f"  part {i:02d}: {p.size}")


if __name__ == "__main__":
    main()
