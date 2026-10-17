// textcheck.mjs — measured phone legibility of every visible DOM text run in a __seek page: EFFECTIVE on-screen size
// (camera zoom included) and WORST-PIXEL contrast (WCAG 2.x and APCA). Node 22+, no npm deps (scripts/cdp.mjs).
//
//   node scripts/textcheck.mjs <page.html[?query] | http://…> <times> [--query q] [--root "#stage"] [--serve [root]]
//        [--read 64] [--caps 48] [--label 28] [--floor 20] [--wcag 4.5] [--lc 60] [--opaque 0.98]
//        [--ignore <regex>] [--json out.json] [--all] [--timeout s]
//   times: "all" (every frame) · "0-30/0.5" (every half second) · "f120-180" (frames) · "8.0,12.2,17.9" (the still reads)
//
// Why: a 16:9 film is watched in a phone feed at ×~0.2, and eyeballing a 1920-px frame on a big monitor over-rates it.
// Chips that carried the beat at 26 px were ~5 px on a phone; hook words measured 2.75:1 over footage; a camera pull-back
// shrank in-app text below 20 px — all invisible in code, all obvious once measured.
// The page contract is capture.mjs's: window.__comp = { width, height, fps, duration } and window.__seek(t), pure in t.
// How, per frame:
//   1. __seek(t); every non-empty DOM text node under --root (default #stage, else body) is a run. Effective size =
//      CSS font-size × the scale of every ancestor (transform, the CSS scale property and zoom — the camera counts).
//      Effective opacity = product of ancestor opacities.
//   2. the same frame again with all text transparent (no text-shadow): that is what lies UNDER the text.
//   3. glyph pixels = where the two renders differ, dilated 2 px. The run's colour, composited at its opacity, is compared
//      with every background pixel under that mask (WCAG ratio and APCA Lc); the minimum is the verdict. Text clipped
//      away has no glyph pixels and is skipped. Text seen only THROUGH something (a glass toast passing over it, a blur, a
//      flash) shows much less difference than its colour predicts: it is listed as "covered" and not judged.
// Verdicts (only for runs with opacity ≥ --opaque, i.e. not mid-fade, and not covered):
//   FAIL size     effective size < --floor (20 px): reads as noise or a rendering error
//   FAIL read     a run inside an element marked data-read (put it on headlines, key statuses, numbers, offers) is below
//                 --read (64 px mixed case) or, in ALL CAPS, below --caps (48 px)
//   WARN label    effective size < --label (28 px) — fine only for texture nobody needs to read
//   FAIL contrast worst pixel below --wcag 4.5:1 or |Lc| below --lc 60 (6.4:1 WCAG once measured only Lc 49.5 on a
//                 saturated plate: check both)
//   WARN edge     the run is sliced by the frame edge (a word cut mid-glyph at the edge reads as a bug during reads)
// Not measured (listed): gradient-filled text (background-clip:text), SVG <text>, and anything drawn into a canvas/WebGL.
// Output: one line per problem, then a summary per distinct string (min size, min contrast, time range).
// Exit code: 0 pass · 1 usage / load error · 2 any FAIL · 3 page errors (exceptions, failed requests, window.__hfError).
import { writeFileSync, existsSync } from 'node:fs';
import { resolve, relative, isAbsolute, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { launch, serveStatic } from './cdp.mjs';

const VALUE = new Set(['--query', '--root', '--read', '--caps', '--label', '--floor', '--wcag', '--lc', '--opaque', '--ignore', '--json', '--timeout']);
const argv = process.argv.slice(2), o = {}, pos = [];
let serveRoot = null;
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (VALUE.has(a)) { if (i + 1 >= argv.length) usage(`${a} needs a value`); o[a] = argv[++i]; }
  else if (a === '--serve') { serveRoot = argv[i + 1] && !argv[i + 1].startsWith('--') && pos.length >= 2 ? argv[++i] : process.cwd(); }
  else if (a === '--all') o.all = true;
  else if (a === '-h' || a === '--help') usage();
  else if (a.startsWith('--')) usage(`unknown option ${a}`);
  else pos.push(a);
}
function usage(msg) {
  if (msg) console.error('textcheck: ' + msg);
  console.error('usage: node textcheck.mjs <page.html[?query]|http://…> <all|a-b/step|fA-B|t1,t2,…> [--query q] [--root sel] [--serve [root]]\n' +
    '                       [--read 64] [--caps 48] [--label 28] [--floor 20] [--wcag 4.5] [--lc 60] [--opaque 0.98] [--ignore re] [--json f] [--all] [--timeout s]');
  process.exit(1);
}
if (pos.length !== 2) usage();
const num = (k, d) => { if (o[k] === undefined) return d; const v = Number(o[k]); if (!Number.isFinite(v)) usage(`${k} must be a number (got ${o[k]})`); return v; };
const TH = { read: num('--read', 64), caps: num('--caps', 48), label: num('--label', 28), floor: num('--floor', 20), wcag: num('--wcag', 4.5), lc: num('--lc', 60), opaque: num('--opaque', 0.98) };
const IGN = o['--ignore'] ? new RegExp(o['--ignore']) : null, ALL = !!o.all, TIMEOUT = num('--timeout', 60) * 1000;
const ROOT_SEL = o['--root'] || null;

