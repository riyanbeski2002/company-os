// activity.mjs — measures DEAD AIR: how long the picture goes without any visible change. Node 22+, no npm deps
// (headless Chrome / Brave through scripts/cdp.mjs decodes the frames).
//
//   node scripts/activity.mjs <framesDir> [--fps 24] [--thr 8] [--min 0.2] [--until s] [--csv out.csv] [--png out.png]
//                                         [--events events.json|.mjs] [--gap 0.6] [--fail-over s] [--workers 4]
//
// Input: a folder of consecutive frames f_NNNNN.png / .jpg (frame index at fps) — normally a capture.mjs run
// (`--draft` is enough for pacing). fps: --fps, else <framesDir>/_comp.json (written by capture.mjs), else 24.
// Per frame, against the previous frame, on a grey downsample 384 px wide:
//   mad       mean |Δluma| over the whole frame (0–255)                 → overall energy of the change
//   frac      share of pixels with |Δluma| > 10                         → how much of the frame changes
//   blockmax  the largest mean |Δluma| of any 12×12 block                → LOCAL change: a cursor or a chip moving on an
//                                                                        otherwise still frame still counts
// Dead air = consecutive frames whose blockmax < --thr (8/255) lasting ≥ --min (0.2 s). A global mean misses a small
// cursor moving over a still UI; the block maximum does not.
// Why: the client said «быстрее … не задерживалось на чем то долго» about a cut whose shots were not long — what they felt
// was dead air. Measuring it moved the film from 4.87 s total / 1.20 s longest dead air to 1.53 s / 0.37 s, approved.
// Run it after every pacing change instead of guessing.
// Reading the report: a still stretch is fine only as a listed read and only as long as the read needs — status 1.0 s,
// name + ✓ 0.6–0.7 s, three numbers 1.2 s, list item 0.8 s, end lockup 2 s. Anything else longer than ≈ 0.5–0.6 s
// needs a trigger, a camera follow or a cut. Use --until to stop before the end lockup (e.g. --until 28).
// A stricter second pass (--thr 20 --min 0.4) finds "almost still" stretches where only something tiny moves.
// Animated grain defeats this metric (and doubles the bitrate): keep grain static.
// --events: a JSON file ([{ t, k, dur }]) or an ES module exporting EVENTS — also lists EVENT GAPS longer than --gap
//   (0.6 s) between consecutive events before --until (a move's dur counts as busy), and draws them as ticks on the PNG.
// Output: the dead stretches, longest and total before --until, mean MAD per second; optional CSV and a PNG chart.
// Exit code: 0 · 1 usage / browser error · 2 when --fail-over is given and the longest dead stretch before --until
// exceeds it. Companion: fdiff (the same metric on the encoded MP4, plus glitches, freezes and timing).
import { readdirSync, readFileSync, writeFileSync, existsSync, mkdtempSync, rmSync } from 'node:fs';
import { resolve, join, extname } from 'node:path';
import { tmpdir } from 'node:os';
import { pathToFileURL } from 'node:url';
import { launch } from './cdp.mjs';

const VALUE = new Set(['--fps', '--thr', '--min', '--until', '--csv', '--png', '--events', '--gap', '--fail-over', '--workers']);
const argv = process.argv.slice(2), o = {}, pos = [];
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (VALUE.has(a)) { if (i + 1 >= argv.length) usage(`${a} needs a value`); o[a] = argv[++i]; }
  else if (a === '-h' || a === '--help') usage();
  else if (a.startsWith('--')) usage(`unknown option ${a}`);
  else pos.push(a);
}
function usage(msg) {
  if (msg) console.error('activity: ' + msg);
  console.error('usage: node activity.mjs <framesDir> [--fps 24] [--thr 8] [--min 0.2] [--until s] [--csv f] [--png f] [--events f] [--gap 0.6] [--fail-over s] [--workers 4]');
  process.exit(1);
}
const num = (k, d) => { if (o[k] === undefined) return d; const v = Number(o[k]); if (!Number.isFinite(v)) usage(`${k} must be a number (got ${o[k]})`); return v; };
if (pos.length !== 1) usage();
const dir = resolve(pos[0]);
if (!existsSync(dir)) usage(`no such folder: ${dir}`);
let compFps = null;
try { const c = JSON.parse(readFileSync(join(dir, '_comp.json'), 'utf8')); if (c && Number(c.fps) > 0) compFps = Number(c.fps); } catch { /* no _comp.json */ }
const FPS = num('--fps', compFps || 24), THR = num('--thr', 8), MIN = num('--min', 0.2), WORKERS = Math.max(1, Math.floor(num('--workers', 4)));
if (o['--fps'] !== undefined && compFps && compFps !== FPS) console.log(`note: --fps ${FPS} overrides _comp.json fps ${compFps}`);
const files = readdirSync(dir).filter((f) => /^f_\d+\.(jpe?g|png)$/i.test(f)).sort((a, b) => parseInt(a.slice(2), 10) - parseInt(b.slice(2), 10));
if (files.length < 2) usage(`need at least two frames f_NNNNN.png|jpg in ${dir}`);
const idx = files.map((f) => parseInt(f.slice(2), 10));
const END = (idx[idx.length - 1] + 1) / FPS;
const UNTIL = num('--until', END);
let EVENTS = [];
if (o['--events']) {
  const f = resolve(o['--events']);
  const raw = extname(f) === '.json' ? JSON.parse(readFileSync(f, 'utf8')) : ((await import(pathToFileURL(f).href)).EVENTS || []);
  EVENTS = (Array.isArray(raw) ? raw : []).filter((e) => e && typeof e.t === 'number').sort((a, b) => a.t - b.t);
}

