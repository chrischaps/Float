// weather.rhai — the sky decides, the wind answers, the sea remembers.
//
// One continuous state value (0 CLEAR, 1 SCATTERED, 2 OVERCAST, 3 RAIN,
// 4 STORM) drives everything, TOD-style: natural drift, debug forcing,
// and scrubbing share one smoothly-lerped code path — no discrete pops.
// A Markov machine walks adjacent states on real seconds (deliberately
// independent of game hours: storms happen when they happen), with long
// calm dwells and rare storms.
//
// Physical lag is a three-speed cascade, the heart of the system:
//     state target  (the sky changes its mind, ~transition_s)
//   → s_wind        (the wind chases the sky, tau ~20 s, gusty)
//   → s_sea         (the swell chases the wind: builds in ~2 min,
//                    dies in ~4 — the dying swell outlives the storm)
// Choppiness follows s_wind (new wind roughens the surface immediately);
// amplitude / wind_speed / fetch_km follow s_sea (the accumulated
// spectrum takes minutes to build and to fade). Only phase-safe ocean
// fields are ever ramped (amplitude, choppiness, wind_speed, fetch_km):
// the spectrum regenerates with phases preserved, so the sea swells and
// calms without a single visual pop. direction/speed/seed/wavelengths
// are load-time only.
//
// The raft's deliberate heavy inertia (heave_response ~3/s) would dig
// ~1.2 m into storm faces and drown the eye, so heave/angular response
// scale up with sea energy (raft_assist) — dramatic wash-overs, camera
// above water. Calm-sea feel untouched.
//
// Light/fog composition: script update order is NOT deterministic (the
// engine iterates a HashMap), so weather never read-modify-writes what
// TOD wrote. Instead it OWNS the sky fields TOD never touches (cloud
// coverage/density/scale/drift, sun_glow, ocean foam_threshold) and
// PUBLISHES multiplier factors (sun_scale, amb_scale, star_scale,
// tint_mul/alpha, ocean_dark, fog_mul/gray, flash) that time_of_day.rhai
// applies when it writes the sun, sky, fog, and ocean palette. One frame
// of staleness at most — invisible at weather timescales.

// ── Per-state targets (rows: CLEAR, SCATTERED, OVERCAST, RAIN, STORM) ──
const WIND_T = [2.5, 4.0, 7.0, 12.0, 24.0];   // mean wind m/s
const AMP_T  = [1.1, 2.0, 2.8, 3.6, 5.5];     // ocean.amplitude ([4] → amp_storm)
const CHOP_T = [0.55, 0.82, 0.88, 0.92, 0.97]; // ocean.choppiness
const FETCH_T = [60.0, 60.0, 80.0, 120.0, 300.0]; // ocean.fetch_km
const FOAM_T = [0.86, 0.815, 0.79, 0.76, 0.70];   // foam_threshold (whitecaps)
const RAIN01 = [0.0, 0.0, 0.0, 0.45, 1.0];        // rain intensity fraction

// ── Sky/light rows (applied via published factors — see note below) ──
const CLOUD_COV = [0.12, 0.38, 0.75, 0.90, 0.98];
const CLOUD_DEN = [0.12, 0.22, 0.40, 0.50, 0.62];
const CLOUD_SCL = [1.1, 0.9, 0.8, 0.75, 0.7];
const SUN_S  = [1.0, 1.0, 0.55, 0.35, 0.18];  // × TOD sun intensity
const AMB_S  = [1.0, 1.0, 0.75, 0.60, 0.45];  // × TOD hemisphere ambient
const STAR_S = [1.0, 0.85, 0.2, 0.05, 0.0];   // × TOD star opacity
const TINT_M = [1.0, 1.0, 0.55, 0.30, 0.10];  // × TOD cloud_tint rgb (linear!)
const TINT_A = [0.0, 0.0, 0.9, 0.95, 1.0];    // cloud_tint alpha floor
const OC_DARK = [1.0, 1.0, 0.7, 0.5, 0.35];   // × TOD ocean palette (linear!)
const FOG_M  = [1.0, 1.0, 1.5, 2.2, 3.5];     // × TOD fog density
const FOG_G  = [0.0, 0.0, 0.3, 0.5, 0.7];     // fog → storm gray
const GLOW_S = [1.0, 1.0, 0.5, 0.3, 0.15];    // × baseline sun_glow

