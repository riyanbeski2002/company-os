#!/usr/bin/env python3
"""Cut the music segment for a film: 48 kHz stereo, a short click-free fade-in, a shaped fade-out at a hard out.

usage: cut_audio.py <track> <start> <length> <out.m4a|out.wav> [--fade 0.25] [--fadein 0.012]
  track    anything afconvert reads (mp3, m4a, wav, aif); ffmpeg is used only if afconvert is missing.
  start    seconds (66.4) or m:ss (1:06.4): pick it with music_window.py, and fix a late or early beat by moving
           the start, never the picture.
  length   seconds: the film's exact duration (frames / fps).
  --fade   fade-out seconds at the hard out, 0.25–1 s (default 0.25; the curve is (remaining / fade) ** 1.5).
  --fadein fade-in seconds (default 0.012: just enough to remove the click).
  out      .m4a = AAC 256 kbps (mux it onto an MP4); .wav = 16-bit PCM (feed it to encode_av or master).
Pure stdlib (wave, array). Exit 1 with a message when the start is past the end or the tools are missing.
"""
import argparse, array, os, shutil, subprocess, sys, tempfile, wave


def seconds(s):
    """'66.4' -> 66.4, '1:06.4' -> 66.4"""
    try:
        if ':' in s:
            m, r = s.split(':', 1)
            return int(m) * 60 + float(r)
        return float(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f'not a time: {s!r} (use seconds or m:ss)')


def die(msg):
    sys.exit(f'cut_audio: {msg}')


def decode(src, dst):
    if shutil.which('afconvert'):
        r = subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16@48000', '-c', '2', src, dst], capture_output=True, text=True)
    elif shutil.which('ffmpeg'):
        r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-ac', '2', '-ar', '48000', '-c:a', 'pcm_s16le', dst], capture_output=True, text=True)
    else:
        die('need afconvert (macOS) or ffmpeg to decode audio')
    if r.returncode != 0:
        die(f'cannot decode {src}: {(r.stderr or r.stdout).strip()[:300]}')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('track'); ap.add_argument('start', type=seconds); ap.add_argument('length', type=float); ap.add_argument('out')
    ap.add_argument('--fade', type=float, default=0.25); ap.add_argument('--fadein', type=float, default=0.012)
    a = ap.parse_args()
    if not os.path.exists(a.track): die(f'no such file: {a.track}')
    if a.length <= 0: die('length must be positive')
    ext = os.path.splitext(a.out)[1].lower()
    if ext not in ('.m4a', '.wav'): die('output must be .m4a or .wav')
    if ext == '.m4a' and not shutil.which('afconvert'): die('writing .m4a needs afconvert (macOS); write .wav instead')
    fd, tmp = tempfile.mkstemp(suffix='.wav'); os.close(fd)
    try:
        decode(a.track, tmp)
        with wave.open(tmp, 'rb') as w:
            sr, ch, total = w.getframerate(), w.getnchannels(), w.getnframes()
            if a.start * sr >= total: die(f'start {a.start:.2f} s is past the end of the track ({total / sr:.2f} s)')
            w.setpos(int(a.start * sr))
            seg = array.array('h', w.readframes(int(a.length * sr)))
        n = len(seg) // ch
        if n < int(a.length * sr) - 1:
            print(f'cut_audio: warning: only {n / sr:.2f} s left after {a.start:.2f} s (asked {a.length:.2f} s)', file=sys.stderr)
        L = n / sr
        fi, fo = max(1, int(a.fadein * sr)), max(1, int(min(a.fade, L) * sr))
        for i in range(min(fi, n)):            # fade-in (linear)
            g = i / fi
            for c in range(ch): seg[i * ch + c] = int(seg[i * ch + c] * g)
        for i in range(max(0, n - fo), n):     # fade-out ((remaining / fade) ** 1.5)
            g = max(0.0, (n - 1 - i) / fo) ** 1.5
            for c in range(ch): seg[i * ch + c] = int(seg[i * ch + c] * g)
        with wave.open(tmp, 'wb') as o:
            o.setnchannels(ch); o.setsampwidth(2); o.setframerate(sr); o.writeframes(seg.tobytes())
        if ext == '.wav':
            shutil.move(tmp, a.out)
        else:
            r = subprocess.run(['afconvert', '-f', 'm4af', '-d', 'aac', '-b', '256000', tmp, a.out], capture_output=True, text=True)
            if r.returncode != 0: die(f'afconvert failed: {(r.stderr or r.stdout).strip()[:300]}')
        m, s = divmod(a.start, 60)
        print(f'wrote {a.out} ({L:.3f} s from {int(m)}:{s:05.2f} = {a.start:.2f} s, fade-in {a.fadein:.3f} s, fade-out {min(a.fade, L):.2f} s, {sr} Hz {ch} ch)')
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


if __name__ == '__main__':
    main()
