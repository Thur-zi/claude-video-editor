"""Clean animated end card → a short clip to append as the last EDL range.

    python templates/end_card.py -o <edit>/animations/endcard/endcard.mp4 \
        --eyebrow "WORKSHOP DE EDIÇÃO" --title "com Claude" --hero "22/10" \
        --line "19H  •  AUDITÓRIO CENTRAL" --footer "inscrições no link da bio" \
        [--bg "#004D9D"] [--accent "#FDCE00"] [--dur 3.5] [--fps 24]

Grammar (see references/short-form-playbook.md, "End cards"): flat background, a big hero element
(date/number/word) whose outline draws per glyph and then fills with the accent colour, centred
lines that fade + blur-in 120 ms apart, no overshoot, then a still hold. Every element is optional.
Fonts: Montserrat (fonts/Montserrat.ttf). Silent stereo track so it concatenates like any source.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = Path(__file__).resolve().parent.parent
W, H = 1080, 1920


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mont(size, wght):
    f = ImageFont.truetype(str(REPO / "fonts" / "Montserrat.ttf"), size)
    f.set_variation_by_axes([wght])
    return f


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(t):
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def text_img(text, font, fill, track=0.0):
    asc, desc = font.getmetrics()
    adv = [font.getlength(c) for c in text]
    tr = track * font.size
    img = Image.new("RGBA", (int(sum(adv) + tr * max(0, len(text) - 1)) + 40, asc + desc + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = 20
    for c, a in zip(text, adv):
        d.text((x, 20), c, font=font, fill=fill + (255,))
        x += a + tr
    return img.crop(img.getchannel("A").getbbox())


def fit(text, wght, size, fill, track, maxw):
    while True:
        im = text_img(text, mont(size, wght), fill, track)
        if im.width <= maxw or size < 20:
            return im
        size -= 4


def fade_blur(img, k, blur_max=6):
    if k >= 1:
        return img
    e = ease_out(k)
    out = img.filter(ImageFilter.GaussianBlur(blur_max * (1 - e))) if e < 0.98 else img.copy()
    out.putalpha(out.getchannel("A").point(lambda v: round(v * e)))
    return out


def outline(img, width=4):
    a = img.getchannel("A").point(lambda v: 255 if v > 110 else 0)
    ring = np.clip(np.asarray(a.filter(ImageFilter.MaxFilter(width * 2 + 1))).astype(int) - np.asarray(a).astype(int), 0, 255)
    out = Image.new("RGBA", img.size, (255, 255, 255, 0))
    out.putalpha(Image.fromarray(ring.astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6)))
    return out


def sweep(img, p):
    """Pen-like reveal: clockwise angular sweep from 12 o'clock."""
    if p <= 0:
        return None
    if p >= 1:
        return img
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w]
    ang = (np.arctan2(xx - w / 2, -(yy - h / 2)) + 2 * np.pi) % (2 * np.pi) / (2 * np.pi)
    a = np.asarray(img).astype(np.float32)
    a[..., 3] *= np.clip((p - ang) / 0.04, 0, 1)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def paint(img, p):
    """Fill reveals with a soft diagonal edge."""
    if p <= 0:
        return None
    if p >= 1:
        return img
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w]
    d = (xx / w + (1 - yy / h)) / 2
    a = np.asarray(img).astype(np.float32)
    a[..., 3] *= np.clip((p * 1.25 - d) / 0.12, 0, 1)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def paste(fr, img, x, y, alpha=1.0):
    if img is None:
        return
    if alpha < 1:
        img = img.copy()
        img.putalpha(img.getchannel("A").point(lambda v: round(v * alpha)))
    layer = Image.new("RGBA", fr.size, (0, 0, 0, 0))
    layer.paste(img, (round(x), round(y)), img)
    fr.alpha_composite(layer)


