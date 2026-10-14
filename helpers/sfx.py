"""Procedural sound effects for short-form edits — no sample packs, no downloads.

    python helpers/sfx.py <out_dir>            # writes whoosh/pop/click/impact/riser wavs
    python helpers/sfx.py <out_dir> --list

Each effect is a 48 kHz stereo 16-bit wav, peak-normalized to -1 dBFS; set the
level in the EDL (`gain_db`). Sync points (where the "hit" is) are printed and
returned by `sync_point()` so a caller can align the hit to a visual frame:

    whoosh  peak ~60% in   → place peak 0–1 frame BEFORE the cut / zoom
    pop     onset at 0     → onset ON the frame the element appears
    click   onset at 0
    impact  onset at 0     → just before the key word, never on a consonant
    riser   ends at hit    → cut hard on the reveal frame

Recipes follow common sound-design practice (pink-noise whoosh with a
rising-then-falling band-pass, pitch-dropping sine pop, 808-style boom with a
click layer so it reads on phone speakers). Levels: keep SFX peaks 6–10 dB
under dialogue peaks; ~2–4 effects per 15 s for a serious tone.
"""

from __future__ import annotations

import argparse
import math
import wave
from pathlib import Path

import numpy as np

SR = 48_000


# ---------------------------------------------------------------- primitives
def _t(dur: float) -> np.ndarray:
    return np.arange(int(SR * dur)) / SR


def _pink(n: int, rng: np.random.Generator) -> np.ndarray:
    """Pink noise via FFT 1/sqrt(f) shaping."""
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    f[0] = f[1]
    x = np.fft.irfft(spec / np.sqrt(f), n)
    return x / (np.max(np.abs(x)) + 1e-9)


def _svf_bandpass(x: np.ndarray, fc: np.ndarray, q: float) -> np.ndarray:
    """Chamberlin state-variable band-pass with a per-sample cutoff."""
    y = np.empty_like(x)
    low = band = 0.0
    damp = 1.0 / q
    f = 2 * np.sin(np.pi * np.clip(fc, 20, SR / 6) / SR)
    for i in range(len(x)):
        high = x[i] - low - damp * band
        band += f[i] * high
        low += f[i] * band
        y[i] = band
    return y


def _fade(x: np.ndarray, ms_in: float = 1.5, ms_out: float = 3.0) -> np.ndarray:
    n_in, n_out = int(SR * ms_in / 1000), int(SR * ms_out / 1000)
    if n_in:
        x[:n_in] *= np.linspace(0, 1, n_in)
    if n_out:
        x[-n_out:] *= np.linspace(1, 0, n_out)
    return x


def _norm(x: np.ndarray, peak_db: float = -1.0) -> np.ndarray:
    return x / (np.max(np.abs(x)) + 1e-9) * 10 ** (peak_db / 20)


def _stereo(x: np.ndarray, pan: np.ndarray | float = 0.0) -> np.ndarray:
    """Equal-power pan; pan in [-1, 1] (scalar or per-sample)."""
    p = (np.asarray(pan) + 1) * np.pi / 4
    return np.stack([x * np.cos(p), x * np.sin(p)], axis=1)


# ---------------------------------------------------------------- effects
def whoosh(dur: float = 0.45, peak: float = 0.6, f_lo: float = 300, f_hi: float = 6000,
           f_end: float = 800, q: float = 1.6, dark: bool = False, seed: int = 1) -> np.ndarray:
    """Airy whoosh: pink noise through a band-pass sweeping up then down, L→R pan."""
    rng = np.random.default_rng(seed)
    t = _t(dur)
    n = len(t)
    k = n * peak
    i = np.arange(n)
    up = f_lo * (f_hi / f_lo) ** np.clip(i / k, 0, 1)
    down = f_hi * (f_end / f_hi) ** np.clip((i - k) / (n - k), 0, 1)
    fc = np.where(i < k, up, down) * (0.5 if dark else 1.0)
    x = _svf_bandpass(_pink(n, rng), fc, q)
    env = np.where(i < k, (i / k) ** 2.2, np.exp(-5.0 * (i - k) / (n - k)))
    x = x * env
    if dark:  # add a low rumble layer for heavy moves
        x += 0.5 * _svf_bandpass(_pink(n, rng), np.full(n, 120.0), 0.9) * env
    return _stereo(_fade(_norm(x)), np.linspace(-0.6, 0.6, n))


