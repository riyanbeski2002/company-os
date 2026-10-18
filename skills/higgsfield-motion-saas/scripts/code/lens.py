"""Photographic lens pass over rendered frames — the BLIP./LO. "photographed, not drawn" look for ANY film (DOM or canvas).
Flat, perfectly clean vector frames read as "cheap"; this adds what a real lens does: barrel bulge, radial chromatic
fringes, multi-scale bloom on highlights, vignette and fine luma grain (seeded per frame, so it never smears in blur).

usage:
  python3 lens.py <frames_dir> [out_dir] [--fps 30] [--k .04] [--ca 1.5] [--bloom .35] [--thr .72] [--vig .35] [--grain .02] [--bloomauto 1]
                  [--sched sched.json]
  sched.json = [{"from": 0, "to": 2.5, "k": 0.12, "ca": 3, "vig": 0.5}, {"from": 2.5, "to": 15, "bloom": 0.5}]  (per-scene overrides, strict JSON)
  out_dir omitted → frames are processed in place. Run it between blend.py and encode (render_film.sh does with LENS=1).
Defaults are deliberately gentle: k .04, ca 1.5 px at the frame edge, bloom .35, vig .35, grain .02 (visible noise was
rejected once — "убери шум" — keep grain a texture you feel, not see). Canvas films with their own WebGL lens
(assets/snippets/lens_gl.js) should skip this pass.
"""
import json, os, re, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from PIL import Image, ImageFilter

DEF = dict(k=.04, ca=1.5, bloom=.35, thr=.72, vig=.35, grain=.02, bloomauto=1)
_grid = {}


def arg(name, default, cast=float):
    a = sys.argv
    return cast(a[a.index(name) + 1]) if name in a else default


def params_at(t, base, sched):
    p = dict(base)
    for s in sched:
        if s.get('from', 0) <= t < s.get('to', 1e9): p.update({k: v for k, v in s.items() if k in DEF})
    return p


def grid(w, h, k, ca):
    """Sampling maps for barrel distortion per channel (R bulges a bit more, B a bit less = radial fringes)."""
    key = (w, h, round(k, 4), round(ca, 3))
    if key in _grid: return _grid[key]
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = (w - 1) / 2, (h - 1) / 2; nx, ny = (x - cx) / cx, (y - cy) / cx          # aspect-correct radius
    r2 = nx * nx + ny * ny; rmax2 = 1 + (cy / cx) ** 2
    zoom = 1 + k * rmax2 * .5                                                         # crop in so corners stay filled
    out = []
    for s in (ca / cx, 0.0, -ca / cx):                                                # R, G, B
        f = (1 + k * r2) / zoom * (1 + s * np.sqrt(r2 / rmax2))
        out.append((cx + nx * f * cx, cy + ny * f * cx))
    _grid[key] = (out, r2 / rmax2); return _grid[key]


def remap(ch, mx, my):
    h, w = ch.shape
    mx = np.clip(mx, 0, w - 1.001); my = np.clip(my, 0, h - 1.001)
    x0 = mx.astype(np.int32); y0 = my.astype(np.int32); fx = mx - x0; fy = my - y0
    a = ch[y0, x0]; b = ch[y0, x0 + 1]; c = ch[y0 + 1, x0]; d = ch[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def process(job):
    src, dst, n, p = job
    im = Image.open(src).convert('RGB'); w, h = im.size
    a = np.asarray(im, dtype=np.float32) / 255
    if p['bloom'] > 0:                                                                # multi-scale bloom from highlights only
        luma = a[..., 0] * .2126 + a[..., 1] * .7152 + a[..., 2] * .0722   # (no float32 matmul: numpy 2.0 + Accelerate emits bogus overflow)
        amt = p['bloom'] * (np.clip((.8 - float(luma.mean())) / .45, 0, 1) if p['bloomauto'] else 1)   # bloom is for dark frames: on paper it only washes out
        hi = np.clip((luma - p['thr']) / (1 - p['thr'] + 1e-6), 0, 1)[..., None] * a
        him = Image.fromarray((hi * 255).astype(np.uint8)); acc = np.zeros_like(a)
        for rad, wgt in ((h * .006, .7), (h * .02, 1.0), (h * .06, .45)):
            acc += np.asarray(him.filter(ImageFilter.GaussianBlur(rad)), np.float32) / 255 * wgt
        a = 1 - (1 - a) * (1 - np.clip(acc * amt, 0, 1))                              # screen
    if p['k'] or p['ca']:
        maps, rn = grid(w, h, p['k'], p['ca'])
        a = np.dstack([remap(a[..., i], *maps[i]) for i in range(3)])
    else:
        rn = grid(w, h, 0, 0)[1]
    if p['vig'] > 0:
        r = np.sqrt(rn); t = np.clip((r - .35) / .9, 0, 1); a *= (1 - p['vig'] * t * t * (3 - 2 * t))[..., None]
    if p['grain'] > 0:
        g = np.random.default_rng(n * 7919 + 13).standard_normal((h, w)).astype(np.float32)
        lm = np.clip(a.mean(2, keepdims=True), 0, 1)
        a += (g * p['grain'])[..., None] * (.3 + 2.8 * lm * (1 - lm))                  # film grain lives in the mid-tones
    Image.fromarray(np.clip(a * 255 + .5, 0, 255).astype(np.uint8)).save(dst, compress_level=1)
    if os.path.abspath(src) != os.path.abspath(dst) and os.path.dirname(os.path.abspath(src)) == os.path.dirname(os.path.abspath(dst)):
        os.remove(src)                                                                # in place: f_N.jpg → f_N.png, never both
    return n


def main():
    pos, i = [], 1
    while i < len(sys.argv):
        if sys.argv[i].startswith('--'): i += 2; continue
        pos.append(sys.argv[i]); i += 1
    src = pos[0]; dst = pos[1] if len(pos) > 1 else src
    os.makedirs(dst, exist_ok=True)
    fps = arg('--fps', 30.0)
    base = {k: arg('--' + k, v) for k, v in DEF.items()}
    sched = json.load(open(sys.argv[sys.argv.index('--sched') + 1])) if '--sched' in sys.argv else []
    jobs = []
    for f in sorted(os.listdir(src)):
        m = re.match(r'f_(\d+)\.(png|jpg)$', f) or re.match(r'still_([\d.]+)\.png$', f)
        if not m: continue
        n = int(m.group(1)) if f.startswith('f_') else int(round(float(m.group(1)) * fps))
        jobs.append((os.path.join(src, f), os.path.join(dst, f if f.endswith('.png') else f[:-4] + '.png'), n, params_at(n / fps, base, sched)))
    with ProcessPoolExecutor() as ex:
        list(ex.map(process, jobs, chunksize=4))
    print('lens', len(jobs), 'frames ->', dst)


if __name__ == '__main__':
    main()
