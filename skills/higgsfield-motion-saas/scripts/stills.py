"""Wait for PNG stills written by SM.shoot (AE writes them asynchronously, 16-bit), convert them to
8-bit JPGs and build one labelled contact sheet you can open with the Read tool.

usage: python3 stills.py <folder> [--expect N] [--timeout 120] [--cols 4] [--width 480] [--sheet <out.jpg>]
"""
import os
import sys
import time

from PIL import Image, ImageDraw


def arg(name, default):
    a = sys.argv
    return type(default)(a[a.index(name) + 1]) if name in a else default


def wait_pngs(folder, expect, timeout):
    t0, last = time.time(), None
    while time.time() - t0 < timeout:
        files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".png"))
        sizes = [os.path.getsize(os.path.join(folder, f)) for f in files]
        state = (len(files), sum(sizes))
        if files and (expect == 0 or len(files) >= expect) and state == last and all(sizes):
            return files
        last = state
        time.sleep(1.0)
    raise SystemExit("stills.py: timed out waiting for %s PNGs in %s" % (expect or "any", folder))


def main():
    folder = os.path.abspath(sys.argv[1])
    files = wait_pngs(folder, arg("--expect", 0), arg("--timeout", 120))
    jdir = os.path.join(folder, "jpg")
    os.makedirs(jdir, exist_ok=True)
    width, cols = arg("--width", 480), arg("--cols", 4)
    thumbs = []
    for f in files:
        im = Image.open(os.path.join(folder, f))
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA") if "A" in im.mode else im.convert("RGB")
        im = im.convert("RGB")
        im.save(os.path.join(jdir, os.path.splitext(f)[0] + ".jpg"), quality=90)
        th = im.resize((width, round(im.height * width / im.width)))
        ImageDraw.Draw(th).text((6, 4), os.path.splitext(f)[0], fill=(0, 255, 0))
        thumbs.append(th)
    rows = (len(thumbs) + cols - 1) // cols
    h = thumbs[0].height
    sheet = Image.new("RGB", (cols * width + (cols + 1) * 4, rows * h + (rows + 1) * 4), (20, 20, 20))
    for i, th in enumerate(thumbs):
        sheet.paste(th, (4 + (i % cols) * (width + 4), 4 + (i // cols) * (h + 4)))
    out = arg("--sheet", os.path.join(folder, "sheet.jpg"))
    sheet.save(out, quality=88)
    print(out)
    print("\n".join(os.path.join(jdir, os.path.splitext(f)[0] + ".jpg") for f in files))


if __name__ == "__main__":
    main()