// the measuring page: decodes frames, keeps the previous luma plane, returns [mad, frac, blockmax] per frame.
// It is a file:// page reading file:// frames (cdp.mjs launches with --allow-file-access-from-files, so the canvas is
// not tainted); if a canvas ever is, the frames are sent as data: URLs instead.
const PAGE = `<!doctype html><meta charset="utf-8"><canvas id=c></canvas><script>
let W = 384, H = 216, BS = 12, prev = null;
const c = document.getElementById('c'), x = c.getContext('2d', { willReadFrequently: true });
async function luma(url) {
  const im = new Image(); im.src = url; await im.decode();
  if (!prev) { W = 384; H = Math.max(BS, Math.round(384 * im.naturalHeight / im.naturalWidth / BS) * BS); c.width = W; c.height = H; }
  x.imageSmoothingEnabled = true; x.imageSmoothingQuality = 'medium'; x.drawImage(im, 0, 0, W, H);
  const d = x.getImageData(0, 0, W, H).data, g = new Float32Array(W * H);
  for (let i = 0, j = 0; i < g.length; i++, j += 4) g[i] = 0.299 * d[j] + 0.587 * d[j + 1] + 0.114 * d[j + 2];
  return g;
}
window.reset = () => { prev = null; return true; };
window.run = async (urls) => {
  const out = [];
  for (const u of urls) {
    const cur = await luma(u);
    if (prev) {
      const bw = Math.floor(W / BS), bh = Math.floor(H / BS), blocks = new Float32Array(bw * bh); let s = 0, n10 = 0;
      for (let y = 0; y < H; y++) for (let xx = 0; xx < W; xx++) { const i = y * W + xx, dd = Math.abs(cur[i] - prev[i]); s += dd; if (dd > 10) n10++;
        const bx = Math.floor(xx / BS), by = Math.floor(y / BS); if (bx < bw && by < bh) blocks[by * bw + bx] += dd; }
      let bm = 0; for (const v of blocks) if (v > bm) bm = v;
      out.push([s / (W * H), n10 / (W * H), bm / (BS * BS)]);
    } else out.push(null);
    prev = cur;
  }
  return out;
};
window.__measureReady = true;</script>`;

