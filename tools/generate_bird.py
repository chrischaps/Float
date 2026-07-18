"""Generate models/bird.glb — a distant seabird glyph for the M8 dawn pass.

At 100+ meters a bird is a rocking V against the sunrise; this is that V
given just enough body to survive a curious look: small teardrop body,
two long swept blades with a shallow dihedral, a hint of tail. Albatross
proportions (big span) so the glyph reads at range. Origin at the body,
nose toward +Z, wings along X.

Output: models/bird.glb
Usage:  python tools/generate_bird.py
"""

import os

import numpy as np
import trimesh
from trimesh.visual.material import PBRMaterial

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
os.makedirs(OUT_DIR, exist_ok=True)

# Warm-dark dawn silhouette (lit by the TOD sun/ambient like everything).
BODY_COLOR = (0.16, 0.14, 0.15, 1.0)


def pbr(mesh, color, roughness=0.8):
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


def ellipsoid(sx, sy, sz, subdivisions=2):
    mesh = trimesh.creation.icosphere(subdivisions=subdivisions, radius=1.0)
    mesh.apply_scale([sx, sy, sz])
    return pbr(mesh, BODY_COLOR)


parts = []

# Body + head-hint + tail
body = ellipsoid(0.10, 0.09, 0.34)
parts.append(body)
head = ellipsoid(0.06, 0.06, 0.10)
head.apply_transform(transform(tz=0.36, ty=0.02))
parts.append(head)
tail = ellipsoid(0.09, 0.02, 0.16)
tail.apply_transform(transform(tz=-0.36))
parts.append(tail)

# Wings: long swept blades, shallow dihedral — 2.6 m span
for side in (-1.0, 1.0):
    wing = ellipsoid(0.66, 0.018, 0.14)
    wing.apply_transform(
        transform(
            tx=side * 0.62,
            ty=0.06,
            ry=side * np.deg2rad(18.0),   # swept back
            rz=side * np.deg2rad(-12.0),  # dihedral
        )
    )
    parts.append(wing)

scene = trimesh.Scene()
for i, part in enumerate(parts):
    scene.add_geometry(part, node_name=f"bird_part_{i}")
path = os.path.join(OUT_DIR, "bird.glb")
# include_normals: without it trimesh omits NORMAL and the engine flat-shades.
scene.export(path, include_normals=True)
b = scene.bounds
print(f"wrote {path}  span x [{b[0][0]:.2f}, {b[1][0]:.2f}] z [{b[0][2]:.2f}, {b[1][2]:.2f}]")
