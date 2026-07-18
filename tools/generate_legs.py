"""Generate models/legs.glb — the player's legs, seated on the raft edge.

Slightly male: slim, navy shorts, warm tan skin with a subtly darker,
speckle-toned lower leg (reads as light hair at this stylization level).
Origin is at the hip on the deck; knees ride slightly ABOVE the hips
(low-dock sit — deck is only 0.26 m over the water), calves hang, feet
trail in the water. The raised knees are deliberate first-person
framing: they crest into the bottom of the seated camera's view, which
is what sells "this is my body" in the periphery. Swappable later:
anything that exports a GLB with the same origin/pose can replace this
file.

Output: models/legs.glb
Usage:  python tools/generate_legs.py
"""

import os

import numpy as np
import trimesh
from trimesh.visual.material import PBRMaterial

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
os.makedirs(OUT_DIR, exist_ok=True)

SKIN = (0.82, 0.60, 0.44, 1.0)
SKIN_LOWER = (0.76, 0.55, 0.40, 1.0)   # calves: hair-shadowed tone
SHORTS = (0.16, 0.20, 0.38, 1.0)       # navy
FOOT = (0.80, 0.58, 0.43, 1.0)

THIGH_R, THIGH_LEN = 0.072, 0.40
CALF_R, CALF_LEN = 0.055, 0.42
LEG_X = 0.115                          # half-distance between legs

THIGH_DROP = np.deg2rad(-4)            # thigh angle below horizontal; negative = knees raised
CALF_SWING = np.deg2rad(12)            # calves hang slightly forward


def pbr(mesh, color, roughness=0.9):
    mesh.visual = trimesh.visual.TextureVisuals(
        material=PBRMaterial(
            baseColorFactor=color, metallicFactor=0.0, roughnessFactor=roughness
        )
    )
    return mesh


def transform(tx=0.0, ty=0.0, tz=0.0, rx=0.0, ry=0.0, rz=0.0):
    m = trimesh.transformations.euler_matrix(rx, ry, rz, "sxyz")
    m[:3, 3] = [tx, ty, tz]
    return m


def capsule_between(p0, p1, radius, color):
    """Capsule from p0 to p1 (numpy arrays)."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    vec = p1 - p0
    length = np.linalg.norm(vec)
    cap = trimesh.creation.capsule(radius=radius, height=length, count=[32, 32])
    # capsule extends along +Z from origin; align to vec
    align = trimesh.geometry.align_vectors([0, 0, 1], vec / length)
    cap.apply_transform(align)
    cap.apply_translation(p0 + vec * 0.5)
    return pbr(cap, color)


parts = []

for side in (-1.0, 1.0):
    x = side * LEG_X

    # Hip pivot sits at the model origin height; thigh runs +Z and down.
    hip = np.array([x, 0.02, -0.06])
    knee = hip + np.array(
        [side * 0.015, -np.sin(THIGH_DROP) * THIGH_LEN, np.cos(THIGH_DROP) * THIGH_LEN]
    )
    ankle = knee + np.array(
        [0.0, -np.cos(CALF_SWING) * CALF_LEN, np.sin(CALF_SWING) * CALF_LEN]
    )

    parts.append(capsule_between(hip, knee, THIGH_R, SKIN))
    parts.append(capsule_between(knee, ankle, CALF_R, SKIN_LOWER))

    # Foot: stylized rounded block pointing forward (+Z), toes dipped
    # toward the water (the raised knees leave only the feet submerged).
    foot = trimesh.creation.box(extents=[0.085, 0.055, 0.22])
    foot.apply_transform(transform(
        tx=ankle[0], ty=ankle[1] - 0.015, tz=ankle[2] + 0.07, rx=np.deg2rad(-14)
    ))
    parts.append(pbr(foot, FOOT))

    # Shorts cuff wrapping the upper thigh.
    cuff_len = 0.20
    c0 = hip + np.array([0.0, 0.012, 0.0])
    cvec = (knee - hip) / np.linalg.norm(knee - hip)
    c1 = c0 + cvec * cuff_len
    parts.append(capsule_between(c0, c1, THIGH_R + 0.022, SHORTS))

# Hip/seat block of the shorts, resting on the deck.
seat = trimesh.creation.box(extents=[2 * (LEG_X + 0.10), 0.16, 0.26])
seat.apply_transform(transform(ty=0.03, tz=-0.16))
parts.append(pbr(seat, SHORTS))

scene = trimesh.Scene()
for i, part in enumerate(parts):
    scene.add_geometry(part, node_name=f"leg_part_{i}")
path = os.path.join(OUT_DIR, "legs.glb")
# include_normals: without it trimesh omits NORMAL and the engine flat-shades.
scene.export(path, include_normals=True)
b = scene.bounds
print(f"wrote {path}  bounds y [{b[0][1]:.2f}, {b[1][1]:.2f}] z [{b[0][2]:.2f}, {b[1][2]:.2f}]")
