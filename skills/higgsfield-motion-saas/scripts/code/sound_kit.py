"""sound_kit — a launch-film soundtrack synthesized in code (numpy + stdlib only: no samples, no scipy, no downloads).
Distilled from the BLIP. and LO. soundtracks (Oct 2026). The cuts ARE the rhythm: every cut gets a hit, risers END on
the cut, small UI sounds sit on the exact frames where the picture clicks, types, pops or lands.

    import sys; sys.path.insert(0, '<skill>/scripts/code'); import sound_kit as S
    S.init(15.0, seed=7)
    S.add_end(S.riser2(.5), 2.5, .55, hall=.12)          # riser that ends exactly on the cut
    S.hit(2.5, 1.2, 1.0, chord=[62, 65, 69, 74], clap_g=.3, cym=.1)
    S.add(S.mclick(), 4.2, .4, pan=.2, room=.2)           # cursor click on the click frame
    S.decode(6.0, .4)                                     # data-bit chatter while text decodes
    S.master('film/sound.wav', fade_from=14.6)            # → sound.wav + sound.m4a (afconvert)
    S.verify([('hit', 2.5, 'lf'), ('click', 4.2, 'hf')])  # onset error per cue, should be within ±5 ms
Then: scripts/code/bin/mux film/film.mp4 film/sound.m4a film/final.mp4
Buses: 'drum' (dry, not ducked) · 'mus' (ducked by kicks/hits) · 'duckfx' (ducked sfx) · 'sfx' (dry) + sends hall/room/echo.
"""
import os, shutil, subprocess, wave
import numpy as np

SR = 48000
DUR = 15.0
N = int(SR * DUR)
rng = np.random.default_rng(7)
t_all = np.arange(N) / SR
BUS = {}
SIDECHAIN = []
IR_HALL = IR_ROOM = None


def init(dur=15.0, seed=7, sr=48000):
    """Reset the mix buffers for a film of `dur` seconds."""
    global SR, DUR, N, rng, t_all, BUS, SIDECHAIN, IR_HALL, IR_ROOM
    SR, DUR = sr, dur
    N = int(round(SR * DUR)); rng = np.random.default_rng(seed); t_all = np.arange(N) / SR
    BUS = {k: np.zeros((2, N)) for k in ('drum', 'mus', 'duckfx', 'sfx', 'hall', 'room', 'echo')}
    SIDECHAIN = []
    IR_HALL = make_ir(2.9, 2.5, .95, .021, 7, hp=140, er=[(.011, .5), (.019, .35), (.027, .3), (.041, .22), (.058, .15)])
    IR_ROOM = make_ir(.55, .42, .2, .004, 8, hp=170, er=[(.003, .6), (.007, .4), (.012, .3), (.017, .2)])


def load_cues(path):
    """cues.json written by `capture.mjs <film> /tmp --cues cues.json` → (cuts, cues). ONE source of truth for timing:
    re-export and re-run the sound (≈1 s) after every retime of the picture."""
    import json
    d = json.load(open(path))
    return d.get('hard') or d.get('cuts', []), d.get('cues', [])


# ---------------------------------------------------------------- placement
def add(sig, t0, gain=1.0, pan=0.0, bus='sfx', hall=0.0, room=0.0, echo=0.0):
    """Mono or (2,n) stereo signal at t0 s. pan −1..1 (scalar or per-sample array, equal power)."""
    sig = np.asarray(sig, float)
    if sig.ndim == 1: sig = np.vstack([sig, sig])
    i0 = int(round(t0 * SR)); p = np.asarray(pan, float)
    if i0 < 0:
        sig = sig[:, -i0:]; p = p[-i0:] if p.ndim else p; i0 = 0
    n = min(sig.shape[1], N - i0)
    if n <= 0: return
    if p.ndim: p = p[:n]
    l, r = np.cos((p + 1) * np.pi / 4) * 1.4142, np.sin((p + 1) * np.pi / 4) * 1.4142
    blk = np.vstack([sig[0, :n] * l, sig[1, :n] * r]) * gain
    BUS[bus][:, i0:i0 + n] += blk
    for k, v in (('hall', hall), ('room', room), ('echo', echo)):
        if v: BUS[k][:, i0:i0 + n] += blk * v


def add_end(sig, t1, gain=1.0, **kw):
    """Place a sound so it ENDS exactly at t1 — risers / reverse cymbals into a cut."""
    add(sig, t1 - np.shape(sig)[-1] / SR, gain, **kw)


# ---------------------------------------------------------------- DSP helpers
def tt(d): return np.arange(int(d * SR)) / SR
def midi(m): return 440 * 2 ** ((m - 69) / 12)
def env(t, a, d): return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / d)
def nrm(x): return x / (np.max(np.abs(x)) + 1e-12)
def kf(t, keys): return np.interp(t, [k[0] for k in keys], [k[1] for k in keys])   # automation curve


