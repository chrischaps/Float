// dead_calm.rhai — the ocean forgets to breathe.
//
// A rare, night-biased world event: over eight unnatural seconds the sea
// collapses to a near-glass stillness — a faint slow breath of its old
// swell — and holds there for four game hours. The wind dies with it, the
// layered soundscape empties out to almost nothing, the water becomes a
// black mirror for the stars. Then life gradually returns. No punchline;
// the stillness is the event.
//
// Race audit (script order is a HashMap — see CLAUDE.md): weather.rhai is
// the SOLE writer of the ocean's sea-state fields and water_ambience.rhai
// owns the bed volumes, so this script writes NONE of them. It publishes
// factors — sea_scale / wind_scale (weather applies) and bed_scale
// (water_ambience applies) — the same one-way pattern as weather→TOD and
// reality→lowpass_scale. The only fields written directly are three nobody
// else drives: ocean.splash_baseline / splash_strength (the contact-foam
// ring must not hug the raft on glass water) and sky_reflection_strength
// (raised so the mirror reads), captured once at start and restored exactly
// on heal (reality.rhai's base_fov idiom).
//
// Timing is hybrid: the eases run on real seconds (the collapse arriving
// unnaturally FAST is the eeriness, and the return shouldn't stretch with
// the day-length ramp), but the hold is integrated game hours from the tod
// clock, so F3 scrubbing and the ramp both behave.
//
// Engine gotcha honored here: helpers are PURE; all state mutation inline.

let phase = 0;             // 0 idle, 1 falling calm, 2 dead calm, 3 returning
let t = 0.0;               // real seconds inside the current ease phase
let hold_t = 0.0;          // game hours accumulated in phase 2
let prev_hours = -1.0;     // last frame's tod hour (wrap detection)
let next_timer = -1.0;     // real seconds until the next autonomous attempt
let base_splash_base = -1.0;  // captured ocean fields to restore on heal
let base_splash_str = -1.0;   // (-1 = uncaptured / field absent)
let base_sky_refl = -1.0;
let last_sb = -9.0;        // write guards for the direct ocean writes
let last_ss = -9.0;
let last_sr = -9.0;
let pub_calm = -9.0;       // publish guards
let pub_sea = -9.0;
let pub_wind = -9.0;
let pub_bed = -9.0;
let pub_phase = -9.0;
let pub_next = -9.0;
let dbg_t = 0.0;

fn sstep(t) {
    let c = clamp(t, 0.0, 1.0);
    c * c * (3.0 - 2.0 * c)
}

