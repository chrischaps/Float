// seat_camera.rhai — First-person seated camera scooting along the raft edge.
//
// The eye is a point on the deck-edge scoot path (raft-local, run through
// the raft's full rotation matrix), so every heave and tilt of the raft
// moves your head — that positional bob is the strongest "I am on this
// thing" cue. A fraction of the deck tilt also leans into the view
// direction (roll_transfer): full transfer is nauseating, zero feels like
// floating on a tripod.
//
// Scooting (M6): the seat rides the raft's perimeter — a rounded
// rectangle (straight edges, quarter-circle corners) parametrized by arc
// length. The seat-outward heading turns with the path, so rounding a
// corner swings your whole view to face the new edge; there is no
// discrete "edge switch", the corner IS the transition.
//
// With animated_scoot (default), A/D triggers discrete scoot STEPS
// synced to the body's skeletal clips: travel follows the clip's
// weight-shift phase, the eye inherits the pelvis lift (step_bob), and
// a step ALWAYS plays to completion. A key still held at the end chains
// the next step immediately (step_dir stays non-zero, step_seq ticks);
// step_pause only rests a step that follows a release.
// animated_scoot = false restores the original continuous slide.
//
// The raft-local seat point + outward heading + step state are written
// back to this entity's seat component (seat_x / seat_z / seat_out_deg /
// step_dir / step_seq) so body.rhai places the body and fires the clips from the
// SAME state — the eye and the body can never drift apart. (body is
// declared after seat_camera in the scene so it reads this frame's
// values.)
//
// Look: mouse (cursor captured via set_cursor_captured) + arrows/stick.
// Yaw is clamped around seat-outward so you can't look through your own
// back; click to recapture the mouse after Escape.

let look_yaw = 0.0;     // radians, relative to seat-outward
let look_pitch = -0.18; // resting gaze ~10° down: horizon rides the upper
                        // third of the frame (human resting gaze is below
                        // horizontal) and the knees crest the bottom edge
let glance = 0.0;       // slewed scoot glance-down overlay (rad, <= 0)
let captured_once = false;
let scoot_s = 0.0;      // arc length along the perimeter (m, 0 = +Z mid)
let scoot_vel = 0.0;    // scoot velocity (m/s; slewed in continuous mode)
let step_dir = 0.0;     // -1/0/+1: scoot step in progress (animated mode)
let step_t = 0.0;       // seconds into the current step
let step_seq = 0.0;     // increments on every step START (chained or not)
let pause_left = 0.0;   // rest before a step that follows a released key
let uw_active = false;  // underwater hysteresis gate (see block below)
let uw_mix = 0.0;       // eased mode-5 mix: ~1-frame attack, short release
let last_sub = -1.0;    // write guard for the published submerged factor

const STICK_SPEED = 2.4;   // rad/s at full deflection
const PITCH_MIN = -1.3;    // ~-75 deg (down at your legs)
const PITCH_MAX = 1.25;
const YAW_LIMIT = 2.1;     // ~±120 deg around seat-outward
const GLANCE_PITCH = 0.14; // ~8 deg: scooting dips the gaze toward the
                           // body doing the work, re-showing the legs
const GLANCE_EASE = 3.0;   // 1/s — a head motion, not a snap

fn sstep(t) {
    let c = clamp(t, 0.0, 1.0);
    c * c * (3.0 - 2.0 * c)
}

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