def ar(n, a=.002, r=.005):
    """Linear attack/release edges for a buffer of n samples (kills clicks)."""
    e = np.ones(n); na = min(n, max(1, int(a * SR))); nr = min(n, max(1, int(r * SR)))
    e[:na] *= np.linspace(0, 1, na); e[n - nr:] *= np.linspace(1, 0, nr); return e


def soft_end(x, r=.015): return x * ar(len(x), .0, r)


def band(x, lo, hi, soft=.25):
    """FFT band-pass with soft skirts."""
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR)
    m = np.clip((f - lo * (1 - soft)) / (lo * soft + 1e-9), 0, 1) * np.clip((hi * (1 + soft) - f) / (hi * soft + 1e-9), 0, 1)
    return np.fft.irfft(X * m, len(x))


def lp1(x, fc):
    """One-pole low-pass; fc may be an array (short sounds only — Python loop)."""
    fc = np.broadcast_to(np.asarray(fc, float), x.shape); a = 1 - np.exp(-2 * np.pi * fc / SR)
    y = np.empty_like(x); s = 0.0
    for i in range(len(x)): s += a[i] * (x[i] - s); y[i] = s
    return y


def glide(f0, f1, d, curve=1.0):
    t = tt(d); p = (t / d) ** curve; f = f0 * (f1 / f0) ** p; return t, np.sin(2 * np.pi * np.cumsum(f) / SR)


def _blep(p, dt):
    y = np.zeros_like(p)
    m = p < dt; x = p[m] / dt[m]; y[m] = x + x - x * x - 1
    m = p > 1 - dt; x = (p[m] - 1) / dt[m]; y[m] = x * x + x + x + 1
    return y


def _phase(f, ph0):
    dt = np.maximum(np.broadcast_to(np.asarray(f, float), np.shape(f)) / SR, 1e-9)
    return (ph0 + np.cumsum(dt) - dt[0]) % 1.0, dt


def saw(f, ph0=0.0):
    """Band-limited (polyBLEP) saw; f is a per-sample frequency array."""
    p, dt = _phase(f, ph0); return 2 * p - 1 - _blep(p, dt)


def pulse(f, duty=.5, ph0=0.0):
    p, dt = _phase(f, ph0); q = (p + duty) % 1
    return (2 * p - 1 - _blep(p, dt)) - (2 * q - 1 - _blep(q, dt))


def svf(x, fc, res=.5, mode='lp'):
    """TPT state-variable filter, time-varying cutoff, resonance 0..0.98. mode lp | bp | hp."""
    x = np.asarray(x, float); n = len(x)
    g = np.tan(np.pi * np.clip(np.broadcast_to(np.asarray(fc, float), (n,)), 20, SR * .42) / SR); k = 2 - 2 * min(res, .98)
    a1 = 1 / (1 + g * (g + k)); a2 = g * a1; a3 = g * a2
    X, A1, A2, A3 = x.tolist(), a1.tolist(), a2.tolist(), a3.tolist()
    lp = [0.0] * n; bp = [0.0] * n; c1 = c2 = 0.0
    for i in range(n):
        v3 = X[i] - c2; v1 = A1[i] * c1 + A2[i] * v3; v2 = c2 + A2[i] * c1 + A3[i] * v3
        c1 = 2 * v1 - c1; c2 = 2 * v2 - c2; lp[i] = v2; bp[i] = v1
    lp = np.array(lp); bp = np.array(bp)
    return lp if mode == 'lp' else bp if mode == 'bp' else x - k * bp - lp


