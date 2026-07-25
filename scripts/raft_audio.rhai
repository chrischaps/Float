// raft_audio.rhai — the water you hear is the water that touches the logs.
//
// The old version fired laps off the raft's heave acceleration — but the
// raft transform is deliberately smoothed (raft.rhai's heavy-raft inertia),
// so the signal arrived late and quiet waves never crossed the threshold.
// Now each of the four deck edges watches the UNSMOOTHED surface directly:
// a slap is the moment the water crosses the log underside moving upward
// (a zero-crossing — framerate independent), and its intensity is the
// relative approach speed, ocean_velocity_y minus the edge's own motion.
// Intensity picks the asset tier (lap/soft → med → hard), the volume, the
// pitch, and how soon that edge may speak again. Big slaps leave drips.
//
// Crest passage is the mirror pair, and it gets its own two voices:
// a BREACH when the surface drops out from under an edge (the downward
// zero-crossing — water sheeting off the logs, runoff_*), which ARMS the
// edge; and a LAND when the water regains the logs inside the window.
// The land matters because the raft's smoothed heave settles onto the
// receding back face nearly at the water's own speed — v_rel almost
// never clears v_min there, so without the armed low threshold the
// whole crest→back-face arc played silent (settle_*).
//
// Legs get their own channel: when the water reaches shin height at the
// seat point (raft-local seat_x/seat_z from seat_camera — set_field is
// deferred, so guard against unset), a small bright splash lands there.
//
// Rotation convention (raft.rhai): Euler DEGREES ZYX; rotation.x positive
// tilts +Z (bow) down, rotation.z positive lifts +X (starboard).

let prev_ey = [0.0, 0.0, 0.0, 0.0];   // per-edge deck underside height
let prev_gap = [0.0, 0.0, 0.0, 0.0];  // per-edge water-above-underside
let refr = [0.0, 0.0, 0.0, 0.0];      // per-edge refractory timers
let breach_refr = [0.0, 0.0, 0.0, 0.0]; // per-edge runoff refractories
let airborne = [-1.0, -1.0, -1.0, -1.0]; // land window after a breach (<0 = unarmed)
let drip_t = [-1.0, -1.0, -1.0, -1.0]; // pending drip countdowns (<0 = free)
let drip_x = [0.0, 0.0, 0.0, 0.0];
let drip_z = [0.0, 0.0, 0.0, 0.0];
let drip_v = [0.0, 0.0, 0.0, 0.0];
let prev_roll = 0.0;
let prev_ley = 0.0;
let prev_leg_gap = 0.0;
let leg_seen = false;
let leg_refr = 0.0;
let creak_cooldown = 0.0;
let voices = 0.0;
let rng = 0;
let initialized = false;
let warmup = 0.0;   // silent settle window after init (see below)

