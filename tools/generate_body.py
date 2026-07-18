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

import os
import struct

import numpy as np
import trimesh
from pygltflib import (
    GLTF2, Scene, Node, Mesh, Primitive, Attributes, Skin, Material,
    PbrMetallicRoughness, Animation, AnimationChannel, AnimationChannelTarget,
    AnimationSampler, Buffer, BufferView, Accessor,
    ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER, FLOAT, UNSIGNED_INT, UNSIGNED_SHORT,
)

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
ELBOW_L = np.array([+0.225, 0.03, -0.04])
ELBOW_R = np.array([-0.225, 0.03, -0.04])
WRIST_L = np.array([+0.155, 0.11, 0.17])  # resting on the thigh
WRIST_R = np.array([-0.155, 0.11, 0.17])

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


parts = []  # (joint_name, trimesh, color, roughness)

for side, hip, knee, ankle in ((+1.0, HIP_L, KNEE_L, ANKLE_L), (-1.0, HIP_R, KNEE_R, ANKLE_R)):
    sfx = "l" if side > 0 else "r"
    parts.append((f"thigh_{sfx}", capsule_between(hip, knee, THIGH_R), SKIN, 0.9))
    parts.append((f"calf_{sfx}", capsule_between(knee, ankle, CALF_R), SKIN_LOWER, 0.9))
    # Toes dipped toward the water and turned slightly OUT — feet at ease.
    foot = box_at([0.085, 0.055, 0.22],
                  tx=ankle[0], ty=ankle[1] - 0.015, tz=ankle[2] + 0.07,
                  rx=d2r(-14), ry=side * d2r(5))
    parts.append((f"foot_{sfx}", foot, FOOT, 0.9))
    # Shorts cuff on the upper thigh (rides with the thigh joint).
    cvec = (knee - hip) / np.linalg.norm(knee - hip)
    c0 = hip + np.array([0.0, 0.012, 0.0])
    parts.append((f"thigh_{sfx}", capsule_between(c0, c0 + cvec * 0.20, THIGH_R + 0.022), SHORTS, 0.9))

# Pelvis/seat block (shorts) on the root — spans the hips, stops shy of
# the legs' outer edges so the thighs read as separate from it.
parts.append(("root", box_at([0.42, 0.16, 0.26], ty=0.03, tz=-0.16), SHORTS, 0.9))
# Torso: belly on root, chest + shoulder bar on spine (tee). Slim and
# pulled BACK: the chest must stay clear of the first-person camera's
# near plane (the eye sits ~6 cm above and just inboard of it) or it
# clips open into a dome with a hole when the player looks down.
# Belly slim and pulled back — looking down it should foreshorten under
# the chest, not sit on the lap like a ball.
parts.append(("spine", capsule_between([0.0, 0.06, -0.17], [0.0, 0.19, -0.17], 0.095), TEE, 0.9))
parts.append(("chest", capsule_between([0.0, 0.19, -0.16], [0.0, 0.30, -0.155], 0.10), TEE, 0.9))
# Clavicles: from near-center chest out to each shoulder ball.
for side, clav in ((+1.0, CLAV_L), (-1.0, CLAV_R)):
    sfx = "l" if side > 0 else "r"
    parts.append((f"clavicle_{sfx}",
                  capsule_between(clav, [side * (SHOULDER - 0.01), 0.29, SHOULDER_Z], 0.055),
                  TEE, 0.9))

for side, elbow, wrist in ((+1.0, ELBOW_L, WRIST_L), (-1.0, ELBOW_R, WRIST_R)):
    sfx = "l" if side > 0 else "r"
    shoulder = np.array([side * SHOULDER, 0.29, SHOULDER_Z])
    parts.append((f"upper_arm_{sfx}", capsule_between(shoulder, elbow, 0.045), SKIN, 0.9))
    # Tee sleeve over the upper third.
    svec = (elbow - shoulder) / np.linalg.norm(elbow - shoulder)
    parts.append((f"upper_arm_{sfx}",
                  capsule_between(shoulder, shoulder + svec * 0.10, 0.058), TEE, 0.9))
    parts.append((f"forearm_{sfx}", capsule_between(elbow, wrist, 0.038), SKIN, 0.9))
    hand = box_at([0.075, 0.03, 0.16],
                  tx=wrist[0], ty=wrist[1] - 0.005, tz=wrist[2] + 0.065, rx=d2r(-8))
    parts.append((f"hand_{sfx}", hand, SKIN, 0.9))


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


def idle_clip():
    rot = {}
    n = 17
    for j, amp, rate, phase in (
        ("calf_l", 3.4, 1.0, 0.0), ("calf_r", 3.0, 1.15, 2.1),
        ("foot_l", 2.0, 1.0, 0.7), ("foot_r", 1.8, 1.15, 2.8),
    ):
        keys = []
        for i in range(n):
            t = IDLE_TIME * i / (n - 1)
            keys.append((t, (amp * np.sin(2 * np.pi * t / IDLE_TIME * 2.0 * rate + phase), 0.0, 0.0)))
        # force exact loop closure
        keys[-1] = (IDLE_TIME, keys[0][1])
        rot[j] = keys
    # breathing: tiny spine sway
    rot["spine"] = [(0.0, (0.0, 0.0, 0.0)), (IDLE_TIME * 0.5, (1.2, 0.0, 0.4)),
                    (IDLE_TIME, (0.0, 0.0, 0.0))]
    return rot, {}


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
        # Left arm: reach down-back beside the hip, plant, take weight,
        # return to rest as the body settles.
        "upper_arm_l": [(0.0, (0, 0, 0)), (0.28, (26, 0, 24)), (0.60, (30, 0, 26)),
                        (0.95, (12, 0, 10)), (1.30, (0, 0, 0))],
        "forearm_l": [(0.0, (0, 0, 0)), (0.30, (-38, 0, 0)), (0.62, (-46, 0, 0)),
                      (0.95, (-16, 0, 0)), (1.30, (0, 0, 0))],
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
ROT_I, TRANS_I = idle_clip()

CLIPS = [
    ("idle", ROT_I, TRANS_I),
    ("scoot_right", ROT_R, TRANS_R),
    ("scoot_left", ROT_L, TRANS_L),
]


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

# Materials + primitives
materials = []
mat_index = {}


def material_for(color, roughness):
    key = (color, roughness)
    if key not in mat_index:
        materials.append(Material(
            name=f"mat_{len(materials)}",
            pbrMetallicRoughness=PbrMetallicRoughness(
                baseColorFactor=list(color), metallicFactor=0.0, roughnessFactor=roughness
            ),
        ))
        mat_index[key] = len(materials) - 1
    return mat_index[key]


primitives = []
for joint_name, mesh, color, roughness in parts:
    verts = mesh.vertices.astype(np.float32)
    norms = mesh.vertex_normals.astype(np.float32)
    faces = mesh.faces.astype(np.uint32).reshape(-1)
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
    primitives.append(Primitive(
        attributes=Attributes(POSITION=a_pos, NORMAL=a_nrm, JOINTS_0=a_jnt, WEIGHTS_0=a_wgt),
        indices=a_idx,
        material=material_for(color, roughness),
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
print(f"wrote {path}  ({len(parts)} parts, {len(JOINTS)} joints, "
      f"clips: {', '.join(name for name, _, _ in CLIPS)})")
