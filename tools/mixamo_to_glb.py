"""mixamo_to_glb.py — convert a Mixamo character + animation FBX pair into a
Flint-compatible skinned GLB.

    "<blender>" --background --factory-startup --python tools/mixamo_to_glb.py

Mixamo's raw export violates five of Flint's import contracts. Each fix below
is load-bearing; the numbers in the comments are measured from the current
assets, and the script ASSERTS the ones that fail silently in-engine.

 1. SCALE. Mixamo authors in centimetres; Blender's FBX importer leaves the
    conversion on the armature OBJECT as scale 0.01. Flint ignores node
    transforms on a skinned mesh, so the demo scenes compensate with
    `transform.scale`. FLOAT CANNOT: seat_camera.rhai composes the bone_probe
    joint offset into world space WITHOUT any entity scale (seat_camera.rhai
    :312), so a 100x rig renders correctly but throws the eye anchor ~80 m
    away. The geometry must therefore be baked to metres here, and the scene
    entity must stay at scale 1.0. Applying scale to an animated armature is
    a known Blender footgun (pose-bone location F-curves), so the result is
    MEASURED against the known seated hip height rather than assumed.

 2. INFLUENCES. Flint reads only JOINTS_0/WEIGHTS_0 — 4 per vertex — and
    silently drops the rest (gltf_import.rs:116), without renormalizing what
    remains, so excess influences SHRINK the mesh. Mixamo ships 7 on the body
    and 6 on the cloth. Limit to 4, then normalize.

 3. THE `eye` JOINT. bone_probe finds its joint by exact name match and fails
    SILENTLY to (0,0,0) when absent (skeleton.rs:85) — the camera would sit
    at the model origin with no warning. Mixamo has no such bone, so one is
    synthesized between Head and HeadTop_End.

 4. CLIP NAMES. Flint's clip registry is one flat global HashMap keyed by
    name (skeletal_sync.rs:51), and EVERY Mixamo action is called
    "Armature|mixamo.com|Layer0" — so two imports silently clobber each
    other. Clip names are the only namespace; rename on the way in.

 5. TEXTURE NAMES. Flint picks sRGB vs linear by testing whether the texture
    name contains lowercase "normal" (texture_cache.rs:112). Mixamo's maps
    are "Ch02_1001_Normal.png" (capital N) and Blender exports the image
    DATABLOCK name ("file3"), so normal maps would upload as sRGB and come
    out gamma-mangled. Rename the datablocks.

Not fixed here (spike scope): the character has no bare feet — the body mesh
ends in a hollow ankle cuff at Z=0.066 and the sneakers are what reach the
ground, so the shoes CANNOT be dropped without leaving amputated ankles.
"""

import math
import os
import sys

import bpy
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAR_FBX = os.path.join(ROOT, "models", "raw", "Character.fbx")
DEFAULT_ANIM = os.path.join(ROOT, "anim", "raw", "Sitting Idle.fbx")
DEFAULT_OUT = os.path.join(ROOT, "models", "mixamo_body.glb")
DEFAULT_CLIP = "idle_sit"       # the scene's animator.clip references this string

HEAD_BONE = "mixamorig:Head"
HEADTOP_BONE = "mixamorig:HeadTop_End"

# Eye placement, as a fraction of the Head->HeadTop_End span and a forward
# offset in metres. Mixamo's Head joint sits at the skull base, so the eye is
# a little under halfway up the head and well forward of the joint.
EYE_UP_FRAC = 0.45
EYE_FORWARD = 0.085

# Scale sanity bounds. These are deliberately POSE-AGNOSTIC: the check exists
# to catch the ~100x errors that Blender's transform handling produces, not to
# validate any particular clip, so swapping in a different sitting idle (with
# a different hip height) must not trip them. The observed failure put the
# hips at -38.8 m, so a generous human-scale window still catches it cleanly.
BIND_HEIGHT_RANGE = (1.4, 2.2)   # rest-pose skeleton height, clip-independent
POSED_HIP_RANGE = (0.05, 1.5)    # any plausible seated/standing hip height

# Mirrors seat.deck_top in the scene; used only to suggest body_seat_y.
DECK_TOP = 0.26


