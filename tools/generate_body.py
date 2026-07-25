"""Generate models/body.glb — the player's rigged seated body (skeletal M6).

Replaces the static legs.glb with a skinned body: pelvis root, spine,
both legs (thigh/calf/foot) and both arms (upper/forearm/hand), plus
three embedded skeletal clips:

  idle         4.8 s loop — calves pendulum in the water, arm micro-sway
  scoot_right  1.4 s      — right leg opens right, left arm plants and
                            takes weight, pelvis lifts, body settles
  scoot_left   1.4 s      — mirror

Rigging approach: RIGID skinning (every vertex 100% one joint) — at this
stylization level segmented capsules ARE the look, and it keeps the
authoring fully procedural. The bind pose IS the seated pose (same
proportions and raised-knee framing contract as generate_legs.py), all
joint rotations identity at bind, so clip rotations are clean deltas in
model space. Inverse bind matrices are pure translations.

Root motion carries ONLY the pelvis lift and a small lateral lean — the
actual travel along the deck comes from the entity transform
(seat_camera.rhai's perimeter path stays the single source of truth for
position). Clip durations are mirrored by body.rhai (the engine has no
skeletal on_animation_end event), so keep STEP_TIME in sync there.

Output: models/body.glb
Usage:  python tools/generate_body.py
"""

import io
import os
import struct
import sys

