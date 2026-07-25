// raft_visitor.rhai — "The Visitor": around noon of day 1 (the first
// counted day after the title card's looping day 0), a
// weathered twin of your raft drifts up out of the haze, holds a
// companionable distance for a few minutes — riding the same swells,
// never anchored — then drifts off on a different bearing than it came.
// After the first visit it may rarely return on later days. A passing
// stranger in a world that doesn't perform for you.
//
// Day tracking: time_of_day.rhai now owns a published day counter on
// the tod component (day 0 loops under the title card, day 1 is the
// first counted day) — when that field exists this script mirrors it,
// so the visitor and the ramp can never disagree. Scenes without the
// ramp fields fall back to the original derived counter: a single-frame
// hours drop > 12 is a forward midnight wrap (day += 1), a single-frame
// rise > 12 is a backward scrub across midnight (day -= 1). Ordinary F3
// slider dragging passes through intermediate values and trips neither
// branch. ACCEPTED DEGRADATION: scrubbing moves within the current day —
// you can't scrub TO the visit day. For testing, use the trigger_visit
// one-shot or a short day_length_sec.
//
// Scheduling is the whale idiom: window entry schedules, scrubbing out
// cancels a PENDING visit, storms make the trigger wait. Once the visit
// starts it runs to completion on real seconds — weather and scrubbing
// never abort an active visit (like the breach).
//
// The visitor's planar position is a polar offset from the PLAYER's raft
// (dist, bearing), so both rafts visibly ride the same current; its
// vertical motion is raft.rhai's 5-point buoyancy math with a slightly
// deeper draft and lazier response — the same sea, an older, heavier
// boat.

let day = 1.0;
let prev_hours = -1.0;
let scheduled = -1.0;       // game-hour of the next visit (-1 = none)
let was_in_window = false;
let rolled_day = -1.0;      // last day the return_chance was rolled
let visited_first = false;  // the guaranteed first visit has happened
let phase = 0;              // 0 parked, 1 approach, 2 hold, 3 depart
let pt = 0.0;               // real seconds into the current phase
let bearing = 0.0;          // approach bearing (deg, world, from player raft)
let depart_bearing = 0.0;
let base_yaw = 0.0;         // the visitor's resting heading (deg)
let hold_exit_brg = 0.0;    // live bearing/distance captured at hold→depart
let hold_exit_dist = 18.0;
let cur_y = 0.0;            // buoyancy smoothing state
let cur_pitch = 0.0;
let cur_roll = 0.0;
let lap_t = 0.0;            // audio timers (real seconds)
let creak_t = 0.0;
let pub_phase = -1.0;       // write guards for the published F3-panel fields
let pub_day = -1.0;         // (set_field is deferred; only push on change)

fn sstep(t) {
    let c = clamp(t, 0.0, 1.0);
    c * c * (3.0 - 2.0 * c)
}