def parse_args():
    """Blender passes script args after a bare '--'."""
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = {"anim": DEFAULT_ANIM, "clip": DEFAULT_CLIP, "out": DEFAULT_OUT}
    i = 0
    while i < len(argv):
        key = argv[i].lstrip("-")
        if key not in args:
            raise SystemExit(
                f"unknown option {argv[i]!r}; expected --anim/--clip/--out\n"
                f"  e.g. --anim \"anim/raw/Seated Idle.fbx\" --clip idle_sit"
            )
        args[key] = argv[i + 1]
        i += 2
    args["anim"] = os.path.abspath(args["anim"])
    args["out"] = os.path.abspath(args["out"])
    if not os.path.exists(args["anim"]):
        raise SystemExit(f"animation FBX not found: {args['anim']}")
    return args


def log(msg):
    print(f"[mixamo] {msg}")


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_character():
    bpy.ops.import_scene.fbx(filepath=CHAR_FBX)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    arm.name = "Armature"
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    log(f"character: {len(arm.data.bones)} bones, {len(meshes)} meshes "
        f"({sum(len(m.data.vertices) for m in meshes)} verts)")
    # The character FBX carries a 2-frame T-pose action; it would export as a
    # junk clip and collide by name with the real one.
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act)
    return arm, meshes


def attach_animation(arm, anim_path, clip_name):
    """Import the animation FBX, move its action onto the character.

    Works with either Mixamo download flavour: "without skin" (armature only)
    or "with skin" (armature + a duplicate mesh) — every object the import
    brings in is removed afterwards, only the action is kept.
    """
    log(f"animation: {os.path.basename(anim_path)}")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=anim_path)
    new_objs = [o for o in bpy.data.objects if o not in before]
    anim_arm = next((o for o in new_objs if o.type == "ARMATURE"), None)
    assert anim_arm is not None, f"no armature in {anim_path}"
    assert anim_arm.animation_data and anim_arm.animation_data.action, (
        f"{os.path.basename(anim_path)} carries no action — was it downloaded "
        f"as a T-pose rather than an animation?"
    )

    act = anim_arm.animation_data.action
    act.name = clip_name
    # Blender 4.4+ slot-based actions: the exporter needs the action's slot to
    # match the target, which assignment handles, but the name must be set
    # before we drop the source armature or the datablock can be freed.
    if not arm.animation_data:
        arm.animation_data_create()
    arm.animation_data.action = act
    if hasattr(arm.animation_data, "action_slot") and act.slots:
        arm.animation_data.action_slot = act.slots[0]

    start, end = (int(v) for v in act.frame_range)
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = start, end
    fps = bpy.context.scene.render.fps
    log(f"clip {clip_name!r}: frames {start}-{end} @ {fps}fps "
        f"= {(end - start) / fps:.3f}s")

    for o in new_objs:
        bpy.data.objects.remove(o, do_unlink=True)
    return act


def limit_influences(meshes, limit=4):
    for ob in meshes:
        before = max((len(v.groups) for v in ob.data.vertices), default=0)
        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.vertex_group_limit_total(limit=limit)
        bpy.ops.object.vertex_group_normalize_all(lock_active=False)
        after = max((len(v.groups) for v in ob.data.vertices), default=0)
        flag = "  <-- was over budget" if before > limit else ""
        log(f"  {ob.name}: max influences {before} -> {after}{flag}")
        assert after <= limit, f"{ob.name} still has {after} influences"


def apply_scale(arm, meshes, action):
    """Bake the cm->m conversion into the geometry (see contract 1).

    transform_apply rescales the bone REST data but leaves pose-bone location
    F-curves untouched — they stay in centimetre magnitudes, so Mixamo's
    animated Hips translation lands ~100x too far and drags the whole rig off
    into space (measured: hips at -38.8 m instead of 0.585 m). Rotation and
    scale curves are unitless and must NOT be touched.
    """
    factor = arm.scale.x
    bpy.ops.object.select_all(action="DESELECT")
    for ob in [arm] + meshes:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = arm
    # Rotation must be applied too. The FBX importer parks glTF's Y-up ->
    # Blender's Z-up conversion as a -90deg X rotation on the armature OBJECT.
    # Leaving it there exports a correct BIND pose (the node transform folds
    # into the inverse-bind matrices) but an animation rotated -90deg about X
    # — the character renders lying on her back while T-pose bounds look
    # perfectly upright. Bone-local rotation channels are relative to the
    # rest pose, so applying rotation is safe in a way applying scale is not.
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    scaled = 0
    for fc in action.fcurves:
        if not fc.data_path.endswith(".location"):
            continue
        for kp in fc.keyframe_points:
            kp.co.y *= factor
            kp.handle_left.y *= factor
            kp.handle_right.y *= factor
        fc.update()
        scaled += 1
    log(f"applied scale {factor} to geometry and to {scaled} location F-curves")


