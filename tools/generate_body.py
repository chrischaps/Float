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
    # Proper mitt: palm block, fused finger mass curling slightly down
    # (knuckle bevel from the angle change), opposable thumb on the
    # inboard side. One joint — the SHAPE carries the read, which
    # matters most when a palm is planted on the deck near the camera.
    palm = box_at([0.072, 0.026, 0.085],
                  tx=wrist[0], ty=wrist[1] - 0.004, tz=wrist[2] + 0.045, rx=d2r(-8))
    parts.append((f"hand_{sfx}", palm, SKIN, 0.9))
    fingers = box_at([0.066, 0.021, 0.082],
                     tx=wrist[0], ty=wrist[1] - 0.016, tz=wrist[2] + 0.122, rx=d2r(-22))
    parts.append((f"hand_{sfx}", fingers, SKIN, 0.9))
    thumb = capsule_between(
        [wrist[0] - side * 0.032, wrist[1] - 0.006, wrist[2] + 0.028],
        [wrist[0] - side * 0.058, wrist[1] - 0.018, wrist[2] + 0.088],
        0.015,
    )
    parts.append((f"hand_{sfx}", thumb, SKIN, 0.9))


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


def solve_arm(wrist_target, coarse=6.0):
    """Brute-force 2-bone IK for the LEFT arm: grid-search upper_arm
    (rx, rz) x forearm rx so the wrist lands on the model-space target.
    Blind euler authoring kept missing (the forearm's effective axis
    flips as the upper arm swings); solving is exact and reusable."""
    s = np.array([+SHOULDER, 0.29, SHOULDER_Z])
    e_off = ELBOW_L - s
    w_off = WRIST_L - ELBOW_L
    target = np.array(wrist_target, dtype=float)
    best = (1e9, (0.0, 0.0), 0.0)
    for ua_x in np.arange(-70, 71, coarse):
        for ua_z in np.arange(-10, 61, coarse):
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
# self-soothing almost rocking chair action." One kick per cycle per
# leg, legs alternating half a phase apart: the knee extends fairly
# briskly, hangs, then the calf pendulums back past neutral and
# settles — a rocking chair's push-glide-return. Feet flex with a lag;
# thighs lift a touch so the motion connects to the pelvis. Runs as an
# ADDITIVE layer on its own clock, so it persists through variant
# crossfades, fidgets, everything (ducked only during scoot steps).
ROCK_TIME = 5.2


def rock_wave(tn):
    """Kick-hang-return waveform over one normalized cycle."""
    pts_t = [0.0, 0.12, 0.30, 0.55, 0.78, 1.0]
    pts_v = [0.0, 24.0, 18.0, -7.0, 3.0, 0.0]
    return np.interp(tn, pts_t, pts_v)


def make_legs_rock():
    rot = {}
    n = 33
    for side, phase, scale in (("l", 0.0, 1.0), ("r", 0.5, 0.94)):
        for j, gain, lag in (("calf", 1.0, 0.0), ("foot", 0.38, 0.06),
                             ("thigh", -0.12, 0.0)):
            keys = []
            for i in range(n):
                t = ROCK_TIME * i / (n - 1)
                tn = (t / ROCK_TIME + phase + lag) % 1.0
                keys.append((t, (rock_wave(tn) * gain * scale, 0.0, 0.0)))
            keys[-1] = (ROCK_TIME, keys[0][1])
            rot[f"{j}_{side}"] = keys
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
        # One lazy kick at the water, follow-through, settle.
        rot["calf_l"] = [(0.0, (0, 0, 0)), (0.5, (26, 0, 0)), (0.9, (-8, 0, 0)),
                         (1.4, (10, 0, 0)), (2.0, (0, 0, 0)), (2.4, (0, 0, 0))]
        rot["foot_l"] = [(0.0, (0, 0, 0)), (0.55, (14, 0, 0)), (1.0, (-10, 0, 0)),
                         (1.6, (4, 0, 0)), (2.2, (0, 0, 0)), (2.4, (0, 0, 0))]
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
print(f"wrote {path}  ({len(parts)} parts, {len(JOINTS)} joints, {len(CLIPS)} clips)")
print("  variants:", ", ".join(IDLE_VARIANTS))
print("  fidget durations (mirror in body.rhai!):",
      ", ".join(f"{k}={v}" for k, v in FIDGET_DURS.items()))
