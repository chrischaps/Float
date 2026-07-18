"""Generate models/whale.glb — a stylized humpback for the M8 dusk breach.

Built for silhouette: at ~130 m the whale is a dark shape against the
sunset band (reference/water/whale-breaching-*.avif), so the read comes
from proportion, not detail. Overlapping ellipsoid segments give the
tapered body; the humpback signatures are the LONG pale pectoral fins
(one-third of body length) and the broad fluke. Origin at body center,
nose toward +Z, back toward +Y.

Output: models/whale.glb
Usage:  python tools/generate_whale.py
"""

import os

import numpy as np
import trimesh
from trimesh.visual.material import PBRMaterial

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
os.makedirs(OUT_DIR, exist_ok=True)

BODY_LENGTH = 13.0  # meters, adult humpback

# Dark slate back for the silhouette; pale fins/fluke undersides catch the
# last light the way the reference photo's spray does.
BACK_COLOR = (0.10, 0.12, 0.17, 1.0)
FIN_COLOR = (0.72, 0.76, 0.80, 1.0)


def pbr(mesh, color, roughness=0.7):
    mesh.visual = trimesh.visual.TextureVisuals(
        material=PBRMaterial(
            baseColorFactor=color,
            metallicFactor=0.0,
            roughnessFactor=roughness,
        )
    )
    return mesh


def transform(tx=0.0, ty=0.0, tz=0.0, rx=0.0, ry=0.0, rz=0.0):
    m = trimesh.transformations.euler_matrix(rx, ry, rz, "sxyz")
    m[:3, 3] = [tx, ty, tz]
    return m


def ellipsoid(sx, sy, sz, color, subdivisions=3):
    mesh = trimesh.creation.icosphere(subdivisions=subdivisions, radius=1.0)
    mesh.apply_scale([sx, sy, sz])
    return pbr(mesh, color)


parts = []

# ── Body: overlapping ellipsoids along Z (z, radius). Deeper than wide
#    (x squashed) — a whale in profile is a heavy teardrop. Segments are
#    stretched in Z well past their spacing so the hull reads as one
#    smooth mass, not beads. ─────────────────────────────────────────────
BODY_PROFILE = [
    (6.35, 0.42),  # rostrum tip
    (5.9, 0.72),
    (5.2, 1.02),
    (4.2, 1.32),
    (3.0, 1.55),
    (1.6, 1.72),   # girth peak, just behind the head
    (0.0, 1.65),
    (-1.6, 1.38),
    (-3.0, 1.05),
    (-4.2, 0.70),
    (-5.2, 0.46),
    (-6.0, 0.30),  # tail stock into the fluke
]
for z, r in BODY_PROFILE:
    seg = ellipsoid(r * 0.85, r, max(r * 1.5, 0.9), BACK_COLOR)
    seg.apply_transform(transform(tz=z))
    parts.append(seg)

# ── Fluke: two broad, thin, swept blades at the tail ───────────────────
for side in (-1.0, 1.0):
    blade = ellipsoid(1.7, 0.09, 0.75, BACK_COLOR)
    blade.apply_transform(
        transform(tx=side * 1.45, tz=-6.6, ry=side * np.deg2rad(-22.0))
    )
    parts.append(blade)

# ── Pectoral fins: the humpback signature — pale, one-third body length,
#    swept back and drooped ─────────────────────────────────────────────
for side in (-1.0, 1.0):
    fin = ellipsoid(2.05, 0.09, 0.42, FIN_COLOR)
    fin.apply_transform(
        transform(
            tx=side * 2.6,
            ty=-0.55,
            tz=2.2,
            ry=side * np.deg2rad(38.0),   # swept back
            rz=side * np.deg2rad(-16.0),  # drooped
        )
    )
    parts.append(fin)

# ── Dorsal: the stubby humpback bump-fin, seated into the back ─────────
dorsal = ellipsoid(0.13, 0.42, 0.60, BACK_COLOR)
dorsal.apply_transform(transform(ty=1.15, tz=-2.0, rx=np.deg2rad(-20.0)))
parts.append(dorsal)

scene = trimesh.Scene()
for i, part in enumerate(parts):
    scene.add_geometry(part, node_name=f"whale_part_{i}")
path = os.path.join(OUT_DIR, "whale.glb")
# include_normals: without it trimesh omits NORMAL and the engine flat-shades.
scene.export(path, include_normals=True)
b = scene.bounds
print(
    f"wrote {path}  ({len(parts)} parts)  "
    f"bounds x [{b[0][0]:.2f}, {b[1][0]:.2f}] "
    f"y [{b[0][1]:.2f}, {b[1][1]:.2f}] z [{b[0][2]:.2f}, {b[1][2]:.2f}]"
)
