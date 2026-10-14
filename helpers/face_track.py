"""Face keep-out track for graphics placement (CPU-only, OpenCV Haar cascade).

    python helpers/face_track.py <video> [-o face.json] [--fps 4] [--start S] [--end E]

Samples the video at --fps, detects the largest frontal face per sample, smooths
the track, and writes normalized boxes (0–1 of the SOURCE frame, after rotation):

    {"video": ..., "fps": 4, "w": 480, "h": 854,
     "samples": [{"t": 0.0, "box": [x0, y0, x1, y1] | null}, ...],
     "union": [x0, y0, x1, y1]}          # every detected face, padded

Use it to keep captions/graphics off the face: map a box to the output canvas
with `to_canvas(box, src_w, src_h, out_w, out_h, zoom, anchor_y)` (same cover-crop
+ punch-in math render.py uses). The face box is padded (hair/forehead and chin
are not in a Haar box): +35 % up, +20 % down, +15 % each side.

Needs opencv-python-headless < 5 (4.x ships haarcascade_frontalface_default.xml;
5.x dropped CascadeClassifier).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

PAD = dict(top=0.35, bottom=0.20, side=0.15)


def _probe(video: Path) -> tuple[int, int, float]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", str(video)],
        capture_output=True, text=True, check=True)
    d = json.loads(out.stdout)
    s = d["streams"][0]
    return int(s["width"]), int(s["height"]), float(d["format"]["duration"])


def _frames(video: Path, fps: float, start: float, end: float, w: int, h: int):
    """Yield (t, gray uint8 frame) via ffmpeg rawvideo pipe (autorotated)."""
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(video),
           "-vf", f"fps={fps},format=gray", "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = 0
    size = w * h
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        yield start + n / fps, np.frombuffer(buf, np.uint8).reshape(h, w)
        n += 1
    proc.wait()


def _pad(box, w, h):
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    return [max(0.0, (x0 - PAD["side"] * bw) / w), max(0.0, (y0 - PAD["top"] * bh) / h),
            min(1.0, (x1 + PAD["side"] * bw) / w), min(1.0, (y1 + PAD["bottom"] * bh) / h)]


def track(video: Path, fps: float = 4.0, start: float = 0.0, end: float | None = None) -> dict:
    import cv2

    cascade = cv2.CascadeClassifier(
        str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    if cascade.empty():
        sys.exit("Haar cascade not found — install opencv-python-headless<5")
    w, h, dur = _probe(video)
    # rotation-aware size: read one frame's real shape from ffmpeg
    probe = next(_frames_any(video, start), None)
    if probe is not None:
        h, w = probe.shape
    end = dur if end is None else min(end, dur)
    samples = []
    min_side = int(min(w, h) * 0.12)
    for t, g in _frames(video, fps, start, end, w, h):
        g = cv2.equalizeHist(g)
        faces = cascade.detectMultiScale(g, scaleFactor=1.1, minNeighbors=6,
                                         minSize=(min_side, min_side))
        if len(faces):
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            samples.append({"t": round(t, 3), "raw": [int(x), int(y), int(x + fw), int(y + fh)]})
        else:
            samples.append({"t": round(t, 3), "raw": None})

    # smooth: median over a 5-sample window, fill gaps with nearest detection
    raws = [s["raw"] for s in samples]
    idx = [i for i, r in enumerate(raws) if r]
    for i, s in enumerate(samples):
        if not idx:
            s["box"] = None
            continue
        near = sorted(idx, key=lambda j: abs(j - i))[:5]
        med = np.median(np.array([raws[j] for j in near], float), axis=0)
        s["box"] = [round(v, 4) for v in _pad(med, w, h)]
        del s["raw"]
    boxes = [s["box"] for s in samples if s.get("box")]
    union = ([min(b[0] for b in boxes), min(b[1] for b in boxes),
              max(b[2] for b in boxes), max(b[3] for b in boxes)] if boxes else None)
    return {"video": str(video), "fps": fps, "w": w, "h": h, "detected": len(idx),
            "samples": samples, "union": union}


def _frames_any(video: Path, start: float):
    """One gray frame at its true (autorotated) size."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", str(video),
                          "-frames:v", "1", "-vf", "format=gray", "-f", "image2pipe",
                          "-vcodec", "pgm", "-"], capture_output=True)
    data = out.stdout
    if not data.startswith(b"P5"):
        return iter([])
    parts = data.split(maxsplit=4)
    w, h = int(parts[1]), int(parts[2])
    return iter([np.frombuffer(parts[4][: w * h], np.uint8).reshape(h, w)])


def to_canvas(box, src_w, src_h, out_w=1080, out_h=1920, zoom=1.0, anchor_y=0.5):
    """Map a normalized source box to output pixels (cover-crop, then punch-in)."""
    s = max(out_w / src_w, out_h / src_h)
    cw, ch = src_w * s, src_h * s
    ox, oy = (cw - out_w) / 2, (ch - out_h) / 2
    x0, y0 = box[0] * cw - ox, box[1] * ch - oy
    x1, y1 = box[2] * cw - ox, box[3] * ch - oy
    vx, vy = (out_w - out_w / zoom) / 2, (out_h - out_h / zoom) * anchor_y
    return [(x0 - vx) * zoom, (y0 - vy) * zoom, (x1 - vx) * zoom, (y1 - vy) * zoom]


def main() -> None:
    ap = argparse.ArgumentParser(description="Face keep-out track for graphics placement")
    ap.add_argument("video", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--fps", type=float, default=4.0)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    args = ap.parse_args()
    res = track(args.video.resolve(), args.fps, args.start, args.end)
    out = args.output or args.video.with_suffix(".face.json")
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"face track -> {out}  ({res['detected']}/{len(res['samples'])} samples with a face)")
    if res["union"]:
        u = res["union"]
        print(f"union (normalized, padded): x {u[0]:.2f}-{u[2]:.2f}  y {u[1]:.2f}-{u[3]:.2f}")


if __name__ == "__main__":
    main()
