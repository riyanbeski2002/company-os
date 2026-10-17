"""Labelled contact sheet from a folder of frames/stills (rendered frames f_NNNNN.png, stills still_<t>.png, or extract.swift output).
usage:
  python3 sheet.py <dir> <out.jpg> [--times 1.0,1.5,2.0 --fps 30] [--range f0 f1 step] [--cols 4] [--width 480] [--every n]
  no --times/--range → every image in the folder (or every n-th), sorted by name.
"""
import os, re, sys
from PIL import Image, ImageDraw


def arg(name, default, n=1):
    a = sys.argv
    if name not in a: return default
    i = a.index(name)
    return a[i + 1] if n == 1 else a[i + 1:i + 1 + n]


def main():
    d, out = sys.argv[1], sys.argv[2]
    fps = float(arg('--fps', '30')); cols = int(arg('--cols', '4')); w = int(arg('--width', '480'))
    items = []
    if arg('--times', None):
        for t in [float(x) for x in arg('--times', '').split(',')]:
            items.append((os.path.join(d, f'f_{int(round(t * fps)):05d}.png'), f'{t:.2f}s'))
    elif arg('--range', None):
        f0, f1, st = [int(x) for x in arg('--range', None, 3)]
        items = [(os.path.join(d, f'f_{n:05d}.png'), f'{n / fps:.2f}s') for n in range(f0, f1 + 1, st)]
    else:
        fs = sorted(f for f in os.listdir(d) if f.lower().endswith(('.png', '.jpg')) and not f.startswith('sheet'))
        fs = fs[::int(arg('--every', '1'))]
        for f in fs:
            m = re.match(r'still_([\d.]+)\.', f) or re.match(r'f_\d+_([\d.]+)\.jpg', f)
            items.append((os.path.join(d, f), (m.group(1) + 's') if m else os.path.splitext(f)[0]))
    items = [(p, lab) for p, lab in items if os.path.exists(p)]
    if not items: sys.exit('sheet.py: no frames found in ' + d)
    im0 = Image.open(items[0][0]); h = round(im0.height * w / im0.width)
    rows = (len(items) + cols - 1) // cols
    S = Image.new('RGB', (cols * w, rows * (h + 22)), '#1b1b1b'); dr = ImageDraw.Draw(S)
    for i, (p, lab) in enumerate(items):
        x, y = (i % cols) * w, (i // cols) * (h + 22)
        S.paste(Image.open(p).convert('RGB').resize((w, h)), (x, y + 22)); dr.text((x + 6, y + 5), lab, fill='white')
    S.save(out, quality=85); print(out)


if __name__ == '__main__':
    main()
