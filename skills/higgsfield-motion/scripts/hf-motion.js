/*! hf-motion.js v2 — deterministic, time-based motion helpers driven by the ACTIVE THEME.
 *
 *  Same API as shared/hf-motion.js v1 (HF.p, HF.tw, HF.kf, HF.E, HF.bezier, HF.clamp, HF.lerp, HF.fps, HF.f2s, HF.T),
 *  but every easing, duration, stagger and overshoot now comes from the theme's motion personality, so one
 *  choreography changes character per style: productive (Higgsfield) lands fast and soft, luxury-slow breathes,
 *  playful-bouncy overshoots, glitch-tech steps.
 *
 *  Browser:
 *    <script src="hf-tokens.js"></script>
 *    <script src="hf-motion.js"></script>                // picks ?style= / <html data-hft-style> / window.HF_THEME / 'higgsfield'
 *    <script> HF.use('luxury-serif', {scheme:'light'}) </script>
 *  Node:
 *    const HFT = require('./hf-tokens.js'); const HF = require('./hf-motion.js'); HF.use('playful-pop');
 *
 *  Time is always an argument (seconds) — never a requestAnimationFrame clock — so frames render identically
 *  in a browser, a headless capture (__seek) or Node.
 *
 *  Eases named by INTENT (the same in every theme; the theme's own E.enter / E.camera … still carry the personality):
 *    HF.E.push   (0.76, 0, 0.24, 1)    camera push / pull
 *    HF.E.follow (0.55, 0, 0.25, 1)    a camera that follows a moving object
 *    HF.E.drift  (0.37, 0, 0.63, 1)    soft drift
 *    HF.E.snap   (0.25, 0.1, 0, 1)     snap pull-back on a drop      (HF.snap(t) is the frame-grid quantiser, not an ease)
 *    HF.E.whip   (0.83, 0, 0.17, 1)    whip
 *    HF.E.suck   (0.62, 0, 0.92, 0.42) suck into a landing
 *  Never tween a fill between distant hues through RGB (magenta → lime passes salmon and mustard): crossfade two solid
 *  fills, or snap the colour under a pop.
 *
 *  Fail loudly: a style asked for explicitly (window.HF_THEME, ?style=, <html data-hft-style>) that does not resolve sets
 *  window.__hfError, logs console.error and throws — capture.mjs then exits non-zero instead of rendering the whole film
 *  in the wrong style. With no explicit style the default 'higgsfield' is used.
 */
