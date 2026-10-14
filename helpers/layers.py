"""Depth-layer compositing utilities: put things BEHIND a person, cut a person out as a sticker.

Building blocks (import from Python) — all images are PIL RGBA / numpy float mattes in [0, 1]:

    occlude(rgba, matte)                 → rgba whose alpha is × (1 − matte): the element now sits
                                           BEHIND the person when composited over the frame.
    cutout(frame_rgb, matte)             → RGBA person only.
    sticker(person_rgba, outline=10, color=(255,255,255), shadow=(30, (0, 22), 0.45))
                                         → person with a solid outline + soft drop shadow (separate layers).
    affine(img, scale, dx, dy, anchor)   → scaled/translated copy on the same canvas size.

CLI — make an existing RGBA overlay sit behind the person, frame by frame:

    python helpers/layers.py occlude --overlay over.mov --mattes <dir of matte_00000.png> \
        --start-frame 188 -o behind.mov
(matte i ↔ overlay frame i − start-frame; get the mattes with helpers/segment.py on the BASE render
so they match the output geometry, including zooms.)
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def occlude(rgba: Image.Image, matte: np.ndarray) -> Image.Image:
    a = np.asarray(rgba).astype(np.float32)
    a[..., 3] *= (1.0 - matte)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def cutout(frame_rgb: Image.Image, matte: np.ndarray) -> Image.Image:
    out = frame_rgb.convert("RGBA")
    out.putalpha(Image.fromarray((matte * 255).astype(np.uint8)))
    return out


def sticker(person: Image.Image, outline: int = 10, color=(255, 255, 255),
            shadow=(30, (0, 22), 0.45)) -> tuple[Image.Image, Image.Image, Image.Image]:
    """Returns (shadow_layer, outline_layer, person) — composite in that order."""
    a = person.getchannel("A")
    hard = a.point(lambda v: 255 if v > 110 else 0)
    grown = hard.filter(ImageFilter.MaxFilter(outline * 2 + 1)).filter(ImageFilter.GaussianBlur(1.2))
    ol = Image.new("RGBA", person.size, color + (0,))
    ol.putalpha(grown)
    blur, (dx, dy), op = shadow
    sh_a = grown.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: round(v * op))
    sh = Image.new("RGBA", person.size, (0, 0, 0, 0))
    sh_shift = Image.new("L", person.size, 0)
    sh_shift.paste(sh_a, (dx, dy))
    sh.putalpha(sh_shift)
    return sh, ol, person


def affine(img: Image.Image, scale: float = 1.0, dx: float = 0.0, dy: float = 0.0,
           anchor=(0.5, 1.0)) -> Image.Image:
    """Scale about an anchor (fractions of the canvas; default bottom-centre) then translate."""
    w, h = img.size
    ax, ay = anchor[0] * w, anchor[1] * h
    # inverse map for Image.transform: src = (dst - t - a) / s + a
    inv = (1 / scale, 0, ax - (ax + dx) / scale, 0, 1 / scale, ay - (ay + dy) / scale)
    return img.transform((w, h), Image.AFFINE, inv, resample=Image.BICUBIC)


def _read_frames(video: Path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", str(video)],
                         capture_output=True, text=True, check=True).stdout.strip().split(",")
    w, h = int(out[0]), int(out[1])
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                         stdout=subprocess.PIPE)
    while True:
        buf = p.stdout.read(w * h * 4)
        if len(buf) < w * h * 4:
            break
        yield Image.frombytes("RGBA", (w, h), buf)
    p.wait()


def main() -> None:
    ap = argparse.ArgumentParser(description="Depth-layer compositing")
    sub = ap.add_subparsers(dest="cmd", required=True)
    oc = sub.add_parser("occlude", help="make an RGBA overlay sit behind the person")
    oc.add_argument("--overlay", type=Path, required=True)
    oc.add_argument("--mattes", type=Path, required=True)
    oc.add_argument("--start-frame", type=int, default=0, help="matte index of overlay frame 0")
    oc.add_argument("--fps", type=int, default=24)
    oc.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args()

    tmp = args.output.parent / f"{args.output.stem}_frames"
    tmp.mkdir(parents=True, exist_ok=True)
    n = 0
    for i, fr in enumerate(_read_frames(args.overlay)):
        mp = args.mattes / f"matte_{i + args.start_frame:05d}.png"
        if mp.exists():
            m = np.asarray(Image.open(mp).convert("L").resize(fr.size)).astype(np.float32) / 255
            fr = occlude(fr, m)
        fr.save(tmp / f"o_{i:05d}.png", compress_level=1)
        n += 1
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(args.fps),
                    "-i", str(tmp / "o_%05d.png"), "-c:v", "png", "-pix_fmt", "rgba", str(args.output)], check=True)
    print(f"occluded overlay -> {args.output}  ({n} frames)")


if __name__ == "__main__":
    main()
