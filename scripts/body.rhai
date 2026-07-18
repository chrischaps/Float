// body.rhai — the player's rigged body: placement, scoot driver, and the
// idle brain.
//
// Placement: the seat's raft-local point and outward heading are read
// from the seat component every frame (seat_camera.rhai owns the
// perimeter math and publishes seat_x / seat_z / seat_out_deg) and
// composed with the raft transform, so the eye and the body can never
// drift apart. set_field is deferred, so the values are at most one
// frame old and DON'T EXIST until the seat's first publish flushes —
// hence the unit-value guard. Shared body_inset / body_seat_y fields
// keep this placement in lockstep with the camera's eye-bone mirror.
//
// The idle brain: the player spends most of the game idling, so the
// idle is the character. Six looping pose variants (hands on deck /
// thighs / trailing toward the water, in L/R permutations) live in the
// GLB; this script dwells in one for 12-30 s, then either crossfades to
// another (the slow blend IS the repositioning move), fires a small
// one-shot fidget (kick, drum, shift, sigh), or — rarely — a big
// stretch. After a scoot, the body lands in the variant whose hand is
// already planted (the arm that pushed stays propped).
//
// The engine has NO skeletal on_animation_end: fidget durations are
// mirrored from tools/generate_body.py (FIDGET_DURS) — keep in sync.
// Blend-back starts slightly before a one-shot's end to mask the loop
// restart (animator loop state is per-entity and effectively sticky).

const PLANT_T = 0.30;   // seconds into a step when the hand takes weight

// ── Tables mirrored from tools/generate_body.py — KEEP IN SYNC ─────────
const VARIANTS = ["idle_deck", "idle_thighs", "idle_left_deck",
                  "idle_right_deck", "idle_water_l", "idle_water_r"];
const HAS_DECK = [true, false, true, true, true, true];  // a deck-planted hand?
const FID_KINDS = ["kick", "shift", "sigh", "drum"];
const FID_DURS  = [2.4, 2.6, 3.0, 2.0];
const BIG_KINDS = ["stretch"];
const BIG_DURS  = [3.6];

let prev_dir = 0.0;
let step_clock = -1.0;  // seconds since scoot step start (-1 = not stepping)
let creak_done = false;
let layer_w = 1.0;      // slewed legs_rock layer weight (ducked in scoots)
let layer_w_written = 1.0;
let cur_v = 0;          // current variant index (idle_deck default)
let mode = 0;           // 0 = idling, 1 = mid-fidget
let dwell = 6.0;        // settle-in before the brain's first act
let fid_left = 0.0;

