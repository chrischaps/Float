// reality.rhai — reality tears: rare render-mode world events.
//
// Every so often the world's skin splits and something else shows through:
// the waves as falling code (Matrix), the sea turned to blood at dusk, a
// woozy drunk lean, a Tron wire-world. Tears are scheduled like the whale
// breach — autonomous, easy to miss, never performing on demand — but each
// mode has a time-of-day affinity (Matrix wants deep night, blood wants the
// sunset band) and the F3 Reality panel can force one at any hour.
//
// The renderer work lives in composite_shader.wgsl / ocean_shader.wgsl,
// driven by set_render_mode(mode, mix): 1 = Matrix, 2 = blood, 3 = drunk,
// 4 = Tron. The call is TRANSIENT — the engine zeroes the mode the frame we
// stop calling it — so this script simply calls it every active frame and
// the failure mode of a dead script is a healed world, never a stuck tear.
//
// Race audit (script order is a HashMap — see CLAUDE.md): fog and exposure
// belong to time_of_day/weather, the audio lowpass belongs to
// water_ambience. We touch NONE of them directly: the drunk muffle is a
// published `lowpass_scale` factor water_ambience applies at its own write
// site, and the drunk haze uses radial blur + chromatic aberration, which
// nothing else drives. Those two ARE sticky, so the heal path zeroes them.
//
// Engine gotcha honored here: the scope with these globals is visible only
// to on_update itself, NOT to sub-functions — so every helper below is
// PURE and all state mutation stays inline (same discipline as weather.rhai).

let phase = 0;            // 0 idle, 1 easing in, 2 holding, 3 easing out
let mode = 0;             // active mode while phase != 0
let t = 0.0;              // real seconds inside the current phase
let hold_dur = 0.0;       // rolled hold time for this tear
let next_timer = -1.0;    // real seconds until the next autonomous tear
let wobble_t = 0.0;       // drunk sway clock
let base_fov = -1.0;      // camera_tuning fov to restore after a drunk tear
let pub_mode = -9.0;      // last published values (write guards)
let pub_mix = -9.0;
let pub_next = -9.0;
let pub_lp = -9.0;

fn sstep(t) {
    let c = clamp(t, 0.0, 1.0);
    c * c * (3.0 - 2.0 * c)
}

// Time-of-day affinity: a smooth bump around `center`, wrapping midnight.
// width <= 0 means the mode is hour-blind.
fn affinity(hours, center, width) {
    if width <= 0.0 { return 1.0; }
    let d = abs(hours - center);
    if d > 12.0 { d = 24.0 - d; }
    let c = clamp(1.0 - d / width, 0.0, 1.0);
    c * c * (3.0 - 2.0 * c)
}

// Weighted pick over enabled modes, shaped by each mode's hour affinity.
// PURE: reads component fields, returns 0 when nothing wants this hour.
fn pick_mode(me, hours) {
    let w1 = max(get_field(me, "reality", "w_matrix"), 0.0)
        * affinity(hours, get_field(me, "reality", "hour_center_matrix"),
                          get_field(me, "reality", "hour_width_matrix"));
    let w2 = max(get_field(me, "reality", "w_blood"), 0.0)
        * affinity(hours, get_field(me, "reality", "hour_center_blood"),
                          get_field(me, "reality", "hour_width_blood"));
    let w3 = max(get_field(me, "reality", "w_drunk"), 0.0)
        * affinity(hours, get_field(me, "reality", "hour_center_drunk"),
                          get_field(me, "reality", "hour_width_drunk"));
    let w4 = max(get_field(me, "reality", "w_tron"), 0.0)
        * affinity(hours, get_field(me, "reality", "hour_center_tron"),
                          get_field(me, "reality", "hour_width_tron"));
    let total = w1 + w2 + w3 + w4;
    if total < 0.001 { return 0; }
    let r = random() * total;
    if r < w1 { return 1; }
    if r < w1 + w2 { return 2; }
    if r < w1 + w2 + w3 { return 3; }
    4
}