(function (root, factory) {
  const HFT = (root && root.HFT) || (typeof require === 'function' ? (function () { try { return require('./hf-tokens.js'); } catch (e) { return null; } })() : null);
  const api = factory(HFT, root);
  if (typeof module === 'object' && module.exports) module.exports = api; // CommonJS: no global leak
  else if (root) root.HF = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (HFT, root) {
  'use strict';
  if (!HFT) throw new Error('hf-motion.js v2 needs hf-tokens.js (window.HFT) loaded first');

  /* ---- cubic-bezier solver (same maths as CSS) ---- */
  function bezier(x1, y1, x2, y2) {
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
    const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const sx = (t) => ((ax * t + bx) * t + cx) * t, sy = (t) => ((ay * t + by) * t + cy) * t;
    const dx = (t) => (3 * ax * t + 2 * bx) * t + cx;
    return (x) => {
      if (x <= 0) return 0; if (x >= 1) return 1;
      let t = x;
      for (let i = 0; i < 8; i++) { const e = sx(t) - x; if (Math.abs(e) < 1e-6) break; const d = dx(t); if (Math.abs(d) < 1e-6) break; t -= e / d; }
      let lo = 0, hi = 1; for (let i = 0; i < 20 && Math.abs(sx(t) - x) > 1e-6; i++) { if (sx(t) < x) lo = t; else hi = t; t = (lo + hi) / 2; }
      return sy(t);
    };
  }
  /** CSS steps(n, jump-start | jump-end) */
  function steps(n, position) {
    const start = position === 'start';
    // x ≤ 0 is "before the event": 0 for both positions, so nothing shows before t0
    return (x) => { if (x <= 0) return 0; if (x >= 1) return 1; return start ? Math.min(1, Math.ceil(x * n) / n) : Math.floor(x * n) / n; };
  }
  /** back-out whose peak overshoot equals `amount` (0.06 = 6 % past the target); 0 → the theme's enter */
  function backOut(amount) {
    if (!(amount > 0)) return null;
    const f = (s) => (x) => { const u = x - 1; return u * u * ((s + 1) * u + s) + 1; };
    const peak = (s) => { let m = 0; for (let i = 1; i < 200; i++) m = Math.max(m, f(s)(i / 200)); return m - 1; };
    let lo = 0, hi = 40; for (let i = 0; i < 50; i++) { const s = (lo + hi) / 2; if (peak(s) < amount) lo = s; else hi = s; }
    const g = f((lo + hi) / 2);
    return (x) => (x <= 0 ? 0 : x >= 1 ? 1 : g(x));
  }
  const fromToken = (tok) => (!tok ? null : tok.steps ? steps(tok.steps, tok.position) : tok.bezier ? bezier.apply(null, tok.bezier) : null);
  /* eases named by intent (theme-independent, re-added by every use()) */
  const INTENT = { push: [0.76, 0, 0.24, 1], follow: [0.55, 0, 0.25, 1], drift: [0.37, 0, 0.63, 1], snap: [0.25, 0.1, 0, 1], whip: [0.83, 0, 0.17, 1], suck: [0.62, 0, 0.92, 0.42] };
  const INTENT_E = {}; for (const k of Object.keys(INTENT)) INTENT_E[k] = bezier.apply(null, INTENT[k]);
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const lerp = (a, b, k) => a + (b - a) * k;

  /* ---- the HF object: stable references, mutated in place by use() ---- */
  const E = {};          // easing functions — consumers may keep `const E = HF.E`
  const D = {};          // durations in seconds (chip, ui, headline, hero, exit, camera, sweep, hit, textMin, endCard)
  const HF = { T: null, theme: null, E, D, dur: D, bezier, steps, backOut, clamp, lerp, fps: 24, os: 0, stagger: 0.125, staggerFrames: 3, bpm: 120, beat: 0.5, personality: null, HFT, INTENT_EASES: INTENT };

  function use(nameOrTheme, opts) {
    const th = nameOrTheme && nameOrTheme.tokens ? nameOrTheme : HFT.theme(nameOrTheme || 'higgsfield', opts);
    const t = th.tokens;
    for (const k of Object.keys(E)) delete E[k];
    for (const k of ['enter', 'exit', 'move', 'ui', 'expressive', 'camera', 'loop']) E[k] = fromToken(t['ease.' + k]);
    E.emphasis = E.expressive;
    E.linear = (x) => x;
    // overshoot has two scopes (core 3.11.2): ELEMENT (chips, pills, sparkles, stickers, small cards) = motion.overshoot (Higgsfield 0.06,
    // playful 0.12) through E.pop / E.overshoot / HF.pop; HERO (logo, headline, product name, hero media) = 0 — every other E.* stays in [0, 1]
    HF.os = t['motion.overshoot'] || 0;
    E.overshoot = backOut(HF.os) || E.enter;               // v1 name: back-out whose peak is exactly 1 + motion.overshoot
    E.pop = fromToken(t['ease.pop']) || E.overshoot;       // the theme's pop curve (CSS / AE twin of ease.pop)
    Object.assign(E, INTENT_E);                            // push / follow / drift / snap / whip / suck (same in every theme)
    for (const k of Object.keys(D)) delete D[k];
    for (const k of ['chip', 'ui', 'headline', 'hero', 'exit', 'camera', 'sweep', 'hit', 'textMin', 'endCard']) D[k] = t['dur.' + k].s;
    HF.fps = t['rhythm.fps'];
    HF.stagger = t['stagger'].s; HF.staggerFrames = t['stagger'].frames;
    HF.staggerLine2 = t['stagger.line2'].s; HF.staggerAccent = t['stagger.accent'].s; HF.followThrough = t['stagger.followThrough'].s;
    HF.bpm = t['rhythm.bpm']; HF.beat = 60 / HF.bpm; HF.framesPerBeat = t['rhythm.framesPerBeat'];
    HF.personality = th.meta.axes.motion; HF.cameraSpeed = t['motion.cameraSpeed'];
    HF.stepped = !!(t['ease.enter'] && t['ease.enter'].steps);
    HF.T = th; HF.theme = th;
    return HF;
  }

  /* ---- v1 API (unchanged signatures) ---- */
  const ease = (name) => (typeof name === 'function' ? name : E[name] || E.enter);
  /** eased progress of t inside [t0, t1] */
  const p = (t, t0, t1, e = 'enter') => ease(e)(clamp((t - t0) / Math.max(1e-6, t1 - t0)));
  /** value tween */
  const tw = (t, t0, t1, a, b, e = 'enter') => lerp(a, b, p(t, t0, t1, e));
  /** keyframes: [[t, v, easeIntoThisKey], …] (default ease 'move') */
  const kf = (t, keys) => {
    if (t <= keys[0][0]) return keys[0][1];
    for (let i = 1; i < keys.length; i++) {
      const [t1, v1, e] = keys[i], [t0, v0] = keys[i - 1];
      if (t <= t1) return lerp(v0, v1, p(t, t0, t1, e || 'move'));
    }
    return keys[keys.length - 1][1];
  };
  const f2s = (frames) => frames / HF.fps;

  /* ---- v2 helpers: choreography in theme units ---- */
  /** duration of a role in seconds: HF.d('hero') */
  const d = (role) => (typeof role === 'number' ? role : D[role] !== undefined ? D[role] : D.ui);
  /** progress of an entrance that starts at t0 and lasts dur(role) — the personality decides speed and curve */
  const enter = (t, t0, role = 'headline', e = 'enter') => p(t, t0, t0 + d(role), e);
  /** progress of an exit (always shorter than its entrance) */
  const exit = (t, t0, role = 'exit') => p(t, t0, t0 + d(role), 'exit');
  /** i-th member of a cascade: same direction, same easing, theme stagger */
  const cascade = (t, t0, i, role = 'headline', e = 'enter') => enter(t, t0 + i * HF.stagger, role, e);
  /** scale for a chip / pill / sparkle / sticker pop (core 3.13 "pop": 0.8 → 1); the peak is 1 + motion.overshoot of the theme
   *  (higgsfield 1.06, soft-pastel 1.03, y2k / kinetic 1.10, playful 1.12; swiss / luxury / cinematic / glitch 0 → a clean landing).
   *  ELEMENTS ONLY — never a logo, headline, product name or hero media (use HF.enter there: it never overshoots). */
  const _pops = new Map();
  const pop = (t, t0, from = 0.8, role = 'chip') => {
    const A = HF.os > 0 ? HF.os / Math.max(1e-6, 1 - from) : 0, key = HF.theme.meta.id + '|' + A;
    if (!_pops.has(key)) _pops.set(key, backOut(A) || E.enter);
    return lerp(from, 1, _pops.get(key)(clamp((t - t0) / Math.max(1e-6, d(role)))));
  };
  /** opacity + travel for a standard enter (du distance, e.g. 24 / 80 / 240) */
  const rise = (t, t0, distance = 24, role = 'headline') => { const k = enter(t, t0, role); return { opacity: k, y: (1 - k) * distance }; };
  /** quantise a time to the frame grid (glitch / stepped personalities read better on whole frames) */
  const snap = (t) => Math.floor(t * HF.fps + 1e-6) / HF.fps;
  /** beat n in seconds on the theme tempo (or a given bpm) */
  const beatAt = (n, bpm) => (n * 60) / (bpm || HF.bpm);
  const ms2f = (ms, opts) => HFT.ms2f(ms, HF.fps, opts);
  const timeline = (id, durationMs, bpm) => HFT.timeline(id, durationMs, HF.fps, bpm);

  Object.assign(HF, { use, p, tw, kf, f2s, d, enter, exit, cascade, pop, rise, snap, beatAt, ms2f, timeline, ease });

  /* ---- default theme ---- */
  let initial = 'higgsfield', initialOpts, source = null;   // source: where an EXPLICIT style request came from
  try {
    if (root && root.HF_THEME) { initial = root.HF_THEME.name || root.HF_THEME; initialOpts = root.HF_THEME.opts; source = 'window.HF_THEME'; }
    else if (root && root.location && root.location.search) {
      const q = {}; // tiny query parser (no URLSearchParams dependency)
      String(root.location.search).replace(/^\?/, '').split('&').forEach((kv) => { const i = kv.indexOf('='); if (i > 0) q[decodeURIComponent(kv.slice(0, i))] = decodeURIComponent(kv.slice(i + 1).replace(/\+/g, ' ')); });
      if (q.style) { initial = q.style; initialOpts = { scheme: q.scheme || undefined, format: q.format || undefined }; source = '?style='; }
    }
    if (root && root.document && root.document.documentElement && root.document.documentElement.dataset && root.document.documentElement.dataset.hftStyle) { initial = root.document.documentElement.dataset.hftStyle; source = '<html data-hft-style>'; }
  } catch (e) { /* no DOM / URL: keep the default */ }
  try { use(initial, initialOpts && Object.fromEntries(Object.entries(initialOpts).filter(([, v]) => v !== undefined))); }
  catch (e) {
    // an explicitly requested style that does not resolve is an ERROR, never a silent fallback: a zsh word-splitting bug
    // once passed three styles as one and 96 frames rendered in 'higgsfield' with exit code 0
    if (source) {
      const msg = 'hf-motion: style ' + JSON.stringify(initial) + ' from ' + source + ' does not resolve: ' + e.message;
      if (root) root.__hfError = msg;
      if (root && root.console) root.console.error(msg);
      throw new Error(msg);
    }
    use('higgsfield');
  }
  return HF;
});