// ── Markov drift: dwell ranges (real seconds) and adjacent-step odds ──
const DWELL_MIN = [240.0, 180.0, 120.0, 120.0, 90.0];
const DWELL_MAX = [600.0, 480.0, 360.0, 300.0, 180.0];
const P_DOWN = [0.0, 0.35, 0.45, 0.50, 1.0];  // toward clear
const P_UP   = [0.5, 0.30, 0.30, 0.25, 0.0];  // toward storm

// ── Cascade state ──────────────────────────────────────────────────────
let s_now = -1.0;      // published continuous state (<0 = adopt on first frame)
let s_wind = 0.0;      // wind-lagged state
let s_sea = 0.0;       // sea-lagged state (the swell's memory)
let target_i = 1;      // Markov target (int, for tables)
let target_f = 1.0;    // same value as float (avoids int→float casts)
let dwell = 30.0;      // seconds left at the current target
let base_heave = -1.0; // raft's calm-sea response, captured once
let base_ang = -1.0;
let base_drift_x = 0.0; // sky baselines, captured once
let base_drift_y = 0.0;
let base_glow = 1.0;
let sky_base_ok = false;
let wind_dir_x = 0.0;   // wind bearing = the ocean's wave bearing, once
let wind_dir_z = 1.0;
let wind_dir_ok = false;
let cur_rain_vol = 0.0; // slewed bed volumes
let cur_howl_vol = 0.0;
let next_strike = -1.0; // seconds to the next lightning strike (-1 = idle)
let flash_t = -1.0;     // seconds into the current flash (-1 = none)
let flash_dur = 0.6;
let flash_amp = 1.0;    // exposure punch (near strikes hit harder)
let flash_p2 = 0.32;    // flicker pulse centers (fractions of flash_dur)
let flash_p3 = 0.65;
let booms_t = [];       // pending thunder: countdowns, volumes, files
let booms_vol = [];
let booms_snd = [];
let last_flash = 0.0;

// ── Write guards (only touch components when a value actually moved) ──
let last_amp = -1.0;
let last_chop = -1.0;
let last_wspd = -1.0;
let last_fetch = -1.0;
let last_foam = -1.0;
let last_heave = -1.0;
let last_state = -1.0;
let last_wind_pub = -1.0;
let last_sea_pub = -1.0;
let last_cov = -1.0;
let last_den = -1.0;
let last_scl = -1.0;
let last_drift = -1.0;
let last_glow = -1.0;
let last_sun_s = -1.0;
let last_amb_s = -1.0;
let last_star_s = -1.0;
let last_tint_m = -1.0;
let last_tint_a = -1.0;
let last_oc_dark = -1.0;
let last_fog_m = -1.0;
let last_fog_g = -1.0;
let last_rate = -1.0;
let last_grav = -1.0;
let last_ripple = -1.0;
let last_bright = -1.0;
let last_rain_vol = -1.0;
let last_howl_vol = -1.0;
let dbg_timer = 0.0;

// Lerp a 5-row channel at continuous state s (0..4).
fn wx(arr, s) {
    let c = clamp(s, 0.0, 4.0);
    let i0 = 0;
    let f0 = 0.0;
    if c >= 1.0 { i0 = 1; f0 = 1.0; }
    if c >= 2.0 { i0 = 2; f0 = 2.0; }
    if c >= 3.0 { i0 = 3; f0 = 3.0; }
    let t = clamp(c - f0, 0.0, 1.0);
    arr[i0] + (arr[i0 + 1] - arr[i0]) * t
}

