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
// Motion: physical, derived from two knobs — breach_height (apex of the
// body center) and breach_duration (airborne seconds). Exit speed and
// gravity follow ballistically from those. Three phases: a powered
// underwater ascent at full exit speed, a true free-flight arc with
// forward carry along the whale's heading (the breach travels — it
// never rises and falls on a rail), and a drag-braked sink after
// impact. Rotation is the humpback signature: launched aligned to its
// velocity, then a constant-rate BACKWARD tip past vertical with a
// belly-up twist, landing on its back — never a forward dive. Splash
// bursts fire from the whale_splash particle entity pinned to
// ocean_height under the whale: a small one when the rostrum pierces,
// the big column when the back hits.
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
let boom_t = -1.0;         // splash-down audio countdown (speed-of-sound lag)
let boom_vol = 0.0;

let hidden = 8.0;          // parked depth of the body center (half-length + margin)
let vy0 = 0.0;             // vertical exit speed (m/s), from height + airtime
let grav = 0.0;            // ballistic gravity for this breach (≈ real g at defaults)
let vh = 0.0;              // forward carry speed along the heading
let fwd_x = 0.0;           // carry direction (unit) — the nose at launch
let fwd_z = 0.0;
let pitch0 = 0.0;          // launch pitch, aligned to the exit velocity
let air_time = 0.0;        // free-flight seconds (center out to center in)
let t_launch = 0.0;        // powered ascent seconds (hidden depth at vy0)
let t_sink = 0.0;          // re-entry sink seconds (drag ease-out to hidden)

fn sstep(t) {
    let c = clamp(t, 0.0, 1.0);
    c * c * (3.0 - 2.0 * c)
}

fn on_update() {
    let me = this_entity();
    let dt = delta_time();
    if dt <= 0.0 { return; }

    // Pending splash-down boom (runs regardless of breach state so the
    // delayed sound still lands after the animation ends).
    if boom_t >= 0.0 {
        boom_t -= dt;
        if boom_t < 0.0 {
            play_sound("audio/breach_splash.ogg", boom_vol);
            boom_t = -1.0;
        }
    }

    if !get_field(me, "whale", "enabled") {
        set_position(me, base_x, -40.0, base_z);
        return;
    }

    let tod = get_entity("tod");
    if tod < 0 { return; }
    let hours = get_field(tod, "time_of_day", "time_hours");

    // Day 0 loops behind the title card (time_of_day.rhai holds the day
    // counter at 0 while title.locked is up) — its dusk passes every
    // ~60 s, and from the locked camera a breach would just be a
    // confusing audio cue. The whale sits out day 0 entirely; the first
    // counted dusk is day 1's.
    let day = get_field(tod, "time_of_day", "day");
    let title_day = day != () && day < 0.5;

    let w0 = get_field(me, "whale", "window_start");
    let w1 = get_field(me, "whale", "window_end");
    let in_window = hours >= w0 && hours <= w1;

    // ── Scheduling: one breach per dusk at a random moment ──────────
    if in_window && !was_in_window && !title_day {
        scheduled = w0 + (w1 - w0) * random_range(0.12, 0.55);
        encore_used = false;
    }
    if !in_window || title_day { scheduled = -1.0; }
    was_in_window = in_window;

    // Storms ground the wildlife: no breach show through heavy weather.
    // (The trigger just waits — if the sky clears inside the window the
    // breach still happens; otherwise the window closes and cancels it.)
    let stormy = false;
    let wxe = get_entity("weather_controller");
    if wxe >= 0 {
        let ws = get_field(wxe, "weather", "state");
        if ws != () && ws > 2.5 { stormy = true; }
    }

    if !breaching && !stormy && scheduled > 0.0 && hours >= scheduled {
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

        // Ballistics from the two tuned knobs: apex = breach_height,
        // free-flight time = breach_duration. At the defaults (6 m,
        // 2.1 s) grav lands within a few percent of real g.
        let h = get_field(me, "whale", "breach_height");
        air_time = get_field(me, "whale", "breach_duration");
        vy0 = 4.0 * h / air_time;
        grav = 8.0 * h / (air_time * air_time);
        // Carry sets the launch angle: 0.38 → ~69° from horizontal,
        // and roughly a body length of travel over the whole breach.
        vh = 0.38 * vy0;
        fwd_x = sin(deg_to_rad(yaw_deg));
        fwd_z = cos(deg_to_rad(yaw_deg));
        pitch0 = -rad_to_deg(atan2(vy0, vh));
        t_launch = hidden / vy0;
        t_sink = 2.0 * hidden / vy0;  // quadratic ease-out entering at vy0
    }

    if !breaching {
        set_position(me, base_x, -40.0, base_z);
        return;
    }

    // ── The breach: powered ascent → free flight → braked sink ──────
    bt += dt;

    if bt >= t_launch + air_time + t_sink {
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

    // Forward carry through the whole breach: the arc travels along the
    // body instead of rising and falling in place.
    let s = vh * bt;
    let x = base_x + fwd_x * s;
    let z = base_z + fwd_z * s;
    let sea = ocean_height(x, z);

    let y = 0.0;
    let pitch = pitch0;
    if bt < t_launch {
        // Powered underwater ascent — already at exit speed, aligned to
        // the exit velocity like a missile leaving the water.
        y = sea - hidden + vy0 * bt;
    } else if bt < t_launch + air_time {
        // Free flight: real ballistics from the moment the center
        // clears. Torque-free backward tip at constant rate, ending
        // ~100° past the launch pitch — over its own back, so it falls
        // back-first (a forward sweep reads as a dolphin dive).
        let ta = bt - t_launch;
        y = sea + vy0 * ta - 0.5 * grav * ta * ta;
        pitch = pitch0 - 100.0 * (ta / air_time);
    } else {
        // Re-entry: water drag bleeds the fall speed off into the deep.
        // Quadratic ease-out enters at exactly vy0 (t_sink = 2·hidden/vy0)
        // so there is no velocity pop at the splash frame.
        let q = clamp((bt - t_launch - air_time) / t_sink, 0.0, 1.0);
        let inv = 1.0 - q;
        y = sea - hidden * (1.0 - inv * inv);
        pitch = pitch0 - 100.0;
    }
    // The belly-up twist develops through mid-flight.
    let qa = clamp((bt - t_launch) / air_time, 0.0, 1.0);
    let roll = 110.0 * sstep((qa - 0.12) / 0.72);
    set_position(me, x, y, z);
    set_rotation(me, pitch, yaw_deg, roll);

    // ── Splash bursts at the waterline, under the moving whale ──────
    let splash = get_entity("whale_splash");
    if splash >= 0 {
        if !splash_exit_done && y - sea > -6.0 {
            // ~6 m of rostrum above the center at launch pitch: the nose
            // pierces well before the center clears.
            splash_exit_done = true;
            set_position(splash, x, sea, z);
            emit_burst(splash, 26);
        }
        if !splash_entry_done && bt >= t_launch + air_time {
            splash_entry_done = true;
            set_position(splash, x, sea, z);
            emit_burst(splash, 90);
            // The sound arrives after the sight — ~340 m/s across the
            // distance. A one-shot spatial track caps at 25 m, so the far
            // boom plays non-spatial; distance is rendered into the asset
            // itself (breach_splash is generated pre-muffled for ~130 m —
            // see tools/generate_audio.py) with volume scaled on top.
            let dist = get_field(me, "whale", "distance");
            boom_t = dist / 340.0;
            boom_vol = clamp(35.0 / dist, 0.08, 0.5);
        }
    }
}
