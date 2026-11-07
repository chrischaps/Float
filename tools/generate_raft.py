"""Generate models/raft.glb and models/raft2.glb — hand-lashed log rafts.

Nine driftwood logs of slightly irregular radius and length, two cross-beams
lashed underneath, and rope wrappings at each junction. The irregularity is
the point: this should read as something a stranded person built by hand,
not milled lumber. Seeded so each raft is reproducible.

Detail pass (issue #5): the logs are no longer clean cylinders. Each one
tapers butt-to-tip, bows slightly, goes a little oval, and carries a few
knots — geometry bulges on the flanks (the deck top stays flush so the
seat and legs keep their framing) with the knot's dark eye baked into the
log's own albedo map at the same (u, v). Ends are chamfered and cut a
touch off-square, capped with end-grain rings. Lashings are three-turn
helices of twisted rope ending in a knot and a short tail, not tori.
Textures come from tools/generate_raft_texture.py and are embedded.

raft2 is the Visitor's raft (scripts/raft_visitor.rhai): the same
construction from a different seed, weathered — sun-bleached gray wood
with salt bloom and more checks, a third of the lashings gone, some of
the survivors frayed: slack, fewer turns, a long unravelling tail.
Recognizably the same kind of raft, built by the same kind of hands,
just older.

Three rng streams, so the baseline seed-7 draw sequence (log radii,
lengths, spacing, yaw, lashing jitter — the raft's extents and layout)
is untouched by the detail and weathering code:
  rng   baseline layout (unchanged draw order since the first raft)
  wrng  weathering decisions (seed + 1000)
  drng  surface detail: taper, bow, knots, textures (seed + 2000)

Output: models/raft.glb, models/raft2.glb, models/buoy.glb
Usage:  python tools/generate_raft.py
"""

import os
import sys

import numpy as np
import trimesh
from pygltflib import GLTF2, Texture, Sampler
from PIL import Image
from trimesh.visual.material import PBRMaterial

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_raft_texture import (  # noqa: E402
    gen_endgrain, gen_rope, gen_wood, ROPE_TWISTS,
)

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
os.makedirs(OUT_DIR, exist_ok=True)

# Raft footprint (meters). Logs run along Z; the player sits on the +Z edge.
DECK_WIDTH = 2.4      # X extent covered by logs
LOG_LENGTH = 2.3      # nominal Z length
LOG_RADIUS = 0.13     # nominal log radius
NUM_LOGS = 9
BEAM_RADIUS = 0.07

LOG_SECTIONS = 48     # verts around a log
LOG_RINGS = 22        # base interior rings along a log (knots add more)
CHAMFER = 0.015       # end chamfer depth (m)
ROPE_MINOR = 0.016    # lashing rope radius
ROPE_LAY = 0.05       # rope length per strand twist (m) — sets rope UV scale

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


class Part:
    """Accumulates explicit vertices/normals/uvs/faces for one material.
    Built by hand (not trimesh primitives) so seams can be UV-split
    while keeping the smooth normal of the unsplit surface."""

    def __init__(self):
        self.v, self.n, self.uv, self.f = [], [], [], []
        self.count = 0

    def add(self, verts, normals, uvs, faces):
        # Wind every triangle to agree with its vertex normals, so a
        # builder's grid orientation can never leave a face back-culled.
        faces = np.asarray(faces)
        a, b, c = (verts[faces[:, k]] for k in range(3))
        geo = np.cross(b - a, c - a)
        avg = normals[faces].sum(axis=1)
        flip = np.sum(geo * avg, axis=1) < 0
        faces = faces.copy()
        faces[flip] = faces[flip][:, [0, 2, 1]]
        self.v.append(verts)
        self.n.append(normals)
        self.uv.append(uvs)
        self.f.append(faces + self.count)
        self.count += len(verts)

    def mesh(self, name, image, roughness):
        n = np.concatenate(self.n)
        n /= np.linalg.norm(n, axis=1, keepdims=True)
        mesh = trimesh.Trimesh(
            vertices=np.concatenate(self.v), faces=np.concatenate(self.f),
            vertex_normals=n, process=False,
        )
        mesh.visual = trimesh.visual.TextureVisuals(
            uv=np.concatenate(self.uv),
            material=PBRMaterial(
                name=name,
                baseColorTexture=Image.fromarray(image, "RGBA"),
                baseColorFactor=[255, 255, 255, 255],
                metallicFactor=0.0,
                roughnessFactor=roughness,
            ),
        )
        return mesh


