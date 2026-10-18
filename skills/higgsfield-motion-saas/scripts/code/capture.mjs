// Deterministic frame capture of a code-built film (DOM/CSS/SVG/Canvas/WebGL) through a headless Chromium + CDP.
// No npm dependencies (Node 22 has fetch + WebSocket built in).
//
// The page must expose (set them only after fonts/assets are loaded):
//   window.__comp = { width, height, fps, duration }        seconds
//   window.__seek = async (t) => { ...draw frame t... }     a PURE function of t (no rAF loops, no CSS transitions)
//   window.__errors = () => [...]                           optional: scene errors, printed as "SCENE ERRORS"
//
// usage:
//   node capture.mjs <page.html[?query]> <out_dir> [--stills 0.5,1.2] [--from s] [--to s] [--every n] [--jpg]
//                    [--sub n] [--shutter 0.5] [--subhi n --hiwin a-b,c-d] [--qa]
//   --stills          only these times → out_dir/still_<t>.png
//   --from/--to       time range (seconds); frames f_NNNNN use the GLOBAL frame number
//   --every n         take every n-th frame starting at --from (interleaved parallel workers: worker i uses --from i/fps --every N)
//   --sub n           sub-frame motion blur: n samples per frame spread over --shutter of a frame (0.5 = 180°) → f_NNNNN_k;
//                     average them with blend.py
//   --subhi/--hiwin   denser sampling inside fast windows (e.g. --sub 4 --subhi 10 --hiwin 1.8-3.2,9.3-10.4)
//   --qa              print window.__qa() (engine cut checks) and exit
//   --cues out.json   write window.__cues ({cuts, hard, cues}) + comp for the soundtrack (sound_kit.load_cues) and exit
//   hard cuts         sub-frames never cross a hard cut (a real shutter does not straddle an edit): the cut list comes from
//                     window.__cues.hard (engine.js fills it) or --cuts 1.6,3.0; --nocuts disables it
// env: HFT_BROWSER  browser binary (Chrome / Brave / Edge / Chromium / Yandex)
//      CAP_PORT     fixed DevTools port — REQUIRED when several captures run in parallel (random ports collide)
//      CAP_TMP      where the throw-away browser profile goes (default /tmp; it is deleted on exit)
import { spawn } from 'node:child_process';
import { existsSync, writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';

const BROWSER = process.env.HFT_BROWSER || [
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  '/Applications/Yandex.app/Contents/MacOS/Yandex',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
].find((p) => existsSync(p));
if (!BROWSER) { console.error('No Chromium-based browser found. Set HFT_BROWSER=/path/to/browser'); process.exit(1); }

const args = process.argv.slice(2);
const [pagePath, inlineQuery] = args[0].split('?');
const page = resolve(pagePath);
const outDir = resolve(args[1]);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const stills = opt('--stills', null);
const from = parseFloat(opt('--from', '0'));
const toArg = opt('--to', null);
const every = parseInt(opt('--every', '1'));
const jpg = args.includes('--jpg');
const SUB = parseInt(opt('--sub', '1'));
const SHUT = parseFloat(opt('--shutter', '0.5'));
const SUBHI = parseInt(opt('--subhi', '0'));
const HIWIN = (opt('--hiwin', '') || '').split(',').filter(Boolean).map((w) => w.split('-').map(Number));
const subAt = (t) => (SUBHI && HIWIN.some(([a, b]) => t >= a && t <= b) ? SUBHI : SUB);
const query = opt('--query', inlineQuery || '');
mkdirSync(outDir, { recursive: true });

const PORT = process.env.CAP_PORT ? parseInt(process.env.CAP_PORT) : 9400 + Math.floor(Math.random() * 500);
const PROFILE = `${process.env.CAP_TMP || '/tmp'}/cap-profile-${PORT}`;
const proc = spawn(BROWSER, [
  '--headless=new', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check',
  '--use-mock-keychain', '--password-store=basic', '--disable-extensions', '--disable-component-update',
  '--force-color-profile=srgb', '--ignore-gpu-blocklist', '--enable-webgl', '--use-angle=metal',
  '--enable-unsafe-swiftshader', '--allow-file-access-from-files', // file:// images would taint a canvas without it
  '--autoplay-policy=no-user-gesture-required',
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${PROFILE}`, 'about:blank',
], { stdio: 'ignore' });
const quit = (code) => { try { proc.kill(); } catch {} setTimeout(() => { try { rmSync(PROFILE, { recursive: true, force: true }); } catch {} process.exit(code); }, 400); };

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let wsUrl;
for (let i = 0; i < 80 && !wsUrl; i++) {
  try { const l = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); wsUrl = l.find((t) => t.type === 'page')?.webSocketDebuggerUrl; } catch {}
  if (!wsUrl) await sleep(250);
}
if (!wsUrl) { console.error('browser did not start on port', PORT); quit(1); }
const ws = new WebSocket(wsUrl);
await new Promise((r) => ws.addEventListener('open', r, { once: true }));
let id = 0; const pending = new Map(); const listeners = [];
ws.addEventListener('message', (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } else listeners.forEach((l) => l(m)); });
const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const evaluate = async (expr) => {
  const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 800));
  return r.result?.result?.value;
};
const consoleMsgs = [];
listeners.push((m) => {
  if (m.method === 'Runtime.consoleAPICalled') consoleMsgs.push(m.params.args.map((a) => a.value).join(' '));
  if (m.method === 'Runtime.exceptionThrown') consoleMsgs.push('EXC ' + JSON.stringify(m.params.exceptionDetails).slice(0, 400));
});

await send('Page.enable'); await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
const loaded = new Promise((r) => { const t = setTimeout(r, 20000); listeners.push((m) => { if (m.method === 'Page.loadEventFired') { clearTimeout(t); r(); } }); });
await send('Page.navigate', { url: 'file://' + page + (query ? '?' + query.replace(/^\?/, '') : '') });
await loaded;
let comp = null;
for (let i = 0; i < 120 && !comp; i++) { comp = await evaluate('window.__comp && window.__seek ? window.__comp : null').catch(() => null); if (!comp) await sleep(250); }
if (!comp) { console.error('page did not expose __comp/__seek. console:', consoleMsgs.slice(-10)); quit(1); }
await send('Emulation.setDeviceMetricsOverride', { width: comp.width, height: comp.height, deviceScaleFactor: 1, mobile: false });
console.log('comp:', JSON.stringify(comp));
await evaluate('document.fonts.ready.then(()=>true)');
if (opt('--cues', null)) {
  const c = await evaluate('window.__cues || {}'); writeFileSync(resolve(opt('--cues')), JSON.stringify({ comp, ...c }, null, 1));
  console.log('cues ->', opt('--cues')); ws.close(); quit(0);
} else if (args.includes('--qa')) {   // engine self-checks (zoom direction across cuts, …) — no frames written
  const q = await evaluate('window.__qa ? window.__qa() : ["page has no __qa()"]').catch((e) => [String(e)]);
  console.log(q.join('\n')); ws.close(); quit(0);
} else {

async function shot(t, file) {
  await evaluate(`(async()=>{await window.__seek(${t}); await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))); return true})()`);
  const s = await send('Page.captureScreenshot', { format: jpg ? 'jpeg' : 'png', quality: jpg ? 95 : undefined, clip: { x: 0, y: 0, width: comp.width, height: comp.height, scale: 1 }, captureBeyondViewport: false });
  writeFileSync(file, Buffer.from(s.result.data, 'base64'));
}

const t0 = Date.now();
const ext = jpg ? 'jpg' : 'png';
if (stills) {
  for (const t of stills.split(',').map(Number)) await shot(t, `${outDir}/still_${t.toFixed(2)}.png`);
  console.log(`stills: ${stills} -> ${outDir}`);
} else {
  const fps = comp.fps, dur = toArg ? parseFloat(toArg) : comp.duration;
  let CUTS = (opt('--cuts', '') || '').split(',').filter(Boolean).map(Number);
  if (!CUTS.length && !args.includes('--nocuts')) CUTS = (await evaluate('window.__cues && window.__cues.hard || []').catch(() => [])) || [];
  const side = (tc, ts) => { for (const c of CUTS) { if (tc >= c - 1e-6 && ts < c) return c + 1e-5; if (tc < c - 1e-6 && ts >= c) return c - 1e-4; } return ts; };
  const n0 = Math.round(from * fps), n1 = Math.round(dur * fps);
  for (let n = n0; n < n1; n += every) {
    const SB = subAt(n / fps), name = `${outDir}/f_${String(n).padStart(5, '0')}`;
    if (SB > 1) { for (let k = 0; k < SB; k++) await shot(side(n / fps, Math.max(0, (n + SHUT * ((k + 0.5) / SB - 0.5)) / fps)), `${name}_${k}.${ext}`); }
    else await shot(n / fps, `${name}.${ext}`);
    if ((n - n0) % (fps * 2 * every) < every) console.log(`frame ${n}/${n1} (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
  }
  console.log(`done frames ${n0}..${n1 - 1} step ${every} @${fps}fps -> ${outDir}`);
}
}
try { const er = await evaluate('window.__errors ? window.__errors() : []'); if (er && er.length) console.log('SCENE ERRORS:', er.join(' | ')); } catch {}
if (consoleMsgs.length) console.log('console:', consoleMsgs.slice(-8).join(' | '));
ws.close(); quit(0);
