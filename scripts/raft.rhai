// raft.rhai — kinematic buoyancy: the raft rides the same Gerstner surface
// the GPU renders (ocean_height samples the identical spectrum + clock).
//
// Five height samples (center + 4 edge midpoints in the raft's yawed local
// frame) give heave (mean) and deck tilt (front/back, left/right slope).
// Critically-damped-ish exponential smoothing supplies the inertia of a
// heavy waterlogged raft: it hesitates, then follows — that lag is most of
// what makes the motion feel real from the deck.
//
// Rotation convention: engine Euler is DEGREES, ZYX. rotation.x tilts +Z
// (bow) down when positive; rotation.z lifts +X (starboard) when positive.

let cur_y = 0.0;
let cur_pitch = 0.0;    // degrees
let cur_roll = 0.0;     // degrees
let drift_x = 0.0;
let drift_z = 0.0;
let init_done = false;

fn on_update() {
    let me = this_entity();
    let dt = delta_time();
    if dt <= 0.0 { return; }

    let heave_resp = get_field(me, "raft_float", "heave_response");
    let ang_resp = get_field(me, "raft_float", "angular_response");
    let draft = get_field(me, "raft_float", "draft");
    let half_w = get_field(me, "raft_float", "half_width");
    let half_l = get_field(me, "raft_float", "half_length");
    let drift_speed = get_field(me, "raft_float", "drift_speed");
    let drift_dir = deg_to_rad(get_field(me, "raft_float", "drift_dir_deg"));
    let sway_amp = get_field(me, "raft_float", "yaw_sway_deg");
    let sway_rate = get_field(me, "raft_float", "yaw_sway_rate");

    if !init_done {
        let p = get_position(me);
        drift_x = p["x"];
        drift_z = p["z"];
        cur_y = ocean_height(drift_x, drift_z) - draft;
        init_done = true;
    }

    // ── Slow drift with the waves + gentle yaw sway ─────────────────
    drift_x += sin(drift_dir) * drift_speed * dt;
    drift_z += cos(drift_dir) * drift_speed * dt;
    let yaw_deg = sin(total_time() * sway_rate) * sway_amp;
    let yaw = deg_to_rad(yaw_deg);

    // ── Sample the water plane under the deck ───────────────────────
    let fwd_x = sin(yaw);
    let fwd_z = cos(yaw);
    let right_x = cos(yaw);
    let right_z = -sin(yaw);

    let h_c = ocean_height(drift_x, drift_z);
    let h_f = ocean_height(drift_x + fwd_x * half_l, drift_z + fwd_z * half_l);
    let h_b = ocean_height(drift_x - fwd_x * half_l, drift_z - fwd_z * half_l);
    let h_r = ocean_height(drift_x + right_x * half_w, drift_z + right_z * half_w);
    let h_l = ocean_height(drift_x - right_x * half_w, drift_z - right_z * half_w);

    let target_y = (h_c + h_f + h_b + h_r + h_l) / 5.0 - draft;
    // Bow lower than stern → positive pitch (bow-down); starboard higher → positive roll.
    let target_pitch = rad_to_deg(atan2(h_b - h_f, 2.0 * half_l));
    let target_roll = rad_to_deg(atan2(h_r - h_l, 2.0 * half_w));

    // ── Heavy-raft smoothing ────────────────────────────────────────
    let ky = clamp(heave_resp * dt, 0.0, 1.0);
    let ka = clamp(ang_resp * dt, 0.0, 1.0);
    cur_y += (target_y - cur_y) * ky;
    cur_pitch += (target_pitch - cur_pitch) * ka;
    cur_roll += (target_roll - cur_roll) * ka;

    set_position(me, drift_x, cur_y, drift_z);
    set_rotation(me, cur_pitch, yaw_deg, cur_roll);
}