def grid_faces(rows, cols):
    """Quads of a rows x cols vertex grid, two CCW triangles each."""
    r, c = np.meshgrid(np.arange(rows - 1), np.arange(cols - 1), indexing="ij")
    a = (r * cols + c).ravel()
    b, d = a + 1, a + cols
    e = d + 1
    return np.concatenate([np.stack([a, d, b], 1), np.stack([b, d, e], 1)])


def wrap_grid(P, N, u_rows, v_cols):
    """A surface wrapping around its columns: P/N are (rows, cols, 3),
    the column seam is duplicated so UVs can run 0..1 cleanly."""
    P = np.concatenate([P, P[:, :1]], axis=1)
    N = np.concatenate([N, N[:, :1]], axis=1)
    rows, cols = P.shape[:2]
    uu, vv = np.meshgrid(u_rows, v_cols, indexing="ij")
    uv = np.stack([uu, vv], -1)
    return P.reshape(-1, 3), N.reshape(-1, 3), uv.reshape(-1, 2), grid_faces(rows, cols)


# ── Logs ────────────────────────────────────────────────────────────

def plan_log(drng, length, taper_max=0.08, knots_max=4, bow_max=0.012):
    """Draw a log's surface detail. Knots are (theta, s, bulge, width):
    s in [-0.5, 0.5] along the log, theta around it (0 = +X, pi/2 = up)."""
    detail = {
        # Every shape term is drawn so the deck TOP can only hold or sink —
        # never rise — or the seated body (framed against a flat deck at
        # 2 x radius) would sink into the wood. Butts sit aft (-Z), tips
        # toward the seat edge; ovality and the 3-lobe term phase so the
        # top (theta = pi/2) is a trough; the bow can only sag.
        "taper": -drng.uniform(0.0, taper_max),
        "bow": drng.uniform(-bow_max, bow_max),
        "bow_y": -drng.uniform(0.0, 0.3) * bow_max,
        "oval": (drng.uniform(0.0, 0.035), drng.uniform(-np.pi / 2, np.pi / 2)),
        "lobe": (drng.uniform(0.0, 0.015), drng.uniform(np.pi, 2 * np.pi)),
        "slant": drng.uniform(-0.12, 0.12, size=(2, 2)),  # per end, (x, y)
        "knots": [],
    }
    for _ in range(drng.integers(1, knots_max + 1)):
        theta = drng.uniform(0, 2 * np.pi)
        s = drng.uniform(-0.40, 0.40)
        # Flush on top: the deck surface (and the seat on it) stays put.
        up = np.cos(theta - np.pi / 2)
        bulge = 0.0 if up > 0.6 else drng.uniform(0.005, 0.010)
        width = drng.uniform(0.022, 0.034)
        detail["knots"].append((theta, s, bulge, width))
    return detail


def log_surface(radius, length, d, theta, s):
    """Radius field r(theta, s) and axis offset (x, y)(s) for a log."""
    a_ov, ph_ov = d["oval"]
    a_lb, ph_lb = d["lobe"]
    r = radius * (1.0 + d["taper"] * s * 2.0)
    r = r * (1.0 + a_ov * np.cos(2 * theta + ph_ov) + a_lb * np.cos(3 * theta + ph_lb))
    for (kt, ks, bulge, width) in d["knots"]:
        if bulge <= 0:
            continue
        dt = np.angle(np.exp(1j * (theta - kt))) * radius
        dz = (s - ks) * length
        r = r + bulge * np.exp(-(dt * dt + dz * dz) / (width * width))
    bow = np.sin(np.pi * (s + 0.5))
    return r, d["bow"] * bow, d["bow_y"] * bow


