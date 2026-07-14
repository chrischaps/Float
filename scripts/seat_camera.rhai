// seat_camera.rhai — First-person seated camera on the raft edge.
//
// The player sits on the +Z edge of the raft, legs over the side, facing
// outward. Look input: arrow keys / gamepad right stick (M0), mouse deltas
// once cursor capture exists (M2). Yaw is clamped around seat-outward so
// you can't look through your own back; pitch is clamped to human range.
//
// M0: the raft is static, so the seat transform is a fixed offset from the
// raft entity. M2 composes raft heave/pitch/roll into eye and view.

let yaw = 0.0;        // radians, 0 = facing +Z (outward over the water)
let pitch = -0.15;    // slight downward gaze toward the horizon-water line

const MOUSE_SENS = 0.0028;
const STICK_SPEED = 2.4;    // rad/s at full deflection
const PITCH_MIN = -1.3;     // ~-75 deg (down at your legs)
const PITCH_MAX = 1.3;
const YAW_LIMIT = 2.1;      // ~±120 deg around seat-outward

const EYE_HEIGHT = 0.55;    // above deck top (seated eye height)
const DECK_TOP = 0.26;      // matches generate_raft.py output
const SEAT_EDGE_Z = 1.05;   // just inside the +Z log ends

fn on_init() {
    set_camera_fov(65.0);
}

fn on_update() {
    let dt = delta_time();
    if dt <= 0.0 { return; }

    // ── Look input ──────────────────────────────────────────────────
    let mdx = mouse_delta_x();
    let mdy = mouse_delta_y();
    let sx = action_value("look_x");
    let sy = action_value("look_y");

    yaw += mdx * MOUSE_SENS + sx * STICK_SPEED * dt;
    pitch += mdy * MOUSE_SENS + sy * STICK_SPEED * dt;

    yaw = clamp(yaw, -YAW_LIMIT, YAW_LIMIT);
    pitch = clamp(pitch, PITCH_MIN, PITCH_MAX);

    // ── Seat position (raft-local, static in M0) ────────────────────
    let raft = get_entity("raft");
    if raft < 0 { return; }
    let rp = get_position(raft);

    let eye_x = rp["x"];
    let eye_y = rp["y"] + DECK_TOP + EYE_HEIGHT;
    let eye_z = rp["z"] + SEAT_EDGE_Z;

    // ── View direction from yaw/pitch (yaw 0 = +Z outward) ──────────
    let cp = cos(pitch);
    let dir_x = sin(yaw) * cp;
    let dir_y = sin(pitch);
    let dir_z = cos(yaw) * cp;

    set_camera_position(eye_x, eye_y, eye_z);
    set_camera_target(eye_x + dir_x, eye_y + dir_y, eye_z + dir_z);
}