// Time-of-day affinity: a smooth bump around `center`, wrapping midnight.
// width <= 0 means hour-blind. (Same shape as reality.rhai — scripts can't
// share functions, so the idiom is copied.)
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

    let enabled = get_field(me, "dead_calm", "enabled");
    if enabled == () { return; }   // component not landed yet (set_field lag)

    // Game hour + day from the tod clock (F3 scrubbing works on both).
    let hours = 12.0;
    let day = -1.0;                // -1 = no counter (ramp-less scene)
    let have_tod = false;
    let tod = get_entity("tod");
    if tod >= 0 {
        let h = get_field(tod, "time_of_day", "time_hours");
        if h != () { hours = h; have_tod = true; }
        let d = get_field(tod, "time_of_day", "day");
        if d != () { day = d; }
    }
    if prev_hours < 0.0 { prev_hours = hours; }

    // ── One-shots from the F3 Dead Calm panel ───────────────────────────
    let want_start = false;
    let trig = get_field(me, "dead_calm", "trigger_calm");
    if trig != () && trig >= 0.5 {
        set_field(me, "dead_calm", "trigger_calm", -1.0);
        if phase == 0 { want_start = true; }   // bypasses every gate below
    }
    let end_req = get_field(me, "dead_calm", "end_now");
    if end_req == true {
        set_field(me, "dead_calm", "end_now", false);
        if phase == 1 || phase == 2 { phase = 3; t = 0.0; }
    }

    // ── Autonomous scheduling (real seconds; gates checked at expiry) ───
    if phase == 0 && !want_start && enabled == true {
        if next_timer < 0.0 {
            next_timer = random_range(
                get_field(me, "dead_calm", "min_interval_s"),
                get_field(me, "dead_calm", "max_interval_s"));
        }
        next_timer -= dt;
        if next_timer <= 0.0 {
            let ok = true;
            // Day gates: the title's looping day 0 never counts, and the
            // player should learn the ocean's normal breathing first.
            if day >= 0.0 {
                if day < 0.5 { ok = false; }
                let min_day = get_field(me, "dead_calm", "min_day");
                if day < min_day { ok = false; }
            }
            // Hour acceptance: attempts are rolled against the night bump.
            if ok {
                let a = affinity(hours,
                    get_field(me, "dead_calm", "hour_center"),
                    get_field(me, "dead_calm", "hour_width"));
                if random() >= a { ok = false; }
            }
            // Weather gate: weather.rhai APPLIES our factors, so it must
            // exist and be running — and the sky must be near-clear (a
            // dead calm out of an overcast churn wouldn't read).
            if ok {
                ok = false;
                let wxe = get_entity("weather_controller");
                if wxe >= 0 {
                    let wen = get_field(wxe, "weather", "enabled");
                    let ws = get_field(wxe, "weather", "state");
                    if wen == true && ws != ()
                        && ws < get_field(me, "dead_calm", "max_weather_state") {
                        ok = true;
                    }
                }
            }
            if ok {
                want_start = true;
            } else {
                next_timer = get_field(me, "dead_calm", "retry_s");
            }
        }
    } else if phase == 0 && enabled != true {
        next_timer = -1.0;         // disabled: forget the schedule
    }

    // ── Begin: capture the ocean fields we own for the duration ─────────
    if want_start && phase == 0 {
        phase = 1;
        t = 0.0;
        hold_t = 0.0;
        base_splash_base = -1.0;
        base_splash_str = -1.0;
        base_sky_refl = -1.0;
        let ocean = get_entity("ocean");
        if ocean >= 0 {
            let sb = get_field(ocean, "ocean", "splash_baseline");
            let ss = get_field(ocean, "ocean", "splash_strength");
            let sr = get_field(ocean, "ocean", "sky_reflection_strength");
            if sb != () { base_splash_base = sb; }
            if ss != () { base_splash_str = ss; }
            if sr != () { base_sky_refl = sr; }
        }
        if get_field(me, "dead_calm", "debug_log") == true {
            print(`dead_calm: falling calm at hour ${hours}`);
        }
    }

    // ── Envelope: real-second eases around a game-hour hold ─────────────
    let calm = 0.0;
    let healed = false;
    if phase != 0 {
        let ease_in = max(get_field(me, "dead_calm", "ease_in_s"), 0.01);
        let ease_out = max(get_field(me, "dead_calm", "ease_out_s"), 0.01);
        if phase == 1 {
            t += dt;
            calm = sstep(t / ease_in);
            if t >= ease_in { phase = 2; hold_t = 0.0; }
        } else if phase == 2 {
            calm = 1.0;
            if have_tod {
                let dh = hours - prev_hours;
                if dh < -12.0 { dh += 24.0; }        // midnight wrap
                hold_t += clamp(dh, 0.0, 12.0);      // backward scrub: no credit
            } else {
                hold_t += dt * 24.0 / 600.0;         // no clock: nominal day
            }
            if hold_t >= get_field(me, "dead_calm", "hold_hours") {
                phase = 3;
                t = 0.0;
            }
        } else {
            t += dt;
            calm = 1.0 - sstep(t / ease_out);
            if t >= ease_out { calm = 0.0; healed = true; }
        }
    }
    prev_hours = hours;

    // ── Direct writes: the three fields nobody else drives ──────────────
    if phase != 0 && !healed {
        let ocean = get_entity("ocean");
        if ocean >= 0 {
            if base_splash_base >= 0.0 {
                let tgt = get_field(me, "dead_calm", "calm_splash_baseline");
                let v = base_splash_base + (tgt - base_splash_base) * calm;
                if abs(v - last_sb) > 0.002 {
                    set_field(ocean, "ocean", "splash_baseline", v);
                    last_sb = v;
                }
            }
            if base_splash_str >= 0.0 {
                let tgt = get_field(me, "dead_calm", "calm_splash_strength");
                let v = base_splash_str + (tgt - base_splash_str) * calm;
                if abs(v - last_ss) > 0.002 {
                    set_field(ocean, "ocean", "splash_strength", v);
                    last_ss = v;
                }
            }
            if base_sky_refl >= 0.0 {
                let tgt = get_field(me, "dead_calm", "calm_sky_reflection");
                let v = base_sky_refl + (tgt - base_sky_refl) * calm;
                if abs(v - last_sr) > 0.002 {
                    set_field(ocean, "ocean", "sky_reflection_strength", v);
                    last_sr = v;
                }
            }
        }
    }

    // ── Heal: restore the captured fields exactly, go idle ──────────────
    if healed {
        let ocean = get_entity("ocean");
        if ocean >= 0 {
            if base_splash_base >= 0.0 {
                set_field(ocean, "ocean", "splash_baseline", base_splash_base);
            }
            if base_splash_str >= 0.0 {
                set_field(ocean, "ocean", "splash_strength", base_splash_str);
            }
            if base_sky_refl >= 0.0 {
                set_field(ocean, "ocean", "sky_reflection_strength", base_sky_refl);
            }
        }
        base_splash_base = -1.0;
        base_splash_str = -1.0;
        base_sky_refl = -1.0;
        last_sb = -9.0; last_ss = -9.0; last_sr = -9.0;
        phase = 0; t = 0.0; hold_t = 0.0;
        next_timer = -1.0;         // roll a fresh interval next frame
        if get_field(me, "dead_calm", "debug_log") == true {
            print("dead_calm: life returns");
        }
    }

    // ── Factors + publish (write-guarded; one-frame-stale is fine) ──────
    let sea = 1.0 + (get_field(me, "dead_calm", "trough_amp_frac") - 1.0) * calm;
    let wind = 1.0 + (get_field(me, "dead_calm", "trough_wind_frac") - 1.0) * calm;
    let bed = 1.0 + (get_field(me, "dead_calm", "trough_bed") - 1.0) * calm;
    if abs(calm - pub_calm) > 0.005 {
        set_field(me, "dead_calm", "calm", calm);
        pub_calm = calm;
    }
    if abs(sea - pub_sea) > 0.005 {
        set_field(me, "dead_calm", "sea_scale", sea);
        pub_sea = sea;
    }
    if abs(wind - pub_wind) > 0.005 {
        set_field(me, "dead_calm", "wind_scale", wind);
        pub_wind = wind;
    }
    if abs(bed - pub_bed) > 0.005 {
        set_field(me, "dead_calm", "bed_scale", bed);
        pub_bed = bed;
    }
    let ph = phase.to_float();
    if abs(ph - pub_phase) > 0.5 {
        set_field(me, "dead_calm", "phase", ph);
        pub_phase = ph;
    }
    let nx = if phase == 0 && next_timer >= 0.0 { next_timer } else { -1.0 };
    if abs(nx - pub_next) > 1.0 {
        set_field(me, "dead_calm", "next_in_s", nx);
        pub_next = nx;
    }

    if get_field(me, "dead_calm", "debug_log") == true && phase != 0 {
        dbg_t += dt;
        if dbg_t >= 1.0 {
            dbg_t = 0.0;
            print(`dead_calm: phase ${phase} calm ${calm} hold ${hold_t}h`);
        }
    }
}