def sweep_noise(d, lo0, hi0, lo1, hi1, curve=1.0):
    """Noise through a band that glides (log-spaced) — the core of every whoosh."""
    n = int(d * SR); pad_ = int(.05 * SR); x = rng.standard_normal(n + 2 * pad_); out = np.zeros(len(x)); B = 2048
    for i in range(0, len(x), B // 2):
        seg = x[i:i + B]
        if len(seg) < 256: break
        q = float(np.clip((i + len(seg) / 2 - pad_) / n, 0, 1)) ** curve
        out[i:i + len(seg)] += band(seg, lo0 * (lo1 / lo0) ** q, hi0 * (hi1 / hi0) ** q) * np.hanning(len(seg))
    return nrm(out[pad_:pad_ + n])


def events(t0, t1, rate, lam):
    """Inhomogeneous Poisson event times (thinning); rate(t) <= lam. For chatter, rain, sparkles."""
    out = []; t = t0
    while True:
        t += rng.exponential(1 / lam)
        if t >= t1: return out
        if rng.random() * lam < rate(t): out.append(t)


def make_ir(dur, rt_lo, rt_hi, pre, seed, hp=120, er=()):
    """Decorrelated stereo impulse response: noise with frequency-dependent decay (RT60 rt_lo @200 Hz → rt_hi @10 kHz)."""
    r = np.random.default_rng(seed); n = int(dur * SR); t = np.arange(n) / SR
    f = np.fft.rfftfreq(n, 1 / SR); lf = np.log(np.maximum(f, 20))
    cen = np.array([60, 200, 500, 1200, 2800, 6000, 12000, 20000.]); lc = np.log(cen)
    out = []
    for ch in range(2):
        X = np.fft.rfft(r.standard_normal(n)); y = np.zeros(n)
        for j, c in enumerate(cen):
            w = np.interp(lf, lc, np.eye(len(cen))[j])
            a = np.clip(np.log(c / 200) / np.log(10000 / 200), 0, 1); rt = rt_lo + (rt_hi - rt_lo) * a
            y += np.fft.irfft(X * w, n) * np.exp(-6.91 * t / rt)
        y *= np.minimum(1, t / .012)
        for dt_, a in er:
            i = int((dt_ + r.uniform(-.002, .002)) * SR); y[i] += a * r.choice([-1, 1]) * 6
        y = band(y, hp, 16000, .4)
        y = np.concatenate([np.zeros(int(pre * SR)), y]); out.append(y / np.sqrt(np.sum(y ** 2)))
    return out


def conv(x, h):
    nfft = 1 << int(np.ceil(np.log2(len(x) + len(h))))
    return np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(h, nfft), nfft)[:len(x)]


def verb(send, ir):
    l, r = send; return np.vstack([conv(.72 * l + .28 * r, ir[0]), conv(.28 * l + .72 * r, ir[1])])


# ---------------------------------------------------------------- drums / hits
def kick(g=1.0, f0=150, f1=44):
    """Round kick (BLIP)."""
    t = tt(.5); f = f1 + (f0 - f1) * np.exp(-t * 30)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7) + band(rng.standard_normal(len(t)), 2000, 7000) * np.exp(-t * 90) * .15) * g


def kick_t(g=1.0, f0=165, f1=47, pd=30, decay=6.0, d=.6, click=.22, drive=1.5):
    """Punchy techno kick (LO)."""
    t = tt(d); f = f1 + (f0 - f1) * np.exp(-t * pd)
    amp = np.minimum(1, t / .0012) * np.where(t < .012, 1.0, np.exp(-(t - .012) * decay))
    body = np.tanh(drive * np.sin(2 * np.pi * np.cumsum(f) / SR) * amp) / np.tanh(drive)
    ck = band(rng.standard_normal(len(t)), 1800, 9000) * np.exp(-t * 260) * click
    return (body + ck) * ar(len(t), .0, .03) * g


def clap(g=.5):
    t = tt(.28); n = band(rng.standard_normal(len(t)), 900, 5000)
    e = sum(np.exp(-np.maximum(t - d, 0) * 60) * (t >= d) for d in (0, .011, .022)) / 2 + np.exp(-t * 14) * .5
    return n * e * g


def hat(g=.2, d=.05): t = tt(d * 3); return band(rng.standard_normal(len(t)), 6500, 16000) * np.exp(-t / d * 3) * g


def hat2(g=.08, d=.03, tone=1.0):
    """808-style metallic hat (six squares + noise)."""
    n = int(max(d * 5, .04) * SR); t = np.arange(n) / SR
    m = sum(np.sign(np.sin(2 * np.pi * f * tone * t + rng.uniform(0, 6.28))) for f in (205.3, 304.4, 369.6, 522.7, 540.0, 800.0))
    x = band(m * .35 + rng.standard_normal(n) * .7, 7000, 15000)
    return nrm(x * np.exp(-t / d) * np.minimum(1, t / .0004)) * g


def cymbal(d=1.2, g=.3, decay=3.2):
    t = tt(d); m = sum(np.sign(np.sin(2 * np.pi * f * 1.73 * t + rng.uniform(0, 6.28))) for f in (205.3, 304.4, 369.6, 522.7, 540.0, 800.0))
    s = band(m * .4 + rng.standard_normal(len(t)), 4200, 15000) + band(rng.standard_normal(len(t)), 2500, 6000) * .25
    return nrm(s * np.exp(-t * decay) * np.minimum(1, t / .001) * ar(len(t), .0, .15)) * g


def rev_cymbal(d=.5, g=.3):
    c = cymbal(d * 1.4, 1.0, 4.0)[::-1][-int(d * SR):]
    return c * np.linspace(0, 1, len(c)) ** 1.5 * g