def add_eye_bone(arm):
    """Synthesize the `eye` joint Float's bone_probe requires (contract 3)."""
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")

    ebs = arm.data.edit_bones
    head_b, top_b = ebs.get(HEAD_BONE), ebs.get(HEADTOP_BONE)
    assert head_b and top_b, f"missing {HEAD_BONE}/{HEADTOP_BONE} — not a Mixamo rig?"

    # Solve in WORLD space (Z up, Mixamo's bind pose faces -Y) and convert
    # back. Armature-local axes are Y-up here after the FBX conversion, so
    # hardcoding a local axis silently moves the eye DOWN instead of forward.
    m, inv = arm.matrix_world, arm.matrix_world.inverted()
    head_w, top_w = m @ head_b.head, m @ top_b.head
    pos_w = head_w + (top_w - head_w) * EYE_UP_FRAC + Vector((0.0, -EYE_FORWARD, 0.0))

    eye = ebs.new("eye")
    eye.head = inv @ pos_w
    eye.tail = inv @ (pos_w + Vector((0.0, -0.04, 0.0)))  # nonzero length or Blender drops it
    eye.parent = ebs[HEAD_BONE]
    eye.use_connect = False
    eye.use_deform = True    # guarantees inclusion in the exported skin joints

    bpy.ops.object.mode_set(mode="OBJECT")
    log(f"added 'eye' joint at world ({pos_w.x:.3f}, {pos_w.y:.3f}, {pos_w.z:.3f}), "
        f"{pos_w.z - head_w.z:.3f} m above the head joint")


def rename_textures():
    """Make the normal maps satisfy Flint's lowercase-'normal' rule."""
    used = set()
    for img in bpy.data.images:
        if img.size[0] == 0:
            continue
        src = os.path.basename(img.filepath).lower()
        if "normal" in src:
            base = "body_normal"
        elif "diffuse" in src or "basecolor" in src:
            base = "body_basecolor"
        elif "specular" in src:
            base = "body_specular"
        elif "glossiness" in src:
            base = "body_glossiness"
        else:
            base = "body_misc"
        name, i = base, 1
        while name in used:
            i += 1
            name = f"{base}_{i}"
        used.add(name)
        packed = img.packed_file is not None
        log(f"  image {img.name!r} -> {name!r} ({img.size[0]}x{img.size[1]}, "
            f"{'packed' if packed else 'EXTERNAL'})")
        if not packed and not os.path.exists(bpy.path.abspath(img.filepath)):
            log(f"    WARNING: {name} has no pixel source on disk and is not "
                f"packed — it will export empty")
        img.name = name
        # The glTF exporter names images from the FILEPATH BASENAME, not the
        # datablock name, so renaming the datablock alone leaves Mixamo's
        # "Ch02_1001_Normal" (capital N) in the GLB and the map uploads as
        # sRGB. The pixels come from the packed data, so repointing the path
        # at a nonexistent file is safe and is what actually renames it.
        img.filepath_raw = f"//{name}.png"


def fix_materials():
    """Convert Mixamo's spec/gloss setup to sane metal/rough scalars.

    Mixamo ships Diffuse + Normal + Specular + Glossiness. Blender's FBX
    importer wires that into the Principled BSDF, and the glTF exporter then
    emits `metallicFactor: 0.5` on skin and cloth plus a metallicRoughness
    TEXTURE that is really the glossiness map — where glTF reads B as metallic
    and G as roughness, so a glossy white pixel means "metallic and rough".
    The result is the wet-plastic look. Flint compounds it by uploading
    metallicRoughness maps as sRGB (texture_cache.rs has no branch for them),
    gamma-mangling whatever values survive.

    Nothing here is recoverable as a texture, so the spec/gloss chain is cut
    and replaced with per-material scalars. Flint ignores glTF extensions, so
    KHR_materials_specular is pure weight; unlinking the maps also drops two
    4096^2 images from the export.
    """
    # One material covers skin AND cloth AND sneakers, so these are blends
    # rather than per-surface truth. Leaning matte suits the cel post.
    ROUGHNESS = {"Ch02_body": 0.75, "Ch02_hair": 0.65}
    DEFAULT_ROUGHNESS = 0.8

    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        bsdf = next((n for n in mat.node_tree.nodes
                     if n.type == "BSDF_PRINCIPLED"), None)
        if not bsdf:
            continue

        rough = ROUGHNESS.get(mat.name, DEFAULT_ROUGHNESS)
        dropped = []
        for socket, value in [("Metallic", 0.0), ("Roughness", rough),
                              ("Specular IOR Level", 0.5), ("Specular Tint", None)]:
            inp = bsdf.inputs.get(socket)
            if inp is None:
                continue
            for link in list(inp.links):
                dropped.append(link.from_node.name)
                mat.node_tree.links.remove(link)
            if value is not None:
                inp.default_value = value

        log(f"  {mat.name}: metallic 0.0, roughness {rough}"
            + (f" (unlinked {len(dropped)} spec/gloss input(s))" if dropped else ""))


