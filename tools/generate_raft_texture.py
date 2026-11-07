"""Generate the raft's texture maps (procedural, reproducible).

The raft polish pass (issue #5): the logs and lashings were flat PBR
colors and read as plain tubes up close. These are small albedo maps
that generate_raft.py embeds into raft.glb / raft2.glb:

  wood        a log's side: debarked driftwood — long grain streaks,
              fine grain lines that swirl around knots, dark drying
              checks running with the grain. u = around the log
              (tiles), v = along the whole log (0..1, no tiling).
              Knots are baked at (u, v) the geometry also bulges at,
              so a bump and its dark eye always coincide.
  endgrain    a log's cut end: growth rings warped off-center, a dark
              pith, a sapwood rim and radial checks. Planar UVs,
              center (0.5, 0.5), rim at radius 0.5.
  rope        three-strand twisted fiber. u = along the rope (tiles,
              integer twist count), v = around the tube (tiles).

`weathered` turns any of them into the Visitor's raft: grayer, salt
bloom in blotches, more and wider checks, fuzzier rope.

Same contract as generate_skin_texture.py: palette constants are
LINEAR floats sRGB-encoded here (the engine samples Rgba8UnormSrgb),
alpha stays 255, features >= 2 px and contrast kept low — the engine
builds no mipmaps and the cel post bands value anyway, so these should
read as material, not pattern. Texture names must never contain
"normal" (the engine uploads those as linear data).

Output: textures/raft_*.png (inspection) + functions importable by
        tools/generate_raft.py
Usage:  python tools/generate_raft_texture.py
"""

import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_skin_texture import _finish  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "textures")

WOOD_W, WOOD_H = 256, 512   # around x along
ENDGRAIN_SIZE = 128
ROPE_W, ROPE_H = 256, 64    # along x around
ROPE_TWISTS = 8             # strand twists per texture tile (u)


def noise2(h, w, cy, cx, seed, octaves=3):
    """Tiling anisotropic value noise in [0,1], h x w, with cy x cx
    lattice cells (the first octave). Wraps in both axes."""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w))
    amp_total = 0.0
    for o in range(octaves):
        ny, nx = cy * 2 ** o, cx * 2 ** o
        amp = 0.5 ** o
        lattice = rng.random((ny, nx))
        ty = np.linspace(0.0, ny, h, endpoint=False)
        tx = np.linspace(0.0, nx, w, endpoint=False)
        y0 = np.floor(ty).astype(int) % ny
        x0 = np.floor(tx).astype(int) % nx
        fy = (ty - np.floor(ty))[:, None]
        fx = (tx - np.floor(tx))[None, :]
        fy = fy * fy * (3 - 2 * fy)
        fx = fx * fx * (3 - 2 * fx)
        a = lattice[np.ix_(y0, x0)]
        b = lattice[np.ix_(y0, (x0 + 1) % nx)]
        c = lattice[np.ix_((y0 + 1) % ny, x0)]
        d = lattice[np.ix_((y0 + 1) % ny, (x0 + 1) % nx)]
        out += amp * (a * (1 - fx) * (1 - fy) + b * fx * (1 - fy)
                      + c * (1 - fx) * fy + d * fx * fy)
        amp_total += amp
    return out / amp_total


def _wrap_du(u, cu):
    d = np.abs(u - cu)
    return np.minimum(d, 1.0 - d)


def _salt_bloom(rgb, h, w, cy, cx, seed, strength):
    """Weathering: sun-bleach + dried-salt patches pulling toward a
    cool off-white, gated by low-frequency noise."""
    n = noise2(h, w, cy, cx, seed, octaves=3)
    m = np.clip((n - 0.56) / 0.16, 0.0, 1.0) ** 1.5 * strength
    salt = np.array([0.78, 0.78, 0.74])
    return rgb * (1.0 - m[..., None]) + salt[None, None, :] * m[..., None]