fn on_update() {
    let dt = delta_time();
    if dt <= 0.0 { return; }

    let raft = get_entity("raft");
    let seat = get_entity("seat_camera");
    if raft < 0 || seat < 0 { return; }

    let out_deg = get_field(seat, "seat", "seat_out_deg");
    if out_deg == () { return; }   // seat hasn't published yet (first frames)
    let psi = deg_to_rad(out_deg);
    // Pull the hips slightly inboard, opposite the outward heading.
    let inset = get_field(seat, "seat", "body_inset");
    let lx = get_field(seat, "seat", "seat_x") - sin(psi) * inset;
    let lz = get_field(seat, "seat", "seat_z") - cos(psi) * inset;
    let ly = get_field(seat, "seat", "body_seat_y");

    let rp = get_position(raft);
    let rr = get_rotation(raft);
    let ax = deg_to_rad(rr["x"]);
    let ay = deg_to_rad(rr["y"]);
    let az = deg_to_rad(rr["z"]);

    let sx = sin(ax); let cx = cos(ax);
    let sy = sin(ay); let cy = cos(ay);
    let sz = sin(az); let cz = cos(az);

    // Seat offset through the raft rotation matrix (R = Rz·Ry·Rx).
    let px = rp["x"] + (cy * cz) * lx + (sx * sy * cz - cx * sz) * ly + (cx * sy * cz + sx * sz) * lz;
    let py = rp["y"] + (cy * sz) * lx + (sx * sy * sz + cx * cz) * ly + (cx * sy * sz - sx * cz) * lz;
    let pz = rp["z"] + (-sy) * lx + (sx * cy) * ly + (cx * cy) * lz;

    let me = this_entity();
    set_position(me, px, py, pz);

    // Body faces seat-outward and inherits the raft attitude; the
    // water-drag roll lean opposes the deck roll (calves lag the deck).
    set_rotation(me, rr["x"], rr["y"] + out_deg, rr["z"] * 0.6);

    // ── Scoot clip driver ───────────────────────────────────────────
    let dir = get_field(seat, "seat", "step_dir");
    if dir == () { dir = 0.0; }

    if dir != 0.0 && prev_dir == 0.0 {
        // Step began. step_dir +1 = scoot-left (+s, toward +X when
        // facing out); the LEFT-moving clip mirrors the right one.
        let clip = if dir > 0.0 { "scoot_left" } else { "scoot_right" };
        blend_to(me, clip, 0.12);
        step_clock = 0.0;
        creak_done = false;
        mode = 0;
    }
    if dir == 0.0 && prev_dir != 0.0 {
        // Step ended: land in the variant whose hand is already planted
        // (scoot_right pushed with the LEFT arm, and vice versa).
        cur_v = if prev_dir < 0.0 { 2 } else { 3 };
        blend_to(me, global::VARIANTS[cur_v], 0.30);
        step_clock = -1.0;
        mode = 0;
        dwell = random_range(4.0, 9.0);   // settle before the brain acts
    }
    prev_dir = dir;

    // Duck the legs_rock additive layer while a scoot step owns the
    // legs; ease it back in as the body settles.
    let lw_target = if step_clock >= 0.0 { 0.0 } else { 1.0 };
    layer_w += (lw_target - layer_w) * clamp(6.0 * dt, 0.0, 1.0);
    if abs(layer_w - layer_w_written) > 0.005 {
        layer_w_written = layer_w;
        set_field(me, "animator", "layer_weight", layer_w);
    }

    // The planting hand takes weight: one soft creak from the deck.
    if step_clock >= 0.0 {
        step_clock += dt;
        if !creak_done && step_clock >= PLANT_T {
            creak_done = true;
            let which = 1 + (random_range(0.0, 2.999)).to_int();
            play_sound_at("audio/creak_" + which + ".ogg", px, py, pz, 0.16);
        }
        return;   // brain paused while stepping
    }

    // ── Idle brain ──────────────────────────────────────────────────
    if !get_field(me, "idle_brain", "enabled") { return; }

    if mode == 1 {
        fid_left -= dt;
        if fid_left <= 0.0 {
            mode = 0;
            blend_to(me, global::VARIANTS[cur_v],
                     get_field(me, "idle_brain", "fidget_blend"));
            dwell = random_range(get_field(me, "idle_brain", "dwell_min"),
                                 get_field(me, "idle_brain", "dwell_max"));
        }
        return;
    }

    dwell -= dt;
    if dwell > 0.0 { return; }

    let big_chance = get_field(me, "idle_brain", "big_chance");
    let fid_chance = get_field(me, "idle_brain", "fidget_chance");
    let r = random();

    if r < big_chance {
        // The rare big gesture.
        let bi = (random_range(0.0, global::BIG_KINDS.len().to_float() - 0.001)).to_int();
        blend_to(me, "fid_" + global::BIG_KINDS[bi] + "_" + global::VARIANTS[cur_v], 0.6);
        mode = 1;
        fid_left = global::BIG_DURS[bi] - 0.15;
    } else if r < big_chance + fid_chance {
        // A small fidget compatible with this variant (drumming needs a
        // deck-planted hand).
        let fi = 0;
        let tries = 0;
        loop {
            fi = (random_range(0.0, global::FID_KINDS.len().to_float() - 0.001)).to_int();
            if global::FID_KINDS[fi] != "drum" || global::HAS_DECK[cur_v] { break; }
            tries += 1;
            if tries > 8 { break; }
        }
        blend_to(me, "fid_" + global::FID_KINDS[fi] + "_" + global::VARIANTS[cur_v],
                 get_field(me, "idle_brain", "fidget_blend"));
        mode = 1;
        fid_left = global::FID_DURS[fi] - 0.15;
    } else {
        // Drift to another pose; the slow crossfade IS the movement.
        let nv = cur_v;
        while nv == cur_v {
            nv = (random_range(0.0, global::VARIANTS.len().to_float() - 0.001)).to_int();
        }
        cur_v = nv;
        blend_to(me, global::VARIANTS[cur_v],
                 get_field(me, "idle_brain", "variant_blend"));
        dwell = random_range(get_field(me, "idle_brain", "dwell_min"),
                             get_field(me, "idle_brain", "dwell_max"));
    }
}