def impact(g=.8):
    """Soft cinematic boom (BLIP)."""
    t = tt(1.6); boom = np.sin(2 * np.pi * np.cumsum(36 + 80 * np.exp(-t * 18)) / SR) * np.exp(-t * 2.8)
    return (boom + band(rng.standard_normal(len(t)), 200, 3000) * np.exp(-t * 7) * .3) * g


def impact2(g=.8, decay=2.8, d=1.6, f_lo=34, sweep=85):
    """Boom with body + air + crack (LO). Put f_lo on the chord root: f_lo=midi(26)."""
    t = tt(d)
    boom = np.sin(2 * np.pi * np.cumsum(f_lo + sweep * np.exp(-t * 16)) / SR) * np.exp(-t * decay) * np.minimum(1, t / .012) ** 2
    air = band(rng.standard_normal(len(t)), 250, 4000) * np.exp(-t * 9) * .35
    crack = band(rng.standard_normal(len(t)), 2500, 10000) * np.exp(-t * 45) * .25
    return (boom + air + crack) * ar(len(t), .0005, .05) * g


def hit(t0, peak, size=1.0, chord=None, clap_g=0.0, cym=0.0, down=0.0, stab_g=.2, kick_kw=None, imp_kw=None):
    """A cut hit = kick + impact (+ clap, chord stab, cymbal, downlifter), scaled so its dry peak is exactly `peak`.
    Use the peaks to set a loudness hierarchy: hero hit (1.2) > big cuts (1.0) > soft cuts (0.8). Ducks the music."""
    SIDECHAIN.append(t0)
    kk = dict(decay=max(2.5, 6.5 - 2 * size)); kk.update(kick_kw or {})
    ik = dict(decay=4.2 - size * 1.2); ik.update(imp_kw or {})
    parts = [(kick_t(size, **kk), 0.0, 0.0, dict(bus='drum')), (impact2(.5 * size, **ik), 0.0, 0.0, dict(hall=.16))]
    if clap_g: parts.append((clap(clap_g), .002, .04, dict(bus='drum', hall=.3, room=.2)))
    if chord: parts.append((stab(chord, .95, stab_g), 0.0, 0.0, dict(hall=.32, echo=.16)))
    if cym: parts.append((cymbal(1.8, cym, 2.2), 0.0, .15, dict(hall=.22)))
    if down: parts.append((downlifter(.9, down), .01, 0.0, dict(hall=.2)))
    n = int(.1 * SR); tmp = np.zeros((2, n))
    for sig, off, pn, kw in parts:
        s2 = sig if np.ndim(sig) == 2 else np.vstack([sig, sig]); i = int(off * SR); m = min(n - i, s2.shape[1])
        tmp[0, i:i + m] += s2[0, :m] * np.cos((pn + 1) * np.pi / 4) * 1.4142; tmp[1, i:i + m] += s2[1, :m] * np.sin((pn + 1) * np.pi / 4) * 1.4142
    sc = peak / np.max(np.abs(tmp))
    for sig, off, pn, kw in parts: add(sig, t0 + off, sc, pan=pn, **kw)


# ---------------------------------------------------------------- tonal
def pluck(m, d=.35, g=.18):
    t = tt(d); f = midi(m)
    s = np.sin(2 * np.pi * f * t) + .45 * np.sin(4 * np.pi * f * t) * np.exp(-t * 18) + .2 * np.sin(6 * np.pi * f * t) * np.exp(-t * 30)
    return s * env(t, .003, d * .3) * g


def bell(m, d=1.2, g=.16):
    t = tt(d); f = midi(m)
    s = sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t * k) for r, a, k in [(1, 1, 2.5), (2.76, .45, 5), (5.4, .25, 9), (8.9, .12, 14)] if f * r < SR * .45)
    return s * np.minimum(1, t / .002) * g


def chime(m, g=.15, d=1.0):
    t = tt(d); f = midi(m)
    s = np.sin(2 * np.pi * f * t + .8 * np.exp(-t * 12) * np.sin(2 * np.pi * f * 2 * t)) + .3 * np.sin(4 * np.pi * f * t) * np.exp(-t * 6)
    return s * np.minimum(1, t / .002) * np.exp(-t * 4) * ar(len(t), .0, .05) * g


def pad(notes, d, g=.07):
    t = tt(d); out = np.zeros(len(t))
    for m in notes:
        for det in (-.07, .07):
            f = midi(m) * (1 + det / 100 * 6); ph = 2 * np.pi * f * t
            out += np.sin(ph) + .25 * np.sin(2 * ph + .3) + .1 * np.sin(3 * ph)
    return out * np.minimum(1, t / .35) * np.clip((d - t) / .4, 0, 1) * g / len(notes)


