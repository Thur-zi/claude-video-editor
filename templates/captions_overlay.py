"""Word-by-word "premium social" captions → transparent overlay for render.py.

    python templates/captions_overlay.py --edit-dir <videos>/edit --source <transcript stem> \
        --start 0.92 --end 13.0 [--fps 24] [--face <edit>/face.json] [--avoid x0,y0,x1,y1 ...] \
        [--fix "Heard=Correct" ...] [--y 0.57] [--lang pt] -o <edit>/animations/captions/overlay.mov

Style (see references/short-form-playbook.md, Style A):
  * Inter Display (fonts/Inter.ttf, opsz 32): key words big (wght 560), function words small (wght 460),
    tracking −6 %, sentence case as spoken.
  * Pages of up to 2 lines, block centred on the frame (lines left-aligned inside the block).
  * Each word fades + blur-ins on its spoken onset; the page clears when the next one starts.
  * Dark glow + tight halo instead of a plate or stroke.
  * Hard rule: no word may touch the face (face.json from helpers/face_track.py) or any --avoid box;
    the block is nudged down/up to find room and the build fails if there is none.

Assumes the overlay covers ONE contiguous source range [--start, --end] placed at output time 0
(EDL: {"overlays": [{"file": ..., "start_in_output": 0, "duration": end-start}]}, render with --no-subtitles).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "helpers"))
from face_track import to_canvas  # noqa: E402

W, H = 1080, 1920
WHITE = (255, 255, 255)
BIG, SMALL = 110, 62
W_BIG, W_SMALL = 560, 460
TRACK = -0.06
WORD_GAP = 0.10
LINE_STEP = 0.84
MAXW = 860
UI_BOTTOM = 1580          # keep clear of the platform caption/username area
CLEAR = 16

STOP = {
    "pt": set("a o as os um uma uns umas de do da dos das no na nos nas em por para pra com sem e ou mas que "
              "se é eu tu ele ela nós vós eles elas te me lhe nos vos ao aos à às seu sua meu minha isso isto "
              "esse essa este esta lá aqui já não sim tá vai vou foi ser ter mais muito".split()),
    "en": set("a an the of to in on at for from with and or but that this these those is are was were be "
              "i you he she we they it me my your our their his her its not yes so do did done".split()),
}


def inter(size, wght):
    f = ImageFont.truetype(str(REPO / "fonts" / "Inter.ttf"), size)
    f.set_variation_by_axes([32, wght])
    return f


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(t):
    return 1 - (1 - t) ** 3


def tracked(text, font, fill, track):
    asc, desc = font.getmetrics()
    pad = 30
    adv = [font.getlength(c) for c in text]
    tr = track * font.size
    w = int(sum(adv) + tr * (len(text) - 1)) + 2 * pad
    img = Image.new("RGBA", (max(1, w), asc + desc + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = pad
    for c, a in zip(text, adv):
        d.text((x, pad), c, font=font, fill=fill + (255,))
        x += a + tr
    return img, pad + asc


def glow(img, blur=16, alpha=0.9, edge=0.75):
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    for b, a_, dy in ((blur, alpha, 3), (2, edge, 1)):
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sh.putalpha(img.getchannel("A").point(lambda v, a_=a_: round(min(255, v * a_))))
        out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(b)), (0, dy))
    out.alpha_composite(img)
    return out


def fade_blur(img, k, blur_max=8):
    if k >= 1:
        return img
    e = ease_out(k)
    out = img.filter(ImageFilter.GaussianBlur(blur_max * (1 - e))) if e < 0.98 else img.copy()
    out.putalpha(out.getchannel("A").point(lambda v: round(v * e)))
    return out


def solid(img, x, y):
    b = img.getchannel("A").point(lambda v: 255 if v > 90 else 0).getbbox()
    return (x + b[0], y + b[1], x + b[2], y + b[3])


def hits(a, b, m=CLEAR):
    return not (a[2] + m <= b[0] or b[2] + m <= a[0] or a[3] + m <= b[1] or b[3] + m <= a[1])


def load_words(path: Path, start: float, end: float, fixes: dict[str, str]):
    d = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for w in d["words"]:
        if w.get("type", "word") != "word" or w["start"] < start - 0.01 or w["end"] > end + 0.2:
            continue
        t = w["text"].strip()
        for a, b in fixes.items():
            t = t.replace(a, b)
        out.append(dict(text=t, s=w["start"] - start, e=w["end"] - start))
    return out


def is_big(text, lang):
    core = re.sub(r"[^\wÀ-ÿ]", "", text.lower())
    return bool(re.search(r"\d", core)) or (len(core) >= 5 and core not in STOP.get(lang, set()))


def pages_of(words, max_words=6, pause=0.35):
    pages, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if (nxt is None or len(cur) >= max_words or w["text"][-1:] in ".!?"
                or (nxt["s"] - w["e"]) >= pause):
            pages.append(cur)
            cur = []
    return pages


def layout(words, idxs, lang):
    items = []
    for i in idxs:
        big = is_big(words[i]["text"], lang)
        img, base = tracked(words[i]["text"], inter(BIG if big else SMALL, W_BIG if big else W_SMALL), WHITE, TRACK)
        items.append((i, glow(img), base, img.getchannel("A").getbbox()))
    gap = int(BIG * WORD_GAP)
    lines, cur, cur_w = [], [], 0
    for it in items:
        wv = it[3][2] - it[3][0]
        add = wv + (gap if cur else 0)
        if cur and cur_w + add > MAXW:
            lines.append(cur)
            cur, cur_w, add = [], 0, wv
        cur.append(it)
        cur_w += add
    lines.append(cur)
    return lines, gap


def place(lines, gap, base1):
    step = round(BIG * LINE_STEP)
    widths = [sum(it[3][2] - it[3][0] for it in ln) + gap * (len(ln) - 1) for ln in lines]
    bx = max(60, round((W - max(widths)) / 2))
    placed = []
    for li, ln in enumerate(lines):
        x = bx
        for i, img, base, bb in ln:
            placed.append((i, img, x - bb[0], base1 + li * step - base))
            x += (bb[2] - bb[0]) + gap
    return placed


def main() -> None:
    ap = argparse.ArgumentParser(description="Word-by-word captions overlay (RGBA .mov)")
    ap.add_argument("--edit-dir", type=Path, required=True)
    ap.add_argument("--source", required=True, help="transcript stem in <edit>/transcripts/")
    ap.add_argument("--start", type=float, required=True, help="range start in the source (s)")
    ap.add_argument("--end", type=float, required=True, help="range end in the source (s)")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--face", type=Path, default=None, help="face.json from helpers/face_track.py")
    ap.add_argument("--avoid", action="append", default=[], help="x0,y0,x1,y1 canvas box to keep clear")
    ap.add_argument("--fix", action="append", default=[], help='"Heard=Correct" text replacement')
    ap.add_argument("--y", type=float, default=0.57, help="target first baseline as a fraction of height")
    ap.add_argument("--lang", default="pt")
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args()

    fixes = dict(f.split("=", 1) for f in args.fix)
    words = load_words(args.edit_dir / "transcripts" / f"{args.source}.json", args.start, args.end, fixes)
    if not words:
        sys.exit("no words in that range")
    zones = [tuple(map(float, b.split(","))) for b in args.avoid]
    if args.face and args.face.exists():
        f = json.loads(args.face.read_text(encoding="utf-8"))
        u = list(f["union"])
        u[3] -= 0.20 * (u[3] - u[1]) / 1.55           # trim the neck padding: chin is the limit
        zones.append(tuple(to_canvas(u, f["w"], f["h"])))
    dur = args.end - args.start
    n_frames = round(dur * args.fps)

    pages = []
    for n, idxs in enumerate(pages_of(words)):
        lines, gap = layout(words, idxs, args.lang)
        if len(lines) > 2:   # split long pages in two
            half = len(idxs) // 2
            for sub in (idxs[:half], idxs[half:]):
                pages.append(sub)
        else:
            pages.append(idxs)
    built = []
    for n, idxs in enumerate(pages):
        lines, gap = layout(words, idxs, args.lang)
        target = round(args.y * H)
        found = None
        for dy in sorted(range(-400, 401, 8), key=abs):        # nearest free height to the target
            placed = place(lines, gap, target + dy)
            boxes = [solid(img, x, y) for _, img, x, y in placed]
            if any(b[3] > UI_BOTTOM or b[1] < 300 for b in boxes):
                continue
            if any(hits(b, z) for b in boxes for z in zones):
                continue
            found = placed
            break
        if found is None:
            sys.exit(f"no free room for page {[words[i]['text'] for i in idxs]} — reduce --avoid or change --y")
        start = max(0.0, words[idxs[0]]["s"] - 0.05)
        end = words[pages[n + 1][0]]["s"] - 0.05 if n + 1 < len(pages) else dur
        built.append(dict(placed=found, s=start, e=end))
        print(f"page {n:02d} {start:6.2f}-{end:6.2f}s  {' '.join(words[i]['text'] for i in idxs)}")

    out = args.output
    frames = out.parent / f"{out.stem}_frames"
    frames.mkdir(parents=True, exist_ok=True)
    for old in frames.glob("*.png"):
        old.unlink()
    for fi in range(n_frames):
        t = fi / args.fps
        fr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for p in built:
            if p["s"] <= t < p["e"]:
                for i, img, x, y in p["placed"]:
                    k = clamp((t - (words[i]["s"] - 0.04)) / 0.12)
                    if k > 0:
                        layer = Image.new("RGBA", fr.size, (0, 0, 0, 0))
                        im = fade_blur(img, k)
                        layer.paste(im, (round(x), round(y)), im)
                        fr.alpha_composite(layer)
        fr.save(frames / f"o_{fi:05d}.png", compress_level=1)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(args.fps),
                    "-i", str(frames / "o_%05d.png"), "-c:v", "png", "-pix_fmt", "rgba", str(out)], check=True)
    print(f"overlay -> {out}  ({n_frames} frames, {dur:.2f}s)")


if __name__ == "__main__":
    main()
