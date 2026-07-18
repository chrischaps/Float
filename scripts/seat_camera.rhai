// seat_camera.rhai — First-person seated camera scooting along the raft edge.
//
// The eye is a point on the deck-edge scoot path (raft-local, run through
// the raft's full rotation matrix), so every heave and tilt of the raft
// moves your head — that positional bob is the strongest "I am on this
// thing" cue. A fraction of the deck tilt also leans into the view
// direction (roll_transfer): full transfer is nauseating, zero feels like
// floating on a tripod.
//
// Scooting (M6): A/D or left stick slide the seat along the raft's
// perimeter — a rounded rectangle (straight edges, quarter-circle
// corners) parametrized by arc length. The seat-outward heading turns
// with the path, so rounding a corner swings your whole view to face the
// new edge; there is no discrete "edge switch", the corner IS the
// transition. Velocity is slewed (scoot_ease) so motion starts and stops
// like a body shifting its weight, not a cursor.
//
// The raft-local seat point + outward heading are written back to this
// entity's seat component (seat_x / seat_z / seat_out_deg) so
// legs_idle.rhai places the body from the SAME state — the eye and the
// legs can never drift apart. (legs is declared after seat_camera in the
// scene so it reads this frame's values.)
//
// Look: mouse (cursor captured via set_cursor_captured) + arrows/stick.
// Yaw is clamped around seat-outward so you can't look through your own
// back; click to recapture the mouse after Escape.

let look_yaw = 0.0;     // radians, relative to seat-outward
let look_pitch = -0.12; // slight downward gaze toward the water line
let captured_once = false;
let scoot_s = 0.0;      // arc length along the perimeter (m, 0 = +Z mid)
let scoot_vel = 0.0;    // slewed scoot velocity (m/s)

const STICK_SPEED = 2.4;   // rad/s at full deflection
const PITCH_MIN = -1.3;    // ~-75 deg (down at your legs)
const PITCH_MAX = 1.25;
const YAW_LIMIT = 2.1;     // ~±120 deg around seat-outward

