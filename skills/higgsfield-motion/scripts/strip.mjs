// Contact strip of review stills (or frames) → one PNG, rendered in headless Chrome/Brave via scripts/cdp.mjs. Node 22+.
// usage: node strip.mjs <stills_dir> <out.png> [title] [cols] [--fps N] [--step N]
//   Reads .png / .jpg / .jpeg. Names: still_<t>[_f<n>] (capture --stills), f_<n> (a frame index: t = n/fps), anything
//   else → the first number in the name is t. Sorted by t; captions read "<t> s · f<n>".
//   --fps N    frame rate for f_<n> and the f-numbers (default: <stills_dir>/_comp.json, else 24)
//   --step N   take every N-th image (a long frame folder is thinned automatically to stay under ~16 000 px)
//   cols       default: all in one row up to 12 images, else 8 per row
//   Cells take the first image's aspect (16:9, 9:16, 1:1 …), images are object-fit: contain. The temp page is removed.
import { readdirSync, readFileSync, writeFileSync, mkdtempSync, rmSync, statSync, openSync, readSync, closeSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { tmpdir } from 'node:os';
import { pathToFileURL } from 'node:url';
import { launch } from './cdp.mjs';

const argv = process.argv.slice(2);
const pos = [], o = {};
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === '--fps' || a === '--step') o[a] = argv[++i];
  else if (a.startsWith('--')) { console.error(`strip: unknown option ${a}`); process.exit(1); }
  else pos.push(a);
}
const [dir, out, title = '', colsArg] = pos;
if (!dir || !out) { console.error('usage: node strip.mjs <stills_dir> <out.png> [title] [cols] [--fps N] [--step N]'); process.exit(1); }

let fps = parseFloat(o['--fps']);
if (!(fps > 0)) { try { fps = JSON.parse(readFileSync(join(dir, '_comp.json'), 'utf8')).fps; } catch {} }
if (!(fps > 0)) fps = 24;

// t and frame index from the file name
const parse = (f) => {
  let m = /^f_(\d+)/.exec(f);
  if (m) { const n = +m[1]; return { t: n / fps, n }; }
  m = /^still_([\d.]+?)(?:_f(\d+))?\.(?:png|jpe?g)$/i.exec(f);
  if (m) { const t = parseFloat(m[1]); return { t, n: m[2] !== undefined ? +m[2] : Math.round(t * fps) }; }
  m = /\d+(?:\.\d+)?/.exec(f);
  const t = m ? parseFloat(m[0]) : 0;
  return { t, n: Math.round(t * fps) };
};
let ims = readdirSync(dir)
  .filter((f) => /\.(png|jpe?g)$/i.test(f) && !f.startsWith('.') && !f.startsWith('_') && statSync(join(dir, f)).isFile())
  .map((f) => ({ f, ...parse(f) }))
  .sort((a, b) => a.t - b.t || a.f.localeCompare(b.f));
if (!ims.length) { console.error(`strip: no .png/.jpg images in ${dir}`); process.exit(1); }
const step = Math.max(1, parseInt(o['--step'] || '1', 10));
if (step > 1) ims = ims.filter((_, i) => i % step === 0);

// pixel size of a PNG or JPEG from its header
function imageSize(file) {
  const fd = openSync(file, 'r'), buf = Buffer.alloc(256 * 1024);
  const len = readSync(fd, buf, 0, buf.length, 0); closeSync(fd);
  if (buf.readUInt32BE(0) === 0x89504e47) return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) };
  if (buf[0] === 0xff && buf[1] === 0xd8) {
    for (let i = 2; i + 9 < len;) {
      if (buf[i] !== 0xff) { i++; continue; }
      const mk = buf[i + 1];
      if (mk >= 0xc0 && mk <= 0xcf && mk !== 0xc4 && mk !== 0xc8 && mk !== 0xcc) return { w: buf.readUInt16BE(i + 7), h: buf.readUInt16BE(i + 5) };
      if (mk === 0xd8 || mk === 0x01 || (mk >= 0xd0 && mk <= 0xd7) || mk === 0xff) { i += mk === 0xff ? 1 : 2; continue; }
      i += 2 + buf.readUInt16BE(i + 2);
    }
  }
  return { w: 16, h: 9 };
}
const { w: iw, h: ih } = imageSize(join(dir, ims[0].f));
const cw = iw >= ih ? 480 : Math.round(480 * iw / ih), ch = iw >= ih ? Math.round(480 * ih / iw) : 480;
const gap = 12, pad = 28, lab = 30, top = title ? 64 : pad;
let cols = parseInt(colsArg || '0', 10) || (ims.length <= 12 ? ims.length : 8);
const rowsFor = (n) => Math.ceil(n / cols);
const height = (n) => top + pad + rowsFor(n) * (ch + lab + gap) - gap;
if (height(ims.length) > 16000) { // keep the page under Chromium's screenshot limit
  const maxRows = Math.floor((16000 - top - pad + gap) / (ch + lab + gap));
  const auto = Math.ceil(ims.length / (maxRows * cols));
  ims = ims.filter((_, i) => i % auto === 0);
  console.log(`strip: taking every ${auto}th image to stay under 16 000 px (choose with --step or cols)`);
}
cols = Math.min(cols, ims.length);
const Wd = pad * 2 + cols * cw + (cols - 1) * gap, Ht = height(ims.length);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const cells = ims.map(({ f, t, n }) => `<figure><img src="${pathToFileURL(resolve(dir, f)).href}"><figcaption>${t.toFixed(2)} s · f${n}</figcaption></figure>`).join('');
const html = `<!doctype html><html><head><meta charset="utf-8"><meta name="frame" content="${Wd}x${Ht}"><style>
body{margin:0;background:#0d0d0e;width:${Wd}px;height:${Ht}px;box-sizing:border-box;padding:${top}px ${pad}px ${pad}px;font:500 17px -apple-system,Helvetica,sans-serif;color:#8d8d90}
h1{position:absolute;left:${pad}px;top:18px;margin:0;font:600 22px -apple-system,Helvetica,sans-serif;color:#e6e6e6}
.g{display:grid;grid-template-columns:repeat(${cols},${cw}px);gap:${gap}px}figure{margin:0}
img{width:${cw}px;height:${ch}px;object-fit:contain;background:#000;display:block;border-radius:4px;outline:1px solid #262626}
figcaption{height:${lab}px;line-height:${lab}px;white-space:nowrap;overflow:hidden}
</style></head><body>${title ? `<h1>${esc(title)}</h1>` : ''}<div class="g">${cells}</div></body></html>`;

const tmp = mkdtempSync(join(tmpdir(), 'hft-strip-'));
let browser, code = 0;
try {
  const page = join(tmp, 'strip.html');
  writeFileSync(page, html);
  browser = await launch({ width: Wd, height: Ht });
  const p = await browser.newPage(pathToFileURL(page).href, { width: Wd, height: Ht });
  await p.waitReady();
  writeFileSync(resolve(out), await p.screenshot());
  const errs = p.errors();
  if (errs.length) console.error('strip: ' + errs.slice(0, 5).join('\n  '));
  console.log(`strip -> ${resolve(out)} (${ims.length} images, ${cols} per row, ${Wd}x${Ht}, ${fps} fps)`);
} catch (e) {
  console.error('strip failed: ' + e.message);
  code = 1;
} finally {
  if (browser) await browser.close();
  rmSync(tmp, { recursive: true, force: true });
}
process.exit(code);
