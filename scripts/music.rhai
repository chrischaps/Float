// music.rhai — the score follows the sky, and comes and goes like weather.
//
// Four looping tracks (day / dusk / night / deep-water) sit in the scene at
// volume 0. The engine has no play/stop script API for component sources, so
// they spawn with autoplay=true and are only ever faded — never stopped.
// Each frame this script reads time_hours from the tod entity, computes a
// trapezoid weight per track (1h crossfade edges, midnight-wrap aware),
// gates the whole mix with a slow swell/ebb timer so the music recedes to
// pure ocean between episodes, and slews each audio_source.volume toward
// its target. The audio system picks up the writes with a 16ms tween, so
// the ramps are click-free. Set ebb_seconds = 0 for continuous music.
//
// Config lives on this entity's `music` component (schemas/components/
// music.toml); tracks + windows are the TRACKS table below.
//
// Intro stretch: the day-length ramp compresses the opening days, which
// would churn all four beds inside the first real minute. The music
// instead runs on its own stretched clock: its hour lerps from the
// scene's start hour to intro_sync_hour across days 0..intro_sync_day,
// so the day bed holds through day 0 and day 1's daytime and the FIRST
// dusk cue lands on day 1's evening — exactly where the music clock
// rejoins the world clock (continuous by construction, no drift to
// unwind). While the title card loops day 0, day progress wraps back
// below the anchor each cycle, so the stretched hour sawtooths within
// the day-bed window — the hold survives an arbitrarily long title.
// Scenes without a day counter, or intro_sync_day <= 0, skip the
// stretch.

// [entity_name, window_start_hour, window_end_hour] — end > 24 wraps past
// midnight. Adjacent windows share an edge so they crossfade, not gap.
const TRACKS = [
    ["music_day",    5.5, 17.0],   // fades in over sunrise
    ["music_dusk",  17.0, 20.5],   // golden hour into sunset
    ["music_night", 20.5, 26.0],   // starfield, wraps to 2:00
    ["music_deep",   2.0,  5.5],   // pre-dawn deep-water unease
];

let cur_w = [0.0, 0.0, 0.0, 0.0];      // slewed track weights
let cur_gate = 0.0;                     // slewed swell/ebb gate
let playing = true;                     // in a swell (music) phase?
let phase_left = -1.0;                  // seconds left in phase (<0 = init)
let last_written = [-1.0, -1.0, -1.0, -1.0];
let anchor_p = -1.0;                    // intro-stretch anchor: day progress
let anchor_h = 0.0;                     //   and music hour at scene start

fn sstep(t) {
    let c = clamp(t, 0.0, 1.0);
    c * c * (3.0 - 2.0 * c)
}

// Trapezoid weight of hour h in window [a, b]; edges are 1h wide (±0.5h).
fn window_weight(h, a, b) {
    if b > 24.0 && h < a - 0.5 { h += 24.0; }
    let rise = sstep((h - (a - 0.5)) / 1.0);
    let fall = 1.0 - sstep((h - (b - 0.5)) / 1.0);
    rise * fall
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

    let enabled = get_field(me, "music", "enabled");
    let master = get_field(me, "music", "master_volume");
    // The score recedes as weather builds past overcast — in a storm the
    // storm is the music. (state 2.5 → full master, 3.5+ → 20%.)
    let wxe = get_entity("weather_controller");
    if wxe >= 0 {
        let ws = get_field(wxe, "weather", "state");
        if ws != () {
            master *= 1.0 - 0.8 * clamp(ws - 2.5, 0.0, 1.0);
        }
    }
    // ...and in a dead calm the silence is the music. The event's own
    // envelope shapes the fade; the swell/ebb gate smooths the rest.
    let dce = get_entity("dead_calm_controller");
    if dce >= 0 {
        let cf = get_field(dce, "dead_calm", "calm");
        if cf != () && cf > 0.0 {
            master *= 1.0 - 0.85 * clamp(cf, 0.0, 1.0);
        }
    }
    let fade_s = get_field(me, "music", "fade_seconds");
    let swell_s = get_field(me, "music", "swell_seconds");
    let ebb_s = get_field(me, "music", "ebb_seconds");
    let swell_fade_s = get_field(me, "music", "swell_fade_seconds");
    if fade_s < 0.1 { fade_s = 0.1; }
    if swell_fade_s < 0.1 { swell_fade_s = 0.1; }

    let tod = get_entity("tod");
    if tod < 0 { return; }
    let hours = get_field(tod, "time_of_day", "time_hours");
    if hours == () { return; }          // set_field is deferred; first frames

    // ── Intro stretch: music hour lerps start → intro_sync_hour over
    //    the opening days, rejoining the world clock at the sync point ─
    let mh = hours;
    let day = get_field(tod, "time_of_day", "day");
    let sync_day = get_field(me, "music", "intro_sync_day");
    let sync_hour = get_field(me, "music", "intro_sync_hour");
    if day != () && sync_day != () && sync_hour != () && sync_day > 0.0 {
        let p = day + hours / 24.0;               // continuous day progress
        let p1 = sync_day + sync_hour / 24.0;
        if anchor_p < 0.0 { anchor_p = p; anchor_h = hours; }
        if p < p1 && anchor_p < p1 {
            let t = clamp((p - anchor_p) / (p1 - anchor_p), 0.0, 1.0);
            mh = anchor_h + (sync_hour - anchor_h) * t;
        }
    }

    // ── Swell/ebb: music for ~swell_s, ocean alone for ~ebb_s ───────
    if ebb_s <= 0.01 {
        playing = true;                 // continuous mode
        phase_left = -1.0;              // re-jitter if ebb is turned back on
    } else {
        if phase_left < 0.0 { phase_left = random_range(0.7, 1.3) * swell_s; }
        phase_left -= dt;
        if phase_left <= 0.0 {
            playing = !playing;
            let base = ebb_s;
            if playing { base = swell_s; }
            phase_left = random_range(0.7, 1.3) * base;
        }
    }

    let gate_target = 0.0;
    if enabled && playing { gate_target = 1.0; }
    cur_gate = toward(cur_gate, gate_target, dt / swell_fade_s);

    // ── Slew each track toward master * gate * window weight ────────
    let wstep = dt / fade_s;
    for i in 0..4 {
        let trk = global::TRACKS[i];
        let w = window_weight(mh, trk[1], trk[2]);
        cur_w[i] = toward(cur_w[i], w, wstep);
        let vol = master * cur_gate * cur_w[i];
        if abs(vol - last_written[i]) > 0.002 {
            let e = get_entity(trk[0]);
            if e >= 0 {
                set_field(e, "audio_source", "volume", vol);
                last_written[i] = vol;
            }
        }
    }
}