// Rounded-rectangle perimeter point. s = arc length from the +Z-edge
// midpoint, increasing toward +X (screen-left when facing outward).
// xe / ze = path half-extents, rc = corner radius (caller keeps it below
// min(xe, ze)). Returns #{x, z, yaw}: raft-local position and outward
// heading, engine yaw convention (0 = +Z, dir = (sin, cos)). On the
// corners pos = center + rc·(sin a, cos a), so position and heading stay
// exactly in sync. File-scope consts are invisible in Rhai sub-functions,
// hence the pi literals.
fn perimeter_point(s, xe, ze, rc) {
    let hx = xe - rc;
    let hz = ze - rc;
    let qa = rc * 1.5707963268;                    // quarter-arc length
    let total = 4.0 * hx + 4.0 * hz + 4.0 * qa;
    let t = s % total;
    if t < 0.0 { t += total; }

    // +Z edge, right half (toward +X)
    if t < hx { return #{ x: t, z: ze, yaw: 0.0 }; }
    t -= hx;
    // corner (+X, +Z)
    if t < qa {
        let a = t / rc;
        return #{ x: hx + rc * sin(a), z: hz + rc * cos(a), yaw: a };
    }
    t -= qa;
    // +X edge (toward -Z)
    if t < 2.0 * hz { return #{ x: xe, z: hz - t, yaw: 1.5707963268 }; }
    t -= 2.0 * hz;
    // corner (+X, -Z)
    if t < qa {
        let a = 1.5707963268 + t / rc;
        return #{ x: hx + rc * sin(a), z: -hz + rc * cos(a), yaw: a };
    }
    t -= qa;
    // -Z edge (toward -X)
    if t < 2.0 * hx { return #{ x: hx - t, z: -ze, yaw: 3.1415926536 }; }
    t -= 2.0 * hx;
    // corner (-X, -Z)
    if t < qa {
        let a = 3.1415926536 + t / rc;
        return #{ x: -hx + rc * sin(a), z: -hz + rc * cos(a), yaw: a };
    }
    t -= qa;
    // -X edge (toward +Z)
    if t < 2.0 * hz { return #{ x: -xe, z: -hz + t, yaw: 4.7123889804 }; }
    t -= 2.0 * hz;
    // corner (-X, +Z)
    if t < qa {
        let a = 4.7123889804 + t / rc;
        return #{ x: -hx + rc * sin(a), z: hz + rc * cos(a), yaw: a };
    }
    t -= qa;
    // +Z edge, left half (back to the midpoint)
    return #{ x: -hx + t, z: ze, yaw: 0.0 };
}

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
    let half_x = get_field(me, "seat", "half_x");
    let rc = get_field(me, "seat", "corner_radius");
    let scoot_speed = get_field(me, "seat", "scoot_speed");
    let scoot_ease = get_field(me, "seat", "scoot_ease");
    let eye_h = get_field(me, "seat", "eye_height");
    let deck = get_field(me, "seat", "deck_top");
    let transfer = get_field(me, "seat", "roll_transfer");
    let sens = get_field(me, "seat", "mouse_sens");

    // Corner radius must stay below both half-extents or the straight
    // segments go negative and the path folds over itself.
    let rc_max = (if half_x < edge_z { half_x } else { edge_z }) - 0.05;
    if rc > rc_max { rc = rc_max; }
    if rc < 0.01 { rc = 0.01; }

    // Recapture the mouse on click (Escape releases it).
    if is_action_just_pressed("recapture") {
        set_cursor_captured(true);
    }
    if !captured_once {
        // on_init may run before the window exists; re-request once here.
        set_cursor_captured(true);
        captured_once = true;
    }

    // ── Scoot along the deck edge ───────────────────────────────────
    let want = action_value("scoot") * scoot_speed;
    let kv = clamp(scoot_ease * dt, 0.0, 1.0);
    scoot_vel += (want - scoot_vel) * kv;
    scoot_s += scoot_vel * dt;

    let seat_pt = perimeter_point(scoot_s, half_x, edge_z, rc);
    let out_yaw = seat_pt.yaw;

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

    // Seat point in raft-local space: on the scoot path, eye above deck.
    let lx = seat_pt.x;
    let ly = deck + eye_h;
    let lz = seat_pt.z;

    let eye_x = rp["x"] + r00 * lx + r01 * ly + r02 * lz;
    let eye_y = rp["y"] + r10 * lx + r11 * ly + r12 * lz;
    let eye_z = rp["z"] + r20 * lx + r21 * ly + r22 * lz;

    // ── View direction ──────────────────────────────────────────────
    // World look yaw = raft yaw + seat-outward heading + seat-relative
    // yaw (positive look_yaw = looking LEFT of outward under the engine
    // convention above). Deck tilt leans into the gaze: facing the bow
    // you feel pitch, facing sideways you feel roll — projected by the
    // TOTAL raft-local gaze yaw, so it stays right on every edge.
    let gaze = out_yaw + look_yaw;
    let world_yaw = ay + gaze;
    let tilt = (-ax * cos(gaze) - az * sin(gaze)) * transfer;
    let eff_pitch = clamp(look_pitch + tilt, -1.45, 1.45);

    let cp = cos(eff_pitch);
    let dir_x = sin(world_yaw) * cp;
    let dir_y = sin(eff_pitch);
    let dir_z = cos(world_yaw) * cp;

    set_camera_position(eye_x, eye_y, eye_z);
    set_camera_target(eye_x + dir_x, eye_y + dir_y, eye_z + dir_z);

    // ── Publish scoot state for legs_idle.rhai ──────────────────────
    set_field(me, "seat", "seat_x", seat_pt.x);
    set_field(me, "seat", "seat_z", seat_pt.z);
    set_field(me, "seat", "seat_out_deg", rad_to_deg(out_yaw));
}
