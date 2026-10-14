"""Raster logo / text → smooth vector contours (JSON) for 3D extrusion (motion3d/render3d.mjs).

    python helpers/vectorize.py logo.png -o shape.json [--threshold 128] [--min-area 0.0005] [--smooth 2]
    python helpers/vectorize.py --text "22" --font fonts/Montserrat.ttf --weight 800 -o shape.json

Input: any image with alpha (or a dark/light logo on a flat background — the alpha, else the
luminance contrast against the corner colour, decides what is "ink"). Output:
    {"w": W, "h": H, "shapes": [{"outer": [[x,y],…], "holes": [[[x,y],…], …], "color": "#rrggbb"}]}
Each shape keeps the dominant colour of its pixels, so multi-colour logos extrude per colour region.
Contours are traced at high resolution (the input is upscaled ×2–4 when small), smoothed with a
circular moving average and simplified (Douglas–Peucker, ~0.6 px), so the 3D edges come out clean.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def ink_mask(img: Image.Image, threshold: int) -> np.ndarray:
    a = np.asarray(img.convert("RGBA")).astype(np.float32)
    if a[..., 3].min() < 250:                     # real alpha
        return (a[..., 3] >= threshold).astype(np.uint8) * 255
    rgb = a[..., :3]
    corner = np.median(np.concatenate([rgb[:8, :8].reshape(-1, 3), rgb[-8:, -8:].reshape(-1, 3)]), axis=0)
    dist = np.linalg.norm(rgb - corner, axis=2)
    return (dist >= 60).astype(np.uint8) * 255


def smooth_contour(c: np.ndarray, k: int) -> np.ndarray:
    if k <= 0 or len(c) < 2 * k + 3:
        return c.astype(np.float32)
    pad = np.concatenate([c[-k:], c, c[:k]]).astype(np.float32)
    ker = np.ones(2 * k + 1, np.float32) / (2 * k + 1)
    xs = np.convolve(pad[:, 0], ker, mode="valid")
    ys = np.convolve(pad[:, 1], ker, mode="valid")
    return np.stack([xs, ys], axis=1)


def vectorize(img: Image.Image, threshold=128, min_area=0.0005, smooth=2) -> dict:
    import cv2

    scale = 1
    while max(img.size) * scale < 1600:
        scale *= 2
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
    rgba = np.asarray(img.convert("RGBA"))
    mask = ink_mask(img, threshold)
    contours, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    shapes = []
    if hier is None:
        return {"w": img.width / scale, "h": img.height / scale, "shapes": []}
    hier = hier[0]
    total = mask.shape[0] * mask.shape[1]

    def prep(c):
        c = smooth_contour(c[:, 0, :], smooth * scale)
        c = cv2.approxPolyDP(c.reshape(-1, 1, 2), 0.6 * scale, True)[:, 0, :]
        return (c / scale).round(2).tolist()

    for i, c in enumerate(contours):
        if hier[i][3] != -1:                       # a hole — handled with its parent
            continue
        if cv2.contourArea(c) < min_area * total:
            continue
        holes = []
        j = hier[i][2]
        while j != -1:
            if cv2.contourArea(contours[j]) >= min_area * total * 0.1:
                holes.append(prep(contours[j]))
            j = hier[j][0]
        region = np.zeros(mask.shape, np.uint8)
        cv2.drawContours(region, [c], -1, 255, -1)
        px = rgba[(region > 0) & (mask > 0)][:, :3]
        col = np.median(px, axis=0).astype(int) if len(px) else np.array([255, 255, 255])
        shapes.append({"outer": prep(c), "holes": holes, "color": "#%02x%02x%02x" % tuple(col)})
    return {"w": img.width / scale, "h": img.height / scale, "shapes": shapes}


def text_image(text: str, font: Path, weight: int, size=600, color=(255, 214, 0)) -> Image.Image:
    f = ImageFont.truetype(str(font), size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    l, t, r, b = f.getbbox(text)
    im = Image.new("RGBA", (r - l + 40, b - t + 40), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((20 - l, 20 - t), text, font=f, fill=color + (255,))
    return im


def main() -> None:
    ap = argparse.ArgumentParser(description="Logo/text → vector contours JSON")
    ap.add_argument("image", nargs="?", type=Path)
    ap.add_argument("--text", default=None)
    ap.add_argument("--font", type=Path, default=Path(__file__).resolve().parent.parent / "fonts" / "Montserrat.ttf")
    ap.add_argument("--weight", type=int, default=800)
    ap.add_argument("--threshold", type=int, default=128)
    ap.add_argument("--min-area", type=float, default=0.0005)
    ap.add_argument("--smooth", type=int, default=2)
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args()
    img = text_image(args.text, args.font, args.weight) if args.text else Image.open(args.image)
    res = vectorize(img, args.threshold, args.min_area, args.smooth)
    args.output.write_text(json.dumps(res), encoding="utf-8")
    pts = sum(len(s["outer"]) + sum(len(h) for h in s["holes"]) for s in res["shapes"])
    print(f"vector -> {args.output}  {len(res['shapes'])} shapes, {pts} points, {res['w']:.0f}x{res['h']:.0f}")


if __name__ == "__main__":
    main()
