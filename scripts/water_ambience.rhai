// water_ambience.rhai — the continuous voice of the water, between the slaps.
//
// Three jobs, all volume-shaping (component sources have no play/stop —
// they spawn autoplay at volume 0 and are only ever faded):
//
//  1. Four spatial wash loops ride the raft's edge midpoints (set_position
//     each frame so the gurgle pans as you scoot and look around). Each
//     edge's volume follows a slewed measure of local water activity:
//     surface speed there, weighted by how close the surface is to the
//     logs — water you'd actually hear against the wood.
//  2. A foam-fizz loop at the raft's waterline follows local steepness
//     (the audible sparkle of worked-up water), and swells with the
//     bioluminescent bloom at night (foam_glow — TOD-driven, never
//     constant, per the wildlife lighting rule).
//  3. The ocean/wind beds scale with sea energy read straight from the
//     ocean component, so F3 scrubs of amplitude/choppiness are heard,
//     not just seen. A proximity lowpass eases the whole mix darker when
//     a swell lifts the water toward the eye.
//
// Edge order matches raft_audio.rhai: front, back, right, left.

const WASHES = ["wash_front", "wash_back", "wash_right", "wash_left"];

let cur_wash = [0.0, 0.0, 0.0, 0.0];
let last_wash = [-1.0, -1.0, -1.0, -1.0];
let cur_fizz = 0.0;
let last_fizz = -1.0;
let cur_ocean = -1.0;   // <0 = adopt current scene value on first frame
let cur_wind = -1.0;
let last_ocean = -1.0;
let last_wind = -1.0;
let last_sub_lvl = 0.0; // plunge/emerge edge detection (seat.submerged)
let dunk_cd = 0.0;      // shared one-shot refractory: chop can't machine-gun
let drip_t = -1.0;      // pending drip tail after an emerge

fn sstep(t) {
    let c = clamp(t, 0.0, 1.0);
    c * c * (3.0 - 2.0 * c)
}

// Move cur toward target by at most step, without overshooting.
fn toward(cur, target, step) {
    let d = clamp(target - cur, -step, step);
    cur + d
}

