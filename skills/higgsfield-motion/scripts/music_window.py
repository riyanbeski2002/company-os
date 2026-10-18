#!/usr/bin/env python3
"""Find the best N-second window of a music track for a film, map its structure, snap scenario times to real hits,
and verify picture hits on the final mix.

usage:
  music_window.py <track> --len 30 [--after 1:00] [--before 2:30] [--top 3] [--fps 24] [--json out.json]
      search: windows may START between --after and --before ('best 30 s from 1:00' = --after 60).
  music_window.py <track> --len 30 --start 1:06.4 [--snap 4,9,17,24]
      one fixed window; --snap moves scenario times (film seconds) onto the nearest strong accent (±0.35 s) or beat.
  music_window.py <mix.wav> --hits 4.28,8.99,17.5,24.24 [--fps 24]
      verify the FINAL muxed audio: RMS in 12.5 ms windows, the onset nearest each picture hit, its offset in ms and
      frames. Energy-based analysis can be beats off: fix by shifting the music start (cut_audio), not the picture.
  music_window.py <score.wav> --sections 0.3-1.7,2.5-9.9,20.3-27.9
      mean level per section (does the build climb? is the breakdown the quietest part?).

Prints the tempo (BPM, beat in frames) and, per window, breath (dip) → DROP → LIFT → strong accents → final hit, in film
time (0 = window start) next to track time, ready for the proposal table: track time → what the music does → what
happens in the film. Pure stdlib; decodes with macOS afconvert (or ffmpeg).
"""
import argparse, array, json, math, os, shutil, subprocess, sys, tempfile, wave


def seconds(s):
    try:
        if ':' in s:
            m, r = s.split(':', 1)
            return int(m) * 60 + float(r)
        return float(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f'not a time: {s!r} (use seconds or m:ss)')