fn on_update() {
    let me = this_entity();
    let dt = delta_time();
    if dt <= 0.0 { return; }

    let enabled = get_field(me, "reality", "enabled");
    if enabled == () { return; }   // component not landed yet (set_field lag)

    // Game hour for affinities (F3 TOD scrubbing works on scheduling too).
    let hours = 12.0;
    let tod = get_entity("tod");
    if tod >= 0 {
        let h = get_field(tod, "time_of_day", "time_hours");
        if h != () { hours = h; }
    }

    // ── One-shots from the F3 Reality panel ─────────────────────────────
    let start_mode = 0;            // >0 = begin this tear below
    let trig = get_field(me, "reality", "trigger_mode");
    if trig != () && trig >= 0.5 {
        set_field(me, "reality", "trigger_mode", -1.0);
        let want = clamp(trig, 1.0, 4.0).to_int();
        if phase == 0 {
            start_mode = want;
        } else {
            mode = want;           // hot-switch the active tear's reality
        }
    }
    let end_req = get_field(me, "reality", "end_now");
    if end_req == true {
        set_field(me, "reality", "end_now", false);
        if phase != 0 && phase != 3 { phase = 3; t = 0.0; }
    }

    // ── Autonomous scheduling (real seconds, storm-shy like the whale) ──
    if phase == 0 && start_mode == 0 && enabled == true {
        if next_timer < 0.0 {
            next_timer = random_range(
                get_field(me, "reality", "min_interval_s"),
                get_field(me, "reality", "max_interval_s"));
        }
        next_timer -= dt;
        if next_timer <= 0.0 {
            let stormy = false;
            let wxe = get_entity("weather_controller");
            if wxe >= 0 {
                let ws = get_field(wxe, "weather", "state");
                if ws != () && ws > 2.5 { stormy = true; }
            }
            // A tear would step on a dead calm's silence — sit it out.
            // (Matrix 23±3 / Tron 22±3 brush the calm's night window.)
            let becalmed = false;
            let dce = get_entity("dead_calm_controller");
            if dce >= 0 {
                let cf = get_field(dce, "dead_calm", "calm");
                if cf != () && cf > 0.1 { becalmed = true; }
            }
            if !stormy && !becalmed { start_mode = pick_mode(me, hours); }
            if start_mode == 0 {
                next_timer = 60.0; // storm, calm, or wrong hour — retry soon
            }
        }
    } else if phase == 0 && enabled != true {
        next_timer = -1.0;         // disabled: forget the schedule
    }

    // ── Begin a tear (from schedule or panel trigger) ───────────────────
    if start_mode > 0 {
        mode = start_mode;
        phase = 1;
        t = 0.0;
        wobble_t = 0.0;
        hold_dur = random_range(
            get_field(me, "reality", "duration_min_s"),
            get_field(me, "reality", "duration_max_s"));
        if mode == 3 {
            // Remember the resting FOV so the drunk lean is undone exactly.
            base_fov = -1.0;
            let cam = get_entity("seat_camera");
            if cam >= 0 {
                let f = get_field(cam, "camera_tuning", "fov_deg");
                if f != () && f > 0.0 { base_fov = f; }
            }
        }
        if get_field(me, "reality", "debug_log") == true {
            print(`reality: tear mode ${mode} for ${hold_dur}s`);
        }
    }

    // ── Envelope ────────────────────────────────────────────────────────
    let mix = 0.0;
    let healed = false;
    if phase != 0 {
        t += dt;
        let ease_in = max(get_field(me, "reality", "ease_in_s"), 0.01);
        let ease_out = max(get_field(me, "reality", "ease_out_s"), 0.01);
        if phase == 1 {
            mix = sstep(t / ease_in);
            if t >= ease_in { phase = 2; t = 0.0; }
        } else if phase == 2 {
            mix = 1.0;
            if t >= hold_dur { phase = 3; t = 0.0; }
        } else {
            mix = 1.0 - sstep(t / ease_out);
            if t >= ease_out { healed = true; mix = 0.0; }
        }
        let pin = get_field(me, "reality", "mix_override");
        if !healed && pin != () && pin >= 0.0 { mix = clamp(pin, 0.0, 1.0); }
    }

    // ── Heal shut: zero the sticky effects we borrowed, go idle ────────
    if healed {
        if mode == 3 {
            if base_fov > 0.0 { set_camera_fov(base_fov); }
            set_radial_blur(0.0);
            set_chromatic_aberration(0.0);
        } else if mode == 1 {
            set_vignette(0.0);
        }
        phase = 0; mode = 0; t = 0.0;
        next_timer = -1.0;         // roll a fresh interval next frame
        if get_field(me, "reality", "debug_log") == true {
            print("reality: healed");
        }
    }

    // ── Drive the renderer + per-mode side effects ──────────────────────
    let lp_scale = 1.0;
    if phase != 0 {
        set_render_mode(mode, mix);
        let rate = if mode == 1 { 6.0 } else { 0.0 };
        set_render_mode_params(
            get_field(me, "reality", "mask_scale"),
            get_field(me, "reality", "mask_style"),
            rate, 0.0);

        if mode == 3 {
            // Drunk: the world leans. FOV breathing on top of the shader's
            // UV sway; blur + fringing nothing else owns; muffled ears via
            // the published factor (water_ambience applies it).
            wobble_t += dt;
            if base_fov > 0.0 {
                set_camera_fov(base_fov + 6.0 * sin(wobble_t * 0.5) * mix);
            }
            set_radial_blur(0.35 * mix);
            set_chromatic_aberration(0.6 * mix);
            lp_scale = 1.0 - 0.6 * mix;
        } else if mode == 1 {
            set_vignette(0.3 * mix);
        }
    }

    // ── Publish (write-guarded; readers see one-frame-stale — fine) ─────
    let am = if phase != 0 { mode.to_float() } else { 0.0 };
    if abs(am - pub_mode) > 0.5 {
        set_field(me, "reality", "active_mode", am);
        pub_mode = am;
    }
    if abs(mix - pub_mix) > 0.005 {
        set_field(me, "reality", "mix", mix);
        pub_mix = mix;
    }
    let nx = if phase == 0 && next_timer >= 0.0 { next_timer } else { -1.0 };
    if abs(nx - pub_next) > 1.0 {
        set_field(me, "reality", "next_in_s", nx);
        pub_next = nx;
    }
    if abs(lp_scale - pub_lp) > 0.01 {
        set_field(me, "reality", "lowpass_scale", lp_scale);
        pub_lp = lp_scale;
    }
}
