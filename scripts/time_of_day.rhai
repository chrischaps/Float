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

    if auto && day_len > 1.0 {
        hours += dt * 24.0 / day_len;
        while hours >= 24.0 { hours -= 24.0; }
        set_field(me, "time_of_day", "time_hours", hours);
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
        set_field(sun, "light", "color", [v[3], v[4], v[5]]);
        set_field(sun, "light", "intensity", v[6]);
    }

    // ── Sky (7..: zenith 7-9, horizon 10-12, haze 13-16, stars 17) ──
    let sky = get_entity("sky_dome");
    if sky >= 0 {
        set_field(sky, "sky", "zenith_color", [v[7], v[8], v[9], 1.0]);
        set_field(sky, "sky", "horizon_color", [v[10], v[11], v[12], 1.0]);
        set_field(sky, "sky", "haze_color", [v[13], v[14], v[15], v[16]]);
        set_field(sky, "sky", "star_opacity", v[17]);
        set_field(sky, "sky", "cloud_tint", [v[18], v[19], v[20], v[21]]);
        set_field(sky, "sky", "ambient_sky", [v[26], v[27], v[28], 1.0]);
        set_field(sky, "sky", "ambient_ground", [v[29], v[30], v[31], 1.0]);
    }

    // ── Fog (22-24 color, 25 density) ────────────────────────────────
    set_fog_color(v[22], v[23], v[24]);
    set_fog_density(v[25]);

    // ── Ocean palette (32-34 deep, 35-37 shallow, 38-40 sss) ────────
    let ocean = get_entity("ocean");
    if ocean >= 0 {
        set_field(ocean, "ocean", "deep_color", [v[32], v[33], v[34], 1.0]);
        set_field(ocean, "ocean", "shallow_color", [v[35], v[36], v[37], 1.0]);
        set_field(ocean, "ocean", "sss_color", [v[38], v[39], v[40], 1.0]);
    }
}