def saw_pad(notes, d, g, lp=1500, atk=.22, rel=.35):
    """Wide detuned saw pad (stereo), band-limited to lp Hz."""
    n = int(d * SR); t = np.arange(n) / SR; L = np.zeros(n); R = np.zeros(n)
    for m in notes:
        for det in (-.1, -.035, .035, .1):
            s = saw(np.full(n, midi(m) * 2 ** (det / 12)), rng.random())
            if det < 0: L += s
            else: R += s
    e = np.minimum(1, t / atk) * np.clip((d - t) / rel, 0, 1); body = pad(notes, d, 1.0)
    return np.vstack([band(L, 70, lp, .6) * e / len(notes) * .7 + body * .4, band(R, 70, lp, .6) * e / len(notes) * .7 + body * .4]) * g


def bass(m, d, g=.3):
    t = tt(d); f = midi(m); s = np.sin(2 * np.pi * f * t) + .3 * np.sin(4 * np.pi * f * t) + .1 * np.sin(6 * np.pi * f * t)
    return s * np.minimum(1, t / .01) * np.exp(-t * 1.6) * g


def stab(notes, d=.9, g=.2, fc0=5000, fc1=280, res=.35, fdec=8):
    """Detuned saw chord stab through a closing resonant filter, stereo."""
    t = tt(d); L = np.zeros(len(t)); R = np.zeros(len(t))
    for m in notes:
        L += saw(np.full(len(t), midi(m) * 2 ** (-.09 / 12)), rng.random()) + .5 * pulse(np.full(len(t), midi(m) * .5), .5, rng.random())
        R += saw(np.full(len(t), midi(m) * 2 ** (.09 / 12)), rng.random()) + .5 * pulse(np.full(len(t), midi(m) * .5 * 1.002), .5, rng.random())
    fc = fc1 + (fc0 - fc1) * np.exp(-t * fdec)
    e = np.minimum(1, t / .003) * np.exp(-t * 4.2) * ar(len(t), .0, .05)
    return np.vstack([svf(L, fc, res), svf(R, fc, res)]) * e * g / len(notes) ** .5


