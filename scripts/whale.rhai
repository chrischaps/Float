// whale.rhai — the distant whale breach at dusk (M8).
//
// Once per dusk (with a chance of an encore), a humpback silhouette rises
// out of the sea far off toward the sunset, hangs, rolls onto its back,
// and falls in a column of spray — the reference photo in
// reference/water. The event is deliberately rare and easy to miss:
// this is a world that doesn't perform for you.
//
// Scheduling reads time_hours from the tod entity, so the F3 time slider
// works: scrub into the dusk window and a breach gets scheduled; scrub
// out and it's cancelled. The breach itself runs on real seconds.
//
// Motion: vertical arc = a plain parabola from fully-submerged to
// breach_height and back (4u(1-u), no ballistics needed at this
// distance); pitch rolls from nose-up launch to a back-first fall, with
// a body twist — the humpback signature. Splash bursts fire from the
// whale_splash particle entity pinned to ocean_height at the breach
// point: a small one when the nose exits, the big column on impact.
//
// The whale model is a normal PBR entity, so the dusk sun and ambient
// light it — palette cohesion for free (see specs/foam_followups.md).

let scheduled = -1.0;      // game-hour of the next breach (-1 = none)
let was_in_window = false;
let encore_used = false;
let breaching = false;
let bt = 0.0;              // real seconds into the current breach
let base_x = 0.0;          // breach point (world)
let base_z = 0.0;
let yaw_deg = 0.0;
let splash_exit_done = false;
let splash_entry_done = false;

fn sstep(t) {
    let c = clamp(t, 0.0, 1.0);
    c * c * (3.0 - 2.0 * c)
}

fn on_update() {
    let me = this_entity();
    let dt = delta_time();
    if dt <= 0.0 { return; }

    if !get_field(me, "whale", "enabled") {
        set_position(me, base_x, -40.0, base_z);
        return;
    }

    let tod = get_entity("tod");
    if tod < 0 { return; }
    let hours = get_field(tod, "time_of_day", "time_hours");

    let w0 = get_field(me, "whale", "window_start");
    let w1 = get_field(me, "whale", "window_end");
    let in_window = hours >= w0 && hours <= w1;

    // ── Scheduling: one breach per dusk at a random moment ──────────
    if in_window && !was_in_window {
        scheduled = w0 + (w1 - w0) * random_range(0.12, 0.55);
        encore_used = false;
    }
    if !in_window { scheduled = -1.0; }
    was_in_window = in_window;

    if !breaching && scheduled > 0.0 && hours >= scheduled {
        scheduled = -1.0;
        breaching = true;
        bt = 0.0;
        splash_exit_done = false;
        splash_entry_done = false;

        // Place the breach against the sunset band, relative to wherever
        // the raft has drifted. Sun-azimuth convention: dir = (sin, -cos)
        // points toward the sun (see time_of_day.rhai).
        let dist = get_field(me, "whale", "distance");
        let az = deg_to_rad(get_field(me, "whale", "bearing_deg")
            + random_range(-1.0, 1.0) * get_field(me, "whale", "bearing_spread_deg"));
        let raft = get_entity("raft");
        let rx = 0.0;
        let rz = 0.0;
        if raft >= 0 {
            let rp = get_position(raft);
            rx = rp["x"];
            rz = rp["z"];
        }
        base_x = rx + sin(az) * dist;
        base_z = rz - cos(az) * dist;
        // Swim across the view so the profile — fins, fluke — is what
        // rises against the sky.
        yaw_deg = rad_to_deg(atan2(rx - base_x, rz - base_z)) + 90.0
            + random_range(-20.0, 20.0);
    }

    if !breaching {
        set_position(me, base_x, -40.0, base_z);
        return;
    }

    // ── The breach ──────────────────────────────────────────────────
    let dur = get_field(me, "whale", "breach_duration");
    let h = get_field(me, "whale", "breach_height");
    bt += dt;
    let u = bt / dur;

    if u >= 1.0 {
        breaching = false;
        set_position(me, base_x, -40.0, base_z);
        // An encore, if the window still has room for one.
        let chance = get_field(me, "whale", "encore_chance");
        if !encore_used && in_window && (w1 - hours) > 0.25 && random() < chance {
            scheduled = hours + (w1 - 0.1 - hours) * random_range(0.3, 0.8);
            encore_used = true;
        }
        return;
    }

    let hidden = 8.0;  // start/end fully submerged (half-length + margin)
    let arc = 4.0 * u * (1.0 - u);
    let sea = ocean_height(base_x, base_z);
    let y = sea - hidden + (h + hidden) * arc;

    // Nose-up launch (-75° = nose skyward under the engine's bow-down-
    // positive pitch). The rotation leads the arc: near-vertical while
    // emerging, past vertical BEFORE the apex, falling back-first with a
    // twist — a flat whale at the top reads as levitation, not a leap.
    let pitch = -75.0 + 150.0 * sstep((u - 0.10) / 0.55);
    let roll = 45.0 * sstep((u - 0.25) / 0.50);
    set_position(me, base_x, y, base_z);
    set_rotation(me, pitch, yaw_deg, roll);

    // ── Splash bursts at the waterline ──────────────────────────────
    let splash = get_entity("whale_splash");
    if splash >= 0 {
        if !splash_exit_done && u > 0.14 {
            splash_exit_done = true;
            set_position(splash, base_x, sea, base_z);
            emit_burst(splash, 26);
        }
        if !splash_entry_done && u > 0.82 {
            splash_entry_done = true;
            set_position(splash, base_x, sea, base_z);
            emit_burst(splash, 90);
        }
    }
}
