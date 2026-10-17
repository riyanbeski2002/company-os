// render_audio.mjs — render a code-synthesised score (an OfflineAudioContext page, e.g. assets/templates/audio/score.html)
// to a WAV in a headless browser. Original sound, no samples, no IP: Higgsfield has no general music/SFX generator.
//
// usage: node scripts/render_audio.mjs <score.html[?k=v&…]> <out.wav> [--query "preset=pulse&bpm=128&dur=15"]
//                                      [--events film/events.js] [--timeout 300]
//   --query    score parameters (override window.SCORE_CONFIG in the page), e.g. preset, bpm, dur, drop, vac, lift, end,
//              key, seed, sfx, sfxLead — see the header of score.html.
//   --events   the film's ONE events file, injected before the page runs so picture and sound share the same timing:
//              *.js   must set window.FILM = { fps, bpm, dur, events: [{ f, k, w, note }] } (the picture page loads the same file);
//              *.json is the same object as JSON.
//   --timeout  seconds to wait for the render (default 300).
// The page contract: when done it sets window.__done = true, window.__wav (Uint8Array, a complete WAV file),
// window.__chunk(i, size) → base64 slice, window.__peak (raw peak before normalising) and optionally window.__map
// (a one-line structure caption: 'вдох 0–2 → удар 0:02 → …'); on failure window.__err.
// Output: the WAV as the page wrote it (score.html: 24-bit, 48 kHz, stereo, peak −1 dBFS). Then master it:
//   master out.wav mix.wav   (−14 LUFS, −1.2 dBTP) → encode_av frames 24 mix.wav film.mp4
// Exit codes: 0 ok · 1 usage / page error / timeout. Node 22+ (scripts/cdp.mjs).
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve, extname } from 'node:path';
import { pathToFileURL } from 'node:url';
import { launch } from './cdp.mjs';

const args = process.argv.slice(2);
const opt = (k, d = null) => { const i = args.indexOf(k); if (i < 0) return d; const v = args[i + 1]; args.splice(i, 2); return v; };
const queryArg = opt('--query', '');
const eventsArg = opt('--events');
const timeoutS = parseFloat(opt('--timeout', '300'));
const [pageArg, outWav] = args;
if (!pageArg || !outWav) {
  console.error('usage: node render_audio.mjs <score.html[?k=v&…]> <out.wav> [--query "preset=pulse&bpm=128"] [--events events.js] [--timeout 300]');
  process.exit(1);
}
const [pagePath, inlineQuery] = pageArg.split('?');
if (!existsSync(pagePath)) { console.error(`render_audio: no such page: ${pagePath}`); process.exit(1); }
const query = [inlineQuery, queryArg.replace(/^\?/, '')].filter(Boolean).join('&');
const url = pathToFileURL(resolve(pagePath)).href + (query ? '?' + query : '');

let inject = null;
if (eventsArg) {
  if (!existsSync(eventsArg)) { console.error(`render_audio: no such events file: ${eventsArg}`); process.exit(1); }
  const src = readFileSync(eventsArg, 'utf8');
  if (extname(eventsArg).toLowerCase() === '.json') {
    try { JSON.parse(src); } catch (e) { console.error(`render_audio: ${eventsArg} is not valid JSON: ${e.message}`); process.exit(1); }
    inject = `window.FILM = Object.assign(window.FILM || {}, ${src});`;
  } else {
    inject = `${src}\n;if (!window.FILM) console.error('events file did not set window.FILM');`;
  }
}

const t0 = Date.now();
const browser = await launch({ width: 800, height: 600 });
let code = 0;
try {
  const page = await browser.newPage();
  if (inject) await page.send('Page.addScriptToEvaluateOnNewDocument', { source: inject });
  await page.goto(url);
  let st = '';
  for (;;) {
    const errs = page.errors().filter((e) => !/favicon/.test(e));
    if (errs.length) { st = 'page error: ' + errs.slice(0, 4).join(' | '); break; }
    st = await page.evaluate('window.__err ? "ERR: " + window.__err : (window.__done ? "done" : "")', { timeoutMs: 20000 }).catch((e) => 'ERR: ' + e.message);
    if (st) break;
    if (Date.now() - t0 > timeoutS * 1000) { st = `timeout after ${timeoutS} s (window.__done never set)`; break; }
    await new Promise((r) => setTimeout(r, 250));
  }
  if (st !== 'done') throw new Error(st.split('\n')[0]);
  const len = await page.evaluate('window.__wav.length');
  const size = 1 << 20, parts = [];
  for (let i = 0; i * size < len; i++) parts.push(Buffer.from(await page.evaluate(`window.__chunk(${i}, ${size})`), 'base64'));
  const wav = Buffer.concat(parts);
  if (wav.length !== len || wav.toString('ascii', 0, 4) !== 'RIFF') throw new Error(`bad WAV from the page (${wav.length} of ${len} bytes)`);
  writeFileSync(outWav, wav);
  const info = await page.evaluate('({ peak: window.__peak, map: window.__map || "", sr: window.__sr || 0, ch: window.__ch || 0, bits: window.__bits || 0, dur: window.__dur || 0 })');
  const peakDb = info.peak > 0 ? (20 * Math.log10(info.peak)).toFixed(1) : '?';
  console.log(`wrote ${outWav} · ${info.dur ? info.dur.toFixed(3) + ' s · ' : ''}${info.sr ? info.sr + ' Hz · ' : ''}${info.ch ? info.ch + ' ch · ' : ''}${info.bits ? info.bits + '-bit · ' : ''}raw peak ${peakDb} dBFS (normalised) · ${((Date.now() - t0) / 1000).toFixed(1)} s`);
  if (info.map) console.log(`map: ${info.map}`);
} catch (e) {
  console.error(`render_audio: ${e.message}`);
  code = 1;
} finally {
  await browser.close();
}
process.exit(code);
