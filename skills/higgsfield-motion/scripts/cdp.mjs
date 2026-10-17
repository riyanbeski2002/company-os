// cdp.mjs — shared headless-browser plumbing for capture.mjs, render.mjs and strip.mjs: raw Chrome DevTools Protocol,
// no npm dependencies, Node 22+ (built-in WebSocket).
//
//   import { launch, findBrowser, serveStatic } from './cdp.mjs';
//   const browser = await launch({ width: 1920, height: 1080 });          // { newPage, close }
//   const page = await browser.newPage('file:///…/index.html', { width: 1920, height: 1080, dpr: 1 });
//   await page.waitReady();                 // every FontFace loaded, fonts.ready, window.__ready, pending <img> decoded
//   await page.seek(1.25);                  // window.__seek(t), then fonts.ready + decode() of changed <img> + 2 rAF
//   writeFileSync('f.png', await page.screenshot());          // { format: 'png' | 'jpeg', quality, clip } → Buffer
//   console.log(page.errors());             // exceptions, console errors, failed requests, HTTP ≥ 400, fallback warnings
//   await browser.close();
//
// Page = { send(method, params), evaluate(expr, { awaitPromise = true, timeoutMs }), waitReady({ timeoutMs }),
//          seek(t, { mbBase, mbDT, timeoutMs }), screenshot({ format, quality, clip }), errors(), close(),
//          goto(url), waitFor(expr), setViewport({ width, height, dpr }), on(event, fn), width, height }
//
// Browser: HFT_BROWSER, else Chrome / Brave / Chromium / Edge in /Applications (or ~/Applications), else Linux paths.
// Launch is collision-free: --remote-debugging-port=0 and the ws:// URL parsed from stderr, so parallel runs never share
// a port. Each launch gets a throwaway mkdtemp profile that is deleted on close(), exit, SIGINT/SIGTERM/SIGHUP or an
// uncaught throw (the old fixed /tmp/brave-cap-<port> profiles were never deleted: `rm -rf /tmp/brave-cap-* /tmp/brave-render-*`).
// Flags: WebGL on (ANGLE/Metal on macOS, SwiftShader fallback), sRGB colour profile, --allow-file-access-from-files
// (file:// pages may read local images into WebGL textures and canvases), no background throttling (parallel tabs).
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync, readdirSync, statSync, createReadStream } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir, homedir, platform } from 'node:os';
import { join, resolve, sep, extname } from 'node:path';

if (typeof globalThis.WebSocket !== 'function') {
  console.error(`higgsfield-motion scripts need Node 22 or newer (they use the built-in WebSocket); this is Node ${process.version}.\n` +
    'Install Node 22 LTS (or newer) and run again.');
  process.exit(1);
}

const MAC_APPS = [
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
];
const LINUX_BINS = [
  '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser',
  '/snap/bin/chromium', '/usr/bin/brave-browser', '/usr/bin/microsoft-edge',
];

/** Path of a Chromium-based browser: HFT_BROWSER, then /Applications, then ~/Applications, then Linux paths. Throws if none. */
export function findBrowser() {
  const env = process.env.HFT_BROWSER;
  if (env) {
    if (!existsSync(env)) throw new Error(`HFT_BROWSER=${env} does not exist`);
    return env;
  }
  const list = [...MAC_APPS, ...MAC_APPS.map((p) => join(homedir(), p)), ...LINUX_BINS];
  const found = list.find((p) => existsSync(p));
  if (!found) throw new Error('No Chromium-based browser found (Chrome, Brave, Chromium or Edge). Set HFT_BROWSER=/path/to/browser');
  return found;
}

const BASE_FLAGS = [
  '--hide-scrollbars', '--no-first-run', '--no-default-browser-check', '--use-mock-keychain', '--password-store=basic',
  '--disable-extensions', '--disable-component-update', '--disable-sync', '--disable-default-apps', '--mute-audio',
  '--force-color-profile=srgb', '--ignore-gpu-blocklist', '--enable-webgl', '--enable-unsafe-swiftshader',
  '--autoplay-policy=no-user-gesture-required', '--allow-file-access-from-files',
  '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding',
  ...(platform() === 'darwin' ? ['--use-angle=metal'] : []),
];

