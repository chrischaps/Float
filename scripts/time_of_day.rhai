// time_of_day.rhai — one continuous parameter, the whole emotional register.
//
// Interpolates keyframes (midnight → dawn → sunrise → day → golden →
// sunset → dusk → midnight) across every channel that participates in the
// light: sun direction/color/intensity, sky gradient + stars + clouds,
// fog, hemisphere ambient, and the ocean's own palette. Because everything
// is one smoothstep-lerped timeline, the debug slider (time_hours) and
// natural time passage are the same code path — no discrete states, no pops.
//
// Writes go through set_field / set_fog_* so the renderer extraction picks
// them up next frame. The sky's sun disc follows the sun light for free.

// ── Keyframes ───────────────────────────────────────────────────────────
// Ambient hues follow the sky's hue family at every hour (dusk = purple,
// night = indigo-violet, never desaturated blue-gray) — anything lit only
// by ambient must sit inside the palette. See specs/foam_followups.md.
// [hour, sun_elev, sun_azim, sun_r,g,b, sun_int,
//  zen_r,g,b, hor_r,g,b, haze_r,g,b,a, stars,
//  cloud_r,g,b,a, fog_r,g,b, fog_d,
//  ambS_r,g,b, ambG_r,g,b,
//  deep_r,g,b, shal_r,g,b, sss_r,g,b]
// (Bioluminescent foam_glow is NOT a keyframe channel: blooms are rare
// night events owned by biolum.rhai, not a deterministic daily cycle.)
const KEYS = [
    // 0: midnight
    [0.0,  -40.0,   0.0,  0.0, 0.0, 0.0,  0.0,
     0.004, 0.008, 0.024,  0.012, 0.022, 0.055,  0.02, 0.03, 0.08, 0.4,  1.0,
     0.05, 0.06, 0.11, 0.7,  0.012, 0.018, 0.038,  0.0012,
     0.05, 0.06, 0.14,  0.025, 0.024, 0.055,
     0.004, 0.020, 0.070,  0.014, 0.055, 0.13,  0.01, 0.06, 0.08],
    // 1: astronomical dawn
    [4.7,  -12.0,  70.0,  0.0, 0.0, 0.0,  0.0,
     0.010, 0.020, 0.060,  0.065, 0.050, 0.105,  0.16, 0.09, 0.13, 0.5,  0.6,
     0.12, 0.10, 0.17, 0.75,  0.05, 0.05, 0.09,  0.0013,
     0.06, 0.06, 0.125,  0.026, 0.022, 0.05,
     0.007, 0.028, 0.085,  0.03, 0.08, 0.17,  0.02, 0.10, 0.12],
    // 2: sunrise
    [6.0,   2.0,   85.0,  1.0, 0.45, 0.18,  1.1,
     0.10, 0.18, 0.38,  0.95, 0.45, 0.22,  1.0, 0.55, 0.25, 0.75,  0.05,
     0.98, 0.62, 0.45, 0.85,  0.85, 0.55, 0.35,  0.0018,
     0.10, 0.10, 0.16,  0.05, 0.04, 0.04,
     0.018, 0.09, 0.26,  0.22, 0.33, 0.44,  0.20, 0.33, 0.30],
    // 3: morning
    [8.5,  25.0,  105.0,  1.0, 0.88, 0.70,  1.4,
     0.10, 0.32, 0.70,  0.55, 0.75, 0.90,  0.80, 0.88, 0.95, 0.55,  0.0,
     1.0, 1.0, 1.0, 0.85,  0.70, 0.80, 0.90,  0.0015,
     0.12, 0.13, 0.18,  0.06, 0.05, 0.04,
     0.016, 0.14, 0.50,  0.10, 0.46, 0.85,  0.05, 0.45, 0.50],
    // 4: noon
    [12.5, 62.0,  180.0,  1.0, 0.96, 0.86,  1.55,
     0.10, 0.30, 0.72,  0.52, 0.74, 0.92,  0.85, 0.92, 0.98, 0.5,  0.0,
     1.0, 1.0, 1.0, 0.85,  0.70, 0.82, 0.92,  0.0013,
     0.12, 0.13, 0.18,  0.06, 0.05, 0.04,
     0.016, 0.14, 0.50,  0.10, 0.46, 0.85,  0.05, 0.45, 0.50],
    // 5: golden hour
    [17.5, 12.0,  258.0,  1.0, 0.62, 0.30,  1.3,
     0.16, 0.26, 0.55,  0.95, 0.60, 0.35,  1.0, 0.65, 0.35, 0.7,  0.0,
     1.0, 0.75, 0.55, 0.85,  0.90, 0.65, 0.45,  0.0016,
     0.11, 0.11, 0.16,  0.055, 0.045, 0.04,
     0.018, 0.10, 0.32,  0.20, 0.38, 0.55,  0.25, 0.40, 0.35],
    // 6: sunset
    [19.0,  0.5,  272.0,  1.0, 0.32, 0.12,  1.0,
     0.22, 0.16, 0.42,  1.0, 0.38, 0.20,  1.0, 0.45, 0.30, 0.8,  0.06,
     0.95, 0.50, 0.48, 0.85,  0.85, 0.45, 0.35,  0.0020,
     0.10, 0.075, 0.145,  0.05, 0.035, 0.045,
     0.016, 0.06, 0.22,  0.28, 0.20, 0.34,  0.35, 0.25, 0.28],
    // 7: dusk
    [20.4, -8.0,  285.0,  0.0, 0.0, 0.0,  0.0,
     0.06, 0.05, 0.18,  0.35, 0.18, 0.35,  0.45, 0.25, 0.42, 0.6,  0.55,
     0.20, 0.15, 0.30, 0.8,  0.18, 0.12, 0.25,  0.0015,
     0.09, 0.06, 0.13,  0.04, 0.028, 0.055,
     0.008, 0.030, 0.11,  0.05, 0.08, 0.20,  0.05, 0.10, 0.16],
    // 8: midnight again (wrap target — same values as key 0, hour 24)
    [24.0, -40.0, 360.0,  0.0, 0.0, 0.0,  0.0,
     0.004, 0.008, 0.024,  0.012, 0.022, 0.055,  0.02, 0.03, 0.08, 0.4,  1.0,
     0.05, 0.06, 0.11, 0.7,  0.012, 0.018, 0.038,  0.0012,
     0.05, 0.06, 0.14,  0.025, 0.024, 0.055,
     0.004, 0.020, 0.070,  0.014, 0.055, 0.13,  0.01, 0.06, 0.08],
];