def times_list(s):
    try:
        return [float(v) for v in s.split(',') if v.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError(f'not a list of seconds: {s!r}')


def mmss(t):
    m, s = divmod(max(0.0, t), 60)
    return f'{int(m)}:{s:05.2f}'


def decode(path, sr):
    fd, tmp = tempfile.mkstemp(suffix='.wav'); os.close(fd)
    try:
        if shutil.which('afconvert'):
            r = subprocess.run(['afconvert', '-f', 'WAVE', '-d', f'LEI16@{sr}', '-c', '1', path, tmp], capture_output=True, text=True)
        elif shutil.which('ffmpeg'):
            r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-ac', '1', '-ar', str(sr), '-c:a', 'pcm_s16le', tmp], capture_output=True, text=True)
        else:
            sys.exit('music_window: need afconvert (macOS) or ffmpeg to decode audio')
        if r.returncode != 0:
            sys.exit(f'music_window: cannot decode {path}: {(r.stderr or r.stdout).strip()[:300]}')
        with wave.open(tmp, 'rb') as w:
            a = array.array('h', w.readframes(w.getnframes()))
    finally:
        os.unlink(tmp)
    return [v / 32768.0 for v in a]


def envelopes(x, sr):
    """100 fps: E = frame energy (dB), O = onset strength (positive energy flux, full band + below 120 Hz)."""
    k = math.exp(-2 * math.pi * 120.0 / sr); y = 0.0; lo = [0.0] * len(x)
    for i, v in enumerate(x):
        y = (1 - k) * v + k * y; lo[i] = y
    hop = sr // 100; n = len(x) // hop
    E, B = [], []
    for f in range(n):
        s, e = f * hop, f * hop + hop
        E.append(10 * math.log10(1e-9 + sum(v * v for v in x[s:e]) / hop))
        B.append(10 * math.log10(1e-9 + sum(v * v for v in lo[s:e]) / hop))
    O = [0.0] + [max(0.0, E[i] - E[i - 1]) + max(0.0, B[i] - B[i - 1]) for i in range(1, n)]
    return E, O


def mean(a): return sum(a) / max(1, len(a))


def analyse(E, O, fps=100):
    n = len(E); sm = [mean(E[max(0, i - 10):i + 10]) for i in range(n)]  # 0.2 s smoothing
    drops, lifts, accents = [], [], []
    for i in range(4 * fps, n - fps):
        dip = mean(sm[i - int(1.2 * fps):i - 5]); before = mean(sm[i - 4 * fps:i - int(1.5 * fps)]); after = mean(sm[i:i + fps // 2])
        if before - dip >= 3.5 and after - dip >= 6.0 and O[i] == max(O[i - 30:i + 30]):
            if not drops or i - drops[-1][0] > 3 * fps: drops.append((i, round(after - dip, 1)))
    for i in range(3 * fps, n - 3 * fps, 5):
        a, b = mean(sm[i - 2 * fps:i]), mean(sm[i:i + 2 * fps])
        if b - a >= 2.0 and all(abs(i - d) > 2 * fps for d, _ in drops):
            j = max(range(i - 30, i + 30), key=lambda k: O[k])
            if not lifts or j - lifts[-1][0] > 4 * fps: lifts.append((j, round(b - a, 1)))
    thr = sorted(O)[int(len(O) * 0.97)] if O else 0
    for i in range(8, n - 8):
        if O[i] >= thr and O[i] == max(O[i - 8:i + 9]): accents.append(i)
    return sm, drops, lifts, accents


def tempo(O, fps=100, lo=70.0, hi=180.0):
    """BPM and beat phase (s) from the onset curve: autocorrelation with a mild prior around 120 BPM, then a fine
    comb search over tempo and phase. Returns (bpm, phase, confidence 0..1)."""
    n = len(O)
    if n < 6 * fps: return None
    m = mean(O); o = [v - m for v in O]
    best, bestL = -1e18, 0
    for L in range(int(60 * fps / hi), int(60 * fps / lo) + 1):
        r = sum(o[i] * o[i + L] for i in range(0, n - L, 2)) / (n - L)
        r *= math.exp(-0.5 * (math.log2((60 * fps / L) / 120.0) / 0.9) ** 2)
        if r > best: best, bestL = r, L
    if best <= 0: return None
    def comb(period, phase):
        s, t, c = 0.0, phase, 0
        while t < n - 1:
            i = int(t); s += max(O[i], O[i + 1]); t += period; c += 1
        return s / max(1, c)
    bpm0 = 60 * fps / bestL; cand = (0.0, bpm0, 0.0)
    b = bpm0 - 3.0
    while b <= bpm0 + 3.0:
        period = 60 * fps / b
        for ph in range(0, int(period), 2):
            sc = comb(period, ph)
            if sc > cand[0]: cand = (sc, b, ph)
        b += 0.1
    sc, bpm, ph = cand
    period = 60 * fps / bpm
    for p in (ph - 1, ph + 1):  # 10 ms phase refinement
        if p >= 0 and comb(period, p) > sc: sc, ph = comb(period, p), p
    conf = min(1.0, sc / (mean(O) * 4 + 1e-9))
    return round(bpm, 2), ph / fps, round(conf, 2)


def describe(start, L, sm, drops, lifts, accents, fps=100):
    s, e = int(start * fps), int((start + L) * fps)
    rel = lambda i: round(i / fps - start, 2)
    d = [(rel(i), g) for i, g in drops if s <= i < e]; l = [(rel(i), g) for i, g in lifts if s <= i < e]
    acc = [rel(i) for i in accents if s <= i < e]
    tail_hit = [a for a in acc if L - 0.9 <= a <= L - 0.1]
    return {'start': round(start, 2), 'end': round(start + L, 2), 'mean_db': round(mean(sm[s:e]), 1), 'drops': d, 'lifts': l,
            'final_hit': tail_hit[-1] if tail_hit else None, 'accents': acc}


def score(desc, L):
    sc = desc['mean_db']
    if any(0.03 * L <= t <= 0.25 * L for t, _ in desc['drops']): sc += 8            # a breath + drop near the top
    if any(0.5 * L <= t <= 0.85 * L for t, _ in desc['lifts'] + desc['drops']): sc += 5  # a lift into the climax
    if desc['final_hit'] is not None: sc += 4                                         # a hit to end on
    return sc


def beats_in(start, L, tp):
    if not tp: return []
    bpm, ph, _ = tp; beat = 60.0 / bpm
    k = math.ceil((start - ph) / beat - 1e-9); out = []
    t = ph + k * beat
    while t < start + L - 1e-6:
        out.append(round(t - start, 3)); t += beat
    return out


def snap(times, desc, beats, fps_film):
    rows = []
    for t in times:
        near = [a for a in desc['accents'] + [d for d, _ in desc['drops']] + [l for l, _ in desc['lifts']] if abs(a - t) <= 0.35]
        if near:
            a = min(near, key=lambda v: abs(v - t)); kind = 'accent'
            if any(abs(a - d) < 0.02 for d, _ in desc['drops']): kind = 'DROP'
            elif any(abs(a - l) < 0.02 for l, _ in desc['lifts']): kind = 'LIFT'
        elif beats:
            a = min(beats, key=lambda v: abs(v - t)); kind = 'beat'
        else:
            a, kind = t, 'none'
        rows.append((t, round(a, 3), kind))
    print(f'\nsnap (film time) → nearest strong accent within 0.35 s, else the beat grid:')
    for t, a, kind in rows:
        print(f'  {t:7.2f} → {a:7.3f}  ({kind}, {a - t:+.3f} s = {(a - t) * fps_film:+.1f} f; frame {round(a * fps_film)} @{fps_film:g})')
    return rows


def verify_hits(path, hits, fps_film):
    sr = 16000; x = decode(path, sr); hop = 200  # 12.5 ms windows
    n = len(x) // hop
    db = [10 * math.log10(1e-10 + sum(v * v for v in x[i * hop:(i + 1) * hop]) / hop) for i in range(n)]
    print(f'{os.path.basename(path)}: {len(x) / sr:.3f} s · RMS in 12.5 ms windows · onset = largest rise over the previous 50 ms')
    print('   hit (s)   onset (s)   offset        rise')
    bad = 0; frame = 1.0 / fps_film
    for h in hits:
        c = int(round(h / 0.0125)); lo, hi = max(4, c - 20), min(n - 1, c + 20)
        if lo >= hi: print(f'  {h:8.3f}   past the end'); bad += 1; continue
        rise = lambda i: db[i] - max(db[i - 4:i])
        i = max(range(lo, hi + 1), key=rise); t = (i + 0.5) * 0.0125; off = t - h
        flag = '' if abs(off) <= frame else ('  LATE' if off > 0 else '  EARLY')
        if flag: bad += 1
        print(f'  {h:8.3f}   {t:8.3f}   {off * 1000:+6.0f} ms {off * fps_film:+5.1f} f   {rise(i):+5.1f} dB{flag}')
    print(f'{len(hits) - bad}/{len(hits)} hits within one frame ({frame * 1000:.1f} ms)' + ('' if not bad else ' — shift the music start, not the picture'))
    return bad


def main():
    ap = argparse.ArgumentParser(description='best music window / structure map / hit check', usage=__doc__.split('\n\n')[1])
    ap.add_argument('track'); ap.add_argument('--len', type=float, default=30)
    ap.add_argument('--after', type=seconds, default=0.0); ap.add_argument('--before', type=seconds, default=None)
    ap.add_argument('--start', type=seconds, default=None); ap.add_argument('--json'); ap.add_argument('--top', type=int, default=3)
    ap.add_argument('--fps', type=float, default=24.0, help='film fps for frame numbers (default 24)')
    ap.add_argument('--snap', type=times_list, default=None, help='scenario times in film seconds, e.g. 4,9,17,24')
    ap.add_argument('--hits', type=times_list, default=None, help='picture hits (film s) to verify on the final mix')
    ap.add_argument('--sections', default=None, help='level per range, e.g. 0.3-1.7,2.5-9.9,20.3-27.9')
    a = ap.parse_args()
    if not os.path.exists(a.track): sys.exit(f'music_window: no such file: {a.track}')
    if a.hits:
        sys.exit(1 if verify_hits(a.track, a.hits, a.fps) else 0)
    x = decode(a.track, 11025); dur = len(x) / 11025
    E, O = envelopes(x, 11025); sm, drops, lifts, accents = analyse(E, O)
    if a.sections:
        for r in a.sections.split(','):
            x0, x1 = (float(v) for v in r.split('-')); seg = sm[int(x0 * 100):int(x1 * 100)]
            print(f'section {x0:>6.2f}–{x1:<6.2f}  mean {mean(seg):6.1f} dB')
        return
    tp = tempo(O)
    if tp:
        bpm, ph, conf = tp; beat = 60 / bpm
        print(f'tempo  {bpm:.2f} BPM (confidence {conf}) · beat {beat:.3f} s = {beat * a.fps:.2f} frames @{a.fps:g} fps · '
              f'bar {4 * beat:.3f} s · first beat at {ph:.2f} s')
    else:
        print('tempo  not found (too short or no steady pulse)')
    print(f'track  {dur:.1f} s ({mmss(dur)}) · drops at {[mmss(i / 100) for i, _ in drops]} · lifts at {[mmss(i / 100) for i, _ in lifts]}')
    if a.len > dur: sys.exit(f'music_window: the track ({dur:.1f} s) is shorter than --len {a.len}')
    if a.start is not None:
        cands = [describe(a.start, a.len, sm, drops, lifts, accents)]
    else:
        hi = min(dur - a.len, a.before if a.before is not None else dur)
        if a.after > hi: sys.exit(f'music_window: no {a.len:g} s window can start after {mmss(a.after)} (track ends {mmss(dur)})')
        cands = []; t = a.after
        while t <= hi + 1e-9:
            d = describe(t, a.len, sm, drops, lifts, accents); d['score'] = round(score(d, a.len), 2); cands.append(d); t += 0.1
        cands.sort(key=lambda d: -d['score']); picked = []
        for c in cands:
            if all(abs(c['start'] - p['start']) > a.len * 0.4 for p in picked): picked.append(c)
            if len(picked) >= a.top: break
        cands = picked
    for c in cands:
        c['beats'] = beats_in(c['start'], a.len, tp)
        print(f"\nwindow {mmss(c['start'])}–{mmss(c['end'])}  (track {c['start']:.2f}–{c['end']:.2f} s)  mean {c['mean_db']} dB  score {c.get('score', '-')}")
        rows = [(0.0, 'start (cut here, 12 ms fade-in)')]
        rows += [(t, f'DROP (+{g} dB after a breath)') for t, g in c['drops']]
        rows += [(t, f'LIFT (+{g} dB step up)') for t, g in c['lifts']]
        if c['final_hit'] is not None: rows.append((c['final_hit'], 'final hit: land the end card here'))
        rows.append((a.len, 'hard out (0.25–1 s fade)'))
        print('  film     track      frame   what the music does')
        for t, what in sorted(rows):
            print(f'  {t:6.2f}   {mmss(c["start"] + t):>8}   {round(t * a.fps):5d}   {what}')
        print(f"  strong accents (film s): {c['accents'][:40]}")
        if a.snap: c['snap'] = snap(a.snap, c, c['beats'], a.fps)
    if a.json:
        with open(a.json, 'w') as f: json.dump({'tempo': tp, 'windows': cands}, f, indent=1)
        print(f'\nwrote {a.json}')


if __name__ == '__main__':
    main()
