// seat_camera.rhai — First-person seated camera on the raft edge.
//
// The eye is a fixed point on the deck (raft-local seat offset run through
// the raft's full rotation matrix), so every heave and tilt of the raft
// moves your head — that positional bob is the strongest "I am on this
// thing" cue. A fraction of the deck tilt also leans into the view
// direction (roll_transfer): full transfer is nauseating, zero feels like
// floating on a tripod.
//
// Look: mouse (cursor captured via set_cursor_captured) + arrows/stick.
// Yaw is clamped around seat-outward (+Z of the raft) so you can't look
// through your own back; click to recapture the mouse after Escape.

let look_yaw = 0.0;     // radians, relative to seat-outward
let look_pitch = -0.12; // slight downward gaze toward the water line
let captured_once = false;

const STICK_SPEED = 2.4;   // rad/s at full deflection
const PITCH_MIN = -1.3;    // ~-75 deg (down at your legs)
const PITCH_MAX = 1.25;
const YAW_LIMIT = 2.1;     // ~±120 deg around seat-outward

fn on_init() {
    set_camera_fov(65.0);
    set_cursor_captured(true);
}

fn on_update() {
    let dt = delta_time();
    if dt <= 0.0 { return; }

    let me = this_entity();
    let raft_name = get_field(me, "seat", "raft");
    let raft = get_entity(raft_name);
    if raft < 0 { return; }

    let edge_z = get_field(me, "seat", "edge_offset_z");
    let eye_h = get_field(me, "seat", "eye_height");
    let deck = get_field(me, "seat", "deck_top");
    let transfer = get_field(me, "seat", "roll_transfer");
    let sens = get_field(me, "seat", "mouse_sens");

    // Recapture the mouse on click (Escape releases it).
    if is_action_just_pressed("recapture") {
        set_cursor_captured(true);
    }
    if !captured_once {
        // on_init may run before the window exists; re-request once here.
        set_cursor_captured(true);
        captured_once = true;
    }

    // ── Look input ──────────────────────────────────────────────────
    // Subtract deltas (engine FPS convention, see flint-physics
    // character.rs): with dir = (sin(yaw), _, cos(yaw)), increasing yaw
    // turns toward +X = screen-LEFT, so mouse-right must decrease yaw.
    // Mouse-forward (negative dy) must increase pitch (look up).
    look_yaw -= mouse_delta_x() * sens + action_value("look_x") * STICK_SPEED * dt;
    look_pitch -= mouse_delta_y() * sens + action_value("look_y") * STICK_SPEED * dt;
    look_yaw = clamp(look_yaw, -YAW_LIMIT, YAW_LIMIT);
    look_pitch = clamp(look_pitch, PITCH_MIN, PITCH_MAX);

    // ── Raft transform ──────────────────────────────────────────────
    let rp = get_position(raft);
    let rr = get_rotation(raft);           // degrees, engine ZYX euler
    let ax = deg_to_rad(rr["x"]);          // pitch (bow down +)
    let ay = deg_to_rad(rr["y"]);          // yaw
    let az = deg_to_rad(rr["z"]);          // roll (starboard up +)

    let sx = sin(ax); let cx = cos(ax);
    let sy = sin(ay); let cy = cos(ay);
    let sz = sin(az); let cz = cos(az);

    // Engine rotation matrix (R = Rz·Ry·Rx, matches Transform::to_matrix).
    let r00 = cy * cz;
    let r01 = sx * sy * cz - cx * sz;
    let r02 = cx * sy * cz + sx * sz;
    let r10 = cy * sz;
    let r11 = sx * sy * sz + cx * cz;
    let r12 = cx * sy * sz - sx * cz;
    let r20 = -sy;
    let r21 = sx * cy;
    let r22 = cx * cy;

    // Seat point in raft-local space: on the +Z edge, eye above deck.
    let lx = 0.0;
    let ly = deck + eye_h;
    let lz = edge_z;

    let eye_x = rp["x"] + r00 * lx + r01 * ly + r02 * lz;
    let eye_y = rp["y"] + r10 * lx + r11 * ly + r12 * lz;
    let eye_z = rp["z"] + r20 * lx + r21 * ly + r22 * lz;

    // ── View direction ──────────────────────────────────────────────
    // World look yaw = raft yaw + seat-relative yaw (seat faces raft +Z;
    // positive look_yaw = looking LEFT of the bow under the engine
    // convention above). Deck tilt leans into the gaze: facing the bow
    // you feel pitch, facing sideways you feel roll — projected by yaw.
    let world_yaw = ay + look_yaw;
    let tilt = (-ax * cos(look_yaw) - az * sin(look_yaw)) * transfer;
    let eff_pitch = clamp(look_pitch + tilt, -1.45, 1.45);

    let cp = cos(eff_pitch);
    let dir_x = sin(world_yaw) * cp;
    let dir_y = sin(eff_pitch);
    let dir_z = cos(world_yaw) * cp;

    set_camera_position(eye_x, eye_y, eye_z);
    set_camera_target(eye_x + dir_x, eye_y + dir_y, eye_z + dir_z);
}
