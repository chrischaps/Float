"""Generate Float's particle textures (procedural, reproducible).

rain_drop.png — a soft radial dot: white with a gaussian alpha falloff.
On a normal billboard it reads as a round droplet/spray puff; with the
particle system's velocity stretch it smears into a clean rain streak.
The color is pure white so the emitter's color_start/color_end tint does
all the work (weather.rhai dims rain with the live sun).

Output: textures/*.png
Usage:  python tools/generate_textures.py
"""

import os

import numpy as np
from PIL import Image

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "textures")
os.makedirs(OUT, exist_ok=True)


def gen_rain_drop(size=64):
    r = np.linspace(-1, 1, size)
    xx, yy = np.meshgrid(r, r)
    d2 = xx * xx + yy * yy
    # Gaussian core with a soft shoulder; hard zero at the quad edge so
    # alpha-blend never shows the billboard's square outline.
    alpha = np.exp(-d2 * 4.2) * np.clip(1.0 - d2, 0.0, 1.0)
    img = np.zeros((size, size, 4), dtype=np.uint8)
    img[..., 0:3] = 255
    img[..., 3] = (alpha * 255).astype(np.uint8)
    path = os.path.join(OUT, "rain_drop.png")
    Image.fromarray(img, "RGBA").save(path)
    print(f"wrote {path}")


if __name__ == "__main__":
    gen_rain_drop()
