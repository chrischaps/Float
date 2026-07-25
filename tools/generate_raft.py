"""Generate models/raft.glb and models/raft2.glb — hand-lashed log rafts.

Nine driftwood logs of slightly irregular radius and length, two cross-beams
lashed underneath, and rope wrappings at each junction. The irregularity is
the point: this should read as something a stranded person built by hand,
not milled lumber. Seeded so each raft is reproducible.

raft2 is the Visitor's raft (scripts/raft_visitor.rhai): the same
construction from a different seed, weathered — sun-bleached gray wood,
a third of the lashings gone, some of the survivors frayed and slipped.
Recognizably the same kind of raft, built by the same kind of hands,
just older.

Output: models/raft.glb, models/raft2.glb, models/buoy.glb
Usage:  python tools/generate_raft.py
"""

import os

import numpy as np
import trimesh
from trimesh.visual.material import PBRMaterial

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
os.makedirs(OUT_DIR, exist_ok=True)

# Raft footprint (meters). Logs run along Z; the player sits on the +Z edge.
DECK_WIDTH = 2.4      # X extent covered by logs
LOG_LENGTH = 2.3      # nominal Z length
LOG_RADIUS = 0.13     # nominal log radius
NUM_LOGS = 9
BEAM_RADIUS = 0.07

# Palette: sun-bleached driftwood browns, one rope tan.
LOG_COLORS = [
    (0.55, 0.42, 0.28, 1.0),
    (0.60, 0.47, 0.32, 1.0),
    (0.50, 0.38, 0.26, 1.0),
    (0.63, 0.51, 0.36, 1.0),
]
ROPE_COLOR = (0.78, 0.68, 0.48, 1.0)

# The Visitor's palette: the same browns years further along — grayed out,
# desaturated, the rope dulled toward the wood.
LOG_COLORS_WEATHERED = [
    (0.58, 0.55, 0.48, 1.0),
    (0.52, 0.50, 0.45, 1.0),
    (0.62, 0.60, 0.53, 1.0),
    (0.48, 0.45, 0.40, 1.0),
]
ROPE_COLOR_WEATHERED = (0.62, 0.56, 0.46, 1.0)


def pbr(mesh, color, roughness=0.85):
    mesh.visual = trimesh.visual.TextureVisuals(
        material=PBRMaterial(
            baseColorFactor=color,
            metallicFactor=0.0,
            roughnessFactor=roughness,
        )
    )
    return mesh


def transform(tx=0.0, ty=0.0, tz=0.0, rx=0.0, ry=0.0, rz=0.0):
    """Translation + XYZ euler rotation (radians) as a 4x4 matrix."""
    m = trimesh.transformations.euler_matrix(rx, ry, rz, "sxyz")
    m[:3, 3] = [tx, ty, tz]
    return m


def log_cylinder(radius, length, color, roughness=0.85):
    # trimesh cylinders extend along +Z, which is exactly the log direction.
    mesh = trimesh.creation.cylinder(radius=radius, height=length, sections=48)
    return pbr(mesh, color, roughness)


def rope_wrap(log_radius, x, z, color, tilt=0.0, minor_radius=0.022):
    """A slightly flattened torus hugging a log at (x, z), axis along Z."""
    ring = trimesh.creation.torus(
        major_radius=log_radius + 0.018,
        minor_radius=minor_radius,
        major_sections=36,
        minor_sections=12,
    )
    # Torus lies in XY plane (axis = Z); rotate so it wraps around the log's
    # Z axis -> that's already correct. Squash slightly along Y so it sits
    # into the wood, and jitter the tilt so wraps look hand-thrown.
    ring.apply_scale([1.0, 0.92, 1.35])
    ring.apply_transform(transform(tx=x, tz=z, rz=tilt))
    return pbr(ring, color, roughness=0.95)


