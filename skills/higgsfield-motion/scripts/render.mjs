// Render HTML files to PNG via headless Chrome/Brave (HFT_BROWSER overrides) + raw CDP (scripts/cdp.mjs). Node 22+, no npm deps.
// usage: node render.mjs <out_dir> <file1.html> [file2.html ...] [--size WxH] [--serve [root]] [--strict] [--timeout s]
// Frame size is read from <meta name="frame" content="1920x1080"> (default 1920x1080; --size overrides) and set before
// the page loads. Same browser flags as capture.mjs (WebGL on, --allow-file-access-from-files). Before each shot it waits
// for every FontFace, document.fonts.ready, window.__ready (if the page sets it) and pending <img> decodes — no fixed sleep.
// A page that is only correct at a time t (exposes window.__seek) belongs to `capture.mjs --stills t`.
// Page errors (exceptions, console errors, failed requests, HTTP ≥ 400) are printed; --strict turns them into exit 3.
// Exit 1 when a file could not be rendered at all.
//   --serve [root]   load pages over http://127.0.0.1 from root (default: cwd) — ES modules, masks, canvas readback.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { basename, resolve, relative, isAbsolute, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { launch, serveStatic, metaFrame } from './cdp.mjs';

const argv = process.argv.slice(2);
const pos = [], o = {};
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === '--size' || a === '--timeout') o[a] = argv[++i];
  else if (a === '--serve') { const nx = argv[i + 1]; if (nx !== undefined && !nx.startsWith('--') && !/\.html?$/i.test(nx)) { o[a] = nx; i++; } else o[a] = ''; }
  else if (a === '--strict') o[a] = true;
  else if (a.startsWith('--')) { console.error(`render: unknown option ${a}`); process.exit(1); }
  else pos.push(a);
}
const [outDir, ...files] = pos;
if (!outDir || !files.length) {
  console.error('usage: node render.mjs <out_dir> <file1.html> [file2.html ...] [--size WxH] [--serve [root]] [--strict] [--timeout s]');
  process.exit(1);
}
let forced = null;
if (o['--size']) { const m = /^(\d+)[x×](\d+)$/.exec(o['--size']); if (!m) { console.error('render: --size must look like 1920x1080'); process.exit(1); } forced = { width: +m[1], height: +m[2] }; }
const TIMEOUT = Math.max(5, parseFloat(o['--timeout'] || '60')) * 1000;
mkdirSync(outDir, { recursive: true });

let server = null, browser = null, exitCode = 0;
const allErrs = [];
const failed = []; // files that produced no PNG → exit 1
try {
  if (o['--serve'] !== undefined) server = await serveStatic(resolve(o['--serve'] || process.cwd()));
  browser = await launch();
  for (const f of files) {
    const path = resolve(f);
    if (!existsSync(path)) { failed.push(`${f}: file not found`); continue; }
    const { width: w, height: h } = forced || metaFrame(readFileSync(path, 'utf8')) || { width: 1920, height: 1080 };
    let url = pathToFileURL(path).href;
    if (server) {
      const rel = relative(server.root, path);
      if (rel.startsWith('..') || isAbsolute(rel)) { failed.push(`${f}: outside the --serve root ${server.root}`); continue; }
      url = `${server.url}/${rel.split(sep).map(encodeURIComponent).join('/')}`;
    }
    let page = null;
    try {
      page = await browser.newPage(url, { width: w, height: h, loadTimeoutMs: TIMEOUT });
      await page.waitReady({ timeoutMs: TIMEOUT });
      const out = `${outDir}/${basename(f).replace(/\.html?$/i, '')}.png`;
      writeFileSync(out, await page.screenshot({ format: 'png' }));
      console.log('wrote', out, `${w}x${h}`);
    } catch (e) {
      failed.push(`${f}: ${e.message.split('\n')[0]}`);
    }
    if (page) { for (const e of page.errors()) allErrs.push(`${basename(f)}: ${e}`); await page.close(); }
  }
} catch (e) {
  console.error('render failed: ' + e.message);
  exitCode = 1;
}
if (failed.length) { console.error('NOT RENDERED:\n  ' + failed.join('\n  ')); if (!exitCode) exitCode = 1; }
if (allErrs.length) {
  console.error(`PAGE ERRORS (${allErrs.length}):\n  ` + [...new Set(allErrs)].slice(0, 25).join('\n  '));
  if (!exitCode && o['--strict']) exitCode = 3;
}
if (browser) await browser.close();
if (server) server.close();
process.exit(exitCode);