def pop(dur: float = 0.07, f0: float = 1100, f1: float = 320) -> np.ndarray:
    """Bubbly UI pop: sine with an exponential pitch drop and fast decay."""
    t = _t(dur)
    f = f0 * (f1 / f0) ** (t / dur)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * np.minimum(1, t / 0.001) * np.exp(-t / (dur * 0.28))
    return _stereo(_fade(_norm(x), 0.5, 2))


def click(seed: int = 3) -> np.ndarray:
    """Short bright click: decaying noise burst + one 3.5 kHz cycle."""
    rng = np.random.default_rng(seed)
    t = _t(0.012)
    x = rng.standard_normal(len(t)) * np.exp(-t / 0.0007)
    x += 0.6 * np.sin(2 * np.pi * 3500 * t) * np.exp(-t / 0.0015)
    x = np.diff(x, prepend=0)  # crude high-pass
    return _stereo(_fade(_norm(x), 0.1, 2))


def impact(dur: float = 0.9, f_hi: float = 150, f_lo: float = 50, drive: float = 1.6,
           seed: int = 5) -> np.ndarray:
    """808-style boom with a transient so it reads on phone speakers."""
    rng = np.random.default_rng(seed)
    t = _t(dur)
    f = f_lo + (f_hi - f_lo) * np.exp(-t / 0.045)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.35)
    x += 0.35 * np.sin(2 * np.pi * np.cumsum(2 * f) / SR) * np.exp(-t / 0.12)  # harmonic for phones
    n_click = int(SR * 0.004)
    x[:n_click] += 0.25 * rng.standard_normal(n_click) * np.linspace(1, 0, n_click)
    x = np.tanh(drive * x)
    return _stereo(_fade(_norm(x), 0.3, 20))


def riser(dur: float = 1.6, f_lo: float = 200, f_hi: float = 9000, seed: int = 7) -> np.ndarray:
    """Noise riser with a rising band-pass + an octave tonal sweep; ends at the hit."""
    rng = np.random.default_rng(seed)
    t = _t(dur)
    n = len(t)
    fc = f_lo * (f_hi / f_lo) ** (t / dur)
    x = _svf_bandpass(_pink(n, rng), fc, 2.2)
    tone_f = 220 * 2 ** (t / dur)
    x += 0.25 * np.sin(2 * np.pi * np.cumsum(tone_f) / SR)
    x *= (t / dur) ** 2.5
    return _stereo(_fade(_norm(x), 5, 1.5))


EFFECTS = {
    "whoosh": (whoosh, lambda: 0.45 * 0.6),
    "whoosh_dark": (lambda: whoosh(dur=0.8, dark=True, f_hi=3500, seed=2), lambda: 0.8 * 0.6),
    "whoosh_short": (lambda: whoosh(dur=0.28, peak=0.55, f_hi=7000, seed=4), lambda: 0.28 * 0.55),
    "pop": (pop, lambda: 0.0),
    "pop_low": (lambda: pop(dur=0.09, f0=700, f1=220), lambda: 0.0),
    "click": (click, lambda: 0.0),
    "impact": (impact, lambda: 0.0),
    "riser": (riser, lambda: 1.6),
}


def sync_point(name: str) -> float:
    """Seconds from the start of the file to its hit."""
    return EFFECTS[name][1]()


def write_wav(path: Path, x: np.ndarray) -> None:
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main() -> None:
    ap = argparse.ArgumentParser(description="Synthesize SFX wavs")
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.list:
        for k in EFFECTS:
            print(f"{k:13s} hit at {sync_point(k):.3f}s")
        return
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, (fn, _) in EFFECTS.items():
        x = fn()
        write_wav(args.out_dir / f"{name}.wav", x)
        print(f"{name:13s} {len(x) / SR:5.2f}s  hit at {sync_point(name):.3f}s")


if __name__ == "__main__":
    main()