def build_raft(seed, log_colors, rope_color,
               rope_skip_chance=0.0, fray_chance=0.0, log_roughness=0.85):
    """Build one raft as a trimesh.Scene.

    Weathering decisions (skipped lashings, fraying) draw from a SEPARATE
    rng stream so the baseline seed-7 draw sequence — raft.glb's visual
    identity — is byte-for-byte untouched by their presence in the code.
    """
    rng = np.random.default_rng(seed)
    wrng = np.random.default_rng(seed + 1000)
    parts = []

    # ── Logs ────────────────────────────────────────────────────────
    # Lay NUM_LOGS side by side along X. Radii/lengths jitter; each log's
    # top surface aims for y≈LOG_RADIUS so the deck is walkable-flat-ish
    # but bumpy.
    slot_width = DECK_WIDTH / NUM_LOGS
    log_info = []  # (x, radius) for beams and lashings
    x = -DECK_WIDTH / 2 + slot_width / 2
    for i in range(NUM_LOGS):
        radius = LOG_RADIUS * rng.uniform(0.88, 1.12)
        length = LOG_LENGTH * rng.uniform(0.94, 1.06)
        color = log_colors[i % len(log_colors)]
        log = log_cylinder(radius, length, color, log_roughness)
        # Small yaw so logs aren't perfectly parallel; z offset so ends are ragged.
        yaw = rng.uniform(-0.02, 0.02)
        z_off = rng.uniform(-0.06, 0.06)
        y = radius  # rest on y=0 plane; deck top ends up ~2*radius
        log.apply_transform(transform(tx=x, ty=y, tz=z_off, ry=yaw))
        parts.append(log)
        log_info.append((x, radius))
        x += slot_width * rng.uniform(0.97, 1.03)

    # ── Cross-beams under the logs, near each end ──────────────────
    for z in (-LOG_LENGTH * 0.36, LOG_LENGTH * 0.36):
        beam = trimesh.creation.cylinder(radius=BEAM_RADIUS, height=DECK_WIDTH + 0.25, sections=32)
        # Cylinder along Z -> rotate 90° about Y to run along X.
        beam.apply_transform(transform(ty=-BEAM_RADIUS * 0.6, tz=z, ry=np.pi / 2))
        parts.append(pbr(beam, log_colors[2], log_roughness))

    # ── Rope lashings where each log crosses each beam ─────────────
    for z in (-LOG_LENGTH * 0.36, LOG_LENGTH * 0.36):
        for (lx, lr) in log_info[::2]:  # every other log: sparser, hand-made
            # Baseline draws happen unconditionally, BEFORE any weathering
            # decision, to keep the seed-7 sequence identical.
            z_jitter = rng.uniform(-0.02, 0.02)
            tilt = rng.uniform(-0.15, 0.15)
            if wrng.random() < rope_skip_chance:
                continue  # a lashing lost to the years
            minor = 0.022
            drop = 0.0
            if wrng.random() < fray_chance:
                # Frayed and slipped: thinner, thrown at a lazier angle,
                # sagged down the log's curve.
                minor = 0.014
                tilt += wrng.uniform(-0.35, 0.35)
                drop = wrng.uniform(0.005, 0.010)
            wrap = rope_wrap(lr, lx, z + z_jitter, rope_color, tilt=tilt, minor_radius=minor)
            # move wraps up to log center height (less any weathering sag)
            wrap.apply_translation([0.0, lr - drop, 0.0])
            parts.append(wrap)

    scene = trimesh.Scene()
    for i, part in enumerate(parts):
        scene.add_geometry(part, node_name=f"part_{i}")
    return scene, len(parts)


deck_top = 2 * LOG_RADIUS  # nominal deck surface height

# ── The player's raft (visually identical to the original seed-7 build) ─
scene, n_parts = build_raft(7, LOG_COLORS, ROPE_COLOR)
raft_path = os.path.join(OUT_DIR, "raft.glb")
# include_normals: trimesh omits the NORMAL attribute by default, and the
# engine falls back to flat [0,1,0] normals -> banded/acne-prone shading.
scene.export(raft_path, include_normals=True)
print(f"wrote {raft_path}  ({n_parts} parts, deck top ~{deck_top:.2f} m)")

# ── The Visitor's raft: weathered twin ──────────────────────────────
scene2, n_parts2 = build_raft(
    12, LOG_COLORS_WEATHERED, ROPE_COLOR_WEATHERED,
    rope_skip_chance=0.35, fray_chance=0.30, log_roughness=0.9,
)
raft2_path = os.path.join(OUT_DIR, "raft2.glb")
scene2.export(raft2_path, include_normals=True)
print(f"wrote {raft2_path}  ({n_parts2} parts, weathered)")

# ── Debug buoy: a bright sphere scripts pin to ocean_height(x, z) ───────
# If it ever detaches from the rendered water surface, CPU/GPU wave parity
# is broken (see scripts/wave_probe.rhai).
buoy = trimesh.creation.icosphere(subdivisions=2, radius=0.18)
buoy = pbr(buoy, (1.0, 0.25, 0.1, 1.0), roughness=0.4)
bscene = trimesh.Scene()
bscene.add_geometry(buoy, node_name="buoy")
buoy_path = os.path.join(OUT_DIR, "buoy.glb")
bscene.export(buoy_path, include_normals=True)
print(f"wrote {buoy_path}")
