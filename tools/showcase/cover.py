"""Time-slice cover: one instant of sea, cut into strips lit at successive hours.

    python tools/showcase/cap.py slice_0 ... slice_7 --out renders/showcase/cover
    python tools/showcase/cover.py [--src renders/showcase/cover] [--out cover.jpg]

The slices (shots.py COVER_HOURS) share game time, camera and every random
draw that could move the water or the body, so the waves and the raft line up
exactly across the cuts and only the light changes: dawn on the left, stars on
the right, after the time-slice photographs of a skyline across a day.
"""

import argparse
import glob
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(ROOT, "renders", "showcase", "cover"))
    ap.add_argument("--out", default=os.path.join(ROOT, "renders", "showcase", "cover.jpg"))
    ap.add_argument("--size", default="1920x1080")
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.src, "slice_*.png")),
                   key=lambda p: int(p.rsplit("_", 1)[1].split(".")[0]))
    ims = [Image.open(p).convert("RGB") for p in files]
    W, H = ims[0].size
    n = len(ims)
    out = Image.new("RGB", (W, H))
    for i, im in enumerate(ims):
        x0, x1 = round(i * W / n), round((i + 1) * W / n)
        out.paste(im.crop((x0, 0, x1, H)), (x0, 0))
    w, h = (int(v) for v in a.size.split("x"))
    out.resize((w, h), Image.LANCZOS).save(a.out, quality=90, optimize=True)
    print("%d slices -> %s" % (n, a.out))


if __name__ == "__main__":
    main()