def log_part(radius, length, d):
    """Side surface (one Part) and both end caps (another), log-local:
    axis along Z through the origin, centered."""
    side, caps = Part(), Part()
    theta = np.linspace(0, 2 * np.pi, LOG_SECTIONS, endpoint=False)
    half = length / 2
    # Sparse rings along the gentle taper/bow, dense ones across each
    # knot so its bulge is actually sampled.
    inner = [np.linspace(-half + CHAMFER * 3, half - CHAMFER * 3, LOG_RINGS)]
    for (_, ks, bulge, width) in d["knots"]:
        if bulge > 0:
            inner.append(ks * length + np.linspace(-2.0, 2.0, 9) * width)
    inner = np.unique(np.concatenate(inner))
    inner = inner[np.abs(inner) < half - CHAMFER * 2]
    zs = np.concatenate([[-half, -half + CHAMFER], inner, [half - CHAMFER, half]])
    s = zs / length
    T, S = np.meshgrid(theta, s)            # rows = along, cols = around
    R, bx, by = log_surface(radius, length, d, T, S)
    # Chamfer: the end rings pull in.
    R[0] *= 0.92
    R[-1] *= 0.92
    X = bx + R * np.cos(T)
    Y = by + R * np.sin(T)
    Z = np.broadcast_to(zs[:, None], T.shape).copy()
    # Off-square cuts: the end rings (and the chamfer rings) slant.
    for row, end in ((0, 0), (1, 0), (-2, 1), (-1, 1)):
        sx, sy = d["slant"][end]
        Z[row] += sx * np.cos(T[row]) * radius + sy * np.sin(T[row]) * radius
    P = np.stack([X, Y, Z], -1)
    # Smooth normals from the unsplit grid: central differences, wrapping
    # around, one-sided at the ends.
    dth = np.roll(P, -1, axis=1) - np.roll(P, 1, axis=1)
    dz = np.gradient(P, axis=0)
    N = np.cross(dth, dz)
    radial = np.stack([np.cos(T), np.sin(T), np.zeros_like(T)], -1)
    if np.mean(np.sum(N * radial, -1)) < 0:
        N = -N
    # u around (tiles), v along the whole log.
    v_rows = (zs + half) / length
    u_cols = np.linspace(0, 1, LOG_SECTIONS + 1)
    verts, norms, uv, faces = wrap_grid(P, N, v_rows, u_cols)
    side.add(verts, norms, uv[:, ::-1], faces)

    # Caps: a fan on each end ring, planar end-grain UVs.
    for row, sign in ((0, -1.0), (-1, 1.0)):
        ring = P[row]
        center = ring.mean(axis=0)
        nrm = np.cross(ring[0] - center, ring[LOG_SECTIONS // 4] - center)
        nrm /= np.linalg.norm(nrm)
        if nrm[2] * sign < 0:
            nrm = -nrm
        rim = R[row].max() / 0.48  # rim lands just inside the texture's sapwood band
        local = ring - center
        uvs = 0.5 + np.stack([local[:, 0], local[:, 1] * sign], -1) / rim
        verts = np.vstack([center, ring])
        uvs = np.vstack([[0.5, 0.5], uvs])
        idx = np.arange(LOG_SECTIONS)
        tri = np.stack([np.zeros_like(idx), 1 + idx, 1 + (idx + 1) % LOG_SECTIONS], 1)
        if np.dot(np.cross(verts[tri[0, 1]] - verts[0], verts[tri[0, 2]] - verts[0]), nrm) < 0:
            tri = tri[:, [0, 2, 1]]
        caps.add(verts, np.tile(nrm, (len(verts), 1)), uvs, tri)
    return side, caps


def knots_uv(d):
    """The knot eyes in texture space: u around (theta / 2pi), v along."""
    return [((kt / (2 * np.pi)) % 1.0, ks + 0.5, max(0.022, w) / 0.82 * 0.9)
            for (kt, ks, _, w) in d["knots"]]


def place(part, matrix):
    """Apply a 4x4 transform to every chunk in a Part, in place."""
    rot = matrix[:3, :3]
    part.v = [v @ rot.T + matrix[:3, 3] for v in part.v]
    part.n = [n @ rot.T for n in part.n]
    return part


# ── Rope ────────────────────────────────────────────────────────────

def tube(path, radii, sections=8):
    """A rope tube along a polyline with parallel-transport frames.
    u = along (arc length -> twists), v = around."""
    path = np.asarray(path, float)
    radii = np.broadcast_to(np.asarray(radii, float), (len(path),))
    T = np.gradient(path, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    ref = np.array([0.0, 1.0, 0.0]) if abs(T[0, 1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    Nf = np.cross(T[0], ref)
    Nf /= np.linalg.norm(Nf)
    frames = []
    for t in T:
        Nf = Nf - np.dot(Nf, t) * t
        Nf /= np.linalg.norm(Nf)
        frames.append((Nf, np.cross(t, Nf)))
    a = np.linspace(0, 2 * np.pi, sections, endpoint=False)
    Nn = np.array([[np.cos(x) * n + np.sin(x) * b for x in a] for (n, b) in frames])
    P = path[:, None, :] + Nn * radii[:, None, None]
    arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))])
    u_rows = arc / (ROPE_LAY * ROPE_TWISTS)
    v_cols = np.linspace(0, 1, sections + 1)
    return wrap_grid(P, Nn, u_rows, v_cols)


def lump(center, radius, squash, sections=10):
    """A knot: a squashed rope-textured sphere."""
    sph = trimesh.creation.uv_sphere(radius=1.0, count=[sections, sections])
    v = sph.vertices * np.array([radius, radius * squash, radius * 1.15]) + center
    n = sph.vertices / np.array([radius, radius * squash, radius * 1.15])
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    uv = np.stack([np.arctan2(sph.vertices[:, 0], sph.vertices[:, 2]) / np.pi,
                   sph.vertices[:, 1]], -1)
    return v, n, uv, sph.faces


def lashing(rope, wrng, lx, lr, zc, tilt, frayed, drop):
    """A hand-wound lashing around the log at (lx, zc): a three-turn
    helix that finishes on the flank in a knot and a short tail. A
    frayed lashing is slack and slipped, two turns, and its tail hangs
    long and splits into unravelled strands."""
    minor = ROPE_MINOR * (0.72 if frayed else 1.0)
    turns = 2.0 if frayed else 3.0
    slack = 0.006 if frayed else 0.0
    pitch = minor * 2.6
    ring_r = lr + minor * 0.25 + slack  # bites into the wood: no taller than the old wraps
    yc = lr - drop
    phi0 = -np.pi / 2 - np.pi * turns  # start and end underneath/aside
    phi = np.linspace(phi0, phi0 + 2 * np.pi * turns, int(36 * turns))
    zoff = (phi - phi.mean()) / (2 * np.pi) * pitch
    # Hand-thrown: each turn leans a little (the baseline tilt draw).
    zoff = zoff + 0.12 * tilt * lr * np.sin(phi)
    path = np.stack([lx + ring_r * np.cos(phi),
                     yc + ring_r * 0.97 * np.sin(phi) - slack * (1 - np.sin(phi)),
                     zc + zoff], -1)
    rope.add(*tube(path, minor))

    # Finish on the flank: knot lump, then a tail.
    end, tangent = path[-1], path[-1] - path[-2]
    tangent /= np.linalg.norm(tangent)
    out = np.array([np.cos(phi[-1]), np.sin(phi[-1]), 0.0])
    rope.add(*lump(end + out * minor * 0.6, minor * 1.6, 0.85))
    tail_len = wrng.uniform(0.10, 0.16) if frayed else 0.05
    steps = np.linspace(0, 1, 12)[:, None]
    sag = np.array([0.0, -1.0, 0.0]) * (tail_len * 0.8 if frayed else tail_len * 0.3)
    tail = end + tangent * tail_len * steps + out * minor * 0.8 + sag * steps ** 2
    rope.add(*tube(tail, minor * (1.0 - 0.35 * steps[:, 0]), sections=8))
    if frayed:
        # Unravelled: three strands splay off the tail's end.
        tip = tail[-1]
        for k in range(3):
            ang = 2 * np.pi * k / 3 + wrng.uniform(-0.4, 0.4)
            spread = np.array([np.cos(ang), 0.0, np.sin(ang)]) * 0.025
            strand = tip + (tangent * 0.03 + spread + sag * 0.15) * steps
            rope.add(*tube(strand, minor * 0.35 * (1.0 - 0.6 * steps[:, 0]), sections=6))


# ── Raft ────────────────────────────────────────────────────────────

def build_raft(seed, log_colors, rope_color, name,
               rope_skip_chance=0.0, fray_chance=0.0, log_roughness=0.85):
    """Build one raft as a trimesh.Scene."""
    rng = np.random.default_rng(seed)
    wrng = np.random.default_rng(seed + 1000)
    drng = np.random.default_rng(seed + 2000)
    weathered = rope_skip_chance > 0.0
    parts = []

    # ── Logs ────────────────────────────────────────────────────────
    # Lay NUM_LOGS side by side along X. Radii/lengths jitter; each log's
    # axis sits at y = its radius so the deck is walkable-flat-ish but
    # bumpy. (The draws below are the baseline layout — do not reorder.)
    slot_width = DECK_WIDTH / NUM_LOGS
    log_info = []  # (x, radius) for beams and lashings
    x = -DECK_WIDTH / 2 + slot_width / 2
    for i in range(NUM_LOGS):
        radius = LOG_RADIUS * rng.uniform(0.88, 1.12)
        length = LOG_LENGTH * rng.uniform(0.94, 1.06)
        color = log_colors[i % len(log_colors)][:3]
        # Small yaw so logs aren't perfectly parallel; z offset so ends are ragged.
        yaw = rng.uniform(-0.02, 0.02)
        z_off = rng.uniform(-0.06, 0.06)

        d = plan_log(drng, length)
        side, caps = log_part(radius, length, d)
        m = transform(tx=x, ty=radius, tz=z_off, ry=yaw)
        tex_seed = int(drng.integers(1 << 30))
        wood = gen_wood(color, tex_seed, knots=knots_uv(d), weathered=weathered)
        grain = gen_endgrain(color, tex_seed + 1, weathered=weathered)
        parts.append(place(side, m).mesh(f"{name}_log{i}_wood", wood, log_roughness))
        parts.append(place(caps, m).mesh(f"{name}_log{i}_endgrain", grain, log_roughness))
        log_info.append((x, radius))
        x += slot_width * rng.uniform(0.97, 1.03)

    # ── Cross-beams under the logs, near each end ──────────────────
    beam_side, beam_caps = Part(), Part()
    for z in (-LOG_LENGTH * 0.36, LOG_LENGTH * 0.36):
        d = plan_log(drng, DECK_WIDTH + 0.25, taper_max=0.06, knots_max=2, bow_max=0.008)
        side, caps = log_part(BEAM_RADIUS, DECK_WIDTH + 0.25, d)
        # Log-local Z -> rotate 90° about Y to run along X.
        m = transform(ty=-BEAM_RADIUS * 0.6, tz=z, ry=np.pi / 2)
        for src, dst in ((place(side, m), beam_side), (place(caps, m), beam_caps)):
            for chunk in zip(src.v, src.n, src.uv, src.f):
                dst.add(chunk[0], chunk[1], chunk[2], chunk[3] - chunk[3].min())
    beam_color = log_colors[2][:3]
    tex_seed = int(drng.integers(1 << 30))
    parts.append(beam_side.mesh(f"{name}_beam_wood",
                                gen_wood(beam_color, tex_seed, weathered=weathered),
                                log_roughness))
    parts.append(beam_caps.mesh(f"{name}_beam_endgrain",
                                gen_endgrain(beam_color, tex_seed + 1, weathered=weathered),
                                log_roughness))

    # ── Rope lashings where each log crosses each beam ─────────────
    rope = Part()
    for z in (-LOG_LENGTH * 0.36, LOG_LENGTH * 0.36):
        for (lx, lr) in log_info[::2]:  # every other log: sparser, hand-made
            # Baseline draws happen unconditionally, BEFORE any weathering
            # decision, to keep the seed-7 sequence identical.
            z_jitter = rng.uniform(-0.02, 0.02)
            tilt = rng.uniform(-0.15, 0.15)
            if wrng.random() < rope_skip_chance:
                continue  # a lashing lost to the years
            frayed = False
            drop = 0.0
            if wrng.random() < fray_chance:
                # Frayed and slipped: thinner, thrown at a lazier angle,
                # sagged down the log's curve.
                frayed = True
                tilt += wrng.uniform(-0.35, 0.35)
                drop = wrng.uniform(0.005, 0.010)
            lashing(rope, wrng, lx, lr, z + z_jitter, tilt, frayed, drop)
    parts.append(rope.mesh(f"{name}_rope", gen_rope(rope_color[:3], seed + 3,
                                                    weathered=weathered), 0.95))

    scene = trimesh.Scene()
    for i, part in enumerate(parts):
        scene.add_geometry(part, node_name=f"part_{i}")
    return scene, len(parts)


def export(scene, path):
    """Export, then fix up texture bookkeeping for the engine's importer:
    it pairs texture i with image i and names textures by `texture.name`
    (namespaced per model). One texture per image, named after the
    material that uses it — and no name may contain "normal" (those are
    uploaded as linear data)."""
    # include_normals: trimesh omits the NORMAL attribute by default, and the
    # engine falls back to flat [0,1,0] normals -> banded/acne-prone shading.
    scene.export(path, include_normals=True)
    g = GLTF2().load(path)
    old = g.textures
    names = {}
    for mat in g.materials:
        info = mat.pbrMetallicRoughness.baseColorTexture
        if info is not None:
            names.setdefault(old[info.index].source, mat.name)
            info.index = old[info.index].source
    g.samplers = [Sampler(wrapS=10497, wrapT=10497, magFilter=9729, minFilter=9729)]
    g.textures = [Texture(source=i, sampler=0, name=names.get(i, f"tex_{i}"))
                  for i in range(len(g.images))]
    assert not any("normal" in t.name.lower() for t in g.textures)
    for prim in (p for m in g.meshes for p in m.primitives):
        assert prim.attributes.NORMAL is not None, "export lost vertex normals"
        assert prim.attributes.TEXCOORD_0 is not None, "export lost UVs"
    g.save(path)
    return len(g.images)


if __name__ == "__main__":
    deck_top = 2 * LOG_RADIUS  # nominal deck surface height

    # ── The player's raft ───────────────────────────────────────────
    scene, n_parts = build_raft(7, LOG_COLORS, ROPE_COLOR, "raft")
    raft_path = os.path.join(OUT_DIR, "raft.glb")
    n_tex = export(scene, raft_path)
    print(f"wrote {raft_path}  ({n_parts} parts, {n_tex} textures, deck top ~{deck_top:.2f} m)")

    # ── The Visitor's raft: weathered twin ──────────────────────────
    scene2, n_parts2 = build_raft(
        12, LOG_COLORS_WEATHERED, ROPE_COLOR_WEATHERED, "raft2",
        rope_skip_chance=0.35, fray_chance=0.30, log_roughness=0.9,
    )
    raft2_path = os.path.join(OUT_DIR, "raft2.glb")
    n_tex2 = export(scene2, raft2_path)
    print(f"wrote {raft2_path}  ({n_parts2} parts, {n_tex2} textures, weathered)")

    # ── Debug buoy: a bright sphere scripts pin to ocean_height(x, z) ───
    # If it ever detaches from the rendered water surface, CPU/GPU wave
    # parity is broken (see scripts/wave_probe.rhai).
    buoy = trimesh.creation.icosphere(subdivisions=2, radius=0.18)
    buoy = pbr(buoy, (1.0, 0.25, 0.1, 1.0), roughness=0.4)
    bscene = trimesh.Scene()
    bscene.add_geometry(buoy, node_name="buoy")
    buoy_path = os.path.join(OUT_DIR, "buoy.glb")
    bscene.export(buoy_path, include_normals=True)
    print(f"wrote {buoy_path}")