// ---------------------------------------------------------------- page URL (file:// like capture.mjs, or --serve)
const [pageArg, which] = pos;
let url, server = null;
{
  const [p0, inline] = pageArg.split('?');
  const query = (o['--query'] ?? inline ?? '').replace(/^\?/, '');
  if (/^https?:\/\//.test(pageArg)) url = pageArg + (o['--query'] ? (pageArg.includes('?') ? '&' : '?') + query : '');
  else {
    const abs = resolve(p0);
    if (!existsSync(abs)) usage(`no such page: ${abs}`);
    if (serveRoot) {
      const root = resolve(serveRoot), rel = relative(root, abs);
      if (rel.startsWith('..') || isAbsolute(rel)) usage(`--serve root ${root} must contain the page ${abs}`);
      server = await serveStatic(root);
      url = `${server.url}/${rel.split(sep).map(encodeURIComponent).join('/')}${query ? '?' + query : ''}`;
    } else url = pathToFileURL(abs).href + (query ? '?' + query : '');
  }
}

function parseTimes(spec, DURATION, FPS) {
  const last = Math.max(0, Math.ceil(DURATION * FPS - 1e-6) - 1);
  if (!spec || spec === 'all') return Array.from({ length: last + 1 }, (_, i) => i);
  let m = String(spec).match(/^f(\d+)-(\d+)$/);
  if (m) { const out = []; for (let f = +m[1]; f <= Math.min(+m[2], last); f++) out.push(f); return out; }
  m = String(spec).match(/^([\d.]+)-([\d.]+)(?:\/([\d.]+))?$/);
  if (m) {
    const a = +m[1], b = +m[2], step = m[3] ? +m[3] : 1 / FPS, out = new Set();
    if (!(step > 0)) usage('the step in a-b/step must be > 0');
    for (let k = 0; ; k++) { const t = a + k * step; if (t > b + 1e-9) break; const f = Math.round(t * FPS); if (f <= last) out.add(f); }
    return [...out].sort((x, y) => x - y);
  }
  const list = String(spec).split(',').map((s) => Math.round(parseFloat(s) * FPS));
  if (list.some((f) => !Number.isFinite(f))) usage(`cannot read the times "${spec}"`);
  return list.filter((f) => f >= 0 && f <= last);
}

// runs: collected in the page under test (pure DOM reads, no layout changes)
const COLLECT = (rootSel) => `(() => {
  const W = innerWidth, H = innerHeight, out = [];
  const stage = ${rootSel ? `document.querySelector(${JSON.stringify(rootSel)})` : `document.getElementById('stage') || document.body`};
  if (!stage) return { error: 'root element not found: ' + ${JSON.stringify(rootSel || '#stage')} };
  const tw = document.createTreeWalker(stage, NodeFilter.SHOW_TEXT);
  const scaleOf = (el) => { let s = 1;
    for (let e = el; e && e !== document.documentElement; e = e.parentElement) { const cs = getComputedStyle(e);
      if (cs.transform && cs.transform !== 'none') { const m = new DOMMatrixReadOnly(cs.transform); s *= Math.sqrt(Math.abs(m.a * m.d - m.b * m.c)); }
      if (cs.scale && cs.scale !== 'none') { const v = cs.scale.split(/\\s+/).map(parseFloat).filter(Number.isFinite); if (v.length) s *= Math.sqrt(Math.abs(v[0] * (v.length > 1 ? v[1] : v[0]))); }
      const z = parseFloat(cs.zoom); if (Number.isFinite(z) && z > 0 && z !== 1) s *= z; }
    return s; };
  const opOf = (el) => { let a = 1; for (let e = el; e && e !== document.documentElement; e = e.parentElement) a *= +getComputedStyle(e).opacity; return a; };
  const parse = (c) => { const m = c && c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null; const v = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return [v[0], v[1], v[2], v.length > 3 ? v[3] : 1]; };
  for (let n = tw.nextNode(); n; n = tw.nextNode()) {
    const text = n.textContent.replace(/\\s+/g, ' ').trim(); if (!text) continue;
    const el = n.parentElement; if (!el) continue;
    if (el.closest('svg')) { out.push({ text, svg: true }); continue; }
    const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    const rg = document.createRange(); rg.selectNodeContents(n);
    const rs = [...rg.getClientRects()].filter((r) => r.width > 0 && r.height > 0); if (!rs.length) continue;
    const x = Math.min(...rs.map((r) => r.left)), y = Math.min(...rs.map((r) => r.top)), x2 = Math.max(...rs.map((r) => r.right)), y2 = Math.max(...rs.map((r) => r.bottom));
    if (x2 < 0 || y2 < 0 || x > W || y > H) continue;
    const fill = cs.webkitTextFillColor && cs.webkitTextFillColor !== cs.color ? cs.webkitTextFillColor : cs.color, color = parse(fill);
    const gradient = /text/.test(cs.backgroundClip || cs.webkitBackgroundClip || '') || !color || color[3] === 0;
    out.push({ text, x, y, w: x2 - x, h: y2 - y, size: parseFloat(cs.fontSize) * scaleOf(el), op: opOf(el), color, gradient,
      read: !!el.closest('[data-read]'), edge: x < -1 || y < -1 || x2 > W + 1 || y2 > H + 1 });
  }
  return { runs: out, canvases: document.querySelectorAll('canvas').length };
})()`;
const HIDE = '*{color:transparent!important;-webkit-text-fill-color:transparent!important;text-shadow:none!important;caret-color:transparent!important;text-decoration-color:transparent!important}svg text{fill:transparent!important;stroke:transparent!important}';

// pixel maths on a separate blank page (the page under test is never touched beyond the hide-text style)
const ANALYSE = `(() => {
const lin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const Lum = (r, g, b) => 0.2126 * lin(r / 255) + 0.7152 * lin(g / 255) + 0.0722 * lin(b / 255);
const Ya = (r, g, b) => 0.2126729 * (r / 255) ** 2.4 + 0.7151522 * (g / 255) ** 2.4 + 0.072175 * (b / 255) ** 2.4;
function apca(t, g) { const cl = (y) => (y > 0.022 ? y : y + (0.022 - y) ** 1.414); const yt = cl(t), yb = cl(g); let s;
  if (yb > yt) { s = (yb ** 0.56 - yt ** 0.57) * 1.14; return s < 0.1 ? 0 : (s - 0.027) * 100; } s = (yb ** 0.65 - yt ** 0.62) * 1.14; return s > -0.1 ? 0 : (s + 0.027) * 100; }
const ctx = (id) => { let c = document.getElementById(id); if (!c) { c = document.createElement('canvas'); c.id = id; document.body.appendChild(c); } return c; };
const load = async (id, b64, W, H) => { const im = new Image(); im.src = 'data:image/png;base64,' + b64; await im.decode(); const c = ctx(id); c.width = W; c.height = H;
  const x = c.getContext('2d', { willReadFrequently: true }); x.drawImage(im, 0, 0); return x; };
window.measure = async (a64, b64, W, H, runs) => {
  const xa = await load('a', a64, W, H), xb = await load('b', b64, W, H);
  return runs.map((r) => {
    const x0 = Math.max(0, Math.floor(r.x - 3)), y0 = Math.max(0, Math.floor(r.y - 3)), x1 = Math.min(W, Math.ceil(r.x + r.w + 3)), y1 = Math.min(H, Math.ceil(r.y + r.h + 3));
    const ww = x1 - x0, hh = y1 - y0; if (ww <= 0 || hh <= 0) return { n: 0 };
    const da = xa.getImageData(x0, y0, ww, hh).data, db = xb.getImageData(x0, y0, ww, hh).data;
    const m = new Uint8Array(ww * hh); let n = 0;
    for (let i = 0; i < ww * hh; i++) { const d = Math.abs(da[4 * i] - db[4 * i]) + Math.abs(da[4 * i + 1] - db[4 * i + 1]) + Math.abs(da[4 * i + 2] - db[4 * i + 2]); if (d > 36) { m[i] = 1; n++; } }
    if (!n) return { n: 0 };
    const R = 2, h1 = new Uint8Array(ww * hh), d2 = new Uint8Array(ww * hh);
    for (let y = 0; y < hh; y++) for (let x = 0; x < ww; x++) { let v = 0; for (let k = -R; k <= R && !v; k++) { const xx = x + k; if (xx >= 0 && xx < ww && m[y * ww + xx]) v = 1; } h1[y * ww + x] = v; }
    for (let y = 0; y < hh; y++) for (let x = 0; x < ww; x++) { let v = 0; for (let k = -R; k <= R && !v; k++) { const yy = y + k; if (yy >= 0 && yy < hh && h1[yy * ww + x]) v = 1; } d2[y * ww + x] = v; }
    const [tr, tg, tb, ta] = r.color; let wMin = 99, lMin = 999, at = null, vis = 0;
    for (let i = 0; i < ww * hh; i++) { if (!m[i]) continue; const a = ta * r.op, br = db[4 * i], bg = db[4 * i + 1], bb = db[4 * i + 2];
      const exp = a * (Math.abs(tr - br) + Math.abs(tg - bg) + Math.abs(tb - bb)); if (exp < 60) continue;
      const act = Math.abs(da[4 * i] - br) + Math.abs(da[4 * i + 1] - bg) + Math.abs(da[4 * i + 2] - bb); vis = Math.max(vis, act / exp); }
    for (let i = 0; i < ww * hh; i++) { if (!d2[i]) continue;
      const br = db[4 * i], bg = db[4 * i + 1], bb = db[4 * i + 2], a = ta * r.op;
      const cr = tr * a + br * (1 - a), cg = tg * a + bg * (1 - a), cb = tb * a + bb * (1 - a);
      const L1 = Lum(cr, cg, cb), L2 = Lum(br, bg, bb), wc = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05), lc = Math.abs(apca(Ya(cr, cg, cb), Ya(br, bg, bb)));
      if (wc < wMin) { wMin = wc; at = [x0 + (i % ww), y0 + Math.floor(i / ww), br, bg, bb]; } if (lc < lMin) lMin = lc; }
    return { n, wMin, lMin, at, vis };
  });
};
return true; })()`;

let browser = null;
try {
  browser = await launch();
  const p = await browser.newPage(url, { loadTimeoutMs: TIMEOUT });
  const comp = await p.waitFor('window.__comp && typeof window.__seek === "function" ? window.__comp : null', { timeoutMs: TIMEOUT });
  if (!comp) throw new Error(`the page did not expose window.__comp + window.__seek (${url})\n  ${p.errors().slice(0, 5).join('\n  ')}`);
  const W = Math.round(comp.width || 1920), H = Math.round(comp.height || 1080), FPS = +comp.fps || 24, DURATION = +comp.duration || 0;
  if (!(DURATION > 0)) throw new Error('window.__comp.duration must be > 0');
  await p.setViewport({ width: W, height: H, dpr: 1 });
  await p.waitReady({ timeoutMs: TIMEOUT });
  const hfErr = await p.evaluate('window.__hfError ? String(window.__hfError) : null').catch(() => null);
  if (hfErr) {   // hf-motion.js refused an explicitly requested style: the page is not the film — stop here
    console.error('textcheck: window.__hfError: ' + hfErr + '\n  ' + p.errors().slice(0, 5).join('\n  '));
    process.exitCode = 3;
    throw Object.assign(new Error('the page set window.__hfError'), { quiet: true });
  }
  const frames = parseTimes(which, DURATION, FPS);
  if (!frames.length) throw new Error(`no frames selected by "${which}" (duration ${DURATION} s @ ${FPS} fps)`);
  const A = await browser.newPage('about:blank', { width: 400, height: 300 });
  await A.evaluate(ANALYSE);

  const rows = [], probs = [], notMeasured = new Set(); let canvasNote = 0;
  const t0 = performance.now();
  for (const fr of frames) {
    const t = Math.min(fr / FPS, DURATION - 1e-4);
    await p.seek(t, { timeoutMs: TIMEOUT });
    const shotA = await p.screenshot({ format: 'png' });
    const col = await p.evaluate(COLLECT(ROOT_SEL));
    if (col.error) throw new Error(col.error);
    canvasNote = Math.max(canvasNote, col.canvases || 0);
    const runs = col.runs.filter((r) => !(IGN && IGN.test(r.text)));
    for (const r of runs.filter((r) => r.svg || r.gradient)) notMeasured.add(r.text.slice(0, 40));
    const meas = runs.filter((r) => !r.svg && !r.gradient);
    if (!meas.length) continue;
    await p.evaluate(`(() => { const s = document.createElement('style'); s.id = '__hft_hide'; s.textContent = ${JSON.stringify(HIDE)}; document.head.appendChild(s);
      return new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(true)))); })()`);
    const shotB = await p.screenshot({ format: 'png' });
    await p.evaluate(`(() => { const s = document.getElementById('__hft_hide'); if (s) s.remove(); return new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(true)))); })()`);
    const payload = meas.map((r) => ({ x: r.x, y: r.y, w: r.w, h: r.h, color: r.color.slice(0, 4), op: r.op }));
    const res = await A.evaluate(`window.measure(${JSON.stringify(shotA.toString('base64'))}, ${JSON.stringify(shotB.toString('base64'))}, ${W}, ${H}, ${JSON.stringify(payload)})`);
    meas.forEach((r, i) => {
      const m = res[i]; if (!m || !m.n) return;                       // clipped away or fully covered: not on screen
      const caps = r.text === r.text.toUpperCase() && /\p{Lu}/u.test(r.text), covered = m.vis < 0.6, opaque = r.op >= TH.opaque && !covered;
      const row = { t: +t.toFixed(3), f: fr, text: r.text, size: +r.size.toFixed(1), op: +r.op.toFixed(2), wcag: +m.wMin.toFixed(2), lc: +m.lMin.toFixed(1), vis: +m.vis.toFixed(2), read: r.read, caps, edge: r.edge, flags: covered ? ['covered'] : [] };
      if (opaque) {
        if (r.size < TH.floor) row.flags.push('FAIL size');
        else if (r.read && r.size < (caps ? TH.caps : TH.read)) row.flags.push('FAIL read');
        else if (r.size < TH.label) row.flags.push('WARN label');
        if (m.wMin < TH.wcag || m.lMin < TH.lc) row.flags.push('FAIL contrast');
        if (r.edge) row.flags.push('WARN edge');
      }
      if (m.at) row.worst = `(${m.at[0]},${m.at[1]}) bg rgb(${m.at[2]},${m.at[3]},${m.at[4]})`;
      rows.push(row); if (row.flags.some((f) => f !== 'covered') || ALL) probs.push(row);
    });
  }
  const pageErrors = p.errors();
  const secs = ((performance.now() - t0) / 1000).toFixed(1);

  const tc = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
  for (const r of probs) console.log(`${r.t.toFixed(2).padStart(6)} s ${tc(r.t)} f${String(r.f).padEnd(5)} ${(r.flags.join(' + ') || 'ok').padEnd(26)} ${String(r.size).padStart(6)} px  ${String(r.wcag).padStart(5)}:1  Lc ${String(r.lc).padStart(5)}  op ${r.op}${r.read ? '  data-read' : ''}  «${r.text.slice(0, 48)}»${r.flags.includes('FAIL contrast') && r.worst ? '  worst ' + r.worst : ''}`);
  const by = new Map();
  for (const r of rows) {
    const k = r.text.slice(0, 60);
    const g = by.get(k) || { text: k, n: 0, size: 1e9, wcag: 99, lc: 999, a: r.t, b: r.t, flags: new Set() };
    g.n++; g.size = Math.min(g.size, r.size);
    if (r.op >= TH.opaque && !r.flags.includes('covered')) { g.wcag = Math.min(g.wcag, r.wcag); g.lc = Math.min(g.lc, r.lc); }
    g.a = Math.min(g.a, r.t); g.b = Math.max(g.b, r.t); r.flags.forEach((f) => g.flags.add(f)); by.set(k, g);
  }
  const groups = [...by.values()].sort((x, y) => (y.flags.size - x.flags.size) || (x.size - y.size));
  console.log(`\n${frames.length} frames · ${rows.length} visible runs · ${by.size} distinct strings · ${secs} s · thresholds: read ${TH.read} / caps ${TH.caps} / label ${TH.label} / floor ${TH.floor} px, WCAG ${TH.wcag}:1, Lc ${TH.lc}`);
  console.log('string (first 60 chars)                                      min px   min WCAG  min Lc   times        flags');
  for (const g of groups) console.log(`${g.text.padEnd(60).slice(0, 60)} ${String(g.size.toFixed(1)).padStart(7)} ${g.wcag === 99 ? '       —' : String(g.wcag.toFixed(2)).padStart(8)} ${g.lc === 999 ? '      —' : String(g.lc.toFixed(1)).padStart(7)}   ${g.a.toFixed(2)}–${g.b.toFixed(2)}  ${[...g.flags].join(', ')}`);
  if (notMeasured.size) console.log(`not measured (gradient-filled or SVG text): ${[...notMeasured].slice(0, 12).join(' · ')}`);
  if (!rows.length && canvasNote) console.log(`no DOM text found; the page has ${canvasNote} canvas element(s) — text drawn into a canvas / WebGL is not measured (check stills by eye)`);
  if (pageErrors.length) console.log('PAGE ERRORS:\n  ' + [...new Set(pageErrors)].slice(0, 10).join('\n  '));
  if (o['--json']) writeFileSync(o['--json'], JSON.stringify({ url, thresholds: TH, frames: frames.length, rows, groups: groups.map((g) => ({ ...g, flags: [...g.flags] })), pageErrors }, null, 1));
  const fails = rows.filter((r) => r.flags.some((f) => f.startsWith('FAIL'))).length;
  console.log(fails ? `FAIL: ${fails} run-frames below the floors (contrast is judged on the worst pixel; fix the scrim, the plate or the size, or document an exception)`
    : 'PASS: every opaque text run meets the size floors and the worst-pixel contrast');
  process.exitCode = fails ? 2 : pageErrors.length ? 3 : 0;
} catch (e) {
  if (!e.quiet) { console.error('textcheck failed: ' + e.message); process.exitCode = 1; }
} finally {
  if (browser) await browser.close().catch(() => {});
  if (server) server.close();
}