def gen_wood(base_rgb, seed, knots=(), weathered=False):
    """A log's side. knots: iterable of (u, v, radius_u) in UV space,
    radius in u units (v radius is scaled by the texel aspect)."""
    h, w = WOOD_H, WOOD_W
    rng = np.random.default_rng(seed)
    u = np.linspace(0.0, 1.0, w, endpoint=False)[None, :]
    v = np.linspace(0.0, 1.0, h, endpoint=False)[:, None]
    # v spans a ~2.3 m log while u spans a ~0.8 m circumference:
    # distances in v count ~2.9x more per unit.
    aspect = 2.9

    # Grain flow: warp u by slow noise, then swirl around each knot.
    warp = (noise2(h, w, 3, 2, seed + 1) - 0.5) * 0.06
    swirl = np.zeros((h, w))
    knot_mask = np.zeros((h, w))
    for (ku, kv, kr) in knots:
        du = _wrap_du(u, ku)
        sgn = np.sign(((u - ku + 0.5) % 1.0) - 0.5)
        dv = (v - kv) * aspect
        d2 = (du * du + dv * dv) / (kr * kr)
        # Lines bow away from the knot like water round a stone.
        swirl += sgn * kr * 0.9 * np.exp(-d2 * 0.35)
        knot_mask = np.maximum(knot_mask, np.exp(-d2 * 1.6))
    uu = u + warp + swirl

    # Broad streaks along the grain (stretched noise) + fine grain lines.
    streak = noise2(h, w, 2, 24, seed + 2, octaves=3)
    lines = 0.5 + 0.5 * np.sin(2 * np.pi * 36 * uu)
    lines = lines ** 6  # thin dark lines, mostly bright
    rgb = np.asarray(base_rgb, float)[None, None, :] * np.ones((h, w, 1))
    rgb = rgb * (1.0 + 0.16 * (streak - 0.5))[..., None]
    rgb = rgb * (1.0 - 0.10 * lines)[..., None]

    # Knots: a dark ringed eye.
    eye = np.clip(knot_mask * 1.6 - 0.6, 0.0, 1.0)
    ring = np.clip(1.0 - np.abs(knot_mask - 0.35) / 0.12, 0.0, 1.0)
    knot_col = np.asarray(base_rgb) * np.array([0.52, 0.45, 0.40])
    rgb = rgb * (1 - eye[..., None]) + knot_col[None, None, :] * eye[..., None]
    rgb = rgb * (1.0 - 0.18 * ring)[..., None]

    # Drying checks: thin dark cracks running with the grain.
    n_checks = 14 if weathered else 7
    for _ in range(n_checks):
        cu = rng.random()
        v0 = rng.uniform(0.0, 0.8)
        length = rng.uniform(0.08, 0.35 if not weathered else 0.5)
        width = rng.uniform(1.2, 2.2) / w * (1.6 if weathered else 1.0)
        along = np.clip((v - v0) / length, 0.0, 1.0)
        # Taper: open in the middle, closed at both ends; drift with warp.
        taper = np.sin(np.pi * along) * ((v >= v0) & (v <= v0 + length))
        du = _wrap_du(uu, cu + 0.004 * np.sin(v * 40))
        crack = np.clip(1.0 - du / (width * (0.4 + taper)), 0.0, 1.0) * taper
        rgb = rgb * (1.0 - 0.45 * crack)[..., None]

    if weathered:
        rgb = _salt_bloom(rgb, h, w, 6, 3, seed + 3, 0.35)
        # Rot shadow: low, damp-dark patches along the grain.
        damp = noise2(h, w, 4, 12, seed + 4, octaves=2)
        rgb = rgb * (1.0 - 0.14 * np.clip((damp - 0.55) / 0.2, 0.0, 1.0))[..., None]
    return _finish(rgb)


