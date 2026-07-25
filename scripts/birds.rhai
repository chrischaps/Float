// birds.rhai — seabirds crossing the sky, densest around dawn (M8).
//
// Flocks can pass at any hour, but the colony wakes with the sun:
// scheduling is the reality.rhai pattern (attempts on REAL seconds,
// each accepted with a probability shaped by an hour-affinity bump
// around dawn — scrub-proof by construction, no windows to enter or
// cancel). At dawn the flight line crosses the sunrise glow; off-peak
// there is no glow to cross, so the bearing spreads toward any-direction.
// Each accepted pass deals a fresh flock of min_birds..max_birds
// silhouettes in a loose trailing V, ~110 m out and 12 m up, and a
// finished crossing may chain a quick encore (encore_chance, capped by
// max_crossings) — flocks travel in waves.
//
// The "flap" is a whole-body roll oscillation with per-bird rate and
// phase — at this distance a rocking V IS a flapping bird, and the
// desynchronized rhythm is what makes the glyphs read as animals
// instead of a formation of drones. Birds are normal PBR entities
// (dark warm material), so the dawn sun and ambient light them —
// palette cohesion for free.
//
// This controller drives entities bird_0..bird_8; they park far below
// the sea when idle. Each crossing uses a random prefix of the pool.
//
// The opening title card cues one special crossing (title_pass one-shot
// from title.rhai): the full V crosses the locked camera's view
// screen-left → screen-right, closer and lower than ambient passes.

const MAX_POOL = 9;

let next_timer = -1.0;     // real seconds until the next attempt
let encore_pending = false; // next attempt is a chained encore (no roll)
let chain = 0;             // crossings flown in the current encore chain
let flying = false;
let ft = 0.0;              // real seconds into the crossing
let sx = 0.0;              // flight-line start (world)
let sz = 0.0;
let dx = 0.0;              // unit flight direction
let dz = 0.0;
let hdg = 0.0;             // heading (deg) along the flight direction
let chirp_t = 0.0;         // seconds until the next cry

// Per-flight flock, dealt at trigger time: a loose trailing V.
// along = behind the leader, side = lateral (meters).
let count = 0;
let off_along = [];
let off_side = [];
let phases = [];
let title_flight = false; // current crossing is the title-card flyby
let flight_len = 0.0;     // this crossing's line length (m), set at launch

fn park(y) {
    for i in 0..global::MAX_POOL {
        let e = get_entity("bird_" + i);
        if e >= 0 { set_position(e, 0.0, y, 0.0); }
    }
}

// Hour affinity: a smooth bump around `center`, wrapping midnight.
// PURE (Rhai scope gotcha) — same shape as reality.rhai's.
fn affinity(hours, center, width) {
    if width <= 0.0 { return 1.0; }
    let d = abs(hours - center);
    if d > 12.0 { d = 24.0 - d; }
    let c = clamp(1.0 - d / width, 0.0, 1.0);
    c * c * (3.0 - 2.0 * c)
}