def verify_pose(arm, clip_name):
    """Catch the ~100x scale errors Blender's transform handling can produce.

    Two independent checks, both POSE-AGNOSTIC so a different sitting idle
    doesn't trip them:

      * rest-pose skeleton height  — geometry/bone scale, clip-independent
      * posed hip height in range  — catches un-scaled location F-curves,
        the failure that put the hips at -38.8 m

    Pinning an exact hip height would be tighter but would reject every clip
    except the one it was measured from.
    """
    # Rest pose: independent of whatever action is loaded.
    bind_top = max((arm.matrix_world @ b.head_local).z for b in arm.data.bones)
    log(f"rest skeleton height = {bind_top:.3f} m")
    lo, hi = BIND_HEIGHT_RANGE
    assert lo < bind_top < hi, (
        f"GEOMETRY SCALE WRONG: rest skeleton is {bind_top:.3f} m tall, expected "
        f"{lo}-{hi} m. The cm->m bake did not take."
    )

    scn = bpy.context.scene
    scn.frame_set((scn.frame_start + scn.frame_end) // 2)
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    ev = arm.evaluated_get(dg)

    def world(bone):
        pb = ev.pose.bones.get(bone)
        return arm.matrix_world @ pb.head if pb else None

    hips = world("mixamorig:Hips")
    foot = world("mixamorig:LeftFoot")
    eye = world("eye")
    log(f"posed hips Z = {hips.z:.3f} m   eye {eye.z - hips.z:.3f} m above hips"
        f"   hips->foot drop {hips.z - foot.z:.3f} m")

    lo, hi = POSED_HIP_RANGE
    assert lo < hips.z < hi, (
        f"ANIMATION SCALE WRONG: hips at {hips.z:.3f} m at mid-clip, expected "
        f"{lo}-{hi} m. transform_apply did not carry the action's location "
        f"F-curves — they are still in centimetres."
    )

    # The clip decides where the body origin must sit: Mixamo's origin is at
    # the FEET, so seating the hips on the deck needs this offset. A different
    # sitting idle WILL want a different value.
    seat_y = DECK_TOP - hips.z
    log("")
    log(f"  scene wiring for {clip_name!r}:")
    log(f"    [entities.body.animator]  clip = \"{clip_name}\"")
    log(f"    [entities.seat_camera.seat]  body_seat_y = {seat_y:.3f}")
    log(f"    (eye will sit {DECK_TOP + (eye.z - hips.z):.3f} m above the raft origin)")
    log("")
    return eye, hips


def export(arm, meshes, out_glb):
    bpy.ops.object.select_all(action="DESELECT")
    for ob in [arm] + meshes:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.gltf(
        filepath=out_glb,
        export_format="GLB",
        use_selection=True,
        export_yup=True,
        export_normals=True,       # Flint falls back to flat [0,1,0] without these
        export_tangents=False,     # never read by the importer
        export_skins=True,
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_def_bones=False,    # keep the full hierarchy, incl. our eye bone
        export_morph=False,        # importer skips morph targets anyway
        export_apply=False,
    )
    log(f"wrote {out_glb} ({os.path.getsize(out_glb) / 1e6:.1f} MB)")


def main():
    args = parse_args()

    clear_scene()
    arm, meshes = import_character()
    action = attach_animation(arm, args["anim"], args["clip"])

    log("limiting vertex influences to 4 (Flint reads JOINTS_0 only):")
    limit_influences(meshes)

    apply_scale(arm, meshes, action)
    add_eye_bone(arm)

    log("converting spec/gloss materials to metal/rough:")
    fix_materials()

    log("renaming textures for the sRGB/linear rule:")
    rename_textures()

    verify_pose(arm, args["clip"])
    export(arm, meshes, args["out"])

    rel = os.path.relpath(args["out"], ROOT).replace("\\", "/")
    log("done. Verify in-engine with:")
    log(f"  flint preview {rel} --clip {args['clip']} --anim-time 1.5 --render out.png")


if __name__ == "__main__":
    main()