def main() -> None:
    ap = argparse.ArgumentParser(description="Animated end card clip")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--eyebrow", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--hero", default="")
    ap.add_argument("--line", default="")
    ap.add_argument("--footer", default="")
    ap.add_argument("--bg", default="#004D9D")
    ap.add_argument("--accent", default="#FDCE00")
    ap.add_argument("--fg", default="#FFFFFF")
    ap.add_argument("--dur", type=float, default=3.5)
    ap.add_argument("--fps", type=int, default=24)
    args = ap.parse_args()
    bg, accent, fg = hexrgb(args.bg), hexrgb(args.accent), hexrgb(args.fg)

    blocks = []   # (kind, image(s), gap_before)
    if args.eyebrow:
        blocks.append(("fade", fit(args.eyebrow, 700, 52, fg, 0.16, 900), 0))
    if args.title:
        blocks.append(("fade", fit(args.title, 800, 128, fg, -0.025, 920), 6))
    hero = None
    if args.hero:
        size = 330
        while True:
            f = mont(size, 800)
            glyphs, x = [], 0
            for c in args.hero:
                im = Image.new("RGBA", (int(f.getlength(c)) + 40, sum(f.getmetrics()) + 40), (0, 0, 0, 0))
                ImageDraw.Draw(im).text((20, 20), c, font=f, fill=accent + (255,))
                glyphs.append((im, x - 20))
                x += f.getlength(c) - 0.035 * size
            if x <= 940 or size < 80:
                break
            size -= 10
        top = min(g.getchannel("A").getbbox()[1] for g, _ in glyphs if g.getchannel("A").getbbox())
        bot = max(g.getchannel("A").getbbox()[3] for g, _ in glyphs if g.getchannel("A").getbbox())
        hero = dict(glyphs=[(outline(g), g, dx) for g, dx in glyphs], width=x, top=top, h=bot - top)
        blocks.append(("hero", hero, 34))
    if args.line:
        blocks.append(("fade", fit(args.line, 700, 44, fg, 0.14, 940), 26))
    if args.footer:
        blocks.append(("fade", fit(args.footer, 500, 38, fg, 0.02, 900), 70))

    heights = [b[1]["h"] if b[0] == "hero" else b[1].height for b in blocks]
    total = sum(heights) + sum(b[2] for b in blocks)
    y = round(H * 0.47 - total / 2)
    layout = []
    t_next = 0.0
    for (kind, obj, gap), hgt in zip(blocks, heights):
        y += gap
        layout.append((kind, obj, y, t_next))
        t_next += 0.42 if kind == "hero" else 0.12
        y += hgt

    frames = args.output.parent / f"{args.output.stem}_frames"
    frames.mkdir(parents=True, exist_ok=True)
    for old in frames.glob("*.png"):
        old.unlink()
    n = round(args.dur * args.fps)
    for fi in range(n):
        t = fi / args.fps
        fr = Image.new("RGBA", (W, H), bg + (255,))
        for kind, obj, yy, t0 in layout:
            if kind == "fade":
                k = clamp((t - t0) / 0.30)
                if k > 0:
                    paste(fr, fade_blur(obj, k), (W - obj.width) / 2, yy + round(12 * (1 - ease_out(k))))
            else:
                x0 = (W - obj["width"]) / 2
                for gi, (ol, fl, dx) in enumerate(obj["glyphs"]):
                    pl = clamp((t - t0 - gi * 0.06) / 0.42)
                    pf = clamp((t - t0 - 0.42 - gi * 0.05) / 0.30)
                    gy = yy - obj["top"]
                    if pf < 1:
                        paste(fr, sweep(ol, ease_in_out(pl)), x0 + dx, gy, 1 - clamp((pf - 0.7) / 0.3))
                    if pf > 0:
                        paste(fr, paint(fl, ease_in_out(pf)), x0 + dx, gy)
        fr.convert("RGB").save(frames / f"e_{fi:04d}.png", compress_level=1)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(args.fps),
                    "-i", str(frames / "e_%04d.png"),
                    "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                    "-t", f"{args.dur}", "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-tune", "animation",
                    "-pix_fmt", "yuv420p", "-r", str(args.fps), "-c:a", "aac", "-shortest", str(args.output)],
                   check=True)
    print(f"endcard -> {args.output}  ({n} frames, {args.dur}s)")


if __name__ == "__main__":
    main()
