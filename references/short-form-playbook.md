# Short-form playbook (Reels / TikTok / Shorts)

Distilled from a web sweep of platform docs, creator/vendor guides, open-source caption tools and
motion-design systems, plus real client feedback. Numbers marked *(weak)* come from a single vendor
blog. Everything here is a default, not a law — but deviate on purpose, not by accident.

## 0. READ FIRST — taste lessons from real feedback
- **Default to RESTRAINT.** A "hype" treatment (emoji pop-ins, badges next to the head, slanted slabs,
  word-by-word yellow box highlight, constant punch-ins, busy flag/stripe end cards) was rejected as
  "ugly, covers the face, too much decoration". Offer hype elements only if the user asks.
- **Face keep-out is a hard rule.** Run `helpers/face_track.py <video> -o <edit>/face.json`, map the box
  with `to_canvas(...)` (per zoom state), add any must-stay-visible box by hand (a logo or number on a
  shirt, a product), keep ≥ 12–24 px clearance, and make the graphics build FAIL on a collision
  (`templates/captions_overlay.py` does this). Never cover face, mouth, eyes or hands mid-gesture.
- **When the user hands you a reference video, copy its grammar precisely** — measure, don't guess:
  overlay a 5 % grid on 6–8 frames and read block x/width, baselines (% of height), cap height, line step;
  tile the animation at 15–30 fps to get exact timings; identify the caption font by glyph shapes
  (double-/single-storey a and g, t terminals) and calibrate weight/tracking side by side. Brand assets
  shown on a flat background can be lifted with `helpers/extract_logo.py` (only the user's own assets).
  Big numerals rebuilt from a font (e.g. Montserrat) beat an upscaled 720p extraction.

### Style A — word-by-word "premium social" captions (default of `templates/captions_overlay.py`)
- Inter Display (opsz 32), key words ~110 px wght 560, function words ~62 px wght 460, tracking −6 %,
  sentence case as spoken, 2-line blocks centred on the frame (lines left-aligned inside the block),
  baseline step 0.84 em, block around 55–60 % of the height (below the chin).
- Each word fades + blur-ins (~110–130 ms) on its spoken onset; the block clears at the phrase end.
- No plate, no stroke: dark glow (blur 16, ~90 %) + a tight 2 px dark halo for light backgrounds.
- Optional: per-phrase framing changes (1.0 ↔ 1.10) that land exactly on caption page starts.

### Style B — restrained phrase captions
- Whole phrases, sentence case, one family, white, soft shadow on a translucent dark plate (black 55 %,
  radius 18). Fade-in 180 ms + 10 px rise, no bounce; one line, 3–6 words, ≤ 17 chars/s, ≥ 0.8 s.
- At most ONE highlight in the whole clip (the key fact) in one accent colour; ≤ 2 graphic elements on
  screen at once; no emojis/stickers/SFX pops; no zooms (or one slow push ≤ 5 %).
- Why: IBM Carbon — "if users frequently notice the motion, remove it"; 0 % overshoot reads premium;
  many successful social teams favour simple and direct over over-produced.

### End cards
- ≤ 3–4 s, start as the last word rings out, no dead frames. Big hero element (date/number) that draws
  as an outline then fills; 3–5 centred lines fading in 120 ms apart, no overshoot; hold ≥ 1.5 s.
  `templates/end_card.py` implements this.

## 1. Hook (0–3 s)
- Frame 1 already carries the message: big on-screen text (what/when/where) + first spoken
  word at t=0. No fade-in, no logo, no "olá, eu sou…". (Instagram/Mosseri 2025; TikTok
  Creative Best Practices: value prop in 3 s, hook within 6 s; ~80–90 % of ad recall in 6 s.)
- Many viewers are on mute → the hook must read without audio.

## 2. Pacing
- Cut silences: keep ~0.08–0.15 s before a word, 0.1–0.2 s after (auto-editor default margin 0.2 s).
- A *visual change* every ~2–3 s: punch-in, graphic event, page of captions. (contested: 1.5–5 s)
- Punch-in **110–115 %** (up to 120 % for the peak line), hard cut back to 100 %; land it on the
  onset of the stressed word. Random zooms without intent look amateur.
- Slow push (Ken Burns) 100→120 % over >2 s for sincere lines. NOTE: ffmpeg `zoompan` jitters on
  slow ramps (ticket #4298) — prefer hard punches, or upscale ×4 before zoompan.
- Implementation: one contiguous take = ONE range with `"zooms"` keys (render.py zoompan) — no
  segment cut, so no audio fade/AAC seam mid-sentence. Align range edges to frames (k/fps).

## 3. Captions (word-synced, drawn in a PIL overlay layer)
- 1–3 words per page (break on silence > 300 ms or ~1.2 s), UPPERCASE, heavy sans
  (Montserrat Black / Anton / TheBoldFont; on Windows: Segoe UI Black `seguibl.ttf`).
- Size ≈ 100–120 px at 1080 wide, auto-fit ≤ 85–90 % width. Black stroke 8–10 px + soft shadow
  (blur ≈ 8–10 % of size, ~60 % opacity).
- Active word: yellow (#FFD400-ish) + scale 1.08–1.15. Second emphasis level (keywords: numbers,
  dates, names, the event): coloured pill behind the word. Max 2 colours + base.
- Page entry: scale 0.8→1 + ~40 px rise, 150–200 ms, ease-out-back (c1 1.2–1.7). Exit: hard cut.
- Active word = from its start to the NEXT word's start (Remotion/captacity convention).
- Lay words out by their visible (alpha>128) edges, not padded boxes, or spacing looks uneven.
- Legibility ceiling: ≤ 42 chars/line, ≤ 20 chars/s.
- Fix ASR mis-hearings of names/places by hand (e.g. a town name heard as a person's name).

## 4. Safe zones (1080×1920)
- Union safe area (IG/TikTok/Shorts incl. ads): x 120–888 (or 65–1015 organic), y 288–1248.
  Organic posts tolerate a lower bottom edge: captions centred y ≈ 1150–1400.
- TikTok right rail of buttons from y ≈ 840 down, ~120–300 px wide: keep stickers off the right edge there.
- Don't cover the speaker's face or a logo/number printed on the shirt — move graphics to the
  chest/background slot instead of the top when the head sits high in frame.

## 5. Motion design
- Entrances 225–300 ms ease-out (emphasized decelerate `cubic-bezier(0.05,0.7,0.1,1)` or
  ease-out-back ~10 % overshoot); exits shorter, 150–200 ms ease-in. Never linear.
- Stagger: per word 80–120 ms, per line/element 100–300 ms; one new thing at a time.
- Lower thirds hold 3–6 s (or "read it twice"). Counters ease-out over 0.6–1 s.
- Stickers/emoji: pop with bigger overshoot (c1 2–2.5) + a damped wobble; tie to the spoken word.

## 6. Ending / CTA
- End card ≤ 2–2.6 s, starts as the last word rings out; no dead frames after the audio.
- Repeat the logistics (date/time/place) and ONE specific, low-friction ask
  ("MANDA PRA QUEM VAI", "chama o vizinho") — sends drive reach for non-followers.

## 7. Sound
- SFX: whoosh on punch-ins/transitions (peak 0–1 frame before the cut), pop/click on sticker
  pop-ins (onset ON the frame), soft impact before a key word (never on a consonant), riser
  ending hard on a reveal. ~2–4 per 15 s for a serious tone (≤ 5 max); vary them.
- Levels: SFX peaks 6–10 dB under dialogue peaks (gain −13…−17 dB on the -1 dBFS files from
  `helpers/sfx.py`). Mix with `amix normalize=0`, then loudnorm the whole mix.
- Music (when used): duck 6–12 dB under speech, attack 30–80 ms, release 250–700 ms.
- Dialogue chain for phone audio (EDL `audio_chain`):
  `highpass=f=90,afftdn=nr=10:nf=-45:tn=1,equalizer=f=250:t=q:w=1.2:g=-3,equalizer=f=3500:t=q:w=1:g=2.5,deesser=i=0.4:m=0.5:f=0.5,acompressor=threshold=-20dB:ratio=3:attack=10:release=150:makeup=2`
  (deesser i/m/f are 0–1, NOT Hz; afftdn nf ≥ −30 starts to muffle.)
- Master: two-pass loudnorm −14 LUFS, TP ≤ −1 dBTP (no official platform number; −14 is the consensus).

## 8. Picture
- Low-res phone footage: scale with `flags=lanczos+accurate_rnd+full_chroma_int`, then
  `hqdn3d=1.5:1.5:3:3,cas=0.35,colorbalance=rm=0.02:bm=-0.015,eq=contrast=1.04:saturation=1.08,vignette=PI/7,noise=c0s=5:c0f=t+u`.
  cas never 1.0; grain ≤ 6 (platform re-encode smears more); saturation ≤ 1.1 for skin.
- Export: H.264 High, yuv420p, keep source fps (don't 30→24), CRF 18–20, AAC ≥ 128k, faststart.
  No bars/borders/watermarks — Instagram down-ranks blurry, bordered or watermarked Reels.

## 9. Amateur tells to avoid
Overused transitions, random zooms, same SFX on every beat, inconsistent voice level, music too
loud, low-contrast or ornate text, missing captions, graphics covering the face, end card that
drags, a silent tail.
