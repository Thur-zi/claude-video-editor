"""Local transcription with faster-whisper, shaped like an ElevenLabs Scribe response.

Drop-in replacement for `call_scribe` when there is no ElevenLabs key (or you
want zero per-minute cost). Runs on the CPU, so it is slower than Scribe, and
it is weaker on two things the editor cares about:

  - Fillers ("éé", "hum", "ahn") — Whisper tends to clean them out of the text.
    A filler-heavy initial prompt keeps many of them, not all. Silences still
    show up as gaps between words, so pause cuts are unaffected.
  - Audio events / diarization — not produced. Every word gets speaker_0.

Output shape (what pack_transcripts / render / timeline_view read):
    {"language_code": "pt", "text": "...", "words": [
        {"type": "word", "text": "Olá", "start": 0.52, "end": 0.81, "speaker_id": "speaker_0"},
        {"type": "spacing", "text": " ", "start": 0.81, "end": 0.90, "speaker_id": "speaker_0"},
        ...]}

Model / device are configurable through env vars (or the .env at the repo root):
    VIDEO_USE_WHISPER_MODEL   tiny | base | small | medium | large-v3 | large-v3-turbo  (default: small)
    VIDEO_USE_WHISPER_COMPUTE int8 | int8_float32 | float32                             (default: int8)
"""

from __future__ import annotations

import os
from pathlib import Path

# Biases Whisper toward keeping verbatim fillers instead of normalizing them away.
FILLER_PROMPTS = {
    "pt": "Então, éé, hum, tipo assim, né, ahn, é... Bom, eu, eu acho que, hã, a gente vai, tipo, começar.",
    "en": "Umm, so, uh, like, you know, I mean, uh, we, we were, hmm, going to start.",
    "es": "Eh, este, o sea, mmm, pues, como que, eh, vamos a empezar.",
}

_MODEL = None
_MODEL_KEY: tuple[str, str] | None = None


def _setting(name: str, default: str) -> str:
    v = os.environ.get(name)
    if v:
        return v.strip()
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            k, _, val = line.strip().partition("=")
            if k.strip() == name and val.strip():
                return val.strip().strip('"').strip("'")
    return default


def _import_whisper_model():
    """Import faster_whisper without PyAV.

    faster_whisper imports `av` at module load, but only uses it to decode audio
    files. We hand it a decoded array (ffmpeg already wrote a 16 kHz wav), so a
    placeholder module is enough — and it sidesteps Windows Smart App Control,
    which blocks PyAV's unsigned DLLs on some machines.
    """
    import sys
    import types

    if "av" not in sys.modules:
        try:
            import av  # noqa: F401
        except Exception:
            sys.modules["av"] = types.ModuleType("av")
    from faster_whisper import WhisperModel
    return WhisperModel


def _read_wav(path: Path):
    """16-bit PCM mono wav → float32 numpy array in [-1, 1]."""
    import wave

    import numpy as np

    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1 or w.getframerate() != 16000:
            raise ValueError(f"{path.name}: expected 16 kHz mono 16-bit wav")
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def _load_model():
    global _MODEL, _MODEL_KEY
    WhisperModel = _import_whisper_model()

    name = _setting("VIDEO_USE_WHISPER_MODEL", "small")
    compute = _setting("VIDEO_USE_WHISPER_COMPUTE", "int8")
    key = (name, compute)
    if _MODEL is None or _MODEL_KEY != key:
        threads = max(1, os.cpu_count() or 1)
        _MODEL = WhisperModel(name, device="cpu", compute_type=compute, cpu_threads=threads)
        _MODEL_KEY = key
    return _MODEL


def transcribe_local(audio_path: Path, language: str | None = None, verbose: bool = True) -> dict:
    model = _load_model()
    lang = language or "pt"
    segments, info = model.transcribe(
        _read_wav(audio_path),
        language=lang,
        word_timestamps=True,
        initial_prompt=FILLER_PROMPTS.get(lang),
        condition_on_previous_text=False,   # stops repetition loops / hallucinated phrases
        vad_filter=True,                     # skip silence → fewer hallucinations
        vad_parameters={"min_silence_duration_ms": 500},
        beam_size=5,
    )

    words: list[dict] = []
    texts: list[str] = []
    for seg in segments:
        texts.append(seg.text.strip())
        if verbose:
            print(f"    [{seg.start:6.1f}-{seg.end:6.1f}] {seg.text.strip()}", flush=True)
        for w in seg.words or []:
            token = w.word.strip()
            if not token:
                continue
            start, end = round(float(w.start), 3), round(float(w.end), 3)
            if words:
                prev_end = words[-1]["end"]
                if start > prev_end:
                    words.append({"type": "spacing", "text": " ", "start": prev_end,
                                  "end": start, "speaker_id": "speaker_0"})
            words.append({"type": "word", "text": token, "start": start, "end": end,
                          "speaker_id": "speaker_0", "probability": round(float(w.probability), 3)})

    return {
        "language_code": info.language,
        "language_probability": round(float(info.language_probability), 3),
        "text": " ".join(texts),
        "words": words,
        "engine": f"faster-whisper:{_MODEL_KEY[0]}:{_MODEL_KEY[1]}" if _MODEL_KEY else "faster-whisper",
    }