fn on_update() {
    let dt = delta_time();
    if dt <= 0.0 { return; }

    let me = this_entity();
    let raft = get_entity("raft");
    if raft < 0 { return; }

    let rp = get_position(raft);
    let rr = get_rotation(raft);

    // ── Tuning ──────────────────────────────────────────────────────
    let underside_y = get_field(me, "raft_audio", "underside_y");
    let v_min = get_field(me, "raft_audio", "v_min");
    let v_ref = get_field(me, "raft_audio", "v_ref");
    let soft_max = get_field(me, "raft_audio", "soft_max");
    let med_max = get_field(me, "raft_audio", "med_max");
    let base_vol = get_field(me, "raft_audio", "base_vol");
    let vol_gain = get_field(me, "raft_audio", "vol_gain");
    let refr_min = get_field(me, "raft_audio", "refractory_min");
    let refr_max = get_field(me, "raft_audio", "refractory_max");
    let max_voices = get_field(me, "raft_audio", "max_voices");
    let breach_v_min = get_field(me, "raft_audio", "breach_v_min");
    let breach_vol = get_field(me, "raft_audio", "breach_vol");
    let breach_vol_gain = get_field(me, "raft_audio", "breach_vol_gain");
    let breach_refractory = get_field(me, "raft_audio", "breach_refractory");
    let land_window = get_field(me, "raft_audio", "land_window");
    let land_v_min = get_field(me, "raft_audio", "land_v_min");
    let settle_vol = get_field(me, "raft_audio", "settle_vol");
    let leg_shin_y = get_field(me, "raft_audio", "leg_shin_y");
    let leg_v_min = get_field(me, "raft_audio", "leg_v_min");
    let leg_refractory = get_field(me, "raft_audio", "leg_refractory");
    let creak_threshold = get_field(me, "raft_audio", "creak_threshold");
    let creak_cd_min = get_field(me, "raft_audio", "creak_cd_min");
    let creak_cd_max = get_field(me, "raft_audio", "creak_cd_max");
    let dbg = get_field(me, "raft_audio", "debug_log");

    let hx = get_field(raft, "ocean_contact", "half_x");
    let hz = get_field(raft, "ocean_contact", "half_z");

    // ── Edge geometry in the raft's yawed frame ─────────────────────
    let yaw = deg_to_rad(rr["y"]);
    let fwd_x = sin(yaw);
    let fwd_z = cos(yaw);
    let right_x = cos(yaw);
    let right_z = -sin(yaw);
    let pr = deg_to_rad(rr["x"]);
    let rl = deg_to_rad(rr["z"]);
    let tan_p = sin(pr) / cos(pr);
    let tan_r = sin(rl) / cos(rl);

    // 0 front (+fwd), 1 back, 2 right (+right / starboard), 3 left
    let ex = [rp["x"] + fwd_x * hz, rp["x"] - fwd_x * hz,
              rp["x"] + right_x * hx, rp["x"] - right_x * hx];
    let ez = [rp["z"] + fwd_z * hz, rp["z"] - fwd_z * hz,
              rp["z"] + right_z * hx, rp["z"] - right_z * hx];
    let ey = [rp["y"] - tan_p * hz + underside_y,
              rp["y"] + tan_p * hz + underside_y,
              rp["y"] + tan_r * hx + underside_y,
              rp["y"] - tan_r * hx + underside_y];

    if !initialized {
        for e in 0..4 {
            prev_ey[e] = ey[e];
            prev_gap[e] = ocean_height(ex[e], ez[e]) - ey[e];
        }
        prev_roll = rr["z"];
        rng = (total_time() * 1000003.0).to_int() % 2147483647;
        if rng < 0 { rng = -rng; }
        if rng == 0 { rng = 12345; }
        initialized = true;
        // raft.rhai's first update snaps the raft from its spawn pose onto
        // the water (set_position is deferred, script order is a HashMap),
        // so our captured prev state is pre-snap: the next frame reads a
        // one-frame deck jump as ~25 m/s and slaps all four edges at max
        // intensity at once. Track silently until the buoyancy smoothing
        // transient (heave + pitch/roll easing from zero) has settled.
        warmup = 1.5;
        return;
    }

    if warmup > 0.0 {
        warmup -= dt;
        for e in 0..4 {
            prev_ey[e] = ey[e];
            prev_gap[e] = ocean_height(ex[e], ez[e]) - ey[e];
        }
        prev_roll = rr["z"];
        return;
    }

    voices = max(voices - dt / 1.2, 0.0);   // ~mean one-shot length

    // ── Edge slaps: water crossing the log underside, moving up ─────
    for e in 0..4 {
        refr[e] = max(refr[e] - dt, 0.0);
        breach_refr[e] = max(breach_refr[e] - dt, 0.0);
        if airborne[e] >= 0.0 { airborne[e] -= dt; }

        let h = ocean_height(ex[e], ez[e]);
        let w_vy = ocean_velocity_y(ex[e], ez[e]);
        let deck_vy = (ey[e] - prev_ey[e]) / dt;
        let gap = h - ey[e];
        let v_rel = w_vy - deck_vy;   // + = water approaching the deck

        // ── Crest breach: the surface drops out from under the logs ─
        if prev_gap[e] >= 0.0 && gap < 0.0 && -v_rel > breach_v_min {
            airborne[e] = land_window;   // the physical event arms the land
            if breach_refr[e] <= 0.0 && voices < max_voices {
                rng = (rng * 1103515245 + 12345) % 2147483648;
                let r_var = rng.to_float() / 2147483648.0;
                rng = (rng * 1103515245 + 12345) % 2147483648;
                let r_pitch = rng.to_float() / 2147483648.0;

                let ib = clamp((-v_rel - breach_v_min) / (v_ref - breach_v_min), 0.0, 1.0);
                let which = 1 + (r_var * 2.999).to_int();
                let vol = clamp(breach_vol + breach_vol_gain * ib, 0.0, 0.6);
                // the sound is water leaving the wood — play at the logs
                play_sound_at("audio/runoff_" + which + ".ogg",
                              ex[e], ey[e], ez[e], vol,
                              1.0 + (r_pitch * 2.0 - 1.0) * 0.1);
                voices += 1.0;
                breach_refr[e] = breach_refractory;

                // a hard breach keeps trickling after the rush
                if ib > 0.5 {
                    rng = (rng * 1103515245 + 12345) % 2147483648;
                    let r_d = rng.to_float() / 2147483648.0;
                    for s in 0..4 {
                        if drip_t[s] < 0.0 {
                            drip_t[s] = 0.5 + r_d * 0.5;
                            drip_x[s] = ex[e];
                            drip_z[s] = ez[e];
                            drip_v[s] = 0.08 + 0.10 * ib;
                            break;
                        }
                    }
                }

                if dbg {
                    print("breach edge=" + e + " I=" + ib + " v_rel=" + v_rel);
                }
            }
        }

        if prev_gap[e] < 0.0 && gap >= 0.0 && v_rel > v_min && refr[e] <= 0.0 {
            airborne[e] = -1.0;   // a full slap IS the landing
            let i = clamp((v_rel - v_min) / (v_ref - v_min), 0.0, 1.0);
            let big = i >= med_max;

            if big || voices < max_voices {
                rng = (rng * 1103515245 + 12345) % 2147483648;
                let r_var = rng.to_float() / 2147483648.0;
                rng = (rng * 1103515245 + 12345) % 2147483648;
                let r_pitch = rng.to_float() / 2147483648.0;

                let asset = "";
                let tier = "";
                if i < soft_max {
                    // calm seas keep the old lap voice, sweetened
                    let idx = (r_var * 6.999).to_int();
                    if idx < 4 { asset = "audio/lap_" + (idx + 1) + ".ogg"; }
                    else { asset = "audio/splash_soft_" + (idx - 3) + ".ogg"; }
                    tier = "soft";
                } else if i < med_max {
                    asset = "audio/splash_med_" + (1 + (r_var * 2.999).to_int()) + ".ogg";
                    tier = "med";
                } else {
                    asset = "audio/splash_hard_" + (1 + (r_var * 1.999).to_int()) + ".ogg";
                    tier = "hard";
                }

                let vol = clamp(base_vol + vol_gain * i, 0.0, 0.85);
                let pitch = 1.0 + (r_pitch * 2.0 - 1.0) * 0.12 - 0.05 * i;
                play_sound_at(asset, ex[e], h, ez[e], vol, pitch);
                voices += 1.0;
                refr[e] = refr_max + (refr_min - refr_max) * i;

                // big slaps leave water running off the logs
                if tier != "soft" {
                    rng = (rng * 1103515245 + 12345) % 2147483648;
                    let r_d = rng.to_float() / 2147483648.0;
                    for s in 0..4 {
                        if drip_t[s] < 0.0 {
                            drip_t[s] = 0.4 + r_d * 0.5;
                            drip_x[s] = ex[e];
                            drip_z[s] = ez[e];
                            drip_v[s] = 0.10 + 0.12 * i;
                            break;
                        }
                    }
                }

                if dbg {
                    print("slap edge=" + e + " I=" + i + " v_rel=" + v_rel + " tier=" + tier);
                }
            }
        }

        // ── Armed land: after a breach the smoothed deck settles onto
        //    the receding back face too gently for the slap threshold —
        //    but the breach promised this sound ─────────────────────────
        if prev_gap[e] < 0.0 && gap >= 0.0 && v_rel <= v_min && airborne[e] >= 0.0 {
            if v_rel > land_v_min && refr[e] <= 0.0 && voices < max_voices {
                rng = (rng * 1103515245 + 12345) % 2147483648;
                let r_var = rng.to_float() / 2147483648.0;
                rng = (rng * 1103515245 + 12345) % 2147483648;
                let r_pitch = rng.to_float() / 2147483648.0;

                let il = clamp((v_rel - land_v_min) / (v_min - land_v_min), 0.0, 1.0);
                let which = 1 + (r_var * 2.999).to_int();
                play_sound_at("audio/settle_" + which + ".ogg",
                              ex[e], h, ez[e],
                              settle_vol * (0.5 + 0.5 * il),
                              0.95 + (r_pitch * 2.0 - 1.0) * 0.08);
                voices += 1.0;
                refr[e] = refr_max;

                if dbg {
                    print("settle edge=" + e + " I=" + il + " v_rel=" + v_rel);
                }
            }
            airborne[e] = -1.0;   // any re-contact consumes the window
        }

        prev_ey[e] = ey[e];
        prev_gap[e] = gap;
    }

    // ── Pending drips ───────────────────────────────────────────────
    for s in 0..4 {
        if drip_t[s] >= 0.0 {
            drip_t[s] -= dt;
            if drip_t[s] < 0.0 {
                rng = (rng * 1103515245 + 12345) % 2147483648;
                let r_v = rng.to_float() / 2147483648.0;
                rng = (rng * 1103515245 + 12345) % 2147483648;
                let r_p = rng.to_float() / 2147483648.0;
                let which = 1 + (r_v * 3.999).to_int();
                play_sound_at("audio/drip_" + which + ".ogg",
                              drip_x[s], rp["y"], drip_z[s],
                              drip_v[s], 0.95 + r_p * 0.2);
                drip_t[s] = -1.0;
            }
        }
    }

    // ── Leg splashes: water reaching the shins at the seat point ────
    leg_refr = max(leg_refr - dt, 0.0);
    let seat = get_entity("seat_camera");
    if seat >= 0 {
        let sx = get_field(seat, "seat", "seat_x");
        let sz = get_field(seat, "seat", "seat_z");
        if sx != () && sz != () {
            // raft-local seat point through the raft rotation (R = Rz·Ry·Rx),
            // same composition body.rhai uses.
            let ax = deg_to_rad(rr["x"]);
            let az = deg_to_rad(rr["z"]);
            let sxr = sin(ax); let cxr = cos(ax);
            let syr = sin(yaw); let cyr = cos(yaw);
            let szr = sin(az); let czr = cos(az);
            let px = rp["x"] + (cyr * czr) * sx + (cxr * syr * czr + sxr * szr) * sz;
            let py = rp["y"] + (cyr * szr) * sx + (cxr * syr * szr - sxr * czr) * sz;
            let pz = rp["z"] + (-syr) * sx + (cxr * cyr) * sz;

            let ley = py + leg_shin_y;
            let h = ocean_height(px, pz);
            let w_vy = ocean_velocity_y(px, pz);
            let gap = h - ley;

            if leg_seen {
                let v_rel = w_vy - (ley - prev_ley) / dt;
                if prev_leg_gap < 0.0 && gap >= 0.0 && v_rel > leg_v_min && leg_refr <= 0.0 {
                    let i = clamp((v_rel - leg_v_min) / (v_ref - leg_v_min), 0.0, 1.0);
                    rng = (rng * 1103515245 + 12345) % 2147483648;
                    let r_v = rng.to_float() / 2147483648.0;
                    rng = (rng * 1103515245 + 12345) % 2147483648;
                    let r_p = rng.to_float() / 2147483648.0;
                    let which = 1 + (r_v * 2.999).to_int();
                    play_sound_at("audio/leg_splash_" + which + ".ogg",
                                  px, h, pz, 0.15 + 0.3 * i, 1.0 + r_p * 0.25);
                    leg_refr = leg_refractory;
                    if dbg { print("leg splash I=" + i + " v_rel=" + v_rel); }
                }
            }
            prev_ley = ley;
            prev_leg_gap = gap;
            leg_seen = true;
        }
    }

    // ── Creaks: the lashings complain when the deck rolls fast ──────
    creak_cooldown -= dt;
    let roll_vel = (rr["z"] - prev_roll) / dt;
    prev_roll = rr["z"];
    if creak_cooldown <= 0.0 && abs(roll_vel) > creak_threshold {
        rng = (rng * 1103515245 + 12345) % 2147483648;
        let r_v = rng.to_float() / 2147483648.0;
        rng = (rng * 1103515245 + 12345) % 2147483648;
        let r_p = rng.to_float() / 2147483648.0;
        rng = (rng * 1103515245 + 12345) % 2147483648;
        let r_c = rng.to_float() / 2147483648.0;
        let which = 1 + (r_v * 2.999).to_int();
        let vol = 0.18 + 0.3 * clamp(abs(roll_vel) / 10.0, 0.0, 1.0);
        play_sound_at("audio/creak_" + which + ".ogg",
                      rp["x"], rp["y"] + 0.2, rp["z"], vol, 0.92 + r_p * 0.16);
        creak_cooldown = creak_cd_min + (creak_cd_max - creak_cd_min) * r_c;
    }
}