# ---------------------------------------------------------------- transitions
def whoosh(d, lo0, hi0, lo1, hi1, g=.4, rev=False):
    """Band-swept noise; rev=True swells into its end (use with add_end)."""
    n = int(d * SR); x = rng.standard_normal(n); out = np.zeros(n); B = 2048
    for i in range(0, n, B // 2):
        p = i / n; seg = x[i:i + B]
        if len(seg) < 64: break
        out[i:i + len(seg)] += band(seg, lo0 + (lo1 - lo0) * p, hi0 + (hi1 - hi0) * p) * np.hanning(len(seg))
    p = np.arange(n) / n; e = (p ** 2.2) if rev else np.sin(np.pi * p) ** 1.4
    return out * e * g


def riser(d, g=.45):
    w = whoosh(d, 300, 1500, 2500, 12000, g * .8, rev=True)
    t, s = glide(180, 1400, d, 2.0); return w + s * (np.arange(len(t)) / len(t)) ** 3 * g * .25


def riser2(d, f0=160, f1=2400, g=.4, lo0=250, hi0=1200, lo1=3500, hi1=14000, curve=2.4, trem=(4, 32)):
    """Tonal + noise swell whose peak (= g) lands on its last sample: the needle zoom's sound. Use add_end(..., cut)."""
    t = tt(d); p = t / d; pc = p ** curve
    nz = sweep_noise(d, lo0, hi0, lo1, hi1, curve)[:len(t)]
    f = f0 * (f1 / f0) ** pc
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * .6 + saw(f) * .25 + np.sin(2 * np.pi * np.cumsum(f * 1.5) / SR) * .25
    rate = trem[0] * (trem[1] / trem[0]) ** pc; tr = .62 + .38 * np.sin(2 * np.pi * np.cumsum(rate) / SR)
    return nrm((nz * .7 + tone * .35 * tr) * p ** 1.4) * g


def downlifter(d=.9, g=.2):
    w = sweep_noise(d, 3000, 12000, 200, 1200, .7); t = np.arange(len(w)) / SR
    return w * np.minimum(1, t / .01) * np.exp(-t * 3.5) * ar(len(t), .0, .1) * g


def whip(d=.22, g=.4):
    """Fast swish into a cut (whip pan, object flying past the lens)."""
    w = sweep_noise(d, 400, 1600, 3000, 13000, 1.6); p = np.arange(len(w)) / len(w)
    _, z = glide(500, 3400, d, 2.0)
    return (w * .85 + z[:len(w)] * .2) * p ** 2.4 * ar(len(w), .0, .008) * g


def shockwave(d=.95, g=.5):
    L = sweep_noise(d, 2500, 12000, 150, 1100, .55); R = sweep_noise(d, 2700, 12500, 165, 1200, .55)
    t = np.arange(len(L)) / SR; e = np.minimum(1, t / .02) * np.exp(-t * 4.2)
    return np.vstack([L * e, R * e]) * g


# ---------------------------------------------------------------- UI foley
def blip(f=1200, d=.06, g=.25, shape='sine'):
    t = tt(d); ph = 2 * np.pi * f * t
    s = np.sin(ph) if shape == 'sine' else np.sign(np.sin(ph)) * .55 + np.sin(ph) * .45
    return s * env(t, .002, d * .35) * g


def boop(f0=480, f1=980, d=.16, g=.35):
    t, s = glide(f0, f1, d, .6); return s * env(t, .004, d * .45) * g


def pop(f=900, g=.32):
    t = tt(.13); return np.sin(2 * np.pi * np.cumsum(f * (1 + 1.6 * np.exp(-t * 55))) / SR) * np.exp(-t * 34) * g


def wpop(f, g=.2):
    """Window / card pop: rising 'bwip' + octave sparkle."""
    t = tt(.13); ff = f * (1 - .38 * np.exp(-t * 70))
    s = np.sin(2 * np.pi * np.cumsum(ff) / SR) * np.exp(-t * 26) + np.sin(2 * np.pi * np.cumsum(ff * 2) / SR) * np.exp(-t * 55) * .3
    return soft_end(s * np.minimum(1, t / .0008) + pop(f * .5, .25)[:len(t)] * .5, .03) * g


def tick(g=.12, f=3200):
    t = tt(.03)
    return band(rng.standard_normal(len(t)), f * .7, f * 1.6) * np.exp(-t * 200) * g + np.sin(2 * np.pi * f * .5 * t) * np.exp(-t * 300) * g


def caret_tick(g=.07):
    t = tt(.03)
    return (np.sin(2 * np.pi * 2350 * t) * np.exp(-t * 260) + band(rng.standard_normal(len(t)), 3000, 9000) * np.exp(-t * 700) * .5) * np.minimum(1, t / .0003) * g


def mclick(g=.25):
    """Crisp mouse click (micro-switch)."""
    t = tt(.05); n = rng.standard_normal(len(t))
    hi = band(n, 2500, 12000) * np.exp(-t * 900)
    s = hi + np.sin(2 * np.pi * rng.uniform(4300, 4800) * t) * np.exp(-t * 650) * .6 \
        + np.sin(2 * np.pi * 1150 * t) * np.exp(-t * 380) * .45 + band(n, 400, 2000) * np.exp(-t * 420) * .5
    i = int(.0035 * SR); s[i:] += hi[:len(s) - i] * .45
    return nrm(s * np.minimum(1, t / .0002)) * g


def keyclick(g=.18, thock=.5):
    """One key of typing — place one per typed character."""
    t = tt(.09); n = rng.standard_normal(len(t))
    s = band(n, 1800, 7000) * np.exp(-t * 500) + (band(n, 180, 900) * np.exp(-t * 90) + np.sin(2 * np.pi * np.cumsum(260 + 200 * np.exp(-t * 120)) / SR) * np.exp(-t * 70) * .8) * thock
    i = int(.006 * SR); s[i:] += band(n, 600, 3000)[:len(s) - i] * np.exp(-t[:len(s) - i] * 300) * .5
    return nrm(s * np.minimum(1, t / .0003) * ar(len(t), .0, .01)) * g


def enter_thock(g=1.0):
    """The hero key press (Enter / Generate / Send)."""
    t = tt(1.4); n = rng.standard_normal(len(t))
    thump = np.sin(2 * np.pi * np.cumsum(60 + 95 * np.exp(-t * 38)) / SR) * np.minimum(1, t / .0008) * np.where(t < .022, 1, np.exp(-(t - .022) * 8.5))
    sub = np.sin(2 * np.pi * np.cumsum(38 + 16 * np.exp(-t * 10)) / SR) * np.minimum(1, t / .006) * np.exp(-t * 3.0)
    click = band(n, 1600, 9000) * np.exp(-t * 320) + np.sin(2 * np.pi * 2350 * t) * np.exp(-t * 240) * .5
    plastic = band(n, 300, 1600) * np.exp(-t * 55) * .9 + sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * k) for f, k, a in [(620, 60, .5), (1040, 80, .35), (1730, 110, .2)])
    mid = np.sin(2 * np.pi * np.cumsum(190 + 160 * np.exp(-t * 90)) / SR) * np.exp(-t * 28) * .7
    s = np.tanh(1.35 * (thump + sub * .7)) + click * .55 + plastic * .5 + mid
    i = int(.017 * SR); s[i:] += band(n, 2000, 6000)[:len(s) - i] * np.exp(-t[:len(s) - i] * 450) * .22
    return nrm(s * ar(len(t), .0, .1)) * g


