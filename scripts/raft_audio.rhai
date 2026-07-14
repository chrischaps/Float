// raft_audio.rhai — the water you hear is the water the deck rides.
//
// Laps fire when the raft's heave velocity spikes (the deck slapping into
// a swell), weighted by local wave steepness; creaks fire on roll-velocity
// spikes (the lashings working). Both read the same ocean/raft state the
// physics uses, so the soundscape tracks the sea state automatically —
// crank choppiness in the F3 panel and the audio follows.

let prev_y = 0.0;
let prev_roll = 0.0;
let prev_vy = 0.0;
let lap_cooldown = 0.0;
let creak_cooldown = 0.0;
let initialized = false;

fn on_update() {
    let dt = delta_time();
    if dt <= 0.0 { return; }

    let raft = get_entity("raft");
    if raft < 0 { return; }

    let rp = get_position(raft);
    let rr = get_rotation(raft);

    if !initialized {
        prev_y = rp["y"];
        prev_roll = rr["z"];
        initialized = true;
        return;
    }

    let vy = (rp["y"] - prev_y) / dt;          // heave velocity (m/s)
    let roll_vel = (rr["z"] - prev_roll) / dt; // roll velocity (deg/s)
    let accel_y = (vy - prev_vy) / dt;         // heave acceleration
    prev_y = rp["y"];
    prev_roll = rr["z"];
    prev_vy = vy;

    lap_cooldown -= dt;
    creak_cooldown -= dt;

    // ── Wave laps: deck decelerating hard against the water ─────────
    if lap_cooldown <= 0.0 && abs(accel_y) > 1.1 {
        // Louder when the local surface is steeper (normal tilted).
        let n = ocean_normal(rp["x"], rp["z"]);
        let steep = clamp((1.0 - n["y"]) * 12.0, 0.2, 1.0);
        let which = 1 + (random_range(0.0, 3.999)).to_int();
        let vol = 0.25 + 0.5 * clamp(abs(accel_y) / 4.0, 0.0, 1.0) * steep;
        play_sound_at("audio/lap_" + which + ".ogg", rp["x"], rp["y"], rp["z"] + 1.2, vol);
        lap_cooldown = random_range(0.9, 1.8);
    }

    // ── Creaks: the lashings complain when the deck rolls fast ──────
    if creak_cooldown <= 0.0 && abs(roll_vel) > 3.2 {
        let which = 1 + (random_range(0.0, 2.999)).to_int();
        let vol = 0.18 + 0.3 * clamp(abs(roll_vel) / 10.0, 0.0, 1.0);
        play_sound_at("audio/creak_" + which + ".ogg", rp["x"], rp["y"] + 0.2, rp["z"], vol);
        creak_cooldown = random_range(2.5, 6.0);
    }
}
