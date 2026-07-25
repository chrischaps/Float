"""Generate the body's texture maps (procedural, reproducible).

Replaces the body's flat vertex-color materials with small tiling
albedo maps — the "+ texture" half of the body detail pass:

  skin_arm       base skin + low-contrast mottle
  skin_thigh     skin + knee blush toward the distal (v→1) end
  skin_calf      darker lower-leg skin + sparse hair speckle + ankle shade
  skin_hand      skin + knuckle darkening laid out for the top-down
                 planar hand UVs
  skin_foot      skin + toe-crease shading for the planar foot UVs
  fabric_shorts  crossed-thread weave over the shorts blue
  fabric_tee     finer jersey knit over the tee off-white

Every pattern tiles in BOTH axes with integer cycle counts (the body's
capsule UVs wrap cylindrically; the sampler repeats). Contrast stays
low and features stay >= 2 px: the engine builds no mipmaps, and the
cel post softens detail anyway — these maps should read as material,
not pattern.

Color math: generate_body.py's palette constants are LINEAR floats
(they were glTF baseColorFactor values). PNGs are sampled as sRGB by
the engine (Rgba8UnormSrgb), so bases are sRGB-ENCODED here — a bare
1/2.2 pow would shift the body's established colors. Alpha stays 255
everywhere (alpha < 1 would push the mesh onto the transparent path).

Output: textures/body_*.png (inspection) + arrays importable by
        tools/generate_body.py (which embeds them into body.glb)
Usage:  python tools/generate_skin_texture.py
"""

import os

import numpy as np
from PIL import Image

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "textures")
os.makedirs(OUT, exist_ok=True)


def srgb_encode(linear):
    a = np.clip(linear, 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(a, 1.0 / 2.4) - 0.055)


def value_noise(size, cells, seed, octaves=2):
    """Tiling value noise in [0,1]: random lattice, bilinear upsample
    with wraparound, a couple of octaves."""
    rng = np.random.default_rng(seed)
    out = np.zeros((size, size))
    amp_total = 0.0
    for o in range(octaves):
        n = cells * (2 ** o)
        amp = 0.5 ** o
        lattice = rng.random((n, n))
        # Bilinear sample the lattice at every texel, wrapping.
        t = np.linspace(0.0, n, size, endpoint=False)
        i0 = np.floor(t).astype(int) % n
        i1 = (i0 + 1) % n
        f = t - np.floor(t)
        # rows (y), cols (x)
        a = lattice[np.ix_(i0, i0)]
        b = lattice[np.ix_(i0, i1)]
        c = lattice[np.ix_(i1, i0)]
        d = lattice[np.ix_(i1, i1)]
        fx = f[None, :]
        fy = f[:, None]
        # smoothstep the lerp factors — pure bilinear looks gridded
        fx = fx * fx * (3 - 2 * fx)
        fy = fy * fy * (3 - 2 * fy)
        layer = (a * (1 - fx) * (1 - fy) + b * fx * (1 - fy)
                 + c * (1 - fx) * fy + d * fx * fy)
        out += amp * layer
        amp_total += amp
    return out / amp_total


def _finish(rgb_linear):
    """Linear float HxWx3 → HxWx4 uint8 sRGB PNG array (alpha 255)."""
    srgb = srgb_encode(rgb_linear)
    img = np.empty((*srgb.shape[:2], 4), dtype=np.uint8)
    img[..., :3] = np.round(srgb * 255).astype(np.uint8)
    img[..., 3] = 255
    return img


def _base(base_rgb, size, seed, mottle=0.04, cells=6):
    """Base tone with low-contrast value-noise mottling (linear space)."""
    noise = value_noise(size, cells, seed)
    mod = 1.0 + (noise[..., None] - 0.5) * 2.0 * mottle
    return np.asarray(base_rgb, float)[None, None, :] * mod