// FOV lives in the seat_camera entity's camera_tuning component (the player
// applies it at load; the F3 Camera panel edits it live) — not set here.
fn on_init() {
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
    let eye_in = get_field(me, "seat", "eye_inboard");
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

    // Title card (title.rhai): while its published `locked` factor is up,
    // look and scoot INPUT are ignored — but everything below still runs,
    // so the raft's heave keeps moving the eye and the world drifts
    // behind the card. One-frame-stale cross-script read is fine for a
    // signal this slow.
    let ui_locked = false;
    let tc = get_entity("title_controller");
    if tc >= 0 {
        let lk = get_field(tc, "title", "locked");
        if lk != () && lk > 0.5 { ui_locked = true; }
    }

    // ── Scoot along the deck edge ───────────────────────────────────
    // Animated mode (default): A/D triggers a discrete scoot STEP.
    // body.rhai plays the matching scoot clip (it watches step_dir);
    // the seat's travel follows the clip's weight-shift phase, and the
    // eye inherits the pelvis lift — the body does the moving, the
    // camera just rides it. Held keys chain steps with a short rest:
    // a shuffle rhythm, not a conveyor belt. step_time MUST match the
    // clip length in tools/generate_body.py.
    let animated = get_field(me, "seat", "animated_scoot");
    let eye_bob = 0.0;
    if animated {
        let step_time = get_field(me, "seat", "step_time");
        let step_dist = get_field(me, "seat", "step_distance");
        let input = if ui_locked { 0.0 } else { action_value("scoot") };
        pause_left -= dt;
        if step_dir == 0.0 && pause_left <= 0.0 {
            if input > 0.35 {
                step_dir = 1.0;
                step_t = 0.0;
                step_seq += 1.0;
            } else if input < -0.35 {
                step_dir = -1.0;
                step_t = 0.0;
                step_seq += 1.0;
            }
        }
        scoot_vel = 0.0;
        if step_dir != 0.0 {
            let u0 = clamp(step_t / step_time, 0.0, 1.0);
            step_t += dt;
            let u = clamp(step_t / step_time, 0.0, 1.0);
            // Travel synced to the clip's weight-shift (u 0.32→0.87):
            // the seat moves only while the body is actually pushing.
            let move_d = step_dist * (sstep((u - 0.32) / 0.55)
                                      - sstep((u0 - 0.32) / 0.55));
            scoot_s += step_dir * move_d;
            scoot_vel = step_dir * move_d / dt;   // feeds the glance below
            // Eye rides the clip's pelvis lift (rise into the push,
            // settle before the clip ends).
            eye_bob = get_field(me, "seat", "step_bob")
                * sstep((u - 0.21) / 0.25) * (1.0 - sstep((u - 0.55) / 0.35));
            if step_t >= step_time {
                // The clip always plays to completion. If the key is
                // still held the same way, roll STRAIGHT into the next
                // step: step_dir never touches 0, so body.rhai never
                // drops to an idle variant between chained steps (that
                // dropout is what read as the clip "restarting"). The
                // scoot clip starts and ends on the neutral pose, so the
                // repeat is seamless. Only a released key rests.
                let held = if step_dir > 0.0 { input > 0.35 }
                           else { input < -0.35 };
                if held {
                    step_t -= step_time;   // carry the overshoot, no drift
                    step_seq += 1.0;
                } else {
                    step_dir = 0.0;
                    pause_left = get_field(me, "seat", "step_pause");
                }
            }
        }
    } else {
        // Continuous fallback: the original M6 slide.
        let want = if ui_locked { 0.0 } else { action_value("scoot") * scoot_speed };
        scoot_vel += (want - scoot_vel) * clamp(scoot_ease * dt, 0.0, 1.0);
        scoot_s += scoot_vel * dt;
    }

    let seat_pt = perimeter_point(scoot_s, half_x, edge_z, rc);
    let out_yaw = seat_pt.yaw;

    // Scooting glances the gaze down at the body doing the work — a view
    // overlay (not look_pitch), so it eases back out on its own and the
    // legs get re-shown every shuffle without stealing the mouse.
    let g_target = if scoot_speed > 0.0 {
        -GLANCE_PITCH * clamp(abs(scoot_vel) / scoot_speed, 0.0, 1.0)
    } else {
        0.0
    };
    glance += (g_target - glance) * clamp(GLANCE_EASE * dt, 0.0, 1.0);

    // ── Look input ──────────────────────────────────────────────────
    // Subtract deltas (engine FPS convention, see flint-physics
    // character.rs): with dir = (sin(yaw), _, cos(yaw)), increasing yaw
    // turns toward +X = screen-LEFT, so mouse-right must decrease yaw.
    // Mouse-forward (negative dy) must increase pitch (look up).
    if !ui_locked {
        look_yaw -= mouse_delta_x() * sens + action_value("look_x") * STICK_SPEED * dt;
        look_pitch -= mouse_delta_y() * sens + action_value("look_y") * STICK_SPEED * dt;
    }
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

    // ── Eye position ────────────────────────────────────────────────
    // Legacy path: a fixed offset above/inboard of the seat point.
    let lx = seat_pt.x - sin(out_yaw) * eye_in;
    let ly = deck + eye_h + eye_bob;
    let lz = seat_pt.z - cos(out_yaw) * eye_in;

    let eye_x = rp["x"] + r00 * lx + r01 * ly + r02 * lz;
    let eye_y = rp["y"] + r10 * lx + r11 * ly + r12 * lz;
    let eye_z = rp["z"] + r20 * lx + r21 * ly + r22 * lz;

    // Bone path: follow the body's "eye" joint (bone_probe, model-local,
    // one frame of POSE lag only) so breathing, weight shifts, and the
    // scoot push-up are FELT in the view. The body placement is mirrored
    // here with THIS frame's raft transform (seat_camera runs before
    // body.rhai; reading the body entity would lag the raft by a frame)
    // — the shared body_inset/body_seat_y fields keep the two scripts in
    // agreement. At bind pose this path equals the legacy one exactly.
    let follow = clamp(get_field(me, "seat", "eye_follow"), 0.0, 1.0);
    let body = get_entity("body");
    if follow > 0.001 && body >= 0 {
        let ex = get_field(body, "bone_probe", "x");
        if ex != () {
            let ey = get_field(body, "bone_probe", "y");
            let ez = get_field(body, "bone_probe", "z");

            let b_in = get_field(me, "seat", "body_inset");
            let b_y = get_field(me, "seat", "body_seat_y");
            let blx = seat_pt.x - sin(out_yaw) * b_in;
            let blz = seat_pt.z - cos(out_yaw) * b_in;
            let bpx = rp["x"] + r00 * blx + r01 * b_y + r02 * blz;
            let bpy = rp["y"] + r10 * blx + r11 * b_y + r12 * blz;
            let bpz = rp["z"] + r20 * blx + r21 * b_y + r22 * blz;

            // Body entity rotation (matches body.rhai's set_rotation):
            // euler ZYX of (raft pitch, raft yaw + outward, damped roll).
            let bx2 = ax;
            let by2 = ay + out_yaw;
            let bz2 = az * 0.6;
            let sx2 = sin(bx2); let cx2 = cos(bx2);
            let sy2 = sin(by2); let cy2 = cos(by2);
            let sz2 = sin(bz2); let cz2 = cos(bz2);
            let bex = bpx + (cy2 * cz2) * ex + (sx2 * sy2 * cz2 - cx2 * sz2) * ey + (cx2 * sy2 * cz2 + sx2 * sz2) * ez;
            let bey = bpy + (cy2 * sz2) * ex + (sx2 * sy2 * sz2 + cx2 * cz2) * ey + (cx2 * sy2 * sz2 - sx2 * cz2) * ez;
            let bez = bpz + (-sy2) * ex + (sx2 * cy2) * ey + (cx2 * cy2) * ez;

            // Blend: the motion-comfort dial. In bone mode the scoot
            // lift comes from the clip's own pelvis motion, so the
            // scripted eye_bob envelope fades out with the legacy path.
            eye_x += (bex - eye_x) * follow;
            eye_y += (bey - eye_y) * follow;
            eye_z += (bez - eye_z) * follow;
        }
    }

    // ── View direction ──────────────────────────────────────────────
    // World look yaw = raft yaw + seat-outward heading + seat-relative
    // yaw (positive look_yaw = looking LEFT of outward under the engine
    // convention above). Deck tilt leans into the gaze: facing the bow
    // you feel pitch, facing sideways you feel roll — projected by the
    // TOTAL raft-local gaze yaw, so it stays right on every edge.
    let gaze = out_yaw + look_yaw;
    let world_yaw = ay + gaze;
    let tilt = (-ax * cos(gaze) - az * sin(gaze)) * transfer;
    let eff_pitch = clamp(look_pitch + tilt + glance, -1.45, 1.45);

    let cp = cos(eff_pitch);
    let dir_x = sin(world_yaw) * cp;
    let dir_y = sin(eff_pitch);
    let dir_z = cos(world_yaw) * cp;

    set_camera_position(eye_x, eye_y, eye_z);
    set_camera_target(eye_x + dir_x, eye_y + dir_y, eye_z + dir_z);

    // ── Underwater moments: a swell buries the eye (render mode 5) ──
    // Detection lives HERE, not in its own script: this is the only place
    // the eye position exists THIS frame (set_field publishes are a frame
    // stale — fine for the audio muffle, too late for the attack frame).
    // set_render_mode is transient: called only while active; the player
    // heals the frame the calls stop. reality.rhai yields the slot by
    // watching the published `submerged` factor.
    let d = ocean_height(eye_x, eye_z) - eye_y;   // + = eye under water
    let force = get_field(me, "seat", "force_submerge_s");
    if force != () && force > 0.0 {
        d = 0.4;
        set_field(me, "seat", "force_submerge_s", force - dt);
    }
    // Hysteresis: arm while the waterline can reach the frame (the near
    // plane sees ~±0.08 m around the eye, plus wave slope), disarm well
    // below — chop modulates the on-screen LINE, never this gate.
    if uw_active {
        if d < -0.25 { uw_active = false; }
    } else if d > -0.15 {
        uw_active = true;
    }
    if uw_active {
        uw_mix += (1.0 - uw_mix) * clamp(dt / 0.03, 0.0, 1.0);
    } else if uw_mix > 0.0 {
        let rel = get_field(me, "seat", "submerge_release_s");
        uw_mix -= uw_mix * clamp(dt / rel, 0.0, 1.0);
        if uw_mix < 0.005 { uw_mix = 0.0; }
    }
    if uw_mix > 0.001 {
        // Context for the shader: sea energy (murk turbidity), daylight
        // (shaft/murk brightness), biolum (night specks) — all TOD/
        // weather-driven upstream, never constants (wildlife light rule).
        let oent = get_entity("ocean");
        let energy = 0.3;
        let glow = 0.0;
        if oent >= 0 {
            let amp = get_field(oent, "ocean", "amplitude");
            let chop = get_field(oent, "ocean", "choppiness");
            if amp != () && chop != () {
                energy = clamp(amp * (0.5 + 0.5 * chop) / 3.5, 0.0, 1.0);
            }
            let fg = get_field(oent, "ocean", "foam_glow");
            if fg != () { glow = clamp(fg, 0.0, 1.0); }
        }
        let daylight = 1.0;
        let sun = get_entity("sun");
        if sun >= 0 {
            let si = get_field(sun, "light", "intensity");
            if si != () { daylight = clamp(si / 2.0, 0.0, 1.0); }
        }
        set_render_mode(5, uw_mix);
        set_render_mode_params(d, energy, daylight, glow);
    }
    // Published factor for water_ambience (muffle/duck) and reality
    // (slot yield). One-frame stale is fine for both readers.
    let full_m = get_field(me, "seat", "submerge_full_m");
    let sub_now = clamp(d / full_m, 0.0, 1.0);
    if abs(sub_now - last_sub) > 0.005 || (sub_now <= 0.0 && last_sub > 0.0) {
        set_field(me, "seat", "submerged", sub_now);
        last_sub = sub_now;
    }

    // ── Publish scoot state for body.rhai ───────────────────────────
    set_field(me, "seat", "seat_x", seat_pt.x);
    set_field(me, "seat", "seat_z", seat_pt.z);
    set_field(me, "seat", "seat_out_deg", rad_to_deg(out_yaw));
    set_field(me, "seat", "step_dir", step_dir);
    set_field(me, "seat", "step_seq", step_seq);
}
