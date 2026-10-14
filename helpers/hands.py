"""Hand tracking (MediaPipe Hand Landmarker, CPU) → per-frame anchor points for 3D/motion elements.

    python helpers/hands.py <video> -o hands.json [--fps 24] [--start S] [--end E]
    python helpers/hands.py <video> -o hands.json --at 12.0          # single frame

Output (pixel coords of the frames as decoded):
    {"w":1080,"h":1920,"fps":24,"samples":[{"t":0.0,"hands":[
        {"side":"Right","score":0.97,
         "palm":[x,y],            # centre of wrist + MCPs (good "float above the palm" anchor)
         "thumb_tip":[x,y], "index_tip":[x,y],
         "top":[x,y],             # highest landmark (for "float above the hand")
         "size":px,               # wrist→middle-MCP distance (scale reference)
         "landmarks":[[x,y,z],…21]}]}]}
Missing detections are filled from the nearest detected sample (≤ 0.5 s away) and the anchors are
smoothed with a short moving average, so attached objects don't jitter.

Model: models/hand_landmarker.task (MediaPipe, ~7.8 MB).
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
MODEL = REPO / "models" / "hand_landmarker.task"


def _landmarker(video_mode: bool):
    import mediapipe as mp
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision

    opts = vision.HandLandmarkerOptions(
        base_options=mpt.BaseOptions(model_asset_path=str(MODEL)),
        running_mode=vision.RunningMode.VIDEO if video_mode else vision.RunningMode.IMAGE,
        num_hands=2, min_hand_detection_confidence=0.4, min_hand_presence_confidence=0.4,
        min_tracking_confidence=0.4)
    return mp, vision.HandLandmarker.create_from_options(opts)


def _probe(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", str(video)],
                         capture_output=True, text=True, check=True).stdout.strip().split(",")
    return int(out[0]), int(out[1])


def _frames(video, fps, start, end, at):
    w, h = _probe(video)
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{(at if at is not None else start):.3f}", "-i", str(video)]
    if at is not None:
        cmd += ["-frames:v", "1"]
    else:
        if end is not None:
            cmd += ["-t", f"{end - start:.3f}"]
        cmd += ["-vf", f"fps={fps}"]
    cmd += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    i = 0
    while True:
        buf = p.stdout.read(w * h * 3)
        if len(buf) < w * h * 3:
            break
        t = at if at is not None else start + i / fps
        yield t, np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        i += 1
    p.wait()


def _summarise(lms, handed, w, h):
    pts = np.array([[l.x * w, l.y * h, l.z * w] for l in lms], float)
    palm = pts[[0, 5, 9, 13, 17], :2].mean(axis=0)
    top = pts[np.argmin(pts[:, 1]), :2]
    return {"side": handed.category_name, "score": round(float(handed.score), 3),
            "palm": palm.round(1).tolist(), "thumb_tip": pts[4, :2].round(1).tolist(),
            "index_tip": pts[8, :2].round(1).tolist(), "top": top.round(1).tolist(),
            "size": round(float(np.linalg.norm(pts[0, :2] - pts[9, :2])), 1),
            "landmarks": pts.round(1).tolist()}


def track(video: Path, fps=24.0, start=0.0, end=None, at=None):
    w, h = _probe(video)
    mp, lm = _landmarker(video_mode=at is None)
    samples = []
    for t, rgb in _frames(video, fps, start, end, at):
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        res = lm.detect(img) if at is not None else lm.detect_for_video(img, int(round(t * 1000)))
        hands = [_summarise(l, hd[0], w, h) for l, hd in zip(res.hand_landmarks, res.handedness)]
        samples.append({"t": round(t, 3), "hands": hands})
    lm.close()
    _fill_and_smooth(samples, fps)
    return {"video": str(video), "w": w, "h": h, "fps": fps, "samples": samples}


def _fill_and_smooth(samples, fps, max_gap=0.5, win=3):
    """Keep the dominant (largest) hand per sample, fill short gaps, smooth the anchors."""
    main = [max(s["hands"], key=lambda x: x["size"]) if s["hands"] else None for s in samples]
    idx = [i for i, m in enumerate(main) if m]
    for i, s in enumerate(samples):
        if main[i] is None and idx:
            j = min(idx, key=lambda k: abs(k - i))
            if abs(j - i) / fps <= max_gap:
                main[i] = dict(main[j], filled=True)
    for key in ("palm", "top", "thumb_tip", "index_tip"):
        arr = [np.array(m[key]) if m else None for m in main]
        for i, m in enumerate(main):
            if not m:
                continue
            near = [arr[k] for k in range(max(0, i - win), min(len(arr), i + win + 1)) if arr[k] is not None]
            m[key] = np.mean(near, axis=0).round(1).tolist()
    for s, m in zip(samples, main):
        s["main"] = m


def main() -> None:
    ap = argparse.ArgumentParser(description="Hand anchors for attaching motion elements")
    ap.add_argument("video", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--fps", type=float, default=24.0)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--at", type=float, default=None)
    args = ap.parse_args()
    res = track(args.video, args.fps, args.start, args.end, args.at)
    args.output.write_text(json.dumps(res), encoding="utf-8")
    found = sum(1 for s in res["samples"] if s["main"])
    print(f"hands -> {args.output}  ({found}/{len(res['samples'])} samples with a hand)")
    for s in res["samples"][:3]:
        if s["main"]:
            m = s["main"]
            print(f"  t={s['t']}: {m['side']} palm={m['palm']} top={m['top']} size={m['size']}")


if __name__ == "__main__":
    main()