// First-order relaxation toward a target (frame-rate safe for tau >> dt).
fn relax(cur, target, dt, tau) {
    if tau < 0.05 { tau = 0.05; }
    cur + (target - cur) * clamp(dt / tau, 0.0, 1.0)
}

// Move cur toward target by at most step, without overshooting.
fn toward(cur, target, step) {
    let d = clamp(target - cur, -step, step);
    cur + d
}

// A soft bump centered at c with half-width w (quadratic, no exp needed).
fn bump(u, c, w) {
    let d = (u - c) / w;
    clamp(1.0 - d * d, 0.0, 1.0)
}

fn on_update() {
    let me = this_entity();
    let dt = delta_time();
    if dt <= 0.0 { return; }

    // ── Pending thunder: booms land after the light, dist/340 s later.
    // Runs before any early return so queued sound always arrives.
    let bi = 0;
    while bi < booms_t.len() {
        booms_t[bi] -= dt;
        if booms_t[bi] <= 0.0 {
            play_sound(booms_snd[bi], booms_vol[bi]);
            booms_t.remove(bi);
            booms_vol.remove(bi);
            booms_snd.remove(bi);
        } else {
            bi += 1;
        }
    }

    let enabled = get_field(me, "weather", "enabled");
    if enabled == () { return; }        // component not ready (first frames)
    if !enabled { return; }             // stood down: the ocean is hand-tunable

    // ── Adopt the scene's starting state on the first live frame ───────
    if s_now < 0.0 {
        let s0 = get_field(me, "weather", "state");
        if s0 == () { return; }
        s_now = clamp(s0, 0.0, 4.0);
        s_wind = s_now;
        s_sea = s_now;
        target_f = s_now;
        target_i = 0;
        if s_now >= 0.5 { target_i = 1; target_f = 1.0; }
        if s_now >= 1.5 { target_i = 2; target_f = 2.0; }
        if s_now >= 2.5 { target_i = 3; target_f = 3.0; }
        if s_now >= 3.5 { target_i = 4; target_f = 4.0; }
        dwell = random_range(global::DWELL_MIN[target_i], global::DWELL_MAX[target_i]);
    }

    let transition_s = get_field(me, "weather", "transition_s");
    let wind_tau = get_field(me, "weather", "wind_tau_s");
    let build_tau = get_field(me, "weather", "sea_build_tau_s");
    let decay_tau = get_field(me, "weather", "sea_decay_tau_s");
    let gust_str = get_field(me, "weather", "gust_strength");
    let amp_storm = get_field(me, "weather", "amp_storm");
    let raft_assist = get_field(me, "weather", "raft_assist");
    if transition_s < 1.0 { transition_s = 1.0; }

    // ── Markov drift / forcing ─────────────────────────────────────────
    let forced = get_field(me, "weather", "forced_state");
    if forced == () { forced = -1.0; }

    if forced >= -0.5 {
        // Forced: freeze the machine, ease toward the forced value.
        target_f = clamp(forced, 0.0, 4.0);
    } else {
        // Auto: dwell at the target, then step to an adjacent state.
        // (If we were just released from forcing, re-anchor the machine
        // to wherever the sky currently is.)
        let drift_err = target_f - s_now;
        if drift_err > 1.5 || drift_err < -1.5 {
            target_i = 0;
            target_f = 0.0;
            if s_now >= 0.5 { target_i = 1; target_f = 1.0; }
            if s_now >= 1.5 { target_i = 2; target_f = 2.0; }
            if s_now >= 2.5 { target_i = 3; target_f = 3.0; }
            if s_now >= 3.5 { target_i = 4; target_f = 4.0; }
            dwell = random_range(global::DWELL_MIN[target_i], global::DWELL_MAX[target_i]);
        }
        let arrived = abs(s_now - target_f) < 0.05;
        if arrived {
            dwell -= dt;
            if dwell <= 0.0 {
                let pd = global::P_DOWN[target_i];
                let pu = global::P_UP[target_i];
                let r = random();
                if r < pd && target_i > 0 {
                    target_i -= 1;
                    target_f -= 1.0;
                } else if r < pd + pu && target_i < 4 {
                    target_i += 1;
                    target_f += 1.0;
                }
                dwell = random_range(global::DWELL_MIN[target_i], global::DWELL_MAX[target_i]);
            }
        }
    }

    // ── The cascade ────────────────────────────────────────────────────
    // Sky: constant-rate slew (one state step per transition_s).
    let step = dt / transition_s;
    let d = clamp(target_f - s_now, -step, step);
    s_now += d;

    // Wind chases the sky; the sea chases the wind, asymmetrically.
    s_wind = relax(s_wind, s_now, dt, wind_tau);
    let sea_tau = decay_tau;
    if s_wind > s_sea { sea_tau = build_tau; }
    s_sea = relax(s_sea, s_wind, dt, sea_tau);

    // Snap (panel one-shot): everything jumps to the target at once.
    let snap = get_field(me, "weather", "snap");
    if snap == true {
        s_now = target_f;
        s_wind = target_f;
        s_sea = target_f;
        set_field(me, "weather", "snap", false);
    }

    // ── Wind with gusts (three incommensurate sines; gustier in storms)
    let wind_mean = wx(global::WIND_T, s_wind);

    // Dead calm: dead_calm.rhai owns the envelope and publishes factors;
    // WE own the writes (the published-factor pattern, applied at the
    // writer's own sites — same as TOD applying our sun/fog factors).
    // wind_mean scaling flows into the gusts, the published wind, cloud
    // drift and the howl target downstream; sea_scale hits amplitude only,
    // so the spectrum keeps its shape, collapsed to a faint breath.
    let sea_scale = 1.0;
    let dce = get_entity("dead_calm_controller");
    if dce >= 0 {
        let ss = get_field(dce, "dead_calm", "sea_scale");
        if ss != () && ss > 0.0 { sea_scale = ss; }
        let ws2 = get_field(dce, "dead_calm", "wind_scale");
        if ws2 != () && ws2 > 0.0 { wind_mean *= ws2; }
    }

    let tt = total_time();
    let g = sin(tt * 0.9) * 0.55 + sin(tt * 2.17 + 1.3) * 0.30
          + sin(tt * 4.31 + 0.7) * 0.15;
    let gust_depth = gust_str * (0.3 + 0.7 * s_wind * 0.25);
    let wind = wind_mean * (1.0 + gust_depth * g);
    let sea_norm = clamp(s_sea * 0.25, 0.0, 1.0);

    // ── Ocean: phase-safe fields only, ramped, write-guarded ───────────
    let rain01 = wx(global::RAIN01, s_now);
    let ocean = get_entity("ocean");
    if ocean >= 0 {
        let amp = wx(global::AMP_T, s_sea);
        if amp_storm > 0.0 && s_sea > 3.0 {
            // Top segment re-aimed at the drama dial instead of the table.
            let f = clamp(s_sea - 3.0, 0.0, 1.0);
            amp = global::AMP_T[3] + (amp_storm - global::AMP_T[3]) * f;
        }
        amp *= sea_scale;   // dead calm collapses whatever the cascade says
        let chop = wx(global::CHOP_T, s_wind);
        let wspd = wx(global::WIND_T, s_sea);   // spectrum shape follows the sea
        let fetch = wx(global::FETCH_T, s_sea);
        let foam = wx(global::FOAM_T, s_wind);  // whitecaps follow the wind

        if abs(amp - last_amp) > 0.003 {
            set_field(ocean, "ocean", "amplitude", amp);
            last_amp = amp;
        }
        if abs(chop - last_chop) > 0.002 {
            set_field(ocean, "ocean", "choppiness", chop);
            last_chop = chop;
        }
        if abs(wspd - last_wspd) > 0.05 {
            set_field(ocean, "ocean", "wind_speed", wspd);
            last_wspd = wspd;
        }
        if abs(fetch - last_fetch) > 0.5 {
            set_field(ocean, "ocean", "fetch_km", fetch);
            last_fetch = fetch;
        }
        if abs(foam - last_foam) > 0.002 {
            set_field(ocean, "ocean", "foam_threshold", foam);
            last_foam = foam;
        }
        // Impact rings on the surface follow the rain itself.
        if abs(rain01 - last_ripple) > 0.01 {
            set_field(ocean, "ocean", "rain_ripple", rain01);
            last_ripple = rain01;
        }
    }

    // ── Raft: stiffen the follow in big seas so the eye stays dry ──────
    let raft = get_entity("raft");
    if raft >= 0 {
        if base_heave < 0.0 {
            let h = get_field(raft, "raft_float", "heave_response");
            let a = get_field(raft, "raft_float", "angular_response");
            if h != () && h > 0.0 { base_heave = h; base_ang = a; }
        }
        if base_heave > 0.0 {
            let scale = 1.0 + sea_norm * raft_assist;
            let heave = base_heave * scale;
            if abs(heave - last_heave) > 0.01 {
                set_field(raft, "raft_float", "heave_response", heave);
                set_field(raft, "raft_float", "angular_response", base_ang * scale);
                last_heave = heave;
            }
        }
    }

    // ── Sky: the cloud fields are weather's alone (TOD never writes them)
    let sky = get_entity("sky_dome");
    if sky >= 0 {
        if !sky_base_ok {
            let bdx = get_field(sky, "sky", "cloud_drift_x");
            if bdx != () {
                base_drift_x = bdx;
                base_drift_y = get_field(sky, "sky", "cloud_drift_y");
                base_glow = get_field(sky, "sky", "sun_glow");
                sky_base_ok = true;
            }
        }
        let cov = wx(global::CLOUD_COV, s_now);
        let den = wx(global::CLOUD_DEN, s_now);
        let scl = wx(global::CLOUD_SCL, s_now);
        let glow = base_glow * wx(global::GLOW_S, s_now);
        // Clouds march with the wind (mean, not gusts — texture drift
        // shouldn't jitter), normalized to the SCATTERED baseline of 4 m/s.
        let drift_mul = clamp(wind_mean * 0.25, 0.4, 7.0);

        if abs(cov - last_cov) > 0.002 {
            set_field(sky, "sky", "cloud_coverage", cov);
            last_cov = cov;
        }
        if abs(den - last_den) > 0.002 {
            set_field(sky, "sky", "cloud_density", den);
            last_den = den;
        }
        if abs(scl - last_scl) > 0.002 {
            set_field(sky, "sky", "cloud_scale", scl);
            last_scl = scl;
        }
        if sky_base_ok && abs(drift_mul - last_drift) > 0.01 {
            set_field(sky, "sky", "cloud_drift_x", base_drift_x * drift_mul);
            set_field(sky, "sky", "cloud_drift_y", base_drift_y * drift_mul);
            last_drift = drift_mul;
        }
        if sky_base_ok && abs(glow - last_glow) > 0.005 {
            set_field(sky, "sky", "sun_glow", glow);
            last_glow = glow;
        }
    }

    // ── Rain: the emitter rides the camera and leans with the wind ────
    let rain_ent = get_entity("rain_emitter");
    if rain_ent >= 0 {
        if !wind_dir_ok && ocean >= 0 {
            let dd = get_field(ocean, "ocean", "direction_deg");
            if dd != () {
                wind_dir_x = sin(deg_to_rad(dd));
                wind_dir_z = cos(deg_to_rad(dd));
                wind_dir_ok = true;
            }
        }
        let cam = get_camera_position();
        // Spawn upwind of the eye so the slanted fall lands on the raft.
        let lead = wind_mean * 0.15;
        set_position(rain_ent,
            cam["x"] - wind_dir_x * lead,
            cam["y"] + 9.0,
            cam["z"] - wind_dir_z * lead);

        let rate_max = get_field(me, "weather", "rain_rate_max");
        let rate = rain01 * rate_max;
        if abs(rate - last_rate) > 5.0 {
            set_emission_rate(rain_ent, rate);
            last_rate = rate;
        }
        // Wind slant as horizontal acceleration (gusts lean the sheets).
        let gh = wind * 0.3;
        if abs(gh - last_grav) > 0.15 {
            set_field(rain_ent, "particle_emitter", "gravity",
                [wind_dir_x * gh, -2.0, wind_dir_z * gh]);
            last_grav = gh;
        }
        // Particles are unlit: dim them with the (weather-dimmed) sun so
        // night rain reads as dark streaks, not glowing sparks.
        let sun_e = get_entity("sun");
        if sun_e >= 0 {
            let si = get_field(sun_e, "light", "intensity");
            if si != () {
                let bright = clamp(0.18 + si * 0.55, 0.18, 1.0);
                if abs(bright - last_bright) > 0.02 {
                    set_field(rain_ent, "particle_emitter", "color_start",
                        [0.70 * bright, 0.78 * bright, 0.88 * bright, 0.35]);
                    set_field(rain_ent, "particle_emitter", "color_end",
                        [0.60 * bright, 0.68 * bright, 0.80 * bright, 0.15]);
                    last_bright = bright;
                }
            }
        }
    }

    // ── Weather beds: rain patter with the rain, howl with the wind ───
    let tgt_rain = rain01 * 0.55;
    let rstep = dt / 4.0;
    if tgt_rain > cur_rain_vol { rstep = dt / 2.0; }
    cur_rain_vol = toward(cur_rain_vol, tgt_rain, rstep);
    let rbed = get_entity("rain_ambience");
    if rbed >= 0 && abs(cur_rain_vol - last_rain_vol) > 0.002 {
        set_field(rbed, "audio_source", "volume", cur_rain_vol);
        last_rain_vol = cur_rain_vol;
    }
    // The gusty wind value flutters the howl naturally.
    let tgt_howl = clamp((wind - 8.0) / 16.0, 0.0, 1.0) * 0.7;
    let hstep = dt / 3.0;
    if tgt_howl > cur_howl_vol { hstep = dt / 1.5; }
    cur_howl_vol = toward(cur_howl_vol, tgt_howl, hstep);
    let hbed = get_entity("storm_howl");
    if hbed >= 0 && abs(cur_howl_vol - last_howl_vol) > 0.002 {
        set_field(hbed, "audio_source", "volume", cur_howl_vol);
        last_howl_vol = cur_howl_vol;
    }

    // ── Lightning: scheduled inside the storm, on real seconds ────────
    let stormy = s_now > 3.5;
    if stormy {
        if next_strike < 0.0 {
            next_strike = random_range(
                get_field(me, "weather", "strike_min_s"),
                get_field(me, "weather", "strike_max_s"));
        }
        next_strike -= dt;
    } else {
        next_strike = -1.0;
    }
    let strike_req = get_field(me, "weather", "strike_now") == true;
    if strike_req { set_field(me, "weather", "strike_now", false); }

    if (stormy && next_strike <= 0.0 && next_strike > -0.9) || strike_req {
        next_strike = -1.0;   // stormy reschedules next frame
        let near = strike_req
            || random() < get_field(me, "weather", "near_strike_chance");
        let dist = random_range(500.0, 3000.0);
        if near { dist = random_range(150.0, 400.0); }

        flash_t = 0.0;
        flash_dur = random_range(0.5, 0.7);
        flash_amp = 1.0;
        if near { flash_amp = 1.5; }
        flash_p2 = random_range(0.25, 0.4);
        flash_p3 = random_range(0.55, 0.75);

        booms_t.push(dist / 340.0);
        booms_vol.push(clamp(600.0 / dist, 0.15, 0.95));
        if dist < 500.0 {
            booms_snd.push("audio/thunder_crack.ogg");
        } else if dist < 1500.0 {
            booms_snd.push("audio/thunder_mid.ogg");
        } else {
            booms_snd.push("audio/thunder_far.ogg");
        }
    }

    // The flash itself: 2-3 flicker pulses over ~0.6 s. Published for
    // time_of_day.rhai (sun/cloud whiteout); exposure spike is transient
    // (the player reverts it the frame we stop calling set_exposure).
    let f = 0.0;
    if flash_t >= 0.0 {
        flash_t += dt;
        let u = flash_t / flash_dur;
        if u >= 1.0 {
            flash_t = -1.0;
        } else {
            f = bump(u, 0.06, 0.10)
              + 0.6 * bump(u, flash_p2, 0.08)
              + 0.85 * bump(u, flash_p3, 0.14);
            f = clamp(f, 0.0, 1.0);
        }
    }
    if abs(f - last_flash) > 0.005 || (f == 0.0 && last_flash != 0.0) {
        set_field(me, "weather", "flash", f);
        last_flash = f;
    }
    if f > 0.01 {
        set_exposure(1.0 + 2.2 * f * flash_amp);
    }

    // ── Publish the light/fog factors time_of_day.rhai applies ────────
    let sun_s = wx(global::SUN_S, s_now);
    let amb_s = wx(global::AMB_S, s_now);
    let star_s = wx(global::STAR_S, s_now);
    let tint_m = wx(global::TINT_M, s_now);
    let tint_a = wx(global::TINT_A, s_now);
    let oc_dark = wx(global::OC_DARK, s_now);
    let fog_m = wx(global::FOG_M, s_now);
    let fog_g = wx(global::FOG_G, s_now);
    if abs(sun_s - last_sun_s) > 0.002 {
        set_field(me, "weather", "sun_scale", sun_s);
        last_sun_s = sun_s;
    }
    if abs(amb_s - last_amb_s) > 0.002 {
        set_field(me, "weather", "amb_scale", amb_s);
        last_amb_s = amb_s;
    }
    if abs(star_s - last_star_s) > 0.002 {
        set_field(me, "weather", "star_scale", star_s);
        last_star_s = star_s;
    }
    if abs(tint_m - last_tint_m) > 0.002 {
        set_field(me, "weather", "tint_mul", tint_m);
        last_tint_m = tint_m;
    }
    if abs(tint_a - last_tint_a) > 0.002 {
        set_field(me, "weather", "tint_alpha", tint_a);
        last_tint_a = tint_a;
    }
    if abs(oc_dark - last_oc_dark) > 0.002 {
        set_field(me, "weather", "ocean_dark", oc_dark);
        last_oc_dark = oc_dark;
    }
    if abs(fog_m - last_fog_m) > 0.005 {
        set_field(me, "weather", "fog_mul", fog_m);
        last_fog_m = fog_m;
    }
    if abs(fog_g - last_fog_g) > 0.002 {
        set_field(me, "weather", "fog_gray", fog_g);
        last_fog_g = fog_g;
    }

    // ── Publish (state/wind/sea are the contract other scripts read) ──
    if abs(s_now - last_state) > 0.002 {
        set_field(me, "weather", "state", s_now);
        last_state = s_now;
    }
    if abs(wind - last_wind_pub) > 0.02 {
        set_field(me, "weather", "wind", wind);
        last_wind_pub = wind;
    }
    if abs(sea_norm - last_sea_pub) > 0.002 {
        set_field(me, "weather", "sea", sea_norm);
        last_sea_pub = sea_norm;
    }

    if get_field(me, "weather", "debug_log") == true {
        dbg_timer -= dt;
        if dbg_timer <= 0.0 {
            dbg_timer = 1.0;
            log("weather tgt=" + target_f + " sky=" + s_now + " wind=" + s_wind
                + " sea=" + s_sea + " amp=" + last_amp + " chop=" + last_chop
                + " w=" + wind);
        }
    }
}
