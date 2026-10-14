# motion3d examples

```bash
cd motion3d && npm install                                   # three + puppeteer-core (uses your Chrome/Edge)
# 3D logo that spins and floats
python ../helpers/vectorize.py my_logo.png -o shapes/logo.json
node render3d.mjs examples/logo_spin.json                    # → out/logo.mov (transparent)
# 3D text that swings (never shows its mirrored back)
python ../helpers/vectorize.py --text "OLÁ" -o shapes/text.json
node render3d.mjs examples/text_swing.json
# 2.5D photo: a still frame gets a slow 3D camera move
ffmpeg -ss 5 -i video.mp4 -frames:v 1 out/frame.png
python ../helpers/depth.py out/frame.png -o out/depth.png
node render3d.mjs examples/parallax_photo.json
```
Overlay the .mov in an EDL (`"overlays"`), or composite it per frame with `helpers/layers.py`
(e.g. anchored to `helpers/hands.py` output so it floats over someone's hand).