// ---------------------------------------------------------------- cleanup registry (one set of process hooks for all launches)
const live = new Set();
let hooked = false;
function killAll() {
  for (const b of live) {
    try { b.proc.kill('SIGKILL'); } catch {}
    try { rmSync(b.profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 50 }); } catch {}
  }
  live.clear();
}
function hook() {
  if (hooked) return;
  hooked = true;
  process.on('exit', killAll); // also runs after an uncaught exception or unhandled rejection
  for (const [sig, code] of [['SIGINT', 130], ['SIGTERM', 143], ['SIGHUP', 129]]) {
    process.on(sig, () => { console.error(`\n${sig}: closing the browser and removing its profile`); process.exit(code); });
  }
}
let staleNoted = false;
function noteStaleProfiles() {
  if (staleNoted) return;
  staleNoted = true;
  try {
    const n = readdirSync('/tmp').filter((d) => /^(brave-cap|brave-render|lf-cap)-\d+$/.test(d)).length;
    if (n >= 20) console.error(`note: ${n} stale browser profiles from older capture runs in /tmp (they can take GBs): rm -rf /tmp/brave-cap-* /tmp/brave-render-* /tmp/lf-cap-*`);
  } catch {}
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const withTimeout = (p, ms, what) => {
  if (!ms) return p;
  let t;
  return Promise.race([p, new Promise((_, rej) => { t = setTimeout(() => rej(new Error(`${what} timed out after ${(ms / 1000).toFixed(1)} s`)), ms); })])
    .finally(() => clearTimeout(t));
};
const FALLBACK_RE = /fall(?:ing)?[\s-]*back/i;
const IGNORE_URL_RE = /\/favicon\.ico(\?|$)/;

/**
 * Launch a headless browser.
 * @returns {Promise<{ newPage(url?: string, opts?: { width?: number, height?: number, dpr?: number, loadTimeoutMs?: number }): Promise<Page>, close(): Promise<void>, send(method: string, params?: object): Promise<any>, bin: string, profile: string }>}
 */
export async function launch({ width = 1920, height = 1080, dpr = 1, headless = true, flags = [] } = {}) {
  const bin = findBrowser();
  hook();
  noteStaleProfiles();
  const profile = mkdtempSync(join(tmpdir(), 'hft-cdp-'));
  const argv = [
    ...(headless ? ['--headless=new'] : []), ...BASE_FLAGS, ...flags,
    '--remote-debugging-port=0', `--user-data-dir=${profile}`, `--window-size=${width},${height}`, 'about:blank',
  ];
  const proc = spawn(bin, argv, { stdio: ['ignore', 'ignore', 'pipe'] });
  const rec = { proc, profile };
  live.add(rec);

  let stderrTail = '';
  let exited = false;
  const exitP = new Promise((r) => proc.once('exit', (code, sig) => { exited = true; r({ code, sig }); }));
  const wsUrl = await new Promise((res, rej) => {
    const to = setTimeout(() => rej(new Error(`browser did not start within 30 s (${bin})\n${stderrTail.slice(-800)}`)), 30000);
    proc.stderr.on('data', (d) => {
      stderrTail = (stderrTail + d).slice(-4000);
      const m = stderrTail.match(/DevTools listening on (ws:\/\/\S+)/);
      if (m) { clearTimeout(to); res(m[1]); }
    });
    proc.once('error', (e) => { clearTimeout(to); rej(new Error(`could not start ${bin}: ${e.message}`)); });
    exitP.then(({ code, sig }) => { clearTimeout(to); rej(new Error(`browser exited during start (code ${code}, signal ${sig})\n${stderrTail.slice(-800)}`)); });
  }).catch((e) => { killRec(); throw e; });

  function killRec() {
    try { proc.kill('SIGKILL'); } catch {}
    try { rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 50 }); } catch {}
    live.delete(rec);
  }

  const ws = new WebSocket(wsUrl);
  await new Promise((res, rej) => {
    ws.addEventListener('open', res, { once: true });
    ws.addEventListener('error', () => rej(new Error('could not connect to the browser DevTools socket')), { once: true });
  }).catch((e) => { killRec(); throw e; });

  let nextId = 0;
  let closed = false;
  const pending = new Map();
  const sessions = new Map(); // sessionId → (msg) => void
  ws.addEventListener('message', (ev) => {
    let m;
    try { m = JSON.parse(typeof ev.data === 'string' ? ev.data : Buffer.from(ev.data).toString('utf8')); } catch { return; }
    if (m.id !== undefined && pending.has(m.id)) {
      const p = pending.get(m.id);
      pending.delete(m.id);
      if (m.error) p.rej(new Error(`${p.method}: ${m.error.message}${m.error.data ? ' (' + m.error.data + ')' : ''}`));
      else p.res(m.result || {});
    } else if (m.sessionId && sessions.has(m.sessionId)) {
      sessions.get(m.sessionId)(m);
    }
  });
  ws.addEventListener('close', () => {
    closed = true;
    for (const p of pending.values()) p.rej(new Error(`${p.method}: browser connection closed`));
    pending.clear();
  });

  const send = (method, params = {}, sessionId) => new Promise((res, rej) => {
    if (closed) return rej(new Error(`${method}: browser connection closed`));
    const id = ++nextId;
    pending.set(id, { res, rej, method });
    const msg = { id, method, params };
    if (sessionId) msg.sessionId = sessionId;
    ws.send(JSON.stringify(msg));
  });

  const pages = new Set();

  async function newPage(url = 'about:blank', { width: w = width, height: h = height, dpr: d = dpr, loadTimeoutMs = 60000 } = {}) {
    const { targetId } = await send('Target.createTarget', { url: 'about:blank', newWindow: true });
    const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
    const handlers = new Map(); // method → Set<fn>
    const errs = [];
    const reqUrls = new Map();
    const view = { width: w, height: h, dpr: d };
    let pageClosed = false;
    const emit = (m) => { const set = handlers.get(m.method); if (set) for (const fn of [...set]) fn(m.params || {}); };
    sessions.set(sessionId, emit);

    const on = (method, fn) => {
      if (!handlers.has(method)) handlers.set(method, new Set());
      handlers.get(method).add(fn);
      return () => handlers.get(method).delete(fn);
    };
    const waitEvent = (method, timeoutMs = 30000, pred = () => true) => new Promise((res, rej) => {
      const off = on(method, (p) => { if (pred(p)) { clearTimeout(t); off(); res(p); } });
      const t = setTimeout(() => { off(); rej(new Error(`${method} not received within ${(timeoutMs / 1000).toFixed(0)} s`)); }, timeoutMs);
    });
    const psend = (method, params = {}) => send(method, params, sessionId);
    const argText = (a) => (a.value !== undefined ? (typeof a.value === 'string' ? a.value : JSON.stringify(a.value)) : a.description ?? a.unserializableValue ?? a.type);

    // ---- error collection
    on('Runtime.exceptionThrown', (p) => {
      const e = p.exceptionDetails || {};
      const where = e.url ? ` (${e.url.split('/').pop()}:${(e.lineNumber ?? 0) + 1})` : '';
      errs.push(`exception: ${(e.exception?.description || e.text || 'unknown').split('\n')[0]}${where}`);
    });
    on('Runtime.consoleAPICalled', (p) => {
      const text = (p.args || []).map(argText).join(' ');
      if (p.type === 'error' || p.type === 'assert') errs.push(`console.${p.type}: ${text.slice(0, 500)}`);
      else if ((p.type === 'warning' || p.type === 'warn') && FALLBACK_RE.test(text)) errs.push(`fallback warning: ${text.slice(0, 500)}`);
    });
    on('Log.entryAdded', (p) => {
      const e = p.entry || {};
      if (e.level === 'error' && e.source !== 'network' && e.source !== 'javascript' && e.source !== 'console-api') errs.push(`${e.source || 'log'}: ${(e.text || '').slice(0, 500)}`);
    });
    on('Network.requestWillBeSent', (p) => { reqUrls.set(p.requestId, p.request?.url || ''); });
    on('Network.loadingFinished', (p) => { reqUrls.delete(p.requestId); });
    on('Network.responseReceived', (p) => {
      const r = p.response || {};
      if (r.status >= 400 && !IGNORE_URL_RE.test(r.url)) errs.push(`HTTP ${r.status} ${r.url}`);
    });
    on('Network.loadingFailed', (p) => {
      const u = reqUrls.get(p.requestId) || '';
      reqUrls.delete(p.requestId);
      if (p.canceled || IGNORE_URL_RE.test(u)) return;
      errs.push(`request failed: ${u || p.requestId} (${p.errorText}${p.blockedReason ? ', ' + p.blockedReason : ''})`);
    });
    on('Inspector.targetCrashed', () => { errs.push('renderer crashed'); });

    await psend('Page.enable');
    await psend('Runtime.enable');
    await psend('Network.enable', { maxTotalBufferSize: 0, maxResourceBufferSize: 0 }).catch(() => psend('Network.enable'));
    await psend('Log.enable');
    await psend('Inspector.enable').catch(() => {});
    await psend('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: d, mobile: false });
    await psend('Emulation.setFocusEmulationEnabled', { enabled: true }).catch(() => {});
    await psend('Page.setWebLifecycleState', { state: 'active' }).catch(() => {});

    const evaluate = async (expr, { awaitPromise = true, timeoutMs = 0 } = {}) => {
      const r = await withTimeout(psend('Runtime.evaluate', { expression: expr, awaitPromise, returnByValue: true, userGesture: true }), timeoutMs, 'evaluate');
      if (r.exceptionDetails) {
        const e = r.exceptionDetails;
        throw new Error((e.exception?.description || e.text || 'evaluation failed').split('\n').slice(0, 3).join(' | '));
      }
      return r.result?.value;
    };

    const page = {
      targetId, sessionId,
      get width() { return view.width; },
      get height() { return view.height; },
      get dpr() { return view.dpr; },
      send: psend,
      on,
      waitEvent,
      evaluate,
      errors: () => errs.slice(),
      clearErrors: () => { errs.length = 0; },
      async setViewport({ width: nw = view.width, height: nh = view.height, dpr: nd = view.dpr } = {}) {
        Object.assign(view, { width: nw, height: nh, dpr: nd });
        await psend('Emulation.setDeviceMetricsOverride', { width: nw, height: nh, deviceScaleFactor: nd, mobile: false });
      },
      async goto(u, { timeoutMs = loadTimeoutMs } = {}) {
        const loaded = waitEvent('Page.loadEventFired', timeoutMs).then(() => true, () => false);
        const nav = await psend('Page.navigate', { url: u });
        if (nav.errorText) throw new Error(`could not open ${u}: ${nav.errorText}`);
        if (!(await loaded)) errs.push(`load event did not fire within ${(timeoutMs / 1000).toFixed(0)} s (${u})`);
      },
      async reload({ timeoutMs = loadTimeoutMs } = {}) {
        const loaded = waitEvent('Page.loadEventFired', timeoutMs).then(() => true, () => false);
        await psend('Page.reload', { ignoreCache: false });
        if (!(await loaded)) errs.push(`load event did not fire within ${(timeoutMs / 1000).toFixed(0)} s (reload)`);
      },
      /** Poll `expr` until it is truthy; returns its value, or null on timeout. */
      async waitFor(expr, { timeoutMs = 30000, intervalMs = 100 } = {}) {
        const t0 = Date.now();
        for (;;) {
          const v = await evaluate(expr, { timeoutMs: 10000 }).catch(() => null);
          if (v) return v;
          if (Date.now() - t0 > timeoutMs) return null;
          await sleep(intervalMs);
        }
      },
      /** Load every declared FontFace, await fonts.ready and window.__ready (a promise, or false → poll until truthy),
       *  load faces added meanwhile, decode pending <img>, then two rAFs. Font faces that fail are recorded as errors. */
      async waitReady({ timeoutMs = 60000 } = {}) {
        const r = await evaluate(`(async () => {
          const deadline = performance.now() + ${Math.max(1000, timeoutMs - 2000)};
          const bad = new Set();
          const preload = async () => {
            const faces = []; document.fonts.forEach((f) => faces.push(f));
            await Promise.all(faces.map((f) => (f.status === 'loaded' ? 0 : f.load().catch(() => bad.add(f.family + ' ' + f.weight + ' ' + f.style)))));
            await document.fonts.ready;
          };
          await preload();
          while (window.__ready === false && performance.now() < deadline) await new Promise((r) => setTimeout(r, 50));
          if (window.__ready === false) return { ready: false, failed: [...bad] };
          const rd = window.__ready;
          if (rd && typeof rd.then === 'function') await rd;
          await preload();
          const pend = [];
          for (const im of document.images) {
            const src = im.currentSrc || im.src;
            if (src && im.loading !== 'lazy' && (!im.complete || im.__hftSrc !== src)) pend.push(im.decode().then(() => { im.__hftSrc = src; }, () => { im.__hftSrc = src; }));
          }
          await Promise.all(pend);
          await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
          return { ready: true, failed: [...bad], faces: document.fonts.size };
        })()`, { timeoutMs });
        for (const f of r?.failed || []) errs.push(`font failed to load: ${f}`);
        if (!r?.ready) throw new Error('window.__ready stayed false');
        return r;
      },
      /** window.__seek(t) (with window.__mbBase / __mbDT set first when given), then fonts.ready, decode() of every <img>
       *  whose source changed, and two rAFs. Throws (with t in the message) when __seek throws or hangs. */
      async seek(t, { mbBase, mbDT, timeoutMs = 30000 } = {}) {
        if (!Number.isFinite(t)) throw new Error(`seek: bad time ${t}`);
        const mb = mbBase !== undefined ? `window.__mbBase = ${+mbBase}; window.__mbDT = ${+(mbDT ?? 0)};` : '';
        try {
          return await evaluate(`(async () => {
            ${mb}
            if (typeof window.__seek !== 'function') throw new Error('window.__seek is not defined');
            await window.__seek(${t});
            if (document.fonts.status !== 'loaded') await document.fonts.ready;
            const pend = [];
            for (const im of document.images) {
              const src = im.currentSrc || im.src;
              if (src && im.loading !== 'lazy' && (!im.complete || im.__hftSrc !== src)) pend.push(im.decode().then(() => { im.__hftSrc = src; }, () => { im.__hftSrc = src; }));
            }
            if (pend.length) await Promise.all(pend);
            await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
            return true;
          })()`, { timeoutMs });
        } catch (e) {
          throw new Error(`seek(${t}) failed: ${e.message}`);
        }
      },
      /** PNG or JPEG of the viewport (or `clip`, in CSS px) → Buffer. */
      async screenshot({ format = 'png', quality, clip } = {}) {
        const fmt = format === 'jpg' ? 'jpeg' : format;
        const c = { x: 0, y: 0, width: view.width, height: view.height, scale: 1, ...(clip || {}) };
        const r = await psend('Page.captureScreenshot', {
          format: fmt, ...(fmt === 'jpeg' || fmt === 'webp' ? { quality: quality ?? 95 } : {}), clip: c, captureBeyondViewport: false, fromSurface: true,
        });
        return Buffer.from(r.data, 'base64');
      },
      async close() {
        if (pageClosed) return;
        pageClosed = true;
        pages.delete(page);
        await send('Target.closeTarget', { targetId }).catch(() => {});
        sessions.delete(sessionId);
      },
    };
    pages.add(page);
    if (url && url !== 'about:blank') await page.goto(url);
    return page;
  }

  async function close() {
    if (!live.has(rec)) return;
    for (const p of [...pages]) await p.close().catch(() => {});
    if (!closed) await withTimeout(send('Browser.close'), 2000, 'Browser.close').catch(() => {});
    try { ws.close(); } catch {}
    if (!exited) await Promise.race([exitP, sleep(3000)]);
    killRec();
  }

  return { bin, profile, wsUrl, get connected() { return !closed; }, send: (m, p) => send(m, p), newPage, close };
}