def thunk(g=.6):
    """Heavy object lands (device on a desk, card slams into place)."""
    t = tt(.6); n = rng.standard_normal(len(t))
    low = np.sin(2 * np.pi * np.cumsum(70 + 85 * np.exp(-t * 45)) / SR) * np.exp(-t * 13)
    modes = sum(a * np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) * np.exp(-t * k) for f, k, a in [(212, 30, .5), (347, 40, .4), (590, 55, .3), (930, 70, .2), (1480, 90, .12)])
    s = np.tanh(1.5 * (low * .95 + band(n, 180, 1400) * np.exp(-t * 38) * .6 + modes * .6)) + band(n, 2000, 7000) * np.exp(-t * 200) * .3
    return nrm(s * np.minimum(1, t / .0008) * ar(len(t), .0, .05)) * g


def paper(d=.2, g=.15, up=True):
    """Paper / card swish (a panel sliding past)."""
    w = whoosh(d, 900, 3500, 2200, 8000, 1.0) if up else whoosh(d, 2200, 8000, 900, 3500, 1.0)
    n = len(w); steps = np.repeat(np.abs(rng.standard_normal(n // 60 + 2)), 60)[:n]; p = np.arange(n) / n
    return nrm(w * (.45 + .55 * lp1(steps, 900)) * np.minimum(1, p / .2) * (1 - p) ** .6) * g


def bit(f, d=.012, g=.04, fall=1.0):
    """Tiny digital grain (glyph / data bit)."""
    t = tt(d); ph = 2 * np.pi * np.cumsum(f * fall ** (t / d)) / SR
    return (np.sin(ph) + .22 * np.sin(3 * ph)) * np.minimum(1, t / .0006) * np.exp(-t / (d * .3)) * ar(len(t), .0, d * .3) * g


def sparkle(f, d=.06, g=.04):
    t = tt(d)
    return (np.sin(2 * np.pi * f * t) + .3 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 90)) * np.minimum(1, t / .0005) * np.exp(-t / (d * .28)) * ar(len(t), .0, d * .3) * g


def decode(t0, d, g=.03, pan=0.0, width=.3, rate=60., fmin=1800, fmax=6000, bus='sfx', power=1.5):
    """Chatter of data bits that thins out over d seconds — under decoding text, code rain, particles settling."""
    for tk in events(t0, t0 + d, lambda t: rate * max(0., 1 - (t - t0) / d) ** power, rate):
        p = (tk - t0) / d; f = rng.uniform(fmin, fmax)
        s = bit(f, rng.uniform(.005, .014), 1.0, rng.choice([1.0, .88, 1.12])) if rng.random() < .72 else tick(.6, f * .8)
        add(s, tk, g * rng.uniform(.55, 1.0) * (1 - .5 * p), pan=float(np.clip(pan + rng.uniform(-width, width), -1, 1)), bus=bus, room=.15)


# ---------------------------------------------------------------- mix / master
def duck_env(times, depth=.5, rel=.24):
    d = np.ones(N); n = int(rel * SR) + int(.003 * SR); t = (np.arange(n) - int(.003 * SR)) / SR
    shape = 1 - depth * np.where(t < 0, (t + .003) / .003, .5 + .5 * np.cos(np.pi * np.clip(t / rel, 0, 1)))
    for tk in times:
        i0 = int(round(tk * SR)) - int(.003 * SR); m = min(n, N - i0)
        if m > 0: d[i0:i0 + m] = np.minimum(d[i0:i0 + m], shape[:m])
    return d


def pingpong(send, D=.375, fb=.42, taps=6):
    src = send[0] * .5 + send[1] * .5; out = np.zeros((2, N)); k_ = int(D * SR)
    for k in range(1, taps + 1):
        sh = np.zeros(N); sh[k * k_:] = src[:N - k * k_]
        out[(k - 1) % 2] += band(sh, 250, 7000 * .78 ** k) * fb ** (k - 1)
    return out


def compress(x, thr_db=-10.0, ratio=2.0, atk=.001, rel=.15, look=.005, B=48):
    mono = np.max(np.abs(x), axis=0); nb = len(mono) // B + 1
    pk = np.zeros(nb * B); pk[:len(mono)] = mono; pk = pk.reshape(nb, B).max(1)
    la = pk.copy()
    for j in range(1, int(look * SR / B) + 1): la[:-j] = np.maximum(la[:-j], pk[j:])
    thr = 10 ** (thr_db / 20) * pk.max()
    gdb = -(1 - 1 / ratio) * 20 * np.log10(np.maximum(la / thr, 1.0))
    aa, rr = np.exp(-B / (atk * SR)), np.exp(-B / (rel * SR)); g = np.empty(nb); s = 0.0
    for j, tg in enumerate(gdb.tolist()):
        c = aa if tg < s else rr; s = c * s + (1 - c) * tg; g[j] = s
    return x * np.interp(np.arange(x.shape[1]), (np.arange(nb) + .5) * B, 10 ** (g / 20))


def master_eq(ch):
    """22 Hz high-pass + a gentle air shelf."""
    X = np.fft.rfft(ch); f = np.fft.rfftfreq(len(ch), 1 / SR)
    return np.fft.irfft(X * np.clip((f - 15) / 7, 0, 1) * (1 - .1 * np.clip((f - 9000) / 5000, 0, 1)), len(ch))


_OUT = None


def master(out_wav, fade_from=None, fade_len=.4, duck_depth=.5, peak_db=-1.0):
    """Sum buses (music + duckfx ducked by every hit/kick in SIDECHAIN), reverbs, compress, soft-clip, fade, write
    16-bit stereo WAV at peak_db, then .m4a (AAC 256k) next to it with macOS afconvert."""
    global _OUT
    duck = duck_env(sorted(SIDECHAIN), duck_depth, .24)
    mix = (BUS['drum'] + (BUS['mus'] + BUS['duckfx']) * duck + BUS['sfx'] + verb(BUS['hall'], IR_HALL) * .42
           + verb(BUS['room'], IR_ROOM) * .38 + pingpong(BUS['echo']) * duck * .55)
    mix = np.vstack([master_eq(ch) for ch in mix])
    mix = compress(mix / (np.max(np.abs(mix)) + 1e-12))
    mix = mix / np.max(np.abs(mix)); K = .88
    mix = np.where(np.abs(mix) > K, np.sign(mix) * (K + (1 - K) * np.tanh((np.abs(mix) - K) / (1 - K))), mix)
    fade_from = DUR - fade_len if fade_from is None else fade_from
    mix = mix * np.clip(t_all / .002, 0, 1) * (.5 + .5 * np.cos(np.pi * np.clip((t_all - fade_from) / fade_len, 0, 1)))
    mix = mix / np.max(np.abs(mix)) * 10 ** (peak_db / 20)
    out = np.round(mix.T * 32767).astype(np.int16); _OUT = out
    os.makedirs(os.path.dirname(os.path.abspath(out_wav)), exist_ok=True)
    with wave.open(out_wav, 'wb') as w_:
        w_.setnchannels(2); w_.setsampwidth(2); w_.setframerate(SR); w_.writeframes(out.tobytes())
    print('wrote', out_wav, f'{DUR}s')
    if shutil.which('afconvert'):
        m4a = out_wav.rsplit('.', 1)[0] + '.m4a'
        subprocess.run(['afconvert', '-f', 'm4af', '-d', 'aac', '-b', '256000', out_wav, m4a], check=True)
        print('wrote', m4a)
    return out_wav


def verify(cues):
    """cues: [(name, t, band)] band in lf | mid | hf. Prints onset error (ms) per cue and per-second RMS —
    every hit should land within ±5 ms of its cut, the loudest transients should be the hero moments."""
    x = _OUT.astype(float) / 32768; blk = 48
    db = lambda v: 20 * np.log10(max(v, 1e-12))
    print('RMS per second (dBFS):', ' '.join(f'{s}s:{db(np.sqrt(np.mean(x[s * SR:(s + 1) * SR] ** 2))):.1f}' for s in range(int(DUR))))
    def benv(lo, hi):
        y = np.vstack([band(x[:, 0], lo, hi), band(x[:, 1], lo, hi)]); return np.abs(y).max(0)[:N // blk * blk].reshape(-1, blk).max(1)
    ENV = {'lf': benv(25, 180), 'mid': benv(600, 3000), 'hf': benv(2500, 16000)}
    for name, tc, bd in cues:
        v = ENV[bd]; a = max(0, int((tc - .015) * 1000)); seg = v[a:int((tc + .05) * 1000)]; j = int(np.argmax(seg))
        base = float(np.median(v[max(0, a - 40):a])) if a > 0 else 0.0
        on = int(np.argmax(seg >= base + .5 * (seg[j] - base)))
        print(f'{name:12s} {tc:6.3f}s {bd:3s} onset {a + on - tc * 1000:+4.0f} ms')


init()
