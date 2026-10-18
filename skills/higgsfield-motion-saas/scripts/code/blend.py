# Average sub-frames f_NNNNN_k.(jpg|png) -> f_NNNNN.png (motion blur). usage: python3 blend.py <subdir> <outdir>
import sys, os, glob, re
import numpy as np
from PIL import Image
from concurrent.futures import ProcessPoolExecutor
sub, out = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ('.', '.')
os.makedirs(out, exist_ok=True)
groups = {}
for f in glob.glob(os.path.join(sub, 'f_*_*.*')):
    m = re.match(r'f_(\d+)_(\d+)\.', os.path.basename(f))
    if m: groups.setdefault(m.group(1), []).append(f)
def job(item):
    n, fs = item
    acc = None
    for f in fs:
        a = np.asarray(Image.open(f).convert('RGB'), dtype=np.float32)
        acc = a if acc is None else acc + a
    Image.fromarray(np.clip(acc / len(fs) + 0.5, 0, 255).astype(np.uint8)).save(os.path.join(out, f'f_{n}.png'), compress_level=1)
    return n
if __name__ == '__main__':
    with ProcessPoolExecutor() as ex:
        list(ex.map(job, sorted(groups.items()), chunksize=8))
    print('blended', len(groups), 'frames ->', out)