const tmp = mkdtempSync(join(tmpdir(), 'hft-activity-'));
let browser = null;
try {
  writeFileSync(join(tmp, 'measure.html'), PAGE);
  browser = await launch({ width: 800, height: 600 });
  const t0 = performance.now();
  const MIME = { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg' };
  const asData = (f) => `data:${MIME[extname(f).toLowerCase()]};base64,${readFileSync(join(dir, f)).toString('base64')}`;
  const asFile = (f) => pathToFileURL(join(dir, f)).href;
  // split into chunks; each chunk re-reads the frame before it so every frame is compared with its true predecessor
  const n = files.length, chunk = Math.ceil(n / WORKERS), rows = new Array(n).fill(null);
  let mode = 'file';
  await Promise.all(Array.from({ length: Math.min(WORKERS, n) }, async (_, k) => {
    const a = k * chunk, z = Math.min(n, a + chunk); if (a >= z) return;
    const from = Math.max(0, a - 1), p = await browser.newPage(pathToFileURL(join(tmp, 'measure.html')).href, { width: 800, height: 600 });
    if (!(await p.waitFor('window.__measureReady === true', { timeoutMs: 30000 }))) throw new Error('the measuring page did not load');
    const BATCH = 24;   // frames per evaluate (keeps each CDP message small in data: mode)
    for (let s = from; s < z; s += BATCH) {
      const part = files.slice(s, Math.min(z, s + BATCH));
      let res;
      try { res = await p.evaluate(`window.run(${JSON.stringify(part.map(mode === 'file' ? asFile : asData))})`); }
      catch (e) {
        if (!/SecurityError|tainted|cross-origin/i.test(e.message)) throw e;
        mode = 'data';                                             // tainted canvas: fall back to data: URLs
        await p.evaluate('window.reset()');
        if (s > from) await p.evaluate(`window.run(${JSON.stringify([asData(files[s - 1])])})`);
        res = await p.evaluate(`window.run(${JSON.stringify(part.map(asData))})`);
      }
      for (let i = 0; i < res.length; i++) if (s + i > from || (s + i === 0)) rows[s + i] = res[i];   // the chunk's first read is the predecessor
    }
    const errs = p.errors(); if (errs.length) throw new Error('measuring page: ' + errs.slice(0, 3).join(' | '));
    await p.close();
  }));
  const secs = ((performance.now() - t0) / 1000).toFixed(1);

  // table (a gap in frame numbers breaks the comparison: that row counts as neither dead nor alive)
  const T = idx.map((fr, i) => ({ fr, t: fr / FPS, m: i > 0 && idx[i - 1] === fr - 1 ? rows[i] : null }));
  const gaps = T.filter((r, i) => i > 0 && !r.m).length;
  const runs = []; let s = null;
  for (let i = 0; i < T.length; i++) {
    const r = T[i], dead = r.m && r.m[2] < THR;
    if (dead && s == null) s = i;
    if ((!dead || i === T.length - 1) && s != null) {
      const e = dead ? i : i - 1;
      // length = number of unchanged frame steps (the metric behind the 4.87 → 1.53 s / 1.20 → 0.37 s numbers)
      runs.push({ a: T[s].fr / FPS, b: (T[e].fr + 1) / FPS });
      s = null;
    }
  }
  for (const r of runs) r.len = r.b - r.a;
  const dead = runs.filter((r) => r.len >= MIN - 1e-9);
  const before = dead.filter((r) => r.a < UNTIL - 1e-9).map((r) => ({ ...r, b: Math.min(r.b, UNTIL), len: Math.min(r.b, UNTIL) - r.a }));
  const longest = before.reduce((m, r) => Math.max(m, r.len), 0), total = before.reduce((acc, r) => acc + r.len, 0);
  const tc = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}+${String(Math.round((t % 1) * FPS) % Math.round(FPS)).padStart(2, '0')}f`;
  console.log(`activity  ${n} frames @ ${FPS} fps${compFps ? ' (from _comp.json)' : ''} · dead = local change < ${THR}/255 for ≥ ${MIN} s · measured in ${secs} s${mode === 'data' ? ' (data: URL mode)' : ''}`);
  if (gaps) console.log(`note: ${gaps} gap(s) in the frame numbers — those frames are not compared`);
  console.log(dead.length ? dead.map((r) => `  ${r.a.toFixed(2)} → ${r.b.toFixed(2)}  ${r.len.toFixed(2)} s   (${tc(r.a)} → ${tc(r.b)})${r.a >= UNTIL - 1e-9 ? '   after --until' : ''}`).join('\n') : '  no dead stretches');
  console.log(`longest before ${UNTIL.toFixed(2)} s: ${longest.toFixed(2)} s · total dead before ${UNTIL.toFixed(2)} s: ${total.toFixed(2)} s`);
  const nsec = Math.ceil(END), per = [];
  for (let q = 0; q < nsec; q++) { const rr = T.filter((r) => r.m && r.t >= q && r.t < q + 1); per.push(rr.length ? (rr.reduce((acc, r) => acc + r.m[0], 0) / rr.length).toFixed(1) : '–'); }
  console.log('mean MAD per second:', per.join(' '));

  if (EVENTS.length) {
    const GAP = num('--gap', 0.6), egaps = []; let busy = 0;
    for (const e of EVENTS) { if (e.t >= UNTIL) break; if (e.t - busy > GAP + 1e-9) egaps.push([busy, e.t]); busy = Math.max(busy, e.t + (e.dur || 0)); }
    if (UNTIL - busy > GAP + 1e-9) egaps.push([busy, UNTIL]);
    console.log(`event gaps > ${GAP} s before ${UNTIL.toFixed(2)} s (move durations count as busy): ` + (egaps.length ? egaps.map(([a, b]) => `${a.toFixed(2)}–${b.toFixed(2)} (${(b - a).toFixed(2)} s)`).join(' · ') : 'none'));
  }
  if (o['--csv']) {
    writeFileSync(o['--csv'], 'frame,t,mad,frac,blockmax\n' + T.map((r) => `${r.fr},${r.t.toFixed(4)},${r.m ? r.m[0].toFixed(3) : ''},${r.m ? r.m[1].toFixed(4) : ''},${r.m ? r.m[2].toFixed(2) : ''}`).join('\n') + '\n');
    console.log('csv', o['--csv']);
  }
  if (o['--png']) {
    const data = { dur: END, pts: T.filter((r) => r.m).map((r) => [r.t, r.m[2], r.m[0]]), dead, THR, UNTIL, ev: EVENTS.map((e) => [e.t, String(e.k ?? ''), e.dur || 0]) };
    const html = `<!doctype html><meta charset="utf-8"><style>html,body{margin:0;background:#fbfaf7}</style><canvas id=c width=1800 height=520></canvas><script>
const D = ${JSON.stringify(data)}, c = document.getElementById('c'), g = c.getContext('2d'), L = 60, R = 1770, TOP = 50, h = 420;
const X = t => L + (R - L) * t / D.dur, Y = v => TOP + h - h * Math.log10(1 + Math.min(255, v)) / Math.log10(256);
g.fillStyle = '#fbfaf7'; g.fillRect(0, 0, 1800, 520); g.fillStyle = '#1d1d1f'; g.font = '600 18px Helvetica, Arial, sans-serif'; g.fillText('picture activity — red: local change (block max) · grey: mean |Δluma| · shaded: dead air · dashed: threshold', L, 30);
for (const r of D.dead) { g.fillStyle = r.a >= D.UNTIL ? '#00000010' : '#d1392b22'; g.fillRect(X(r.a), TOP, X(r.b) - X(r.a), h); }
g.strokeStyle = '#0000001a'; for (let t = 0; t <= D.dur; t += 1) { g.beginPath(); g.moveTo(X(t), TOP); g.lineTo(X(t), TOP + h); g.stroke(); g.fillStyle = '#555'; g.font = '12px Helvetica, Arial, sans-serif'; g.fillText(t + 's', X(t) - 6, TOP + h + 18); }
for (const v of [1, 4, 8, 20, 64, 255]) { g.fillStyle = '#555'; g.fillText(String(v), 20, Y(v) + 4); }
g.setLineDash([6, 4]); g.strokeStyle = '#b26b00'; g.beginPath(); g.moveTo(L, Y(D.THR)); g.lineTo(R, Y(D.THR)); g.stroke(); g.setLineDash([]);
const pl = (k, col, w) => { g.strokeStyle = col; g.lineWidth = w; g.beginPath(); D.pts.forEach((p, i) => i ? g.lineTo(X(p[0]), Y(p[k])) : g.moveTo(X(p[0]), Y(p[k]))); g.stroke(); };
for (const [t, k, d] of D.ev) { if (d > 0) { g.fillStyle = '#2f63d614'; g.fillRect(X(t), TOP, X(t + d) - X(t), h); } g.strokeStyle = '#2f63d6aa'; g.beginPath(); g.moveTo(X(t), TOP); g.lineTo(X(t), TOP + 14); g.stroke();
  g.save(); g.translate(X(t) + 2, TOP + 18); g.rotate(Math.PI / 2); g.fillStyle = '#2f63d6'; g.font = '11px Helvetica, Arial, sans-serif'; g.fillText(k, 0, 0); g.restore(); }
pl(2, '#8892a8', 1); pl(1, '#d1392b', 1.6); g.strokeStyle = '#0003'; g.lineWidth = 1; g.strokeRect(L, TOP, R - L, h); window.__done = true;</script>`;
    writeFileSync(join(tmp, 'chart.html'), html);
    const p = await browser.newPage(pathToFileURL(join(tmp, 'chart.html')).href, { width: 1800, height: 520 });
    if (!(await p.waitFor('window.__done === true', { timeoutMs: 30000 }))) throw new Error('the chart page did not render');
    writeFileSync(o['--png'], await p.screenshot({ format: 'png' }));
    await p.close();
    console.log('png', o['--png']);
  }
  if (o['--fail-over'] !== undefined && longest > num('--fail-over', Infinity) + 1e-9) {
    console.log(`FAIL: longest dead stretch ${longest.toFixed(2)} s > ${o['--fail-over']} s`);
    process.exitCode = 2;
  }
} catch (e) {
  console.error('activity failed: ' + e.message);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close().catch(() => {});
  rmSync(tmp, { recursive: true, force: true });
}
