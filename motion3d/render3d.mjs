// Render an extruded 3D logo/text animation to a transparent PNG sequence (+ optional .mov with alpha).
//
//   node motion3d/render3d.mjs spec.json
//
// spec.json:
// {
//   "vector": "shapes/num22.json",          // from helpers/vectorize.py (path relative to spec or absolute)
//   "out": "C:/…/frames_22",                // output dir (PNG frames f_0000.png …)
//   "mov": "C:/…/obj22.mov",                // optional: also encode PNG-in-MOV with alpha
//   "width": 600, "height": 600, "fps": 24, "duration": 3.0,
//   "color": "#FDCE00",                     // optional: override the per-shape colours
//   "depth": 0.35, "bevel": 0.05, "metalness": 0.25, "roughness": 0.3, "clearcoat": 0.8,
//   "scale": 1.0, "cameraZ": 6, "fov": 30, "exposure": 1.05,
//   "anim": { "entrance": 0.6, "overshoot": 1.4, "entranceTwistDeg": 180, "spinDegPerSec": 60,
//             "startYawDeg": -25, "tiltDeg": 8, "wobbleDeg": 4, "rollDeg": 3, "bob": 0.08, "bobPeriod": 2.4 }
// }
// Uses the locally installed Chrome/Edge (puppeteer-core) — no browser download. WebGL runs on the GPU
// when available, else SwiftShader (software) automatically.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const specPath = path.resolve(process.argv[2]);
const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
const rel = p => (path.isAbsolute(p) ? p : path.resolve(path.dirname(specPath), p));
if (spec.vector) spec.vector = JSON.parse(fs.readFileSync(rel(spec.vector), 'utf8'));
spec.out = rel(spec.out);                 // outputs are relative to the spec file too
if (spec.mov) spec.mov = rel(spec.mov);
spec.width ??= 600; spec.height ??= 600; spec.fps ??= 24; spec.duration ??= 3;
spec.page ??= 'page.html';                 // or 'parallax.html' (2.5D photo: needs image + depthMap)
// image assets are copied next to the pages so the local server can serve them
const ASSETS = path.join(HERE, '_assets');
fs.mkdirSync(ASSETS, { recursive: true });
for (const key of ['image', 'depthMap']) {
  if (spec[key]) {
    const name = `${key}_${path.basename(rel(spec[key]))}`;
    fs.copyFileSync(rel(spec[key]), path.join(ASSETS, name));
    spec[key] = `/_assets/${encodeURIComponent(name)}`;
  }
}

const BROWSERS = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
];
const exe = process.env.CHROME_PATH || BROWSERS.find(p => fs.existsSync(p));
if (!exe) { console.error('No Chrome/Edge found — set CHROME_PATH'); process.exit(1); }

// tiny static server so ES modules load (file:// would be blocked)
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json',
               '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg' };
const server = http.createServer((req, res) => {
  const p = path.join(HERE, decodeURIComponent(req.url.split('?')[0]));
  if (!p.startsWith(HERE) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'Content-Type': MIME[path.extname(p)] || 'application/octet-stream' });
  fs.createReadStream(p).pipe(res);
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const port = server.address().port;

const browser = await puppeteer.launch({
  executablePath: exe, headless: true,
  args: ['--enable-webgl', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader', '--use-angle=default'],
});
try {
  const page = await browser.newPage();
  page.on('console', m => { if (m.type() === 'error') console.error('[page]', m.text()); });
  page.on('pageerror', e => console.error('[page error]', e.message));
  await page.setViewport({ width: spec.width, height: spec.height, deviceScaleFactor: 1 });
  await page.evaluateOnNewDocument(s => { window.SPEC = s; }, spec);
  await page.goto(`http://127.0.0.1:${port}/${spec.page}`, { waitUntil: 'load' });
  await page.waitForFunction('window.READY === true', { timeout: 60000 });

  fs.mkdirSync(spec.out, { recursive: true });
  for (const f of fs.readdirSync(spec.out)) if (f.endsWith('.png')) fs.unlinkSync(path.join(spec.out, f));
  const n = Math.round(spec.duration * spec.fps);
  const t0 = Date.now();
  for (let i = 0; i < n; i++) {
    const url = await page.evaluate(t => window.renderFrame(t), i / spec.fps);
    fs.writeFileSync(path.join(spec.out, `f_${String(i).padStart(4, '0')}.png`), Buffer.from(url.split(',')[1], 'base64'));
  }
  console.log(`3d frames -> ${spec.out}  (${n} frames, ${((Date.now() - t0) / n).toFixed(0)} ms/frame)`);
  if (spec.mov) {
    const r = spawnSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-framerate', String(spec.fps),
      '-i', path.join(spec.out, 'f_%04d.png'), '-c:v', 'png', '-pix_fmt', 'rgba', spec.mov], { stdio: 'inherit' });
    if (r.status === 0) console.log(`3d mov -> ${spec.mov}`);
  }
} finally {
  await browser.close();
  server.close();
}