def gen_endgrain(base_rgb, seed, weathered=False):
    """A log's cut end, planar UVs centered at (0.5, 0.5)."""
    s = ENDGRAIN_SIZE
    rng = np.random.default_rng(seed)
    t = (np.arange(s) + 0.5) / s - 0.5
    x, y = np.meshgrid(t, t)
    # Off-center pith: trees grow lopsided toward the light.
    px, py = rng.uniform(-0.06, 0.06, 2)
    r = np.hypot(x - px, y - py)
    ang = np.arctan2(y - py, x - px)
    wob = (noise2(s, s, 4, 4, seed + 1) - 0.5) * 0.035
    rings = 0.5 + 0.5 * np.cos(2 * np.pi * 14 * (r + wob))
    rings = rings ** 4
    # End grain is lighter and warmer than the weathered side.
    base = np.asarray(base_rgb, float) * np.array([1.15, 1.08, 0.98])
    rgb = base[None, None, :] * (1.0 - 0.14 * rings)[..., None]
    pith = np.clip(1.0 - r / 0.04, 0.0, 1.0)
    rgb = rgb * (1.0 - 0.45 * pith)[..., None]
    rim = np.clip((np.hypot(x, y) - 0.40) / 0.08, 0.0, 1.0)
    rgb = rgb * (1.0 - 0.28 * rim)[..., None]
    # Radial checks from the pith outward.
    # Soft, wavering, and mostly from the rim inward (where wood dries
    # first) — crisp pith-to-rim lines read as glyphs under the cel post.
    for _ in range(4 if weathered else 2):
        a0 = rng.uniform(-np.pi, np.pi)
        inner = rng.uniform(0.12, 0.30)
        a_r = a0 + 0.08 * np.sin(r * 40 + a0)
        da = np.abs(np.angle(np.exp(1j * (ang - a_r)))) * np.maximum(r, 0.03)
        open_ = np.clip((r - inner) / (0.48 - inner), 0.0, 1.0)
        width = 0.004 + 0.006 * open_ * (1.4 if weathered else 1.0)
        crack = np.clip(1.0 - da / width, 0.0, 1.0) * (r > inner) * (r < 0.49)
        rgb = rgb * (1.0 - 0.32 * crack)[..., None]
    if weathered:
        rgb = _salt_bloom(rgb, s, s, 3, 3, seed + 3, 0.4)
    return _finish(rgb)


def gen_rope(base_rgb, seed, weathered=False):
    """Three twisted strands: bright crowns, dark grooves between."""
    h, w = ROPE_H, ROPE_W
    u = np.linspace(0.0, 1.0, w, endpoint=False)[None, :]
    v = np.linspace(0.0, 1.0, h, endpoint=False)[:, None]
    phase = (3 * v + ROPE_TWISTS * u) % 1.0
    crown = np.sin(np.pi * phase)          # 0 in the grooves, 1 on top
    shade = 0.70 + 0.30 * crown ** 0.6
    # Fibers: fine streaks running along each strand's lay.
    fiber_n = noise2(h, w, 16, 64, seed + 1, octaves=2)
    fiber = 0.5 + 0.5 * np.sin(2 * np.pi * (24 * v - 3 * ROPE_TWISTS * u)
                               + 6.0 * fiber_n)
    rgb = np.asarray(base_rgb, float)[None, None, :] * shade[..., None]
    rgb = rgb * (1.0 - 0.08 * fiber)[..., None]
    if weathered:
        fuzz = noise2(h, w, 16, 64, seed + 2, octaves=2)
        rgb = rgb * (0.88 + 0.24 * fuzz)[..., None]
        rgb = _salt_bloom(rgb, h, w, 2, 8, seed + 3, 0.35)
    return _finish(rgb)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    samples = {
        "wood": gen_wood((0.55, 0.42, 0.28), 1, knots=[(0.3, 0.4, 0.05)]),
        "wood_weathered": gen_wood((0.58, 0.55, 0.48), 1, knots=[(0.3, 0.4, 0.05)],
                                   weathered=True),
        "endgrain": gen_endgrain((0.55, 0.42, 0.28), 2),
        "endgrain_weathered": gen_endgrain((0.58, 0.55, 0.48), 2, weathered=True),
        "rope": gen_rope((0.78, 0.68, 0.48), 3),
        "rope_weathered": gen_rope((0.62, 0.56, 0.46), 3, weathered=True),
    }
    for name, img in samples.items():
        path = os.path.join(OUT, f"raft_{name}.png")
        Image.fromarray(img, "RGBA").save(path)
        print(f"wrote {path}")
