---
name: claude-video-editor-install
description: Install claude-video-editor (a fork of browser-use/video-use with local transcription) into Claude Code on Windows, macOS or Linux, so the user can start editing immediately.
---

# claude-video-editor — install (for the agent)

Use this file only for first-time install. For daily editing, read `SKILL.md`. Talk to the user in their
language (default pt-BR).

## What must exist

1. This repo cloned somewhere stable (e.g. `C:\dev\claude-video-editor` or `~/Developer/claude-video-editor`).
2. Python ≥ 3.10 and a virtualenv at `<repo>/.venv` with the deps from `pyproject.toml`.
3. `ffmpeg` + `ffprobe` on PATH.
4. The skill registered with Claude Code (the WHOLE repo directory, so `helpers/` sits next to `SKILL.md`).
5. `.env` at the repo root (copy of `.env.example`). No API key is needed — transcription is local.

## Steps

### 1. Clone
```bash
git clone https://github.com/Thur-zi/claude-video-editor <stable path>
```

### 2. Python deps (in a venv)
```bash
cd <repo>
python -m venv .venv
.venv/Scripts/python -m pip install -e .        # Windows   (macOS/Linux: .venv/bin/python)
```
The first transcription downloads the Whisper model (`small`, ~460 MB) from Hugging Face automatically.

### 3. ffmpeg
- Windows: `winget install Gyan.FFmpeg` (then open a new terminal).
- macOS: `brew install ffmpeg` · Debian/Ubuntu: `sudo apt-get install -y ffmpeg`.
Ask before installing system packages; never invent passwords.

### 4. Windows gotchas (check, don't guess)
- **Microsoft Visual C++ Redistributable** is required by the Whisper engine (`ctranslate2`) and OpenCV.
  Test: `.venv/Scripts/python -c "import ctranslate2, cv2"`. If it fails with "could not find module …dll",
  install it (with the user's OK): `winget install Microsoft.VCRedist.2015+.x64`.
- **Smart App Control** may block some unsigned DLLs ("Uma política de Controle de Aplicativo bloqueou este
  arquivo"). Never change that security setting. `helpers/local_asr.py` already works without PyAV (the
  package most often blocked). If another package is blocked, look for a workaround and tell the user.
- Use `PYTHONIOENCODING=utf-8` in Bash so accented text prints.

### 5. Register the skill
- Windows (junction, no admin needed):
  ```bash
  cmd //c mklink //J "%USERPROFILE%\.claude\skills\claude-video-editor" "<repo>"
  ```
- macOS/Linux: `mkdir -p ~/.claude/skills && ln -sfn <repo> ~/.claude/skills/claude-video-editor`

### 6. Config
```bash
cp .env.example .env      # VIDEO_USE_ASR=local, VIDEO_USE_WHISPER_MODEL=small
```
Optional: ElevenLabs Scribe for faster/more verbatim transcription — set `ELEVENLABS_API_KEY` and
`VIDEO_USE_ASR=scribe` (paid per minute).

### 7. Verify for real
```bash
.venv/Scripts/python -m pytest -q tests
.venv/Scripts/python helpers/timeline_view.py --help
```
Then tell the user, in one short message: where it is installed, that they should open Claude Code in the
folder with their videos and say something like *"edita esse vídeo para Reels de até 1 minuto, com legenda"*,
and that outputs go to `<videos folder>/edit/`.
