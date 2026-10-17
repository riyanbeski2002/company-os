// Deterministic frame capture of a code-based motion composition (DOM/CSS/SVG/Canvas/WebGL) via headless Chrome/Brave
// (HFT_BROWSER overrides) + raw CDP (scripts/cdp.mjs). Node 22+, no npm dependencies.
// The page MUST expose:
//   window.__comp = { width, height, fps, duration }      (seconds)
//   window.__seek = async (t) => { ...render the frame at time t...; }   (pure, continuous in fractional t)
// Optional: window.__ready (promise, or false until ready); window.__hfError (set by hf-motion.js → the run fails).
//
// usage:
//   node capture.mjs <page.html[?query] | http://…> <out_dir> [options]
//     --query "style=luxury-serif&scheme=light"   query string for the page (same as page.html?…)
//     --stills 0.5,1.2,...    review stills → still_<t.toFixed(3)>_f<n>.png (n = round(t·fps)) instead of frames
//     --snap                  snap --stills times to the frame grid (t = n/fps)
//     --from s --to s         frame range in seconds (default 0 … duration)
//     --every n               every n-th frame (default 1)
//     --jpg                   JPEG q95 instead of PNG
//     --draft                 fast interim: JPEG q95, 4 workers, never motion blur
//     --workers N             N parallel browsers (one tab each); worker k takes frames n ≡ k (mod N). Separate
//                             processes, not tabs: PNG encoding serialises inside one browser (96 frames: 4 tabs
//                             14.9 s vs 4 browsers 5.9 s)
//     --mb [N]                motion blur for masters: N sub-frames to start (default 8) over a forward shutter window
//       --shutter 0.5         shutter as a fraction of the frame interval (0.5 = 180°)
//       --mb-max 32           adaptive refinement: double the samples (midpoints) up to this many …
//       --mb-diff 2.0         … while neighbouring sub-frames differ by more than this (mean |Δluma| 0–255, sparse grid)
//     --check-determinism     seek-order test: stills (--stills, else every 0.25 s + last frame) captured in forward,
//                             reverse and shuffled order in fresh tabs, pixel-diffed; report → <out_dir>/_determinism.json
//     --size WxH              viewport before navigation (default: <meta name="frame" content="WxH">, else 1920x1080)
//     --serve [root]          load the page over http://127.0.0.1 from root (default: cwd) instead of file://
//     --clean                 delete f_* / still_* / _comp.json in out_dir first (finals go into a fresh folder)
//     --lenient               exit 0 despite page errors (they are still printed)
//     --timeout s             load/ready and per-seek timeout (default 60)
//
// Frames: out_dir/f_00000.png …; stills: out_dir/still_<t>_f<n>.png. After a frame run the folder is checked for
// completeness (missing runs re-captured in fresh tabs, up to 3 passes) and out_dir/_comp.json is written for encode:
//   { width, height, fps, duration, frames, from, to, every, ext, complete, missing, mb, page, query }
//   (frames = number of f_* files this run must leave in the folder; from/to = frame indices, to exclusive)
// Exit codes: 0 ok · 1 setup/usage · 3 page errors (exceptions, console errors, failed requests, HTTP ≥ 400, fallback
// warnings, window.__hfError, a seek that threw) · 4 frames still missing · 5 seek-order determinism failed.
//
// Motion blur (--mb): frame n is the linear-light mean of sub-frames at t = n/fps + (k/N)·shutter/fps (forward window,
// clamped to duration − 1e-4); before each sub-frame seek the page gets window.__mbBase = n/fps and window.__mbDT = offset
// (footage/plates hold one source frame across the shutter by reading these). Frames whose first and last sub-frames are
// identical render once. Sub-frames are JPEG q98, averaged in a compositor tab per worker.
import { writeFileSync, mkdirSync, existsSync, statSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { resolve, relative, isAbsolute, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { cpus } from 'node:os';
import { launch, serveStatic, metaFrame } from './cdp.mjs';

// ---------------------------------------------------------------- arguments
const VALUE = new Set(['--query', '--stills', '--from', '--to', '--every', '--workers', '--shutter', '--mb-max', '--mb-diff', '--size', '--timeout']);
const OPTIONAL = { '--mb': '8', '--serve': '' };
const BOOL = new Set(['--jpg', '--draft', '--snap', '--lenient', '--check-determinism', '--clean']);
const argv = process.argv.slice(2);
const pos = [], o = {};
const usage = (msg) => {
  if (msg) console.error('capture: ' + msg);
  console.error('usage: node capture.mjs <page.html[?query]> <out_dir> [--query q] [--stills t1,t2|--check-determinism] [--snap] [--from s] [--to s] [--every n]\n' +
    '                     [--jpg|--draft] [--workers N] [--mb [N] --shutter 0.5 --mb-max 32 --mb-diff 2.0] [--size WxH] [--serve [root]] [--clean] [--lenient] [--timeout s]');
  process.exit(1);
};
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (VALUE.has(a)) { if (i + 1 >= argv.length) usage(`${a} needs a value`); o[a] = argv[++i]; }
  else if (a in OPTIONAL) { const nx = argv[i + 1]; if (nx !== undefined && !nx.startsWith('--') && (a !== '--mb' || /^\d+$/.test(nx))) { o[a] = nx; i++; } else o[a] = OPTIONAL[a]; }
  else if (BOOL.has(a)) o[a] = true;
  else if (a.startsWith('--')) usage(`unknown option ${a}`);
  else pos.push(a);
}
if (pos.length < 2) usage();
const num = (k, d) => { if (o[k] === undefined) return d; const v = parseFloat(o[k]); if (!Number.isFinite(v)) usage(`${k} must be a number`); return v; };

const [pageArg, outArg] = pos;
const outDir = resolve(outArg);
const isUrl = /^https?:\/\//i.test(pageArg);
const qi = pageArg.indexOf('?');
const pagePath = isUrl ? null : resolve(qi >= 0 ? pageArg.slice(0, qi) : pageArg);
const query = (o['--query'] ?? (qi >= 0 ? pageArg.slice(qi + 1) : '')).replace(/^\?/, '');
const draft = !!o['--draft'];
const jpg = draft || !!o['--jpg'];
const ext = jpg ? 'jpg' : 'png';
const stills = o['--stills'] ? o['--stills'].split(',').map((s) => s.trim()).filter(Boolean).map(Number) : null;
if (stills && stills.some((t) => !Number.isFinite(t) || t < 0)) usage('--stills must be a comma list of times in seconds');
const snap = !!o['--snap'];
const from = num('--from', 0);
const toArg = o['--to'] !== undefined ? num('--to') : null;
const every = Math.max(1, Math.round(num('--every', 1)));
let workers = Math.max(1, Math.round(num('--workers', draft ? Math.min(4, Math.max(2, cpus().length >> 1)) : 1)));
let mbN = o['--mb'] !== undefined ? Math.max(1, parseInt(o['--mb'], 10)) : 0;
if (mbN && draft) { console.log('note: --draft renders without motion blur; --mb ignored'); mbN = 0; }
const SHUTTER = Math.min(1, Math.max(0, num('--shutter', 0.5)));
const MB_MAX = Math.max(mbN, Math.round(num('--mb-max', 32)));
const MB_DIFF = num('--mb-diff', 2.0);
const det = !!o['--check-determinism'];
const lenient = !!o['--lenient'];
const TIMEOUT = Math.max(5, num('--timeout', 60)) * 1000;
let size = null;
if (o['--size']) { const m = /^(\d+)[x×](\d+)$/.exec(o['--size']); if (!m) usage('--size must look like 1920x1080'); size = { width: +m[1], height: +m[2] }; }
if (!isUrl && !existsSync(pagePath)) usage(`page not found: ${pagePath}`);
if (!size && pagePath) size = metaFrame(readFileSync(pagePath, 'utf8'));
size = size || { width: 1920, height: 1080 };

mkdirSync(outDir, { recursive: true });
if (o['--clean']) {
  for (const f of readdirSync(outDir)) if (/^(f_\d+|still_[\d.]+(_f\d+)?)\.(png|jpe?g)$/.test(f) || f === '_comp.json') rmSync(resolve(outDir, f), { force: true });
}

// ---------------------------------------------------------------- page URL
let server = null;
let url;
if (isUrl) url = pageArg.split('?')[0] + (query ? '?' + query : '');
else if (o['--serve'] !== undefined) {
  const root = resolve(o['--serve'] || process.cwd());
  const rel = relative(root, pagePath);
  if (rel.startsWith('..') || isAbsolute(rel)) usage(`--serve root ${root} does not contain ${pagePath}; pass the project root: --serve <root>`);
  server = await serveStatic(root);
  url = `${server.url}/${rel.split(sep).map(encodeURIComponent).join('/')}${query ? '?' + query : ''}`;
} else url = pathToFileURL(pagePath).href + (query ? '?' + query : '');

// ---------------------------------------------------------------- helpers
const t0 = Date.now();
const secs = () => ((Date.now() - t0) / 1000).toFixed(1);
const pad5 = (n) => String(n).padStart(5, '0');
const runErrors = []; // seek / shot failures with their t
const pages = new Set(); // every page ever opened (their errors are collected at the end)
const browsers = new Set();
let comp;

async function newBrowser() {
  const b = await launch({ width: comp ? comp.width : size.width, height: comp ? comp.height : size.height });
  browsers.add(b);
  return b;
}
async function openPage(browser) {
  const p = await browser.newPage(url, { width: comp ? comp.width : size.width, height: comp ? comp.height : size.height, loadTimeoutMs: TIMEOUT });
  pages.add(p);
  const c = await p.waitFor('window.__comp && typeof window.__seek === "function" ? window.__comp : null', { timeoutMs: TIMEOUT, intervalMs: 150 });
  if (!c) throw new Error(`page did not expose window.__comp + window.__seek within ${TIMEOUT / 1000} s\n  ${p.errors().slice(-8).join('\n  ')}`);
  await p.waitReady({ timeoutMs: TIMEOUT });
  const hfErr = await p.evaluate('window.__hfError ? String(window.__hfError) : null').catch(() => null);
  if (hfErr && !p.__hfNoted) { p.__hfNoted = true; runErrors.push(`window.__hfError: ${hfErr}`); }
  return { p, c };
}

// compositor tab: linear-light averaging of sub-frames and pixel diffs (one per worker)
const COMPOSITOR = `window.__hftc = (() => {
  const S2L = new Float32Array(256);
  for (let i = 0; i < 256; i++) { const c = i / 255; S2L[i] = c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }
  const L2S = new Uint8Array(65536);
  for (let i = 0; i < 65536; i++) { const l = i / 65535; L2S[i] = Math.round(255 * (l <= 0.0031308 ? l * 12.92 : 1.055 * Math.pow(l, 1 / 2.4) - 0.055)); }
  let W = 0, H = 0, cv = null, cx = null, acc = null, n = 0, lumas = [];
  const STEP = 6;
  const pixels = async (b64, type) => {
    const bm = await createImageBitmap(await (await fetch('data:' + type + ';base64,' + b64)).blob());
    if (bm.width !== W || bm.height !== H || !cv) { W = bm.width; H = bm.height; cv = document.createElement('canvas'); cv.width = W; cv.height = H; cx = cv.getContext('2d', { willReadFrequently: true }); acc = null; }
    cx.clearRect(0, 0, W, H); cx.drawImage(bm, 0, 0); bm.close();
    return cx.getImageData(0, 0, W, H).data;
  };
  const luma = (d) => { const out = []; for (let y = 0; y < H; y += STEP) for (let x = 0; x < W; x += STEP) { const i = (y * W + x) * 4; out.push(d[i] * 0.3 + d[i + 1] * 0.59 + d[i + 2] * 0.11); } return Float32Array.from(out); };
  return {
    reset() { if (acc) acc.fill(0); n = 0; lumas = []; return true; },
    async add(b64) {
      const d = await pixels(b64, 'image/jpeg');
      if (!acc || acc.length !== W * H * 3) acc = new Float32Array(W * H * 3);
      for (let i = 0, j = 0; i < d.length; i += 4, j += 3) { acc[j] += S2L[d[i]]; acc[j + 1] += S2L[d[i + 1]]; acc[j + 2] += S2L[d[i + 2]]; }
      n++; lumas.push(luma(d)); return lumas.length - 1;
    },
    worst(ids) {
      let w = 0;
      for (let k = 1; k < ids.length; k++) { const A = lumas[ids[k - 1]], B = lumas[ids[k]]; let s = 0; for (let i = 0; i < A.length; i++) s += Math.abs(A[i] - B[i]); w = Math.max(w, s / A.length); }
      return w;
    },
    result(type, q) {
      const img = cx.createImageData(W, H), d = img.data, k = 65535 / n;
      for (let i = 0, j = 0; i < d.length; i += 4, j += 3) {
        d[i] = L2S[Math.min(65535, Math.round(acc[j] * k))]; d[i + 1] = L2S[Math.min(65535, Math.round(acc[j + 1] * k))];
        d[i + 2] = L2S[Math.min(65535, Math.round(acc[j + 2] * k))]; d[i + 3] = 255;
      }
      cx.putImageData(img, 0, 0);
      return cv.toDataURL(type, q).split(',')[1];
    },
    async compare(a64, b64) {
      const A = (await pixels(a64, 'image/png')).slice(), B = await pixels(b64, 'image/png');
      let sum = 0, max = 0, n16 = 0, x0 = W, y0 = H, x1 = -1, y1 = -1;
      for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
        const i = (y * W + x) * 4;
        const d = Math.max(Math.abs(A[i] - B[i]), Math.abs(A[i + 1] - B[i + 1]), Math.abs(A[i + 2] - B[i + 2]));
        sum += d; if (d > max) max = d;
        if (d > 16) { n16++; if (x < x0) x0 = x; if (y < y0) y0 = y; if (x > x1) x1 = x; if (y > y1) y1 = y; }
      }
      return { mean: sum / (W * H), max, n16, bbox: n16 ? [x0, y0, x1, y1] : null };
    },
  };
})(); true`;
async function openCompositor(browser) {
  const c = await browser.newPage('about:blank', { width: 64, height: 64 });
  await c.evaluate(COMPOSITOR);
  return c;
}

// one output image at time t (plain or motion-blurred) → file
const mbStats = { blurred: 0, still: 0, refined: 0, samples: 0 };
async function renderAt(w, t, file, base = t) {
  const { p } = w;
  if (!mbN) {
    await p.seek(t, { timeoutMs: TIMEOUT });
    writeFileSync(file, await p.screenshot({ format: jpg ? 'jpeg' : 'png', quality: 95 }));
    return;
  }
  const tMax = comp.duration - 1e-4;
  const at = (frac) => Math.min(tMax, Math.max(0, base + frac * SHUTTER / comp.fps));
  const sub = async (ts) => { await p.seek(ts, { mbBase: base, mbDT: ts - base, timeoutMs: TIMEOUT }); return p.screenshot({ format: 'jpeg', quality: 98 }); };
  let times = Array.from({ length: mbN }, (_, k) => at(k / mbN));
  const first = await sub(times[0]);
  const last = mbN > 1 ? await sub(times[mbN - 1]) : first;
  if (mbN === 1 || first.equals(last)) { // static over the shutter (or no blur asked): one render
    await p.seek(times[0], { mbBase: base, mbDT: 0, timeoutMs: TIMEOUT });
    writeFileSync(file, await p.screenshot({ format: jpg ? 'jpeg' : 'png', quality: 95 }));
    mbStats.still++; mbStats.samples += mbN > 1 ? 3 : 1;
    return;
  }
  const c = w.c;
  await c.evaluate('__hftc.reset()');
  const add = (buf) => c.evaluate(`__hftc.add("${buf.toString('base64')}")`);
  let ids = [await add(first)];
  for (let k = 1; k < mbN - 1; k++) ids.push(await add(await sub(times[k])));
  ids.push(await add(last));
  let step = SHUTTER / comp.fps / mbN;
  while (times.length * 2 <= MB_MAX) {
    const worst = await c.evaluate(`__hftc.worst(${JSON.stringify(ids)})`);
    if (worst < MB_DIFF) break;
    step /= 2;
    const nt = [], ni = [];
    for (let k = 0; k < times.length; k++) {
      nt.push(times[k]); ni.push(ids[k]);
      const tm = Math.min(tMax, times[k] + step);
      nt.push(tm); ni.push(await add(await sub(tm)));
    }
    times = nt; ids = ni; mbStats.refined++;
  }
  const b64 = await c.evaluate(`__hftc.result(${JSON.stringify(jpg ? 'image/jpeg' : 'image/png')}, 0.95)`);
  writeFileSync(file, Buffer.from(b64, 'base64'));
  mbStats.blurred++; mbStats.samples += times.length;
}

// a worker = its own browser + page (+ compositor tab for motion blur); a dead browser is replaced
async function openWorker(b) {
  if (!b || !b.connected) { if (b) { browsers.delete(b); await b.close().catch(() => {}); } b = await newBrowser(); }
  const { p } = await openPage(b);
  const c = mbN ? await openCompositor(b) : null;
  return { b, p, c };
}
async function closeWorker(w) { await w.p.close().catch(() => {}); if (w.c) await w.c.close().catch(() => {}); }

// run jobs [{ t, base, file, label }] over N workers (job i → worker i mod N)
async function runJobs(jobs, ws, onDone) {
  await Promise.all(ws.map(async (w, k) => {
    for (let i = k; i < jobs.length; i += ws.length) {
      const j = jobs[i];
      try { await renderAt(w, j.t, j.file, j.base); }
      catch (e) {
        runErrors.push(`${j.label} (t=${+j.t.toFixed(4)}): ${e.message.split('\n')[0]}`);
        if (/crash|closed|Target|timed out/i.test(e.message)) { // tab died or hung: replace it
          await closeWorker(w);
          try { Object.assign(w, await openWorker(w.b)); } catch (e2) { runErrors.push(`worker restart failed: ${e2.message.split('\n')[0]}`); return; }
        }
      }
      onDone?.();
    }
  }));
}

// ---------------------------------------------------------------- main
let exitCode = 0;
try {
  const b0 = await newBrowser();
  // first tab: learn the composition
  let first = await openPage(b0);
  comp = first.c;
  if (!(comp.fps > 0 && comp.duration > 0 && comp.width > 0 && comp.height > 0)) throw new Error(`window.__comp is incomplete: ${JSON.stringify(comp)}`);
  if (comp.width !== size.width || comp.height !== size.height) {
    console.log(`note: viewport was ${size.width}x${size.height} at load but __comp is ${comp.width}x${comp.height}; reloading at the comp size (add <meta name="frame" content="${comp.width}x${comp.height}"> or --size)`);
    await first.p.close(); pages.delete(first.p);
    first = await openPage(b0);
  }
  console.log('comp:', JSON.stringify(comp));
  const fps = comp.fps;

  if (det) {
    // ------------------------------------------------ seek-order determinism test
    const dur = toArg ?? comp.duration;
    let ts = stills ? stills.slice() : [];
    if (!stills) { for (let t = from; t < dur - 1e-9; t += 0.25) ts.push(+t.toFixed(4)); ts.push(+((Math.round(dur * fps) - 1) / fps).toFixed(4)); }
    ts = [...new Set(ts.map((t) => (snap ? Math.round(t * fps) / fps : t)))].sort((a, b) => a - b);
    let seed = 7; const rnd = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
    const shuffled = ts.slice(); for (let i = shuffled.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]; }
    const orders = { F: ts, R: ts.slice().reverse(), S: shuffled };
    const shots = {};
    await first.p.close();
    for (const [name, list] of Object.entries(orders)) {
      const { p } = await openPage(b0); // fresh tab per order
      shots[name] = new Map();
      const dir = resolve(outDir, '_det', name); mkdirSync(dir, { recursive: true });
      for (const t of list) {
        try {
          await p.seek(t, { timeoutMs: TIMEOUT });
          const png = await p.screenshot();
          shots[name].set(t, png);
          writeFileSync(resolve(dir, `still_${t.toFixed(3)}_f${Math.round(t * fps)}.png`), png);
        } catch (e) { runErrors.push(`determinism ${name} (t=${t}): ${e.message.split('\n')[0]}`); }
      }
      await p.close();
    }
    const c = await openCompositor(b0);
    const rows = [];
    for (const t of ts) {
      for (const other of ['R', 'S']) {
        const a = shots.F.get(t), b = shots[other].get(t);
        if (!a || !b) continue;
        const r = await c.evaluate(`__hftc.compare("${a.toString('base64')}", "${b.toString('base64')}")`);
        rows.push({ t, order: other, ...r, mean: +r.mean.toFixed(3), visible: r.max >= 32 || r.n16 >= 24 });
      }
    }
    await c.close();
    const bad = rows.filter((r) => r.visible);
    writeFileSync(resolve(outDir, '_determinism.json'), JSON.stringify({ comp, stills: ts, threshold: 'visible = max channel diff ≥ 32 or ≥ 24 px above 16', rows }, null, 1));
    const worst = rows.reduce((m, r) => Math.max(m, r.max), 0);
    console.log(`determinism: ${ts.length} stills × forward/reverse/shuffled, worst max channel diff ${worst}/255 → ${bad.length ? 'FAIL' : 'ok'} (${secs()} s)`);
    for (const r of bad.slice(0, 20)) console.log(`  t=${r.t} F vs ${r.order}: max ${r.max}, ${r.n16} px > 16, mean ${r.mean}, bbox ${r.bbox?.join(',')}`);
    console.log(`  stills: ${resolve(outDir, '_det')}/{F,R,S}  report: ${resolve(outDir, '_determinism.json')}`);
    if (bad.length) exitCode = 5;
  } else if (stills) {
    // ------------------------------------------------ review stills
    const jobs = stills.map((t0_) => {
      const n = Math.round(t0_ * fps), t = snap ? n / fps : t0_;
      return { t, base: t, label: `still ${t}`, file: resolve(outDir, `still_${t.toFixed(3)}_f${n}.${ext}`) };
    });
    const ws = [{ b: b0, p: first.p, c: mbN ? await openCompositor(b0) : null }];
    ws.push(...await Promise.all(Array.from({ length: Math.min(workers, jobs.length) - 1 }, () => openWorker())));
    await runJobs(jobs, ws);
    const missing = jobs.filter((j) => !existsSync(j.file));
    console.log(`stills: ${stills.join(',')}${snap ? ' (snapped)' : ''}${mbN ? ` with motion blur ×${mbN}` : ''} -> ${outDir} (${secs()} s)`);
    if (missing.length) { console.log(`missing stills: ${missing.map((j) => j.t).join(',')}`); exitCode = 4; }
    const cj = resolve(outDir, '_comp.json');
    let prev = null; try { prev = JSON.parse(readFileSync(cj, 'utf8')); } catch {}
    if (!prev || prev.mode === 'stills') writeFileSync(cj, JSON.stringify({ mode: 'stills', width: comp.width, height: comp.height, fps, duration: comp.duration, frames: 0, stills: jobs.map((j) => +j.t.toFixed(4)), ext, page: pagePath || url, query }, null, 1));
  } else {
    // ------------------------------------------------ frame sequence
    const dur = toArg ?? comp.duration;
    const n0 = Math.round(from * fps), n1 = Math.min(Math.round(dur * fps), Math.round(comp.duration * fps));
    const list = []; for (let n = n0; n < n1; n += every) list.push(n);
    if (!list.length) throw new Error(`no frames in range ${from}–${dur} s at ${fps} fps`);
    const job = (n) => ({ t: n / fps, base: n / fps, label: `frame ${n}`, file: resolve(outDir, `f_${pad5(n)}.${ext}`) });
    const stale = readdirSync(outDir).filter((f) => /^f_\d+\.(png|jpe?g)$/.test(f) && !list.includes(parseInt(f.slice(2), 10))).length;
    workers = Math.min(workers, list.length);
    const ws = [{ b: b0, p: first.p, c: mbN ? await openCompositor(b0) : null }];
    const opened = await Promise.all(Array.from({ length: workers - 1 }, () => openWorker().catch((e) => { runErrors.push(`worker failed to start: ${e.message.split('\n')[0]}`); return null; })));
    ws.push(...opened.filter(Boolean));
    console.log(`capturing ${list.length} frames (${n0}…${n1 - 1}${every > 1 ? ` every ${every}` : ''}) with ${ws.length} worker${ws.length > 1 ? 's' : ''}${mbN ? `, motion blur ×${mbN}…${MB_MAX} shutter ${SHUTTER}` : ''}${draft ? ', draft' : ''} (ready in ${secs()} s)`);
    let done = 0; const tick = Math.max(1, Math.round(fps * 2 / every));
    await runJobs(list.map(job), ws, () => { done++; if (done % tick === 0) console.log(`frame ${done}/${list.length} (${secs()} s)`); });
    // completeness: re-capture missing runs in fresh tabs, up to 3 passes
    const isMissing = (n) => { const f = job(n).file; try { return statSync(f).size === 0; } catch { return true; } };
    let missing = list.filter(isMissing);
    for (let pass = 1; pass <= 3 && missing.length; pass++) {
      console.log(`pass ${pass}: re-capturing ${missing.length} missing frame(s): ${runs(missing)}`);
      for (const w of ws) await closeWorker(w);
      const pool = ws.splice(0).map((w) => w.b);
      ws.push(...await Promise.all(pool.slice(0, Math.min(pool.length, missing.length)).map((b) => openWorker(b))));
      await runJobs(missing.map(job), ws);
      missing = list.filter(isMissing);
    }
    writeFileSync(resolve(outDir, '_comp.json'), JSON.stringify({
      mode: 'frames', width: comp.width, height: comp.height, fps, duration: comp.duration,
      frames: list.length, from: n0, to: n1, every, ext, complete: missing.length === 0, missing: missing.slice(0, 200),
      mb: mbN ? { samples: mbN, max: MB_MAX, diff: MB_DIFF, shutter: SHUTTER } : null, draft, page: pagePath || url, query,
    }, null, 1));
    console.log(`done ${list.length - missing.length}/${list.length} frames @${fps}fps -> ${outDir} (${secs()} s, ${(list.length / Math.max(0.001, (Date.now() - t0) / 1000)).toFixed(1)} fps)`);
    if (mbN) console.log(`motion blur: ${mbStats.blurred} blurred, ${mbStats.still} static (single render), ${mbStats.refined} refinements, ${(mbStats.samples / Math.max(1, mbStats.blurred + mbStats.still)).toFixed(1)} renders/frame`);
    if (stale) console.log(`warning: ${stale} f_* file(s) outside this range are in ${outDir}; encode only from a clean folder (--clean)`);
    if (missing.length) { console.error(`MISSING ${missing.length} frame(s) after 3 passes: ${runs(missing)}`); exitCode = 4; }
  }
} catch (e) {
  console.error('capture failed: ' + e.message);
  exitCode = 1;
}

function runs(ns) {
  const out = [];
  for (const n of ns) { const r = out[out.length - 1]; if (r && n === r[1] + every) r[1] = n; else out.push([n, n]); }
  return out.map(([a, b]) => (a === b ? `${a}` : `${a}-${b}`)).join(', ');
}

// ---------------------------------------------------------------- errors → exit code
const pageErrs = [...pages].flatMap((p) => p.errors());
const all = [...runErrors, ...pageErrs];
if (all.length) {
  const counts = new Map(); for (const e of all) counts.set(e, (counts.get(e) || 0) + 1);
  console.error(`PAGE ERRORS (${all.length}${lenient ? ', --lenient' : ''}):`);
  for (const [e, k] of [...counts].slice(0, 25)) console.error(`  ${k > 1 ? `${k}× ` : ''}${e}`);
  if (counts.size > 25) console.error(`  … ${counts.size - 25} more`);
  if (!exitCode && !lenient) exitCode = 3;
}
for (const b of browsers) await b.close().catch(() => {});
if (server) server.close();
process.exit(exitCode);
