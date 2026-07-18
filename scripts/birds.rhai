// birds.rhai — dawn seabirds crossing the sunrise (M8).
//
// Once per dawn (encore_chance for a second pass), five silhouettes in a
// loose trailing V cross the sunrise glow, ~110 m out and 12 m up. Same
// scheduling pattern as whale.rhai: time_hours from the tod entity picks
// the moment, F3 scrubbing schedules/cancels, the crossing itself runs
// on real seconds.
//
// The "flap" is a whole-body roll oscillation with per-bird rate and
// phase — at this distance a rocking V IS a flapping bird, and the
// desynchronized rhythm is what makes five glyphs read as animals
// instead of a formation of drones. Birds are normal PBR entities
// (dark warm material), so the dawn sun and ambient light them —
// palette cohesion for free.
//
// This controller drives entities bird_0..bird_4; they park far below
// the sea when idle.

let scheduled = -1.0;
let was_in_window = false;
let encore_used = false;
let flying = false;
let ft = 0.0;              // real seconds into the crossing
let sx = 0.0;              // flight-line start (world)
let sz = 0.0;
let dx = 0.0;              // unit flight direction
let dz = 0.0;
let hdg = 0.0;             // heading (deg) along the flight direction

// Loose trailing V (meters): along = behind the leader, side = lateral.
const OFF_ALONG = [0.0, -5.0, -5.8, -10.6, -11.6];
const OFF_SIDE  = [0.0,  4.2, -3.8,  8.2,  -7.6];
const PHASES    = [0.0,  1.7,  3.1,  4.6,   5.9];

fn park(y) {
    for i in 0..5 {
        let e = get_entity("bird_" + i);
        if e >= 0 { set_position(e, 0.0, y, 0.0); }
    }
}

fn on_update() {
    let me = this_entity();
    let dt = delta_time();
    if dt <= 0.0 { return; }

    if !get_field(me, "birds", "enabled") {
        park(-60.0);
        return;
    }

    let tod = get_entity("tod");
    if tod < 0 { return; }
    let hours = get_field(tod, "time_of_day", "time_hours");

    let w0 = get_field(me, "birds", "window_start");
    let w1 = get_field(me, "birds", "window_end");
    let in_window = hours >= w0 && hours <= w1;

    if in_window && !was_in_window {
        scheduled = w0 + (w1 - w0) * random_range(0.1, 0.5);
        encore_used = false;
    }
    if !in_window { scheduled = -1.0; }
    was_in_window = in_window;

    if !flying && scheduled > 0.0 && hours >= scheduled {
        scheduled = -1.0;
        flying = true;
        ft = 0.0;

        // Flight line: crosses the bearing point at right angles, so the
        // flock traverses the sunrise glow. Sun-azimuth convention:
        // dir = (sin, -cos) points toward the sun (see time_of_day.rhai).
        let dist = get_field(me, "birds", "distance");
        let len = get_field(me, "birds", "crossing_length");
        let az = deg_to_rad(get_field(me, "birds", "bearing_deg")
            + random_range(-1.0, 1.0) * get_field(me, "birds", "bearing_spread_deg"));
        let raft = get_entity("raft");
        let rx = 0.0;
        let rz = 0.0;
        if raft >= 0 {
            let rp = get_position(raft);
            rx = rp["x"];
            rz = rp["z"];
        }
        let cx = rx + sin(az) * dist;
        let cz = rz - cos(az) * dist;
        // Perpendicular to the bearing; direction of travel flips randomly.
        let flip = if random() < 0.5 { 1.0 } else { -1.0 };
        dx = -cos(az) * flip;
        dz = -sin(az) * flip;
        sx = cx - dx * len * 0.5;
        sz = cz - dz * len * 0.5;
        hdg = rad_to_deg(atan2(dx, dz));
    }

    if !flying {
        park(-60.0);
        return;
    }

    // ── The crossing ────────────────────────────────────────────────
    let speed = get_field(me, "birds", "speed");
    let len = get_field(me, "birds", "crossing_length");
    let height = get_field(me, "birds", "height");
    ft += dt;

    if ft * speed > len {
        flying = false;
        park(-60.0);
        let chance = get_field(me, "birds", "encore_chance");
        if !encore_used && in_window && (w1 - hours) > 0.2 && random() < chance {
            scheduled = hours + (w1 - 0.1 - hours) * random_range(0.3, 0.8);
            encore_used = true;
        }
        return;
    }

    let bx = sx + dx * speed * ft;
    let bz = sz + dz * speed * ft;
    let px = -dz;   // lateral (perpendicular) axis for formation offsets
    let pz = dx;
    let t = total_time();

    let along = global::OFF_ALONG;
    let side = global::OFF_SIDE;
    let phases = global::PHASES;
    for i in 0..5 {
        let e = get_entity("bird_" + i);
        if e < 0 { continue; }
        let x = bx + dx * along[i] + px * side[i];
        let z = bz + dz * along[i] + pz * side[i];
        let ph = phases[i];
        // Slow height swell + the flap: desynced whole-body rocking.
        let y = height + sin(t * 1.3 + ph) * 0.8;
        let flap = sin(t * (5.3 + i.to_float() * 0.45) + ph) * 17.0;
        set_position(e, x, y, z);
        set_rotation(e, 0.0, hdg, flap);
    }
}