fn on_update() {
    let dt = delta_time();
    if dt <= 0.0 { return; }
    let me = this_entity();

    let raft = get_entity("raft");
    let ocean = get_entity("ocean");
    if raft < 0 || ocean < 0 { return; }

    // ── Submersion factor: seat_camera publishes seat.submerged while a
    // swell buries the eye (one-frame stale — fine for audio). Everything
    // below composes it at THIS script's own write sites (the published-
    // factor pattern); no second writer for the lowpass or bed volumes.
    let sub = 0.0;
    let sce = get_entity("seat_camera");
    if sce >= 0 {
        let sb = get_field(sce, "seat", "submerged");
        if sb != () && sb > 0.0 { sub = clamp(sb, 0.0, 1.0); }
    }

    let wash_max = get_field(me, "water_ambience", "wash_max");
    let wash_v_ref = get_field(me, "water_ambience", "wash_v_ref");
    let gap_range = get_field(me, "water_ambience", "wash_gap_range");
    let attack_s = get_field(me, "water_ambience", "attack_s");
    let release_s = get_field(me, "water_ambience", "release_s");
    let fizz_max = get_field(me, "water_ambience", "fizz_max");
    let fizz_gain = get_field(me, "water_ambience", "fizz_steep_gain");
    let glow_boost = get_field(me, "water_ambience", "fizz_glow_boost");
    let bo_min = get_field(me, "water_ambience", "bed_ocean_min");
    let bo_max = get_field(me, "water_ambience", "bed_ocean_max");
    let bw_min = get_field(me, "water_ambience", "bed_wind_min");
    let bw_max = get_field(me, "water_ambience", "bed_wind_max");
    let e_ref = get_field(me, "water_ambience", "bed_energy_ref");
    let bed_slew = get_field(me, "water_ambience", "bed_slew_s");
    let lp_hz = get_field(me, "water_ambience", "lowpass_near_hz");
    let lp_dist = get_field(me, "water_ambience", "lowpass_dist");
    if attack_s < 0.1 { attack_s = 0.1; }
    if release_s < 0.1 { release_s = 0.1; }
    if bed_slew < 0.1 { bed_slew = 0.1; }

    let rp = get_position(raft);
    let rr = get_rotation(raft);
    let hx = get_field(raft, "ocean_contact", "half_x");
    let hz = get_field(raft, "ocean_contact", "half_z");

    // ── Edge geometry (raft_audio.rhai's convention) ────────────────
    let yaw = deg_to_rad(rr["y"]);
    let fwd_x = sin(yaw);
    let fwd_z = cos(yaw);
    let right_x = cos(yaw);
    let right_z = -sin(yaw);
    let pr = deg_to_rad(rr["x"]);
    let rl = deg_to_rad(rr["z"]);
    let tan_p = sin(pr) / cos(pr);
    let tan_r = sin(rl) / cos(rl);

    let ex = [rp["x"] + fwd_x * hz, rp["x"] - fwd_x * hz,
              rp["x"] + right_x * hx, rp["x"] - right_x * hx];
    let ez = [rp["z"] + fwd_z * hz, rp["z"] - fwd_z * hz,
              rp["z"] + right_z * hx, rp["z"] - right_z * hx];
    let ey = [rp["y"] - tan_p * hz, rp["y"] + tan_p * hz,
              rp["y"] + tan_r * hx, rp["y"] - tan_r * hx];

    // ── Wash loops: water working along the logs ────────────────────
    let steep_sum = 0.0;
    for e in 0..4 {
        let h = ocean_height(ex[e], ez[e]);
        let w_vy = ocean_velocity_y(ex[e], ez[e]);
        let n = ocean_normal(ex[e], ez[e]);
        steep_sum += 1.0 - n["y"];

        let gap = h - ey[e];
        let act = clamp(abs(w_vy) / wash_v_ref, 0.0, 1.0)
                * clamp(1.0 - abs(gap) / gap_range, 0.0, 1.0);

        let step = dt / release_s;
        if act > cur_wash[e] { step = dt / attack_s; }
        cur_wash[e] = toward(cur_wash[e], act, step);

        let went = get_entity(global::WASHES[e]);
        if went >= 0 {
            set_position(went, ex[e], h, ez[e]);
            // Half-duck underwater: the washes are AT the surface, so a
            // buried ear still hears them, just through the water.
            let vol = cur_wash[e] * wash_max * (1.0 - 0.5 * sub);
            if abs(vol - last_wash[e]) > 0.002 {
                set_field(went, "audio_source", "volume", vol);
                last_wash[e] = vol;
            }
        }
    }

    // ── Foam fizz: steepness sparkle, glowing brighter on bloom nights
    let glow = get_field(ocean, "ocean", "foam_glow");
    if glow == () { glow = 0.0; }
    let fizz_act = clamp((steep_sum / 4.0) * fizz_gain, 0.0, 1.0)
                 * (1.0 + glow * glow_boost);
    let fstep = dt / release_s;
    if fizz_act > cur_fizz { fstep = dt / attack_s; }
    cur_fizz = toward(cur_fizz, fizz_act, fstep);

    let fent = get_entity("foam_fizz");
    if fent >= 0 {
        set_position(fent, rp["x"], ocean_height(rp["x"], rp["z"]), rp["z"]);
        // Fizz is an air-side sound — it nearly vanishes underwater.
        let vol = clamp(cur_fizz, 0.0, 1.5) * fizz_max * (1.0 - 0.8 * sub);
        if abs(vol - last_fizz) > 0.002 {
            set_field(fent, "audio_source", "volume", vol);
            last_fizz = vol;
        }
    }

    // ── Reactive beds: the sea's size is audible, not just visible ──
    let amp = get_field(ocean, "ocean", "amplitude");
    let chop = get_field(ocean, "ocean", "choppiness");
    let energy = clamp(amp * (0.5 + 0.5 * chop) / e_ref, 0.0, 1.0);
    let tgt_ocean = bo_min + (bo_max - bo_min) * energy;
    let tgt_wind = bw_min + (bw_max - bw_min) * energy;
    // Dead calm: the beds must sink BELOW their glassy-sea floors — the
    // event publishes bed_scale and we apply it here (this script owns the
    // bed writes; same composition as reality's lowpass_scale below).
    let dce = get_entity("dead_calm_controller");
    if dce >= 0 {
        let bs = get_field(dce, "dead_calm", "bed_scale");
        if bs != () && bs >= 0.0 && bs < 1.0 { tgt_ocean *= bs; tgt_wind *= bs; }
    }
    if cur_ocean < 0.0 { cur_ocean = tgt_ocean; cur_wind = tgt_wind; }
    cur_ocean = toward(cur_ocean, tgt_ocean, dt / bed_slew);
    cur_wind = toward(cur_wind, tgt_wind, dt / bed_slew);

    let oent = get_entity("ocean_ambience");
    if oent >= 0 && abs(cur_ocean - last_ocean) > 0.002 {
        set_field(oent, "audio_source", "volume", cur_ocean);
        last_ocean = cur_ocean;
    }
    // Wind dies with the ears under the surface (ducked at the write, not
    // through the slow bed slew — a sub-second dunk must be heard). The
    // ocean bed stays: it reads as body-conducted rumble.
    let went2 = get_entity("wind_ambience");
    let wind_out = cur_wind * (1.0 - 0.8 * sub);
    if went2 >= 0 && abs(wind_out - last_wind) > 0.002 {
        set_field(went2, "audio_source", "volume", wind_out);
        last_wind = wind_out;
    }

    // ── Proximity lowpass: the mix darkens as the water nears the eye.
    // reality.rhai publishes lowpass_scale < 1 during a drunk tear (the
    // published-factor pattern: this script OWNS the lowpass write, so the
    // tear's muffle composes here instead of racing us — see CLAUDE.md).
    let lp_scale = 1.0;
    let rent = get_entity("reality_controller");
    if rent >= 0 {
        let s = get_field(rent, "reality", "lowpass_scale");
        if s != () && s > 0.0 { lp_scale = s; }
    }
    let cam = get_camera_position();
    let clearance = cam["y"] - ocean_height(cam["x"], cam["z"]);
    let open = sstep(clearance / lp_dist);
    let prox_hz = (lp_hz + (20000.0 - lp_hz) * open) * lp_scale;
    // Underwater muffle: min() against the proximity result so a drunk
    // tear's lowpass_scale and a dunk never multiply into sub-audible mud.
    let uw_hz = 20000.0 + (400.0 - 20000.0) * sstep(sub);
    set_audio_lowpass(if uw_hz < prox_hz { uw_hz } else { prox_hz });

    // ── Plunge / emerge one-shots. Thresholds sit inside the visual
    // hysteresis band on purpose (independent — the picture can flicker
    // a waterline while the sound stays put), and a shared refractory
    // keeps chop from machine-gunning the pair.
    dunk_cd -= dt;
    if sub > 0.65 && last_sub_lvl <= 0.65 && dunk_cd <= 0.0 {
        let n = if random_range(0.0, 1.0) < 0.5 { 1 } else { 2 };
        play_sound(`audio/dunk_in_${n}.ogg`, 0.85);
        dunk_cd = 0.8;
    }
    if sub < 0.35 && last_sub_lvl >= 0.35 && dunk_cd <= 0.0 {
        let n = if random_range(0.0, 1.0) < 0.5 { 1 } else { 2 };
        play_sound(`audio/dunk_out_${n}.ogg`, 0.8);
        drip_t = 0.35;             // the drip tail lands just after the sheet
        dunk_cd = 0.8;
    }
    if drip_t >= 0.0 {
        drip_t -= dt;
        if drip_t < 0.0 {
            let n = 1 + random_range(0.0, 3.999).to_int();
            play_sound(`audio/drip_${n}.ogg`, 0.5);
        }
    }
    last_sub_lvl = sub;
}