fn on_update() {
    let me = this_entity();
    let dt = delta_time();
    if dt <= 0.0 { return; }

    let raft2 = get_entity("raft2");
    if raft2 < 0 { return; }

    let enabled = get_field(me, "raft_visitor", "enabled");
    if enabled == () { return; }    // component not landed yet (deferred writes)
    if !enabled {
        set_position(raft2, -80.0, -50.0, -80.0);
        return;
    }

    let dbg = get_field(me, "raft_visitor", "debug_log");
    if dbg == () { dbg = false; }

    // ── Day counter (see header for the rule + degradation) ────────
    let tod = get_entity("tod");
    if tod < 0 { return; }
    let hours = get_field(tod, "time_of_day", "time_hours");
    let tod_day = get_field(tod, "time_of_day", "day");
    if tod_day != () {
        // TOD owns the count (day-0 title loop, scrub rules) — mirror it.
        if dbg && tod_day != day { log("visitor: day " + tod_day); }
        day = tod_day;
    } else if prev_hours >= 0.0 {
        if prev_hours - hours > 12.0 {
            day += 1.0;
            if dbg { log("visitor: day " + day); }
        } else if hours - prev_hours > 12.0 {
            day -= 1.0;
            if day < 1.0 { day = 1.0; }
            if dbg { log("visitor: day " + day + " (scrubbed back)"); }
        }
    }
    prev_hours = hours;

    // ── Publish phase/day for the F3 Visitor panel (read-only there) ──
    if day != pub_day {
        set_field(me, "raft_visitor", "day", day);
        pub_day = day;
    }
    if phase.to_float() != pub_phase {
        set_field(me, "raft_visitor", "phase", phase.to_float());
        pub_phase = phase.to_float();
    }

    // ── Debug one-shot: consume and reset (reality.rhai idiom).
    //    Fires immediately, bypassing day/window/storm; does NOT consume
    //    the guaranteed first visit. ──────────────────────────────────
    let force_fire = false;
    let trig = get_field(me, "raft_visitor", "trigger_visit");
    if trig != () && trig >= 0.5 {
        set_field(me, "raft_visitor", "trigger_visit", -1.0);
        if phase == 0 { force_fire = true; }
    }

    // ── Scheduling: window entry schedules, scrubbing out cancels ──
    let w0 = get_field(me, "raft_visitor", "window_start");
    let w1 = get_field(me, "raft_visitor", "window_end");
    let first_day = get_field(me, "raft_visitor", "first_day");
    let in_window = hours >= w0 && hours <= w1;

    if in_window && !was_in_window {
        if day >= first_day && !visited_first {
            // The guaranteed visit, early in the window — the ~6-minute
            // encounter runs on real seconds regardless of window width.
            scheduled = w0 + (w1 - w0) * random_range(0.1, 0.4);
        } else if day > first_day && rolled_day != day {
            rolled_day = day;
            let chance = get_field(me, "raft_visitor", "return_chance");
            if random() < chance {
                scheduled = w0 + (w1 - w0) * random_range(0.1, 0.4);
            }
        }
    }
    if !in_window { scheduled = -1.0; }
    was_in_window = in_window;

    // Storms keep the stranger away: the trigger just waits — if the sky
    // clears inside the window the visit still happens; otherwise the
    // window closes and cancels it.
    let stormy = false;
    let wxe = get_entity("weather_controller");
    if wxe >= 0 {
        let ws = get_field(wxe, "weather", "state");
        if ws != () && ws > 2.5 { stormy = true; }
    }

    let spawn_dist = get_field(me, "raft_visitor", "spawn_distance");
    let hold_dist = get_field(me, "raft_visitor", "hold_distance");
    let draft = get_field(me, "raft_visitor", "draft");

    // Player raft position — the polar origin for everything below.
    let rx = 0.0;
    let rz = 0.0;
    let raft = get_entity("raft");
    if raft >= 0 {
        let rp = get_position(raft);
        rx = rp["x"];
        rz = rp["z"];
    }

    // ── Fire ────────────────────────────────────────────────────────
    if phase == 0 && (force_fire || (!stormy && scheduled > 0.0 && hours >= scheduled)) {
        scheduled = -1.0;
        if !force_fire { visited_first = true; }
        phase = 1;
        pt = 0.0;
        bearing = get_field(me, "raft_visitor", "bearing_deg")
            + random_range(-1.0, 1.0) * get_field(me, "raft_visitor", "bearing_spread_deg");
        let turn = get_field(me, "raft_visitor", "depart_turn_deg");
        if random() < 0.5 {
            depart_bearing = bearing + turn;
        } else {
            depart_bearing = bearing - turn;
        }
        // A raft has no bow: it arrives broadside-ish, at its own angle.
        base_yaw = bearing + 90.0 + random_range(-25.0, 25.0);
        // Seed the buoyancy smoothing at the spawn point so it doesn't
        // lurch up from y=0 on the first visible frame.
        let az0 = deg_to_rad(bearing);
        let sx = rx + sin(az0) * spawn_dist;
        let sz = rz - cos(az0) * spawn_dist;
        cur_y = ocean_height(sx, sz) - draft;
        cur_pitch = 0.0;
        cur_roll = 0.0;
        lap_t = 1.0;
        creak_t = 5.0;
        if dbg { log("visitor: approaching, bearing " + bearing + " depart " + depart_bearing); }
    }

    if phase == 0 {
        set_position(raft2, -80.0, -50.0, -80.0);
        return;
    }

    // ── The visit: approach → hold → depart, on real seconds ───────
    pt += dt;
    let dist = hold_dist;
    let brg = bearing;

    if phase == 1 {
        let dur = get_field(me, "raft_visitor", "approach_duration_s");
        let u = pt / dur;
        if u >= 1.0 {
            phase = 2;
            pt = 0.0;
            u = 1.0;
            if dbg { log("visitor: holding"); }
        }
        let s = sstep(u);
        dist = spawn_dist + (hold_dist - spawn_dist) * s;
        // A gentle arc, not a beeline: the bearing eases in by 25°.
        brg = bearing + 25.0 * (1.0 - s);
    } else if phase == 2 {
        let dur = get_field(me, "raft_visitor", "hold_duration_s");
        let wander = get_field(me, "raft_visitor", "wander_amp_m");
        // Wander runs on phase time so it starts at zero offset — no pop
        // at the approach→hold seam. Periods are minutes-long: current,
        // not steering.
        dist = hold_dist + wander * sin(pt * 0.045);
        brg = bearing + 6.0 * sin(pt * 0.03);
        if pt >= dur {
            // Capture the live offsets so departure starts exactly where
            // the wander left it — no pop at the hold→depart seam.
            hold_exit_dist = dist;
            hold_exit_brg = brg;
            phase = 3;
            pt = 0.0;
            if dbg { log("visitor: departing"); }
        }
    } else {
        let dur = get_field(me, "raft_visitor", "depart_duration_s");
        let u = pt / dur;
        if u >= 1.0 {
            phase = 0;
            set_position(raft2, -80.0, -50.0, -80.0);
            if dbg { log("visitor: gone"); }
            return;
        }
        let s = sstep(u);
        dist = hold_exit_dist + (spawn_dist - hold_exit_dist) * s;
        brg = hold_exit_brg + (depart_bearing - hold_exit_brg) * s;
    }

    let az = deg_to_rad(brg);
    let vx = rx + sin(az) * dist;
    let vz = rz - cos(az) * dist;

    // ── Buoyancy: raft.rhai's 5-point math, deeper draft, lazier ───
    let heave_resp = get_field(me, "raft_visitor", "heave_response");
    let ang_resp = get_field(me, "raft_visitor", "angular_response");
    let yaw_deg = base_yaw + 6.0 * sin(total_time() * 0.05);
    let yaw = deg_to_rad(yaw_deg);
    let half_l = 0.9;
    let half_w = 1.0;

    let fwd_x = sin(yaw);
    let fwd_z = cos(yaw);
    let right_x = cos(yaw);
    let right_z = -sin(yaw);

    let h_c = ocean_height(vx, vz);
    let h_f = ocean_height(vx + fwd_x * half_l, vz + fwd_z * half_l);
    let h_b = ocean_height(vx - fwd_x * half_l, vz - fwd_z * half_l);
    let h_r = ocean_height(vx + right_x * half_w, vz + right_z * half_w);
    let h_l = ocean_height(vx - right_x * half_w, vz - right_z * half_w);

    let target_y = (h_c + h_f + h_b + h_r + h_l) / 5.0 - draft;

    let slope_f = (h_f - h_b) / (2.0 * half_l);
    let slope_r = (h_r - h_l) / (2.0 * half_w);
    let n = ocean_normal(vx, vz);
    let normal_blend = 0.4;
    let n_slope_f = -(n["x"] * fwd_x + n["z"] * fwd_z) / n["y"];
    let n_slope_r = -(n["x"] * right_x + n["z"] * right_z) / n["y"];
    let s_f = slope_f + (n_slope_f - slope_f) * normal_blend;
    let s_r = slope_r + (n_slope_r - slope_r) * normal_blend;

    let target_pitch = rad_to_deg(atan(-s_f));
    let target_roll = rad_to_deg(atan(s_r));

    let ky = clamp(heave_resp * dt, 0.0, 1.0);
    let ka = clamp(ang_resp * dt, 0.0, 1.0);
    cur_y += (target_y - cur_y) * ky;
    cur_pitch += (target_pitch - cur_pitch) * ka;
    cur_roll += (target_roll - cur_roll) * ka;

    set_position(raft2, vx, cur_y, vz);
    set_rotation(raft2, cur_pitch, yaw_deg, cur_roll);

    // ── Faint water voice while it's near (spatial cap is 25 m, so
    //    beyond 30 m we don't even ask) ──────────────────────────────
    if dist < 30.0 {
        lap_t -= dt;
        if lap_t <= 0.0 {
            // Chance of a lap follows the local water activity at one of
            // its edges — sparse by construction, no zero-cross machinery.
            let a = abs(ocean_velocity_y(vx + right_x * half_w, vz + right_z * half_w));
            if random() < clamp(a * 1.5, 0.05, 0.6) {
                let which = 1 + (random() * 3.999).to_int();
                let vol = get_field(me, "raft_visitor", "lap_volume");
                play_sound_at("audio/lap_" + which + ".ogg", vx, cur_y, vz,
                    vol, random_range(0.9, 1.1));
                if dbg { log("visitor: lap_" + which); }
            }
            lap_t = get_field(me, "raft_visitor", "lap_min_gap_s") + random_range(0.0, 3.0);
        }
        creak_t -= dt;
        if creak_t <= 0.0 {
            let which = 1 + (random() * 2.999).to_int();
            let vol = get_field(me, "raft_visitor", "creak_volume");
            play_sound_at("audio/creak_" + which + ".ogg", vx, cur_y, vz,
                vol, random_range(0.85, 1.0));
            if dbg { log("visitor: creak_" + which); }
            creak_t = random_range(7.0, 16.0);
        }
    }
}