def _soft_spot(size, cu, cv, ru, rv):
    """Tiling soft elliptical mask centered at (cu, cv) in UV [0,1]."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    du = np.abs(u[None, :] - cu)
    du = np.minimum(du, 1.0 - du) / ru
    dv = np.abs(u[:, None] - cv)
    dv = np.minimum(dv, 1.0 - dv) / rv
    d2 = du * du + dv * dv
    return np.clip(1.0 - d2, 0.0, 1.0) ** 2


def _blush(rgb, mask, strength):
    """Ruddier and slightly darker where mask is high (knees, ankles)."""
    m = (mask * strength)[..., None]
    tint = rgb * np.array([1.10, 0.94, 0.90])[None, None, :] * 0.96
    return rgb * (1.0 - m) + tint * m


def gen_skin(base_rgb, size=256, seed=1, speckle=0.0, blush_v=None,
             blush_strength=0.5):
    """General skin: mottle, optional hair speckle (density fades
    toward v=0 and v=1 so it thins at the joints), optional blush band
    centered at blush_v."""
    rgb = _base(base_rgb, size, seed)
    if speckle > 0.0:
        rng = np.random.default_rng(seed + 77)
        count = int(size * size * speckle)
        us = rng.integers(0, size, count)
        vs = rng.integers(0, size, count)
        # Fade density toward the v ends: keep a speckle with
        # probability shaped like a raised cosine over v.
        vfrac = vs / size
        keep = rng.random(count) < (0.15 + 0.85 * np.sin(np.pi * vfrac) ** 2)
        us, vs = us[keep], vs[keep]
        dark = np.array([0.80, 0.78, 0.82])
        for du in (0, 1):  # 2-px-wide dots — mip-less minification safe
            rgb[(vs) % size, (us + du) % size] *= dark
    if blush_v is not None:
        band = _soft_spot(size, 0.5, blush_v, 0.75, 0.30) \
            + _soft_spot(size, 0.0, blush_v, 0.75, 0.30)
        rgb = _blush(rgb, np.clip(band, 0.0, 1.0), blush_strength)
    return _finish(rgb)


def gen_hand_skin(base_rgb, size=256, seed=5):
    """Skin for the top-down planar hand UVs: u across the hand,
    v wrist→fingertips. Knuckle darkening where the knuckle bumps sit
    (v≈0.55), slight warmth at the fingertips."""
    rgb = _base(base_rgb, size, seed, mottle=0.03, cells=5)
    for cu in (0.20, 0.40, 0.60, 0.80):
        rgb = _blush(rgb, _soft_spot(size, cu, 0.55, 0.07, 0.05), 0.35)
    tip_band = _soft_spot(size, 0.5, 0.92, 0.75, 0.10) \
        + _soft_spot(size, 0.0, 0.92, 0.75, 0.10)
    rgb = _blush(rgb, np.clip(tip_band, 0.0, 1.0), 0.25)
    return _finish(rgb)


def gen_foot_skin(base_rgb, size=256, seed=6):
    """Skin for the planar foot UVs: v heel→toes. A toe-crease shade
    band where the toes meet the foot (v≈0.72), warmer toes."""
    rgb = _base(base_rgb, size, seed, mottle=0.03, cells=5)
    crease = _soft_spot(size, 0.5, 0.72, 0.75, 0.05) \
        + _soft_spot(size, 0.0, 0.72, 0.75, 0.05)
    rgb = rgb * (1.0 - 0.10 * np.clip(crease, 0.0, 1.0))[..., None]
    tip_band = _soft_spot(size, 0.5, 0.88, 0.75, 0.10) \
        + _soft_spot(size, 0.0, 0.88, 0.75, 0.10)
    rgb = _blush(rgb, np.clip(tip_band, 0.0, 1.0), 0.30)
    return _finish(rgb)


def gen_fabric(base_rgb, size=256, seed=9, weave_n=24, style="weave"):
    """Cloth: 'weave' = crossed thread grid (shorts), 'knit' = fine
    vertical jersey ribs (tee). Noise-warped so the threads aren't
    ruler-straight; integer cycle counts so it tiles."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    uu, vv = np.meshgrid(u, u)
    warp = (value_noise(size, 4, seed) - 0.5) * 0.008
    if style == "weave":
        tu = np.sin(2 * np.pi * weave_n * (uu + warp))
        tv = np.sin(2 * np.pi * weave_n * (vv - warp))
        pattern = 0.5 * (tu + tv)          # crossed threads
        contrast = 0.045
    else:  # knit: dominant vertical ribs with a half-frequency stagger
        rib = np.sin(2 * np.pi * weave_n * (uu + warp))
        stag = 0.35 * np.sin(2 * np.pi * weave_n * 2 * (vv + warp))
        pattern = rib * (0.8 + stag)
        contrast = 0.035
    rgb = _base(base_rgb, size, seed, mottle=0.02, cells=4)
    rgb = rgb * (1.0 + contrast * pattern)[..., None]
    return _finish(rgb)


# Palette mirror (linear, = generate_body.py's constants).
SKIN = (0.82, 0.60, 0.44)
SKIN_LOWER = (0.76, 0.55, 0.40)
SHORTS = (0.16, 0.20, 0.38)
FOOT = (0.80, 0.58, 0.43)
TEE = (0.85, 0.82, 0.75)


def body_textures():
    """name → HxWx4 uint8 array. Imported by generate_body.py."""
    return {
        "skin_arm": gen_skin(SKIN, seed=11),
        "skin_thigh": gen_skin(SKIN, seed=12, blush_v=0.88, blush_strength=0.45),
        "skin_calf": gen_skin(SKIN_LOWER, seed=13, speckle=0.010,
                              blush_v=0.90, blush_strength=0.35),
        "skin_hand": gen_hand_skin(SKIN, seed=14),
        "skin_foot": gen_foot_skin(FOOT, seed=15),
        "fabric_shorts": gen_fabric(SHORTS, seed=16, weave_n=24, style="weave"),
        "fabric_tee": gen_fabric(TEE, seed=17, weave_n=32, style="knit"),
    }


if __name__ == "__main__":
    for name, img in body_textures().items():
        path = os.path.join(OUT, f"body_{name}.png")
        Image.fromarray(img, "RGBA").save(path)
        print(f"wrote {path}")