// ---------------------------------------------------------------- zero-dependency static server on 127.0.0.1
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.htm': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
  '.gif': 'image/gif', '.avif': 'image/avif', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.otf': 'font/otf',
  '.mp4': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime', '.wav': 'audio/wav', '.mp3': 'audio/mpeg',
  '.m4a': 'audio/mp4', '.aac': 'audio/aac', '.txt': 'text/plain; charset=utf-8', '.glsl': 'text/plain; charset=utf-8',
};

/** Serve `root` on 127.0.0.1 (random port, loopback only, no CORS headers, nothing outside root). http:// pages get
 *  ES modules, CSS masks and canvas/WebGL pixel readback that file:// blocks. Honours Range requests (audio/video
 *  seeking). → Promise<{ url, root, close() }> */
export function serveStatic(root = process.cwd(), { port = 0 } = {}) {
  const base = resolve(root);
  const server = createServer((req, res) => {
    let file;
    try { file = resolve(join(base, decodeURIComponent(new URL(req.url, 'http://x').pathname))); } catch { res.writeHead(400); return res.end('bad url'); }
    if (file !== base && !file.startsWith(base + sep)) { res.writeHead(403); return res.end('outside root'); }
    let st;
    try { st = statSync(file); if (st.isDirectory()) { file = join(file, 'index.html'); st = statSync(file); } } catch { res.writeHead(404); return res.end('not found'); }
    const headers = {
      'content-type': TYPES[extname(file).toLowerCase()] || 'application/octet-stream',
      'accept-ranges': 'bytes', 'cache-control': 'no-store', 'x-content-type-options': 'nosniff',
    };
    const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || '');
    if (range && (range[1] || range[2])) {
      let a = range[1] ? +range[1] : Math.max(0, st.size - +range[2]);
      let b = range[1] && range[2] ? Math.min(+range[2], st.size - 1) : st.size - 1;
      if (a > b || a >= st.size) { res.writeHead(416, { 'content-range': `bytes */${st.size}` }); return res.end(); }
      res.writeHead(206, { ...headers, 'content-range': `bytes ${a}-${b}/${st.size}`, 'content-length': b - a + 1 });
      if (req.method === 'HEAD') return res.end();
      return createReadStream(file, { start: a, end: b }).pipe(res);
    }
    res.writeHead(200, { ...headers, 'content-length': st.size });
    if (req.method === 'HEAD') return res.end();
    createReadStream(file).pipe(res);
  });
  return new Promise((ok, fail) => {
    server.once('error', fail);
    server.listen(port, '127.0.0.1', () => ok({ url: `http://127.0.0.1:${server.address().port}`, root: base, close: () => server.close() }));
  });
}

/** Frame size declared by <meta name="frame" content="1920x1080"> in an HTML string, or null. */
export function metaFrame(html) {
  const m = /<meta\s+[^>]*name=["']frame["'][^>]*>/i.exec(html || '');
  if (!m) return null;
  const c = /content=["']\s*(\d+)\s*[x×]\s*(\d+)\s*["']/i.exec(m[0]);
  return c ? { width: +c[1], height: +c[2] } : null;
}