import numpy as np
import trimesh
from PIL import Image as PILImage
from pygltflib import (
    GLTF2, Scene, Node, Mesh, Primitive, Attributes, Skin, Material,
    PbrMetallicRoughness, Animation, AnimationChannel, AnimationChannelTarget,
    AnimationSampler, Buffer, BufferView, Accessor,
    Image as GltfImage, Texture, TextureInfo, Sampler as GltfSampler,
    ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER, FLOAT, UNSIGNED_INT, UNSIGNED_SHORT,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_skin_texture import body_textures  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
os.makedirs(OUT_DIR, exist_ok=True)

# ── Palette (matches generate_legs.py + a muted tee for the torso) ──────
SKIN = (0.82, 0.60, 0.44, 1.0)
SKIN_LOWER = (0.76, 0.55, 0.40, 1.0)
SHORTS = (0.16, 0.20, 0.38, 1.0)
FOOT = (0.80, 0.58, 0.43, 1.0)
TEE = (0.85, 0.82, 0.75, 1.0)

# ── Seated proportions (generate_legs.py contract) ──────────────────────
THIGH_R, THIGH_LEN = 0.072, 0.40
CALF_R, CALF_LEN = 0.055, 0.42
LEG_X = 0.115
THIGH_DROP = np.deg2rad(-4)
CALF_SWING = np.deg2rad(12)

STEP_TIME = 1.4   # scoot clip duration — body.rhai mirrors this
IDLE_TIME = 4.8

# Micro-sway damp for arms whose hands rest ON the thighs: the contact
# supports the hand, so it drifts less than a free arm — and the reduced
# excursion is what keeps the palm from dipping into the shorts cuff
# (check_clearance() sweeps these extremes; keep it in sync).
REST_SWAY_SCALE = 0.30


def d2r(d):
    return np.deg2rad(d)


# ── Skeleton: (name, parent, global bind position) ──────────────────────
# Standard humanoid layout (Hips → Spine → Chest → Clavicle → UpperArm;
# legs branch from Hips at the anatomical hip sockets):
#   - the root sits at the TOP of the pelvis near the sacrum, toward the
#     back of the mesh, and the spine runs near the back — not centered;
#   - the leg joints do NOT meet at the pelvis center: they sit at the
#     femoral heads — lateral (about halfway out to the pelvis edge),
#     FORWARD of the spine base, mid-pelvis height;
#   - arms hang from clavicles placed near the body center (that's where
#     the real rotation happens), with the shoulder ball outboard.
# Relaxed dock-sit pose: knees splayed wider than the hips, calves
# dropping, feet drifting back inward under the knees.
# Legs like the ledge-sit reference (reference/raft): near-PARALLEL
# thighs with a clear gap running their whole length — not a V fanning
# out from the crotch. The gap comes from the socket spacing (wide, per
# the rigging-wiki "run it to the outside" rule — on this chunky
# stylized body the sockets carry outward with the mesh), not from
# splaying the knees.
LEG_X = 0.13         # hip socket lateral offset — clears the shorts cuffs
KNEE_SPLAY = 0.03    # knees barely wider than the sockets (parallel read)
ANKLE_TUCK = 0.01    # feet nearly under the knees


def leg_points(side):
    # Hip sockets: forward of the spine base, mid-pelvis height.
    hip = np.array([side * LEG_X, 0.0, -0.05])
    knee = hip + np.array(
        [side * KNEE_SPLAY, -np.sin(THIGH_DROP) * THIGH_LEN, np.cos(THIGH_DROP) * THIGH_LEN]
    )
    ankle = knee + np.array(
        [-side * ANKLE_TUCK, -np.cos(CALF_SWING) * CALF_LEN, np.sin(CALF_SWING) * CALF_LEN]
    )
    return hip, knee, ankle


HIP_L, KNEE_L, ANKLE_L = leg_points(+1.0)
HIP_R, KNEE_R, ANKLE_R = leg_points(-1.0)
SHOULDER = 0.20
SHOULDER_Z = -0.15   # shoulder balls sit back with the (reclined) chest
CLAV_L = np.array([+0.035, 0.295, -0.13])   # near center, slightly front
CLAV_R = np.array([-0.035, 0.295, -0.13])
ELBOW_L = np.array([+0.235, 0.03, -0.03])
ELBOW_R = np.array([-0.235, 0.03, -0.03])
# Wrists rest ON TOP of the thighs, pulled back toward the hip and up:
# the legs_rock layer lifts the knee under statically-posed hands, and
# the old rest ([0.155, 0.11, 0.17]) started ~1.5 cm INSIDE the thigh
# capsule (−2.8 cm at peak knee lift, worse against the fatter shorts
# cuff). The palm sits just above the cuff apex with a small outboard
# roll (HAND_ROLL) following the curve; check_clearance() guards the
# rest pose, the knee lift + sway extremes, and the scoot plant path.
WRIST_L = np.array([+0.165, 0.158, 0.12])
WRIST_R = np.array([-0.165, 0.158, 0.12])
HAND_ROLL = 12.0  # deg, outboard edge drops toward the thigh's curve

JOINTS = [
    # name          parent         global bind position
    # Hips root: top of the pelvis by the sacrum, toward the back.
    ("root",        None,          np.array([0.0, 0.06, -0.17])),
    ("spine",       "root",        np.array([0.0, 0.17, -0.175])),
    ("chest",       "spine",       np.array([0.0, 0.26, -0.165])),
    ("thigh_l",     "root",        HIP_L),
    ("calf_l",      "thigh_l",     KNEE_L),
    ("foot_l",      "calf_l",      ANKLE_L),
    ("thigh_r",     "root",        HIP_R),
    ("calf_r",      "thigh_r",     KNEE_R),
    ("foot_r",      "calf_r",      ANKLE_R),
    ("clavicle_l",  "chest",       CLAV_L),
    ("upper_arm_l", "clavicle_l",  np.array([+SHOULDER, 0.29, SHOULDER_Z])),
    ("forearm_l",   "upper_arm_l", ELBOW_L),
    ("hand_l",      "forearm_l",   WRIST_L),
    ("clavicle_r",  "chest",       CLAV_R),
    ("upper_arm_r", "clavicle_r",  np.array([-SHOULDER, 0.29, SHOULDER_Z])),
    ("forearm_r",   "upper_arm_r", ELBOW_R),
    ("hand_r",      "forearm_r",   WRIST_R),
    # Camera anchor: the "center eye". No geometry — seat_camera.rhai
    # follows this joint (via the engine bone_probe), so any clip that
    # moves the spine/chest chain is FELT in the first-person camera.
    # Bind position = exactly where the legacy fixed-offset eye sat.
    ("eye",         "chest",       np.array([0.0, 0.53, -0.07])),
]
JIDX = {name: i for i, (name, _, _) in enumerate(JOINTS)}


# ── Mesh parts: rigid capsule segments weighted to one joint each ───────
def capsule_between(p0, p1, radius):
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    vec = p1 - p0
    length = np.linalg.norm(vec)
    cap = trimesh.creation.capsule(radius=radius, height=length, count=[24, 24])
    align = trimesh.geometry.align_vectors([0, 0, 1], vec / length)
    cap.apply_transform(align)
    cap.apply_translation(p0 + vec * 0.5)
    return cap


def box_at(extents, tx=0.0, ty=0.0, tz=0.0, rx=0.0, ry=0.0):
    b = trimesh.creation.box(extents=extents)
    m = trimesh.transformations.euler_matrix(rx, ry, 0.0, "sxyz")
    m[:3, 3] = [tx, ty, tz]
    b.apply_transform(m)
    return b


def tapered_capsule_between(p0, p1, r0, r1, count=(16, 16)):
    """Capsule p0→p1 whose cross-section eases from r0 (at p0) to r1
    (at p1) — breaks the uniform-tube read: forearms thin toward the
    wrist, calves toward the ankle. Built as an r0 capsule with the
    verts scaled radially along the axis; the far cap squashes into a
    slight ellipsoid, which reads organic at this stylization."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    vec = p1 - p0
    length = np.linalg.norm(vec)
    cap = trimesh.creation.capsule(radius=r0, height=length, count=list(count))
    v = cap.vertices.copy()
    z0, z1 = v[:, 2].min(), v[:, 2].max()
    f = (v[:, 2] - z0) / (z1 - z0)
    scale = 1.0 + (r1 / r0 - 1.0) * f
    v[:, 0] *= scale
    v[:, 1] *= scale
    cap = trimesh.Trimesh(vertices=v, faces=cap.faces, process=False)
    align = trimesh.geometry.align_vectors([0, 0, 1], vec / length)
    cap.apply_transform(align)
    cap.apply_translation(p0 + vec * 0.5)
    return cap


def sphere_at(radius, center, squash_dir=None, squash=1.0):
    """Icosphere, optionally flattened along squash_dir (kneecaps)."""
    s = trimesh.creation.icosphere(subdivisions=2, radius=radius)
    if squash_dir is not None and squash != 1.0:
        d = np.asarray(squash_dir, float)
        d = d / np.linalg.norm(d)
        v = s.vertices.copy()
        proj = v @ d
        v -= np.outer(proj * (1.0 - squash), d)
        s = trimesh.Trimesh(vertices=v, faces=s.faces, process=False)
    s.apply_translation(np.asarray(center, float))
    return s


def ring_at(major_r, minor_r, center, axis):
    """Thin torus hem ring perpendicular to axis (sleeve/cuff edges)."""
    ring = trimesh.creation.torus(major_radius=major_r, minor_radius=minor_r,
                                  major_sections=24, minor_sections=8)
    d = np.asarray(axis, float)
    ring.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], d / np.linalg.norm(d)))
    ring.apply_translation(np.asarray(center, float))
    return ring


def _dir(pitch_deg, yaw_deg):
    """Unit vector: +z pitched DOWN by pitch_deg, yawed by yaw_deg."""
    p, y = d2r(pitch_deg), d2r(yaw_deg)
    return np.array([np.cos(p) * np.sin(y), -np.sin(p), np.cos(p) * np.cos(y)])


def build_hand(side, wrist):
    """Hand meshes in bind position: palm block, four individual
    2-segment fingers in a relaxed curl (touching at the knuckles,
    parting toward the tips — how a hand actually rests), knuckle
    bumps, and a 2-segment thumb riding the inboard-TOP of the hand
    (the inboard side hangs directly over the fat shorts cuff, so
    anything dipping down there is the first thing to clip). All on
    the ONE hand joint — static posed geometry; the drum fidget rocks
    the whole hand and the fingers pat together. The whole hand is
    rolled HAND_ROLL° about the wrist so the palm follows the thigh's
    outboard curve instead of bridging flat across its apex."""
    meshes = []
    palm = box_at([0.068, 0.024, 0.075],
                  tx=wrist[0], ty=wrist[1] - 0.004, tz=wrist[2] + 0.040, rx=d2r(-8))
    meshes.append(palm)
    # Fingers, index (beside the thumb, inboard) → pinky (outboard).
    # Proximal segment continues the palm's droop at −25°, distal −40°:
    # a DRAPE along the thigh's downslope, not a fist — steeper curls
    # stabbed the fingertips into the thigh capsule (the checker
    # catches it). A slight per-finger fan separates the tips.
    offs = (-0.0255, -0.0085, 0.0085, 0.0255)
    lens = (0.038, 0.041, 0.039, 0.030)
    rads = (0.0095, 0.0095, 0.0090, 0.0078)
    fans = (-4.0, -1.0, 1.5, 4.0)
    for off, ln, r, fan in zip(offs, lens, rads, fans):
        b = np.array([wrist[0] + off * side, wrist[1] - 0.008, wrist[2] + 0.074])
        knuckle = sphere_at(r * 1.15, b + np.array([0.0, 0.004, -0.004]))
        meshes.append(knuckle)
        e1 = b + _dir(22.0, fan * side) * ln
        meshes.append(capsule_between(b, e1, r))
        e2 = e1 + _dir(36.0, fan * side) * (ln * 0.75)
        meshes.append(capsule_between(e1, e2, r * 0.92))
    # Thumb: metacarpal from the inboard palm heel angling forward-in,
    # distal curling toward the fingers. Kept high (above palm plane at
    # the base) for cuff clearance.
    t0 = np.array([wrist[0] - side * 0.030, wrist[1] + 0.002, wrist[2] + 0.022])
    tdir = np.array([-side * 0.55, -0.25, 0.80])
    tdir /= np.linalg.norm(tdir)
    t1 = t0 + tdir * 0.042
    meshes.append(capsule_between(t0, t1, 0.013))
    tdir2 = np.array([-side * 0.25, -0.35, 0.90])
    tdir2 /= np.linalg.norm(tdir2)
    meshes.append(capsule_between(t1, t1 + tdir2 * 0.032, 0.011))
    roll = trimesh.transformations.rotation_matrix(
        d2r(-HAND_ROLL) * side, [0, 0, 1], wrist)
    for m in meshes:
        m.apply_transform(roll)
    return meshes


def build_foot(side, ankle):
    """Foot meshes: heel/midfoot block, rounded heel, five individual
    toe capsules (big toe inboard) with an extra −8° curl beyond the
    foot pitch so the toes point INTO the water in the dangle pose —
    each toe refracting on its own is the 'those are mine' read.
    Same overall stance as the old single box: pitched toes-down −14°,
    turned out 5°, total length ≈0.22 so the waterline contact along
    the leg is unchanged."""
    local = [box_at([0.085, 0.052, 0.15], ty=-0.015, tz=0.04)]
    local.append(sphere_at(0.030, [0.0, -0.030, -0.030]))
    offs = (-0.028, -0.0115, 0.0035, 0.016, 0.0265)   # big → pinky
    lens = (0.045, 0.040, 0.036, 0.032, 0.028)
    rads = (0.0125, 0.0100, 0.0095, 0.0090, 0.0082)
    fans = (0.0, 1.0, 2.0, 3.0, 4.5)                   # toes fan outboard
    for off, ln, r, fan in zip(offs, lens, rads, fans):
        b = np.array([off * side, -0.030, 0.110])
        local.append(capsule_between(b, b + _dir(8.0, fan * side) * ln, r))
    m = trimesh.transformations.euler_matrix(d2r(-14), side * d2r(5), 0.0, "sxyz")
    m[:3, 3] = ankle
    for mesh in local:
        mesh.apply_transform(m)
    return local


# ── UV mapping ──────────────────────────────────────────────────────────
# Per-part mapping onto small per-class tiling textures (no atlas: the
# engine's Repeat sampler handles the cylindrical wrap, and there is no
# gutter bleed to manage).
#   ("cyl", p0, p1, seam_dir)  — capsules: v = 0..1 along the axis,
#       u = azimuth with the WRAP rotated toward seam_dir (pick a
#       hidden direction: down for horizontal limbs, back for vertical)
#   ("planar", group)          — u/v = x/z over the named part-GROUP's
#       bbox, so features (knuckle spots) line up across the group
#   ("patch", offset, scale)   — planar over the part's own bbox but
#       sampling only a small window of the tile (tiny bumps/rings:
#       full-tile mapping would compress the whole pattern onto them)

def cylindrical_uv(verts, p0, p1, seam_dir):
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    axis = p1 - p0
    length = np.linalg.norm(axis)
    axis = axis / length
    s = np.asarray(seam_dir, float)
    s = s - axis * (s @ axis)
    sn = np.linalg.norm(s)
    assert sn > 0.2, "seam_dir nearly parallel to the capsule axis"
    b1 = -s / sn                      # u=0.5 opposite the seam
    b2 = np.cross(axis, b1)
    d = verts - p0
    u = np.arctan2(d @ b2, d @ b1) / (2.0 * np.pi) + 0.5
    v = (d @ axis) / length
    return np.stack([u, v], axis=1)


def split_uv_seam(verts, norms, faces, uv):
    """Duplicate the low-u vertices of faces that span the u wrap
    (u range > 0.5), giving the copies u+1.0 — the Repeat sampler
    reads u>1 correctly, while WITHOUT the split the interpolator
    smears the whole texture backwards across one triangle ring.
    Normals are carried over so the seam doesn't shade."""
    verts = list(verts)
    norms = list(norms)
    uv = list(uv)
    faces = faces.copy()
    dup = {}
    for fi in np.where(
            np.ptp(np.asarray(uv)[faces, 0], axis=1) > 0.5)[0]:
        for k in range(3):
            vi = faces[fi, k]
            if uv[vi][0] < 0.5:
                if vi not in dup:
                    verts.append(verts[vi])
                    norms.append(norms[vi])
                    uv.append(np.array([uv[vi][0] + 1.0, uv[vi][1]]))
                    dup[vi] = len(verts) - 1
                faces[fi, k] = dup[vi]
    return (np.asarray(verts, np.float32), np.asarray(norms, np.float32),
            faces, np.asarray(uv, np.float32))


parts = []  # (joint_name, trimesh, color, roughness, tex_name, uvspec)


def add_part(joint, mesh, color, roughness, tex=None, uv=None):
    parts.append((joint, mesh, color, roughness, tex, uv))

DOWN = (0.0, -1.0, 0.0)
BACK = (0.0, 0.0, -1.0)

for side, hip, knee, ankle in ((+1.0, HIP_L, KNEE_L, ANKLE_L), (-1.0, HIP_R, KNEE_R, ANKLE_R)):
    sfx = "l" if side > 0 else "r"
    cvec = (knee - hip) / np.linalg.norm(knee - hip)
    # Limbs taper toward the distal joint (mean radii match the old
    # uniform capsules — the silhouette narrows, it doesn't shrink).
    add_part(f"thigh_{sfx}",
             tapered_capsule_between(hip, knee, THIGH_R + 0.003, THIGH_R - 0.006),
             SKIN, 0.9, tex="skin_thigh", uv=("cyl", hip, knee, DOWN))
    add_part(f"calf_{sfx}",
             tapered_capsule_between(knee, ankle, CALF_R + 0.004, CALF_R - 0.008),
             SKIN_LOWER, 0.9, tex="skin_calf", uv=("cyl", knee, ankle, BACK))
    # Kneecap: flattened ball just proud of the thigh's knee cap —
    # sharpens the raised-knee framing, catches the TOD light. On the
    # thigh joint (the patella stays with the femur when the calf kicks).
    add_part(f"thigh_{sfx}",
             sphere_at(0.045, knee + cvec * 0.050, squash_dir=cvec, squash=0.6),
             SKIN, 0.9, tex="skin_thigh", uv=("patch", 0.30, 0.25))
    # Ankle bumps (malleoli) on the CALF: they don't pitch with the foot.
    for mx in (+0.050, -0.050):
        add_part(f"calf_{sfx}",
                 sphere_at(0.016, [ankle[0] + mx, ankle[1] + 0.008, ankle[2]]),
                 SKIN_LOWER, 0.9, tex="skin_calf", uv=("patch", 0.35, 0.20))
    for fmesh in build_foot(side, ankle):
        add_part(f"foot_{sfx}", fmesh, FOOT, 0.9,
                 tex="skin_foot", uv=("planar", f"foot_{sfx}"))
    # Shorts cuff on the upper thigh (rides with the thigh joint), with
    # a hem ring at its open end.
    c0 = hip + np.array([0.0, 0.012, 0.0])
    add_part(f"thigh_{sfx}", capsule_between(c0, c0 + cvec * 0.20, THIGH_R + 0.022),
             SHORTS, 0.9, tex="fabric_shorts", uv=("cyl", c0, c0 + cvec * 0.20, DOWN))
    add_part(f"thigh_{sfx}", ring_at(THIGH_R + 0.019, 0.006, c0 + cvec * 0.20, cvec),
             SHORTS, 0.9, tex="fabric_shorts", uv=("patch", 0.25, 0.35))

# Pelvis/seat block (shorts) on the root — spans the hips, stops shy of
# the legs' outer edges so the thighs read as separate from it.
add_part("root", box_at([0.42, 0.16, 0.26], ty=0.03, tz=-0.16), SHORTS, 0.9,
         tex="fabric_shorts", uv=("planar", "pelvis"))
# Torso: belly on root, chest + shoulder bar on spine (tee). Slim and
# pulled BACK: the chest must stay clear of the first-person camera's
# near plane (the eye sits ~6 cm above and just inboard of it) or it
# clips open into a dome with a hole when the player looks down.
# Belly slim and pulled back — looking down it should foreshorten under
# the chest, not sit on the lap like a ball.
add_part("spine", capsule_between([0.0, 0.06, -0.17], [0.0, 0.19, -0.17], 0.095),
         TEE, 0.9, tex="fabric_tee",
         uv=("cyl", [0.0, 0.06, -0.17], [0.0, 0.19, -0.17], BACK))
add_part("chest", capsule_between([0.0, 0.19, -0.16], [0.0, 0.30, -0.155], 0.10),
         TEE, 0.9, tex="fabric_tee",
         uv=("cyl", [0.0, 0.19, -0.16], [0.0, 0.30, -0.155], BACK))
# Clavicles: from near-center chest out to each shoulder ball.
for side, clav in ((+1.0, CLAV_L), (-1.0, CLAV_R)):
    sfx = "l" if side > 0 else "r"
    sh_end = np.array([side * (SHOULDER - 0.01), 0.29, SHOULDER_Z])
    add_part(f"clavicle_{sfx}", capsule_between(clav, sh_end, 0.055),
             TEE, 0.9, tex="fabric_tee", uv=("cyl", clav, sh_end, DOWN))

for side, elbow, wrist in ((+1.0, ELBOW_L, WRIST_L), (-1.0, ELBOW_R, WRIST_R)):
    sfx = "l" if side > 0 else "r"
    shoulder = np.array([side * SHOULDER, 0.29, SHOULDER_Z])
    add_part(f"upper_arm_{sfx}", tapered_capsule_between(shoulder, elbow, 0.047, 0.042),
             SKIN, 0.9, tex="skin_arm", uv=("cyl", shoulder, elbow, BACK))
    # Tee sleeve over the upper third, with a hem ring at its open end.
    svec = (elbow - shoulder) / np.linalg.norm(elbow - shoulder)
    add_part(f"upper_arm_{sfx}", capsule_between(shoulder, shoulder + svec * 0.10, 0.058),
             TEE, 0.9, tex="fabric_tee",
             uv=("cyl", shoulder, shoulder + svec * 0.10, BACK))
    add_part(f"upper_arm_{sfx}", ring_at(0.055, 0.005, shoulder + svec * 0.10, svec),
             TEE, 0.9, tex="fabric_tee", uv=("patch", 0.25, 0.35))
    add_part(f"forearm_{sfx}", tapered_capsule_between(elbow, wrist, 0.042, 0.031),
             SKIN, 0.9, tex="skin_arm", uv=("cyl", elbow, wrist, DOWN))
    for hmesh in build_hand(side, wrist):
        add_part(f"hand_{sfx}", hmesh, SKIN, 0.9,
                 tex="skin_hand", uv=("planar", f"hand_{sfx}"))


# ── Quaternion helpers (x, y, z, w) ─────────────────────────────────────
def quat_from_euler(rx, ry, rz):
    """Intrinsic XYZ euler (degrees) → quaternion. Small-angle authoring."""
    def axis_q(angle_deg, axis):
        h = d2r(angle_deg) * 0.5
        s = np.sin(h)
        q = [0.0, 0.0, 0.0, np.cos(h)]
        q[axis] = s
        return q

    def qmul(a, b):
        ax, ay, az, aw = a
        bx, by, bz, bw = b
        return [
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz,
        ]

    return qmul(qmul(axis_q(rx, 0), axis_q(ry, 1)), axis_q(rz, 2))


# ── Clip authoring ──────────────────────────────────────────────────────
# rot channels: joint -> [(t, (rx, ry, rz))]; trans: joint -> [(t, (x,y,z))]
# Translations are LOCAL (relative to parent), so only root gets them —
# authored as deltas on its bind-local translation.

def mirror_rot_keys(keys):
    return [(t, (rx, -ry, -rz)) for (t, (rx, ry, rz)) in keys]


# ── Idle variant library ────────────────────────────────────────────────
# Amplitudes are THEATRICAL, not realistic: at this stylization (and
# against wave motion) subtle reads as stiff. Verified by probing the eye
# bone: the first calibration pass moved the camera 2 mm and was
# invisible; the current numbers give ~19 mm of breathing sway.
#
# Arm-chain POSES (left-side eulers; right side mirrors ry/rz). Every
# idle variant is base poses + layered sway; every fidget HOLDS the
# variant's poses on un-moving joints, because sparse clips fall back to
# bind — a fidget that didn't key the arms would yank them to rest.

def euler_to_mat(rx, ry, rz):
    """Rotation matrix matching quat_from_euler's composition (Rx·Ry·Rz)."""
    q = quat_from_euler(rx, ry, rz)
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def solve_arm(wrist_target, coarse=6.0, rz_max=60):
    """Brute-force 2-bone IK for the LEFT arm: grid-search upper_arm
    (rx, rz) x forearm rx so the wrist lands on the model-space target.
    Blind euler authoring kept missing (the forearm's effective axis
    flips as the upper arm swings); solving is exact and reusable.
    rz_max stays 60 for the idle poses (changing the grid would nudge
    the established deck/water looks); the scoot plant path passes 90
    for the far-outboard waypoints."""
    s = np.array([+SHOULDER, 0.29, SHOULDER_Z])
    e_off = ELBOW_L - s
    w_off = WRIST_L - ELBOW_L
    target = np.array(wrist_target, dtype=float)
    best = (1e9, (0.0, 0.0), 0.0)
    for ua_x in np.arange(-70, 71, coarse):
        for ua_z in np.arange(-10, rz_max + 1, coarse):
            r_ua = euler_to_mat(ua_x, 0.0, ua_z)
            e = r_ua @ e_off
            for fa_x in np.arange(-70, 71, coarse):
                w = s + e + r_ua @ (euler_to_mat(fa_x, 0.0, 0.0) @ w_off)
                err = np.linalg.norm(w - target)
                # prefer the elbow OUTBOARD of the shoulder (natural)
                if (s + e)[0] < s[0]:
                    err += 0.05
                if err < best[0]:
                    best = (err, (ua_x, ua_z), fa_x)
    (ua_x, ua_z), fa_x = best[1], best[2]
    return best[0], (float(ua_x), 0.0, float(ua_z)), (float(fa_x), 0.0, 0.0)


def arm_pose_thigh():
    return {"upper_arm": (0, 0, 0), "forearm": (0, 0, 0), "hand": (0, 0, 0)}


# Solved once at generation time (targets in model space, LEFT side):
# deck: palm flat on the deck (y -0.02) outboard beside the hip;
# water: arm slack over the deck edge reaching toward the water. The
# CALM waterline (y ~ -0.33) is beyond arm reach (needs 0.75 m, arm has
# 0.52) — so the hand DANGLES toward it and the swells rise to meet it,
# helped by a baked spine lean in the water variants.
_err_d, _UA_DECK, _FA_DECK = solve_arm((0.27, 0.01, -0.02))
_err_w, _UA_WATER, _FA_WATER = solve_arm((0.20, -0.19, 0.27))
print(f"  arm IK: deck wrist err {_err_d * 100:.1f} cm, water wrist err {_err_w * 100:.1f} cm")

# Scoot plant path (LEFT arm, model-space wrist targets). The old
# hand-authored keys swung the hand down the thigh AXIS (x≈0.14 the
# whole path — through the capsule). This is a CARTESIAN path of
# IK-solved waypoints, keyed densely because euler-lerping between two
# solved poses does not follow the straight line between their targets
# (a sparse plant→rest lerp cut the corner through the cuff both ways).
# Shape: lift over the thigh, reach down-OUTBOARD, plant beside the
# hip, climb straight up the outboard side, come back in from above.
# x is bumped ~+0.03 vs where the hand should land to counter the
# plant-side spine lean (−9° roll shifts the below-pivot hand inboard).
_SCOOT_ARM_PATH = [
    (0.14, (0.27, 0.20, 0.10)),    # lift over the thigh
    (0.21, (0.35, 0.11, 0.05)),    # descend OUTSIDE the cuff shoulder
    (0.28, (0.33, 0.03, 0.03)),    # reach down-outboard
    (0.60, (0.34, -0.01, -0.02)),  # plant beside the hip
    (0.72, (0.35, 0.06, 0.02)),    # return: straight up the outboard side
    (0.82, (0.34, 0.12, 0.05)),
    (0.91, (0.31, 0.18, 0.08)),
    (0.98, (0.27, 0.20, 0.10)),    # over the thigh again, settle to rest
]
_UA_KEYS = [(0.0, (0, 0, 0))]
_FA_KEYS = [(0.0, (0, 0, 0))]
_scoot_errs = []
for _t, _tgt in _SCOOT_ARM_PATH:
    _e, _ua, _fa = solve_arm(_tgt, rz_max=90)
    _scoot_errs.append(_e)
    _UA_KEYS.append((_t, _ua))
    _FA_KEYS.append((_t, _fa))
_UA_KEYS.append((1.30, (0, 0, 0)))
_FA_KEYS.append((1.30, (0, 0, 0)))
print("  scoot IK errs (cm):", ", ".join(f"{e * 100:.1f}" for e in _scoot_errs))


def arm_pose_deck():
    return {"upper_arm": _UA_DECK, "forearm": _FA_DECK, "hand": (-12, 0, 0)}


def arm_pose_water():
    return {"upper_arm": _UA_WATER, "forearm": _FA_WATER, "hand": (16, 0, 0)}


def side_euler(e, side):
    return e if side == "l" else (e[0], -e[1], -e[2])


def wobble_rot(base, amp, cycles, phase, dur, axis=0, n=17):
    keys = []
    for i in range(n):
        t = dur * i / (n - 1)
        e = list(base)
        e[axis] = e[axis] + amp * np.sin(2 * np.pi * cycles * t / dur + phase)
        keys.append((t, tuple(e)))
    keys[-1] = (dur, keys[0][1])  # exact loop closure
    return keys


# name: (left arm pose, right arm pose, loop seconds, seed). Durations
# deliberately differ so variant rhythms never phase-lock.
IDLE_VARIANTS = {
    "idle_deck":       (arm_pose_deck,  arm_pose_deck,  8.6, 11),
    "idle_thighs":     (arm_pose_thigh, arm_pose_thigh, 9.4, 22),
    "idle_left_deck":  (arm_pose_deck,  arm_pose_thigh, 8.9, 33),
    "idle_right_deck": (arm_pose_thigh, arm_pose_deck,  9.1, 44),
    "idle_water_l":    (arm_pose_water, arm_pose_deck,  10.2, 55),
    "idle_water_r":    (arm_pose_deck,  arm_pose_water, 10.0, 66),
}


def make_idle(name, lpose_fn, rpose_fn, dur, seed):
    # NOTE: no leg channels here — ALL lower-leg motion lives in the
    # legs_rock additive layer, which loops independently and survives
    # variant crossfades and fidgets (legs never freeze).
    rng = np.random.default_rng(seed)
    rot = {}
    trans = {}
    # Breathing: one cycle per loop, spine + chest compound to the eye.
    # Water variants bake a spine lean toward the trailing side (extends
    # the reach and reads as the body committing to the gesture; the
    # camera leans with it via the eye bone). Negative roll = toward +X.
    lean = 0.0
    if lpose_fn is arm_pose_water:
        lean = -7.0
    elif rpose_fn is arm_pose_water:
        lean = 7.0
    br = rng.uniform(0.9, 1.1)
    rot["spine"] = [(0.0, (0, 0, lean)), (dur * 0.5, (2.4 * br, 0, 0.7 + lean)),
                    (dur, (0, 0, lean))]
    rot["chest"] = [(0.0, (0, 0, lean * 0.5)),
                    (dur * 0.45, (1.6 * br, 0, -0.4 + lean * 0.5)),
                    (dur, (0, 0, lean * 0.5))]
    # Arms: base pose + micro-sway. A water-trailing hand drags BIG and
    # slow — the water is moving it, not the muscles.
    for side, pose_fn in (("l", lpose_fn), ("r", rpose_fn)):
        in_water = pose_fn is arm_pose_water
        for j, base in pose_fn().items():
            b = side_euler(base, side)
            if in_water and j == "hand":
                amp, cyc = 7.0, 1.0
            elif in_water:
                amp, cyc = 3.0, 1.0
            else:
                amp = {"upper_arm": 1.8, "forearm": 2.2, "hand": 3.0}[j]
                cyc = rng.uniform(2.2, 3.2)
                if pose_fn is arm_pose_thigh:
                    amp *= REST_SWAY_SCALE
            rot[f"{j}_{side}"] = wobble_rot(
                b, amp * rng.uniform(0.8, 1.2), cyc, rng.uniform(0.0, 6.28), dur)
    # Slow weight sway in the pelvis (millimeters — felt via the eye).
    n = 17
    ph = rng.uniform(0.0, 6.28)
    tk = []
    for i in range(n):
        t = dur * i / (n - 1)
        tk.append((t, (0.006 * np.sin(2 * np.pi * t / dur + ph),
                       0.003 * np.sin(2 * np.pi * 2.0 * t / dur + ph * 1.7), 0.0)))
    tk[-1] = (dur, tk[0][1])
    trans["root"] = tk
    return name, rot, trans


# ── The legs_rock additive layer ────────────────────────────────────────
# Chris: "the legs kick out at the knee during idle, a sort of
# self-soothing almost rocking chair action" — and the legs should
# reach FULL EXTENSION regularly. Each leg runs a kick TRAIN: kicks of
# varying amplitude (kick-hang-pendulum-return), one of which per cycle
# swings all the way out (~78° = knee straight, the legs-off-the-dock
# move). Bigger kicks take longer — a lazy full swing, not a punt. The
# backswing is CAPPED at 12°: a full kick's uncapped return would swing
# the calf into the raft hull below the deck edge. Feet flex with a
# lag; thighs lift a touch so the motion connects to the pelvis. Runs
# as an ADDITIVE layer on its own clock, persisting through variant
# crossfades and fidgets (ducked only during scoot steps).
# Calf rotation magnitude for a straight knee. SIGN: probing foot_l
# showed POSITIVE calf rx tucks the foot back under the deck; EXTENSION
# is NEGATIVE. The signal below is authored in positive "extension
# units" and negated at emission.
FULL_EXT_DEG = 78.0

# Normalized kick shape: out, hang, pendulum past neutral, settle.
KICK_SHAPE_T = [0.0, 0.14, 0.32, 0.58, 0.80, 1.0]
KICK_SHAPE_V = [0.0, 1.0, 0.72, -0.29, 0.12, 0.0]

# Per-leg kick trains (amplitude fraction of full extension, seconds).
# Both trains total the same loop length. SCALE: the feet live IN the
# water — the ankle crosses the calm waterline at ~14° of extension
# (0.18 of full), toes at ~22° — so the ordinary kicks slosh below the
# surface and only the biggest (0.33 ≈ 26°) briefly breaks it with the
# toes. Full extension was tried and read as too much (feet in the sky).
KICKS_L = [(0.12, 4.4), (0.32, 6.6), (0.17, 4.6), (0.24, 5.4)]
KICKS_R = [(0.21, 5.0), (0.13, 4.4), (0.33, 6.8), (0.15, 4.8)]
ROCK_TIME = 21.0
assert abs(sum(d for _, d in KICKS_L) - ROCK_TIME) < 1e-9
assert abs(sum(d for _, d in KICKS_R) - ROCK_TIME) < 1e-9


def kick_train_signal(kicks, step=0.15):
    """Dense (times, degrees) over the loop for a train of kicks."""
    ts, vs = [], []
    t0 = 0.0
    for amp_frac, dur in kicks:
        amp = FULL_EXT_DEG * amp_frac
        neg_scale = min(1.0, 12.0 / (0.29 * amp))  # backswing cap
        n = max(10, int(dur / step))
        for i in range(n):
            u = i / n
            v = np.interp(u, KICK_SHAPE_T, KICK_SHAPE_V)
            if v < 0.0:
                v *= neg_scale
            ts.append(t0 + u * dur)
            vs.append(v * amp)
        t0 += dur
    ts.append(ROCK_TIME)
    vs.append(vs[0])
    return np.array(ts), np.array(vs)


def make_legs_rock():
    rot = {}
    for side, kicks in (("l", KICKS_L), ("r", KICKS_R)):
        ts, vs = kick_train_signal(kicks)
        # The foot POINTS as the leg extends (plantar flexion — water
        # drag trails the toes behind the swing) and flexes slightly up
        # on the backswing; it lags the calf ~0.35 s. A 90° foot on an
        # extended leg reads rigid — a relaxed foot follows through.
        # Signs: calf extension is NEGATIVE rx; foot pointing (toes
        # down) is POSITIVE rx — so the foot takes the signal unnegated
        # at full gain. Thigh lifts slightly with the kick.
        lag_vs = np.interp((ts - 0.35) % ROCK_TIME, ts, vs)
        rot[f"calf_{side}"] = [(float(t), (-float(v), 0.0, 0.0)) for t, v in zip(ts, vs)]
        rot[f"foot_{side}"] = [(float(t), (float(v) * 1.0, 0.0, 0.0)) for t, v in zip(ts, lag_vs)]
        # Gain 0.05 (was 0.12): still connects the kick to the pelvis at
        # ~1.3° peak, but keeps the rising knee clear of the resting hands.
        rot[f"thigh_{side}"] = [(float(t), (float(v) * -0.05, 0.0, 0.0)) for t, v in zip(ts, vs)]
    return "legs_rock", rot, {}


# ── Fidgets: one-shots layered over a variant's held poses ──────────────
FIDGET_DURS = {"kick": 2.4, "drum": 2.0, "shift": 2.6, "sigh": 3.0, "stretch": 3.6}


def held_arms(lpose_fn, rpose_fn, dur):
    rot = {}
    for side, fn in (("l", lpose_fn), ("r", rpose_fn)):
        for j, base in fn().items():
            b = side_euler(base, side)
            rot[f"{j}_{side}"] = [(0.0, b), (dur, b)]
    return rot


def eadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def make_fidget(kind, vname, lpose_fn, rpose_fn):
    dur = FIDGET_DURS[kind]
    rot = held_arms(lpose_fn, rpose_fn, dur)
    trans = {}
    lean = 0.0
    if lpose_fn is arm_pose_water:
        lean = -7.0
    elif rpose_fn is arm_pose_water:
        lean = 7.0

    if kind == "kick":
        # One deliberate kick THROUGH the water (extension = negative
        # rx), toes just breaking the surface — foot POINTS with the
        # kick (positive rx), flexes up on the return drag.
        rot["calf_l"] = [(0.0, (0, 0, 0)), (0.5, (-27, 0, 0)), (0.9, (8, 0, 0)),
                         (1.4, (-10, 0, 0)), (2.0, (0, 0, 0)), (2.4, (0, 0, 0))]
        rot["foot_l"] = [(0.0, (0, 0, 0)), (0.55, (24, 0, 0)), (1.0, (-8, 0, 0)),
                         (1.6, (6, 0, 0)), (2.2, (0, 0, 0)), (2.4, (0, 0, 0))]
    elif kind == "drum":
        # Fingers drumming on the deck — on whichever hand is planted.
        d = "l" if lpose_fn is arm_pose_deck else "r"
        base = side_euler(arm_pose_deck()["hand"], d)
        sgn = 1.0 if d == "l" else -1.0
        taps = [(0.0, 0.0), (0.35, 6.0), (0.5, -3.0), (0.65, 7.0), (0.8, -3.0),
                (0.95, 6.0), (1.1, -2.0), (1.3, 4.0), (1.7, 0.0), (2.0, 0.0)]
        rot[f"hand_{d}"] = [(t, (base[0], base[1], base[2] + sgn * v)) for t, v in taps]
    elif kind == "shift":
        # Weight rocks onto one hip and back.
        trans["root"] = [(0.0, (0, 0, 0)), (0.9, (-0.03, 0.004, 0)),
                         (1.7, (-0.026, 0.002, 0)), (2.6, (0, 0, 0))]
        rot["spine"] = [(0.0, (0, 0, 0)), (0.9, (0.5, 0, 3.5)),
                        (1.8, (0.4, 0, 3.0)), (2.6, (0, 0, 0))]
    elif kind == "sigh":
        # One deep breath: shoulders rise, hold, drop.
        rot["spine"] = [(0.0, (0, 0, 0)), (1.1, (4.5, 0, 0)), (1.9, (3.6, 0, 0)),
                        (3.0, (0, 0, 0))]
        rot["chest"] = [(0.0, (0, 0, 0)), (1.0, (2.6, 0, 0)), (2.0, (2.0, 0, 0)),
                        (3.0, (0, 0, 0))]
        rot["clavicle_l"] = [(0.0, (0, 0, 0)), (1.05, (0, 0, -6)),
                             (2.0, (0, 0, -4)), (3.0, (0, 0, 0))]
        rot["clavicle_r"] = [(0.0, (0, 0, 0)), (1.05, (0, 0, 6)),
                             (2.0, (0, 0, 4)), (3.0, (0, 0, 0))]
    elif kind == "stretch":
        # The rare big gesture: arch back, shoulders roll up and back,
        # arms pull back, release. Felt strongly through the eye bone.
        rot["spine"] = [(0.0, (0, 0, 0)), (1.2, (-5, 0, 0)), (2.2, (-4.4, 0, 0)),
                        (3.3, (0.6, 0, 0)), (3.6, (0, 0, 0))]
        rot["chest"] = [(0.0, (0, 0, 0)), (1.2, (-3, 0, 0)), (2.2, (-2.6, 0, 0)),
                        (3.6, (0, 0, 0))]
        rot["clavicle_l"] = [(0.0, (0, 0, 0)), (1.3, (0, 0, -13)),
                             (2.3, (0, 0, -11)), (3.6, (0, 0, 0))]
        rot["clavicle_r"] = [(0.0, (0, 0, 0)), (1.3, (0, 0, 13)),
                             (2.3, (0, 0, 11)), (3.6, (0, 0, 0))]
        for side, fn in (("l", lpose_fn), ("r", rpose_fn)):
            ua = side_euler(fn()["upper_arm"], side)
            pull = (16, 0, 8 if side == "l" else -8)
            rot[f"upper_arm_{side}"] = [
                (0.0, ua), (1.3, eadd(ua, pull)),
                (2.3, eadd(ua, (14, 0, pull[2] * 0.85))), (3.6, ua)]
        trans["root"] = [(0.0, (0, 0, 0)), (1.3, (0, 0.012, 0)),
                         (2.3, (0, 0.010, 0)), (3.6, (0, 0, 0))]

    # Water variants hold their spine lean through every fidget —
    # otherwise blending into one would un-lean the body mid-gesture.
    if lean != 0.0:
        if "spine" in rot:
            rot["spine"] = [(t, (x, y, z + lean)) for t, (x, y, z) in rot["spine"]]
        else:
            rot["spine"] = [(0.0, (0, 0, lean)), (dur, (0, 0, lean))]
        if "chest" in rot:
            rot["chest"] = [(t, (x, y, z + lean * 0.5)) for t, (x, y, z) in rot["chest"]]
        else:
            rot["chest"] = [(0.0, (0, 0, lean * 0.5)), (dur, (0, 0, lean * 0.5))]

    return f"fid_{kind}_{vname}", rot, trans


def scoot_right_clip():
    """Moving toward body-right = model -X. The LEFT arm plants."""
    rot = {
        # Right leg unweights and opens toward -X (negative yaw swings +Z→-X).
        "thigh_r": [(0.0, (0, 0, 0)), (0.32, (-6, -30, 0)), (0.70, (-3, -24, 0)),
                    (1.05, (0, -4, 0)), (1.30, (0, 0, 0))],
        "calf_r":  [(0.0, (0, 0, 0)), (0.40, (10, 0, 0)), (0.90, (4, 0, 0)),
                    (1.30, (0, 0, 0))],
        # Left leg trails under the body during the shift.
        "thigh_l": [(0.0, (0, 0, 0)), (0.55, (-4, -10, 0)), (0.95, (0, -3, 0)),
                    (1.30, (0, 0, 0))],
        # Left arm: the IK-solved Cartesian plant path (_SCOOT_ARM_PATH).
        "upper_arm_l": list(_UA_KEYS),
        "forearm_l": list(_FA_KEYS),
        "hand_l": [(0.0, (0, 0, 0)), (0.32, (14, 0, 0)), (0.90, (10, 0, 0)),
                   (1.25, (0, 0, 0))],
        # Shoulders dip toward the planted (left, +X) arm while it bears
        # weight: negative roll leans the spine toward +X, and the left
        # clavicle shrugs up as the arm takes the load.
        "spine": [(0.0, (0, 0, 0)), (0.35, (4, 0, -7)), (0.70, (5, 0, -9)),
                  (1.05, (1, 0, -2)), (1.35, (0, 0, 0))],
        "clavicle_l": [(0.0, (0, 0, 0)), (0.35, (0, 0, -9)), (0.75, (0, 0, -11)),
                       (1.05, (0, 0, -3)), (1.35, (0, 0, 0))],
    }
    # Root: the lift-and-settle. Only lift + lateral LEAN — travel comes
    # from the entity transform.
    trans = {
        "root": [(0.0, (0, 0, 0)), (0.30, (0, 0.005, 0)), (0.55, (-0.035, 0.062, 0)),
                 (0.85, (-0.05, 0.028, 0)), (1.08, (-0.015, -0.006, 0)),
                 (1.30, (0, 0, 0))],
    }
    return rot, trans


def mirror_clip(rot, trans):
    def swap(j):
        if j.endswith("_l"):
            return j[:-2] + "_r"
        if j.endswith("_r"):
            return j[:-2] + "_l"
        return j

    mrot = {swap(j): mirror_rot_keys(keys) for j, keys in rot.items()}
    mtrans = {
        swap(j): [(t, (-x, y, z)) for (t, (x, y, z)) in keys]
        for j, keys in trans.items()
    }
    return mrot, mtrans


ROT_R, TRANS_R = scoot_right_clip()
ROT_L, TRANS_L = mirror_clip(ROT_R, TRANS_R)

CLIPS = [
    ("scoot_right", ROT_R, TRANS_R),
    ("scoot_left", ROT_L, TRANS_L),
    make_legs_rock(),
]
for vname, (lp, rp, dur, seed) in IDLE_VARIANTS.items():
    CLIPS.append(make_idle(vname, lp, rp, dur, seed))
    for kind in FIDGET_DURS:
        # Drumming needs a deck-planted hand.
        if kind == "drum" and arm_pose_deck not in (lp, rp):
            continue
        CLIPS.append(make_fidget(kind, vname, lp, rp))


# ── Generation-time clearance check: hands vs thighs ────────────────────
# The hands rest on the outer thighs while the legs_rock layer lifts the
# knees beneath them, and the scoot clips swing the planted arm down past
# the hip — both have clipped in the past. FK the actual clip keys against
# the actual hand vertices so a future retune that re-introduces an
# intersection fails the generation run, not Chris's playtest.

BIND_GPOS = {name: gpos for name, _, gpos in JOINTS}
_JPARENT = {name: parent for name, parent, _ in JOINTS}


def _sample_euler(keys, t):
    times = np.array([k[0] for k in keys])
    return tuple(float(np.interp(t, times, np.array([k[1][i] for k in keys])))
                 for i in range(3))


def _fk(rot_eulers):
    """Global rotation/position per joint given local euler overrides
    (unkeyed joints = identity, matching the engine's rest-pose seeding).
    Root translation is skipped: it moves the arm and leg subtrees
    together, so hand-vs-thigh distances are unaffected."""
    g_rot, g_pos = {}, {}
    for name, parent, gpos in JOINTS:
        r_local = euler_to_mat(*rot_eulers.get(name, (0.0, 0.0, 0.0)))
        if parent is None:
            g_rot[name] = r_local
            g_pos[name] = gpos.astype(float).copy()
        else:
            g_rot[name] = g_rot[parent] @ r_local
            g_pos[name] = g_pos[parent] + g_rot[parent] @ (gpos - BIND_GPOS[parent])
    return g_rot, g_pos


def _skin_pts(verts, joint, g_rot, g_pos):
    return (g_rot[joint] @ (verts - BIND_GPOS[joint]).T).T + g_pos[joint]


def _seg_clearance(pts, a, b, radius):
    ab = b - a
    u = np.clip(((pts - a) @ ab) / (ab @ ab), 0.0, 1.0)
    proj = a + u[:, None] * ab
    return float(np.linalg.norm(pts - proj, axis=1).min() - radius)


def _thigh_solids(sfx, g_rot, g_pos):
    """Animated thigh capsule + shorts cuff for one side, as
    (seg_a, seg_b, radius) — the cuff is FATTER than the thigh and sits
    exactly where the hands rest, so it must be part of the check."""
    hip_b, knee_b = (HIP_L, KNEE_L) if sfx == "l" else (HIP_R, KNEE_R)
    cvec = (knee_b - hip_b) / np.linalg.norm(knee_b - hip_b)
    c0_b = hip_b + np.array([0.0, 0.012, 0.0])
    c1_b = c0_b + cvec * 0.20
    j = f"thigh_{sfx}"
    c0 = _skin_pts(c0_b[None, :], j, g_rot, g_pos)[0]
    c1 = _skin_pts(c1_b[None, :], j, g_rot, g_pos)[0]
    return [
        # THIGH_R + 0.003 = the tapered thigh's fattest (hip) end —
        # conservative along the rest of its length.
        (g_pos[j], g_pos[f"calf_{sfx}"], THIGH_R + 0.003),
        (c0, c1, THIGH_R + 0.022),
    ]


def check_clearance():
    hand_verts = {"l": [], "r": []}
    for joint_name, mesh, *_rest in parts:
        if joint_name.startswith("hand_"):
            hand_verts[joint_name[-1]].append(mesh.vertices)
    hand_verts = {s: np.vstack(v) for s, v in hand_verts.items()}
    clip_rot = {name: rot for name, rot, _ in CLIPS}

    results = {}

    # Case 0: the pure bind rest — not an intersection risk but a HOVER
    # gauge: much above ~+1.5 cm and the resting hands read as floating.
    g_rot, g_pos = _fk({})
    gap = 1e9
    for sfx in ("l", "r"):
        pts = _skin_pts(hand_verts[sfx], f"hand_{sfx}", g_rot, g_pos)
        for a, b, r in _thigh_solids(sfx, g_rot, g_pos):
            gap = min(gap, _seg_clearance(pts, a, b, r))
    print(f"  bind rest gap (palm to thigh): {gap * 100:+.2f} cm")

    # Case 1: legs_rock knee lift under idle-resting hands. Base pose =
    # idle_thighs (bind arms) ± the idle micro-sway extremes (max rng
    # scale 1.2 on the authored amps × the resting damp), composed with
    # the layer's thigh rotation sampled across the whole loop.
    sway = 1.2 * REST_SWAY_SCALE
    wob = [(ua, fa, ha)
           for ua in (-1.8 * sway, 0.0, 1.8 * sway)
           for fa in (-2.2 * sway, 0.0, 2.2 * sway)
           for ha in (-3.0 * sway, 0.0, 3.0 * sway)]
    rock = clip_rot["legs_rock"]
    worst = (1e9, "")
    for t in np.arange(0.0, ROCK_TIME, 0.15):
        for sfx in ("l", "r"):
            thigh_e = _sample_euler(rock[f"thigh_{sfx}"], t)
            for ua, fa, ha in wob:
                g_rot, g_pos = _fk({
                    f"thigh_{sfx}": thigh_e,
                    f"upper_arm_{sfx}": (ua, 0.0, 0.0),
                    f"forearm_{sfx}": (fa, 0.0, 0.0),
                    f"hand_{sfx}": (ha, 0.0, 0.0),
                })
                pts = _skin_pts(hand_verts[sfx], f"hand_{sfx}", g_rot, g_pos)
                for solid, (a, b, r) in zip(("thigh", "cuff"),
                                            _thigh_solids(sfx, g_rot, g_pos)):
                    c = _seg_clearance(pts, a, b, r)
                    if c < worst[0]:
                        worst = (c, f"t={t:.1f} hand_{sfx} vs {solid}_{sfx}")
    results["legs_rock + idle sway"] = worst

    # Case 2: the scoot plant path (legs_rock is ducked during scoots,
    # so the scoot clip alone is the whole pose). Both hands vs both
    # thighs — the planted arm crosses the hip line.
    for cname in ("scoot_right", "scoot_left"):
        rot = clip_rot[cname]
        dur = max(k[0] for keys in rot.values() for k in keys)
        worst = (1e9, "")
        for t in np.arange(0.0, dur, 1.0 / 30.0):
            g_rot, g_pos = _fk({j: _sample_euler(keys, t) for j, keys in rot.items()})
            for hs in ("l", "r"):
                pts = _skin_pts(hand_verts[hs], f"hand_{hs}", g_rot, g_pos)
                for ts_ in ("l", "r"):
                    for solid, (a, b, r) in zip(("thigh", "cuff"),
                                                _thigh_solids(ts_, g_rot, g_pos)):
                        c = _seg_clearance(pts, a, b, r)
                        if c < worst[0]:
                            worst = (c, f"t={t:.2f} hand_{hs} vs {solid}_{ts_}")
        results[cname] = worst

    if os.environ.get("BODY_DEBUG_PATH"):
        rot = clip_rot["scoot_right"]
        print("  scoot_right hand_l center path (model space):")
        for t in np.arange(0.0, 1.35, 0.1):
            g_rot, g_pos = _fk({j: _sample_euler(keys, t) for j, keys in rot.items()})
            c = _skin_pts(hand_verts["l"].mean(axis=0)[None, :], "hand_l", g_rot, g_pos)[0]
            print(f"    t={t:.1f}  ({c[0]:+.3f}, {c[1]:+.3f}, {c[2]:+.3f})")

    print("  hand-vs-thigh clearance (worst, cm):")
    for case, (w, where) in results.items():
        print(f"    {case:24s} {w * 100:+6.2f}   ({where})")
    results = {k: v[0] for k, v in results.items()}
    worst_all = min(results.values())
    assert worst_all > -0.005, (
        f"hand/thigh intersection: worst clearance {worst_all * 100:.2f} cm "
        "(tolerance -0.5 cm) — retune WRIST_*, the legs_rock thigh gain, "
        "or the scoot arm keys")


check_clearance()


# ── glTF assembly ───────────────────────────────────────────────────────
blob = bytearray()
buffer_views = []
accessors = []


def pad4():
    while len(blob) % 4 != 0:
        blob.extend(b"\x00")


def add_view(data: bytes, target=None):
    pad4()
    offset = len(blob)
    blob.extend(data)
    view = BufferView(buffer=0, byteOffset=offset, byteLength=len(data))
    if target is not None:
        view.target = target
    buffer_views.append(view)
    return len(buffer_views) - 1


def add_accessor(data_np, comp_type, acc_type, target=None, minmax=False):
    data_np = np.ascontiguousarray(data_np)
    view = add_view(data_np.tobytes(), target)
    acc = Accessor(
        bufferView=view, componentType=comp_type, count=len(data_np), type=acc_type
    )
    if minmax:
        if data_np.ndim == 1:
            acc.min = [float(data_np.min())]
            acc.max = [float(data_np.max())]
        else:
            acc.min = [float(v) for v in data_np.min(axis=0)]
            acc.max = [float(v) for v in data_np.max(axis=0)]
    accessors.append(acc)
    return len(accessors) - 1


gltf = GLTF2()
gltf.scene = 0

# Nodes: joints first (indices match JIDX), then the skinned mesh node.
nodes = []
for name, parent, gpos in JOINTS:
    local = gpos if parent is None else gpos - dict((n, p) for n, _, p in JOINTS)[parent]
    nodes.append(Node(name=name, translation=[float(v) for v in local],
                      rotation=[0.0, 0.0, 0.0, 1.0]))
for i, (name, parent, _) in enumerate(JOINTS):
    if parent is not None:
        pi = JIDX[parent]
        if nodes[pi].children is None:
            nodes[pi].children = []
        nodes[pi].children.append(i)

# Embedded textures: PNG-encode the generated maps into the binary
# blob. One REPEAT sampler serves all of them (the cylindrical UVs wrap
# and the seam-split verts sample u > 1). Names must not contain
# "normal" — the engine uploads such textures as linear data.
TEXTURES = body_textures()
gltf_samplers = [GltfSampler(wrapS=10497, wrapT=10497, magFilter=9729, minFilter=9729)]
gltf_images = []
gltf_textures = []
tex_index = {}
for tname, timg in TEXTURES.items():
    buf = io.BytesIO()
    PILImage.fromarray(timg, "RGBA").save(buf, format="PNG")
    view = add_view(buf.getvalue())
    gltf_images.append(GltfImage(bufferView=view, mimeType="image/png", name=tname))
    gltf_textures.append(Texture(source=len(gltf_images) - 1, sampler=0, name=tname))
    tex_index[tname] = len(gltf_textures) - 1

# Group bboxes for planar UVs (shared frame per hand/foot so features
# like the knuckle spots land consistently across a group's parts).
group_bounds = {}
for joint_name, mesh, _c, _r, _t, uvspec in parts:
    if uvspec and uvspec[0] == "planar":
        g = uvspec[1]
        lo, hi = mesh.vertices.min(axis=0), mesh.vertices.max(axis=0)
        if g in group_bounds:
            glo, ghi = group_bounds[g]
            group_bounds[g] = (np.minimum(glo, lo), np.maximum(ghi, hi))
        else:
            group_bounds[g] = (lo, hi)

# Materials + primitives
materials = []
mat_index = {}


def material_for(color, roughness, tex=None):
    key = (color, roughness, tex)
    if key not in mat_index:
        pbr = PbrMetallicRoughness(metallicFactor=0.0, roughnessFactor=roughness)
        if tex is None:
            pbr.baseColorFactor = list(color)
        else:
            # The color lives in the texture (sRGB-encoded there).
            pbr.baseColorFactor = [1.0, 1.0, 1.0, 1.0]
            pbr.baseColorTexture = TextureInfo(index=tex_index[tex])
        materials.append(Material(name=f"mat_{len(materials)}",
                                  pbrMetallicRoughness=pbr))
        mat_index[key] = len(materials) - 1
    return mat_index[key]


primitives = []
for joint_name, mesh, color, roughness, tex, uvspec in parts:
    verts = mesh.vertices.astype(np.float32)
    norms = mesh.vertex_normals.astype(np.float32)
    faces = mesh.faces.astype(np.uint32)
    uv = None
    if uvspec is not None:
        kind = uvspec[0]
        if kind == "cyl":
            uv = cylindrical_uv(verts, uvspec[1], uvspec[2], uvspec[3])
            verts, norms, faces, uv = split_uv_seam(verts, norms, faces, uv)
        elif kind == "planar":
            lo, hi = group_bounds[uvspec[1]]
            span = np.maximum(hi - lo, 1e-6)
            uv = np.stack([(verts[:, 0] - lo[0]) / span[0],
                           (verts[:, 2] - lo[2]) / span[2]], axis=1)
        elif kind == "patch":
            off, scale = uvspec[1], uvspec[2]
            lo, hi = verts.min(axis=0), verts.max(axis=0)
            span = np.maximum(hi - lo, 1e-6)
            uv = np.stack([off + scale * (verts[:, 0] - lo[0]) / span[0],
                           off + scale * (verts[:, 2] - lo[2]) / span[2]], axis=1)
        uv = uv.astype(np.float32)
    faces = faces.reshape(-1)
    ji = JIDX[joint_name]
    joints_attr = np.full((len(verts), 4), 0, dtype=np.uint16)
    joints_attr[:, 0] = ji
    weights_attr = np.zeros((len(verts), 4), dtype=np.float32)
    weights_attr[:, 0] = 1.0

    a_pos = add_accessor(verts, FLOAT, "VEC3", ARRAY_BUFFER, minmax=True)
    a_nrm = add_accessor(norms, FLOAT, "VEC3", ARRAY_BUFFER)
    a_jnt = add_accessor(joints_attr, UNSIGNED_SHORT, "VEC4", ARRAY_BUFFER)
    a_wgt = add_accessor(weights_attr, FLOAT, "VEC4", ARRAY_BUFFER)
    a_idx = add_accessor(faces, UNSIGNED_INT, "SCALAR", ELEMENT_ARRAY_BUFFER)
    attrs = Attributes(POSITION=a_pos, NORMAL=a_nrm, JOINTS_0=a_jnt, WEIGHTS_0=a_wgt)
    if uv is not None:
        attrs.TEXCOORD_0 = add_accessor(uv, FLOAT, "VEC2", ARRAY_BUFFER)
    primitives.append(Primitive(
        attributes=attrs,
        indices=a_idx,
        material=material_for(color, roughness, tex),
    ))

gltf.meshes = [Mesh(name="body", primitives=primitives)]

# Skin: inverse bind matrices = inverse of the pure-translation bind.
ibms = np.zeros((len(JOINTS), 4, 4), dtype=np.float32)
for i, (_, _, gpos) in enumerate(JOINTS):
    m = np.eye(4, dtype=np.float32)
    m[3, 0:3] = -gpos  # glTF matrices are column-major; row 3 = translation
    ibms[i] = m
a_ibm = add_accessor(ibms.reshape(len(JOINTS), 16), FLOAT, "MAT4")
gltf.skins = [Skin(name="body_rig", joints=list(range(len(JOINTS))),
                   inverseBindMatrices=a_ibm, skeleton=JIDX["root"])]

mesh_node = Node(name="body", mesh=0, skin=0)
nodes.append(mesh_node)
gltf.nodes = nodes
gltf.scenes = [Scene(nodes=[JIDX["root"], len(nodes) - 1])]
gltf.materials = materials
gltf.images = gltf_images
gltf.samplers = gltf_samplers
gltf.textures = gltf_textures

# Animations
animations = []
for clip_name, rot_tracks, trans_tracks in CLIPS:
    samplers = []
    channels = []
    for joint, keys in rot_tracks.items():
        times = np.array([t for t, _ in keys], dtype=np.float32)
        quats = np.array([quat_from_euler(*e) for _, e in keys], dtype=np.float32)
        a_in = add_accessor(times, FLOAT, "SCALAR", minmax=True)
        a_out = add_accessor(quats, FLOAT, "VEC4")
        samplers.append(AnimationSampler(input=a_in, output=a_out, interpolation="LINEAR"))
        channels.append(AnimationChannel(
            sampler=len(samplers) - 1,
            target=AnimationChannelTarget(node=JIDX[joint], path="rotation"),
        ))
    for joint, keys in trans_tracks.items():
        base = np.array(nodes[JIDX[joint]].translation, dtype=np.float32)
        times = np.array([t for t, _ in keys], dtype=np.float32)
        vals = np.array([base + np.array(d, dtype=np.float32) for _, d in keys],
                        dtype=np.float32)
        a_in = add_accessor(times, FLOAT, "SCALAR", minmax=True)
        a_out = add_accessor(vals, FLOAT, "VEC3")
        samplers.append(AnimationSampler(input=a_in, output=a_out, interpolation="LINEAR"))
        channels.append(AnimationChannel(
            sampler=len(samplers) - 1,
            target=AnimationChannelTarget(node=JIDX[joint], path="translation"),
        ))
    animations.append(Animation(name=clip_name, samplers=samplers, channels=channels))
gltf.animations = animations

gltf.buffers = [Buffer(byteLength=len(blob))]
gltf.bufferViews = buffer_views
gltf.accessors = accessors
gltf.set_binary_blob(bytes(blob))

path = os.path.join(OUT_DIR, "body.glb")
gltf.save_binary(path)
print(f"wrote {path}  ({len(parts)} parts, {len(JOINTS)} joints, {len(CLIPS)} clips)")
print("  variants:", ", ".join(IDLE_VARIANTS))
print("  fidget durations (mirror in body.rhai!):",
      ", ".join(f"{k}={v}" for k, v in FIDGET_DURS.items()))