fn on_update() {
    let me = this_entity();
    let dt = delta_time();
    if dt <= 0.0 { return; }

    if !get_field(me, "birds", "enabled") {
        park(-60.0);
        next_timer = -1.0;
        encore_pending = false;
        return;
    }

    let tod = get_entity("tod");
    if tod < 0 { return; }
    let hours = get_field(tod, "time_of_day", "time_hours");

    // How much this hour wants birds (1 at peak dawn, 0 far from it).
    let aff = affinity(hours,
        get_field(me, "birds", "dawn_center_h"),
        get_field(me, "birds", "dawn_width_h"));

    // Birds don't fly through rain or storm.
    let stormy = false;
    let wxe = get_entity("weather_controller");
    if wxe >= 0 {
        let ws = get_field(wxe, "weather", "state");
        if ws != () && ws > 2.5 { stormy = true; }
    }
    // ...and they sit out a dead calm — the emptiness is the point, and
    // dawn-dense flocks genuinely overlap the calm's pre-dawn tail.
    let becalmed = false;
    let dce = get_entity("dead_calm_controller");
    if dce >= 0 {
        let cf = get_field(dce, "dead_calm", "calm");
        if cf != () && cf > 0.1 { becalmed = true; }
    }

    // ── Title-card flyby: one-shot cued by title.rhai ───────────────
    // Consume-and-reset (trigger_visit pattern). Hour-blind — the card
    // is the occasion. A storm just eats the cue: no birds over rain.
    let title_launch = false;
    let tp = get_field(me, "birds", "title_pass");
    if tp != () && tp {
        set_field(me, "birds", "title_pass", false);
        if !flying && !stormy { title_launch = true; }
    }

    // ── Scheduling: attempts on real seconds, accepted by hour ──────
    let launch = title_launch;
    if !flying && !title_launch {
        if next_timer < 0.0 {
            next_timer = random_range(
                get_field(me, "birds", "min_interval_s"),
                get_field(me, "birds", "max_interval_s"));
        }
        next_timer -= dt;
        if next_timer <= 0.0 {
            // The attempt (and any pending encore) waits out weather.
            if stormy || becalmed {
                next_timer = 30.0;
            } else {
                let oc = get_field(me, "birds", "offpeak_chance");
                let p = oc + (get_field(me, "birds", "dawn_chance") - oc) * aff;
                if encore_pending || random() < p {
                    launch = true;
                    if !encore_pending { chain = 0; }
                    encore_pending = false;
                } else {
                    next_timer = -1.0;   // roll a fresh interval next frame
                }
            }
        }
    }

    if launch {
        flying = true;
        title_flight = title_launch;
        ft = 0.0;

        // Deal this crossing's flock: size, then a loose V grown pair by
        // pair with jitter so no two flocks fly the same shape. The
        // title flyby always fields the full V — it's the one crossing
        // everybody sees.
        let minb = get_field(me, "birds", "min_birds").to_float();
        let maxb = get_field(me, "birds", "max_birds").to_float();
        count = if title_launch {
            maxb.to_int()
        } else {
            random_range(minb, maxb + 0.999).to_int()
        };
        if count < 1 { count = 1; }
        if count > global::MAX_POOL { count = global::MAX_POOL; }
        off_along = [0.0];
        off_side = [0.0];
        phases = [random_range(0.0, 6.28)];
        for k in 1..count {
            let rank = ((k + 1) / 2).to_float();      // 1,1,2,2,3,3,...
            let s = if k % 2 == 1 { 1.0 } else { -1.0 };
            off_along.push(-rank * 5.3 + random_range(-1.4, 1.4));
            off_side.push(s * (rank * 4.0 + random_range(-1.2, 1.8)));
            phases.push(random_range(0.0, 6.28));
        }

        chirp_t = random_range(1.0, 3.0);

        let raft = get_entity("raft");
        let rx = 0.0;
        let rz = 0.0;
        if raft >= 0 {
            let rp = get_position(raft);
            rx = rp["x"];
            rz = rp["z"];
        }

        if title_launch {
            // Title flyby: cross the LOCKED opening camera's view,
            // screen-left → screen-right. The title gaze is raft yaw +
            // seat-outward (look_yaw rests at 0 while locked); under the
            // engine convention dir = (sin, cos) and yaw+ = screen-LEFT
            // (see seat_camera.rhai), so screen-left = (cos, -sin) and
            // the birds travel toward (-cos, sin). Length 3.4 × distance
            // keeps entry and exit just past the ~97° horizontal FOV.
            let dist = get_field(me, "birds", "title_distance");
            let outd = 0.0;
            let seat = get_entity("seat_camera");
            if seat >= 0 {
                let od = get_field(seat, "seat", "seat_out_deg");
                if od != () { outd = od; }
            }
            let ry = 0.0;
            if raft >= 0 { ry = get_rotation(raft)["y"]; }
            let th = deg_to_rad(ry + outd);
            flight_len = dist * 3.4;
            let cx = rx + sin(th) * dist;
            let cz = rz + cos(th) * dist;
            dx = -cos(th);
            dz = sin(th);
            sx = cx - dx * flight_len * 0.5;
            sz = cz - dz * flight_len * 0.5;
            hdg = rad_to_deg(atan2(dx, dz));
        } else {
            // Flight line: crosses the bearing point at right angles. At
            // dawn the bearing hugs the sunrise glow; off-peak the spread
            // opens toward any-direction (no glow to cross). Sun-azimuth
            // convention: dir = (sin, -cos) points toward the sun (see
            // time_of_day.rhai).
            let dist = get_field(me, "birds", "distance");
            flight_len = get_field(me, "birds", "crossing_length");
            let spread = get_field(me, "birds", "bearing_spread_deg")
                + (1.0 - aff) * 140.0;
            let az = deg_to_rad(get_field(me, "birds", "bearing_deg")
                + random_range(-1.0, 1.0) * spread);
            let cx = rx + sin(az) * dist;
            let cz = rz - cos(az) * dist;
            // Perpendicular to the bearing; travel direction flips randomly.
            let flip = if random() < 0.5 { 1.0 } else { -1.0 };
            dx = -cos(az) * flip;
            dz = -sin(az) * flip;
            sx = cx - dx * flight_len * 0.5;
            sz = cz - dz * flight_len * 0.5;
            hdg = rad_to_deg(atan2(dx, dz));
        }
    }

    if !flying {
        park(-60.0);
        return;
    }

    // ── The crossing ────────────────────────────────────────────────
    let speed = get_field(me, "birds", "speed");
    let height = get_field(me, "birds",
        if title_flight { "title_height" } else { "height" });
    ft += dt;

    if ft * speed > flight_len {
        flying = false;
        park(-60.0);
        chain += 1;
        // A finished crossing may chain a quick encore — another flock
        // from the same wave, minutes-of-real-time apart at most.
        let chance = get_field(me, "birds", "encore_chance");
        let maxc = get_field(me, "birds", "max_crossings");
        if chain < maxc && random() < chance {
            encore_pending = true;
            next_timer = random_range(15.0, 45.0);
        } else {
            chain = 0;
            next_timer = -1.0;   // roll a fresh interval next frame
        }
        return;
    }

    // Sparse cries drifting across — far off, so non-spatial and faint
    // (one-shot spatial tracks cap at 25 m; the flock is ~110 m out).
    // Bigger flocks cry more often.
    chirp_t -= dt;
    if chirp_t <= 0.0 {
        let dist = get_field(me, "birds",
            if title_flight { "title_distance" } else { "distance" });
        let which = if random() < 0.5 { 1 } else { 2 };
        play_sound("audio/bird_chirp_" + which + ".ogg", clamp(20.0 / dist, 0.05, 0.25));
        chirp_t = random_range(2.5, 6.5) * 5.0 / count.to_float();
    }

    let bx = sx + dx * speed * ft;
    let bz = sz + dz * speed * ft;
    let px = -dz;   // lateral (perpendicular) axis for formation offsets
    let pz = dx;
    let t = total_time();

    for i in 0..count {
        let e = get_entity("bird_" + i);
        if e < 0 { continue; }
        let x = bx + dx * off_along[i] + px * off_side[i];
        let z = bz + dz * off_along[i] + pz * off_side[i];
        let ph = phases[i];
        // Slow height swell + the flap: desynced whole-body rocking.
        let y = height + sin(t * 1.3 + ph) * 0.8;
        let flap = sin(t * (5.3 + i.to_float() * 0.45) + ph) * 17.0;
        set_position(e, x, y, z);
        set_rotation(e, 0.0, hdg, flap);
    }
}
