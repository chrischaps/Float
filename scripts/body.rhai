// body.rhai — the player's rigged body: placement + scoot clip driver.
//
// Placement is legs_idle.rhai's contract, unchanged: the seat's raft-local
// point and outward heading are read from the seat component every frame
// (seat_camera.rhai owns the perimeter math and publishes seat_x / seat_z
// / seat_out_deg) and composed with the raft transform, so the eye and
// the body can never drift apart. set_field is deferred, so the values
// are at most one frame old and DON'T EXIST until the seat's first
// publish flushes — hence the unit-value guard.
//
// Animation: idle loops by default (calf sway lives in the CLIP now, not
// in script rotation). When seat.step_dir flips 0 → ±1, this blends into
// scoot_right/scoot_left (non-looping) and back to idle when the step
// ends. The engine has NO skeletal on_animation_end event: the step
// timing lives in seat_camera.rhai (step_time mirrors the clip length),
// and this script just follows step_dir transitions. A creak fires when
// the planting hand takes weight (~0.3 s in) — the same body-drives-audio
// principle as the wave-driven laps.
//
// Root motion in the clips carries only the pelvis lift and lean; travel
// comes from the entity position following the seat point, which is
// already eased to the clip's weight-shift phase by seat_camera.rhai.

// Body placement (inset from the scoot path, height above raft origin)
// comes from the seat component's body_inset / body_seat_y — SHARED with
// seat_camera.rhai, which mirrors this placement to follow the eye bone.
const PLANT_T = 0.30;   // seconds into a step when the hand takes weight

let prev_dir = 0.0;
let step_clock = -1.0;  // seconds since step start (-1 = idle)
let creak_done = false;

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
    // All limb motion is skeletal now — no scripted sway.
    set_rotation(me, rr["x"], rr["y"] + out_deg, rr["z"] * 0.6);

    // ── Scoot clip driver ───────────────────────────────────────────
    let dir = get_field(seat, "seat", "step_dir");
    if dir == () { dir = 0.0; }

    if dir != 0.0 && prev_dir == 0.0 {
        // Step began. step_dir +1 = scoot-left (+s, toward +X when facing
        // out); the LEFT-moving clip mirrors the right one.
        let clip = if dir > 0.0 { "scoot_left" } else { "scoot_right" };
        set_field(me, "animator", "loop", false);
        blend_to(me, clip, 0.12);
        step_clock = 0.0;
        creak_done = false;
    }
    if dir == 0.0 && prev_dir != 0.0 {
        // Step ended: settle back into the idle sway.
        set_field(me, "animator", "loop", true);
        blend_to(me, "idle", 0.30);
        step_clock = -1.0;
    }
    prev_dir = dir;

    // The planting hand takes weight: one soft creak from the deck.
    if step_clock >= 0.0 {
        step_clock += dt;
        if !creak_done && step_clock >= PLANT_T {
            creak_done = true;
            let which = 1 + (random_range(0.0, 2.999)).to_int();
            play_sound_at("audio/creak_" + which + ".ogg", px, py, pz, 0.16);
        }
    }
}