fn smooth(t) {
    t * t * (3.0 - 2.0 * t)
}

fn on_update() {
    let me = this_entity();
    let dt = delta_time();

    let hours = get_field(me, "time_of_day", "time_hours");
    let day_len = get_field(me, "time_of_day", "day_length_sec");
    let auto = get_field(me, "time_of_day", "auto_advance");
    let tilt = get_field(me, "time_of_day", "sun_path_tilt_deg");

    // ── Day counter + first-days ramp ───────────────────────────────
    // The opening days pass in a blur: day 0 lasts a tenth of
    // day_length_sec, and only by day 4 does time settle to the normal
    // rate. Fractions (not absolute seconds) so the F3 panel's
    // day-length control still scales the whole ramp. Scenes that don't
    // list `day`/`last_hours` in their time_of_day block skip all of
    // this and run at the flat rate (unit reads would throw otherwise).
    //
    // Day 0 is the title day: while the title card's published `locked`
    // factor is up, the midnight wrap does NOT advance the counter, so
    // the compressed opening day cycles behind the card for as long as
    // the player watches. The first input drops the lock; the day-0
    // cycle then in progress completes naturally, and its midnight is
    // the first one that counts — day 1 begins.
    let day = get_field(me, "time_of_day", "day");
    let last = get_field(me, "time_of_day", "last_hours");
    let ramped = day != () && last != ();
    if ramped {
        // External writes (panel scrub, one-shots) show up as >12h
        // jumps between frames — same rule raft_visitor.rhai uses:
        // forward wrap +1, backward scrub -1. Our own advance below
        // never lands here because last_hours is written post-wrap.
        let jump = hours - last;
        if jump < -12.0 { day += 1.0; }
        else if jump > 12.0 { day -= 1.0; if day < 0.0 { day = 0.0; } }
    }

    let title_up = false;
    let tc = get_entity("title_controller");
    if tc >= 0 {
        let lk = get_field(tc, "title", "locked");
        if lk != () && lk > 0.5 { title_up = true; }
    }

    if auto && day_len > 1.0 {
        let eff_len = day_len;
        if ramped {
            let frac = 1.0;
            if day < 0.5      { frac = 0.1; }   // day 0 (title): 60 s at 600
            else if day < 1.5 { frac = 0.2; }   // day 1: 120 s
            else if day < 2.5 { frac = 0.4; }   // day 2: 240 s
            else if day < 3.5 { frac = 0.7; }   // day 3: 420 s
            eff_len = day_len * frac;
        }
        hours += dt * 24.0 / eff_len;
        while hours >= 24.0 {
            hours -= 24.0;
            if ramped && !title_up { day += 1.0; }
        }
        set_field(me, "time_of_day", "time_hours", hours);
    }
    if ramped {
        if day != get_field(me, "time_of_day", "day") {
            log("day " + day);
        }
        set_field(me, "time_of_day", "day", day);
        set_field(me, "time_of_day", "last_hours", hours);
    }

    // ── Find bracketing keys and interpolate every channel ──────────
    let keys = global::KEYS;
    let n = keys.len();
    let i0 = 0;
    for i in 0..n-1 {
        if hours >= keys[i][0] { i0 = i; }
    }
    let k0 = keys[i0];
    let k1 = keys[i0 + 1];
    let span = k1[0] - k0[0];
    let t = 0.0;
    if span > 0.0001 { t = smooth(clamp((hours - k0[0]) / span, 0.0, 1.0)); }

    let v = [];
    for c in 0..k0.len() {
        v.push(k0[c] + (k1[c] - k0[c]) * t);
    }

    // ── Weather factors (published by weather.rhai; script update order
    //    is nondeterministic, so weather multiplies THROUGH this script
    //    rather than overwriting after it — one frame stale at most) ──
    let wx_sun = 1.0;    // sun intensity ×
    let wx_amb = 1.0;    // ambient ×
    let wx_star = 1.0;   // star opacity ×
    let wx_tint = 1.0;   // cloud_tint rgb ×
    let wx_tint_a = 0.0; // cloud_tint alpha floor
    let wx_ocean = 1.0;  // ocean palette ×
    let wx_fog_m = 1.0;  // fog density ×
    let wx_fog_g = 0.0;  // fog → storm gray
    let wx_flash = 0.0;  // lightning whiteout 0..1
    let wxe = get_entity("weather_controller");
    if wxe >= 0 {
        let f = get_field(wxe, "weather", "sun_scale");
        if f != () {
            wx_sun = f;
            wx_amb = get_field(wxe, "weather", "amb_scale");
            wx_star = get_field(wxe, "weather", "star_scale");
            wx_tint = get_field(wxe, "weather", "tint_mul");
            wx_tint_a = get_field(wxe, "weather", "tint_alpha");
            wx_ocean = get_field(wxe, "weather", "ocean_dark");
            wx_fog_m = get_field(wxe, "weather", "fog_mul");
            wx_fog_g = get_field(wxe, "weather", "fog_gray");
            wx_flash = get_field(wxe, "weather", "flash");
        }
    }

    // ── Sun light (index 1..7: elev, azim, rgb, intensity) ──────────
    let sun = get_entity("sun");
    if sun >= 0 {
        let elev = deg_to_rad(v[1]);
        let azim = deg_to_rad(v[2]);
        let path_tilt = deg_to_rad(tilt);
        // Direction points TOWARD the sun (engine convention). The arc is
        // tilted so the sun crosses the sky at an angle — low golden light.
        let y = sin(elev);
        let horiz = cos(elev);
        let dx = sin(azim) * horiz;
        let dz = -cos(azim) * horiz;
        let dy = y * cos(path_tilt) + 0.0;
        set_field(sun, "light", "direction", [dx, dy, dz]);
        // Overcast dims the sun; a lightning flash spikes it toward white
        // (the flash lights the sea and raft directionally, not just the sky).
        let sr = v[3] + (1.0 - v[3]) * wx_flash;
        let sg = v[4] + (1.0 - v[4]) * wx_flash;
        let sb = v[5] + (1.0 - v[5]) * wx_flash;
        set_field(sun, "light", "color", [sr, sg, sb]);
        set_field(sun, "light", "intensity", v[6] * wx_sun + 6.0 * wx_flash);
    }

    // ── Sky (7..: zenith 7-9, horizon 10-12, haze 13-16, stars 17) ──
    let sky = get_entity("sky_dome");
    if sky >= 0 {
        set_field(sky, "sky", "zenith_color", [v[7], v[8], v[9], 1.0]);
        set_field(sky, "sky", "horizon_color", [v[10], v[11], v[12], 1.0]);
        // The bright horizon band dims under a storm deck (0.55 of the
        // fog-gray strength — the horizon darkens before the zenith does).
        let hm = 1.0 - 0.75 * wx_fog_g;
        set_field(sky, "sky", "haze_color",
            [v[13] * hm, v[14] * hm, v[15] * hm, v[16]]);
        set_field(sky, "sky", "star_opacity", v[17] * wx_star);
        // Storm clouds darken (tint_mul) and thicken (alpha floor); a
        // flash whites them out from within.
        let tr = v[18] * wx_tint;
        let tg = v[19] * wx_tint;
        let tb = v[20] * wx_tint;
        tr += (1.0 - tr) * wx_flash;
        tg += (1.0 - tg) * wx_flash;
        tb += (1.0 - tb) * wx_flash;
        let ta = v[21];
        if wx_tint_a > ta { ta = wx_tint_a; }
        set_field(sky, "sky", "cloud_tint", [tr, tg, tb, ta]);
        set_field(sky, "sky", "ambient_sky",
            [v[26] * wx_amb, v[27] * wx_amb, v[28] * wx_amb, 1.0]);
        set_field(sky, "sky", "ambient_ground",
            [v[29] * wx_amb, v[30] * wx_amb, v[31] * wx_amb, 1.0]);
    }

    // ── Fog (22-24 color, 25 density) — weather thickens, grays, and
    //    DARKENS it: storm fog is lit by a dimmed sky, so the gray target
    //    scales with the sun factor (bright noon fog → dark slate wall).
    let gray = (v[22] + v[23] + v[24]) / 3.0 * (0.2 + 0.8 * wx_sun);
    let fr = v[22] + (gray * 0.9 - v[22]) * wx_fog_g;
    let fg = v[23] + (gray * 0.95 - v[23]) * wx_fog_g;
    let fb = v[24] + (gray - v[24]) * wx_fog_g;
    set_fog_color(fr, fg, fb);
    set_fog_density(v[25] * wx_fog_m);

    // ── Ocean palette (32-34 deep, 35-37 shallow, 38-40 sss) ────────
    // Heavy weather both darkens (wx_ocean ×) and DESATURATES the water:
    // storm light is gray, so the bold blues pull toward their own
    // luminance before dimming — a slate sea, not a dim vivid one.
    let ocean = get_entity("ocean");
    if ocean >= 0 {
        let desat = wx_fog_g * 0.5;
        let dl = v[32] * 0.35 + v[33] * 0.5 + v[34] * 0.15;
        let sl = v[35] * 0.35 + v[36] * 0.5 + v[37] * 0.15;
        let xl = v[38] * 0.35 + v[39] * 0.5 + v[40] * 0.15;
        set_field(ocean, "ocean", "deep_color", [
            (v[32] + (dl - v[32]) * desat) * wx_ocean,
            (v[33] + (dl - v[33]) * desat) * wx_ocean,
            (v[34] + (dl - v[34]) * desat) * wx_ocean, 1.0]);
        set_field(ocean, "ocean", "shallow_color", [
            (v[35] + (sl - v[35]) * desat) * wx_ocean,
            (v[36] + (sl - v[36]) * desat) * wx_ocean,
            (v[37] + (sl - v[37]) * desat) * wx_ocean, 1.0]);
        set_field(ocean, "ocean", "sss_color", [
            (v[38] + (xl - v[38]) * desat) * wx_ocean,
            (v[39] + (xl - v[39]) * desat) * wx_ocean,
            (v[40] + (xl - v[40]) * desat) * wx_ocean, 1.0]);
    }
}
