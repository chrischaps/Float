// biolum.rhai — rare bioluminescent bloom nights (M8, retuned).
//
// Bioluminescence is not a nightly fixture: MOST nights the sea stays
// dark. When night falls (h' passes 20.8 in night-continuous hours,
// where after-midnight = hour + 24), this rolls `chance` once; on a
// bloom night it picks a start hour and a duration, and fades the
// ocean's foam_glow in and out across that window — an hour or two of
// glowing wake, then dark again. Rarity is the beauty budget: like the
// whale, a bloom you happen to catch feels like grace, not wallpaper.
//
// This script OWNS ocean.foam_glow (time_of_day.rhai deliberately does
// not touch it). Everything is clamped inside a hard darkness envelope
// (20.8 → astronomical dawn 28.7) so scrubbing the F3 slider into
// daylight can never leave glow on the water. Scrub-friendly like the
// other event scripts: jumping into night re-rolls, jumping out resets.

let rolled = false;        // this night's dice have been cast
let bloom_start = -1.0;    // night-continuous hours (-1 = no bloom tonight)
let bloom_end = -1.0;
let last_glow = -1.0;      // last written value (skip redundant set_field)

fn sstep(t) {
    let c = clamp(t, 0.0, 1.0);
    c * c * (3.0 - 2.0 * c)
}

fn on_update() {
    let me = this_entity();
    let ocean = get_entity("ocean");
    let tod = get_entity("tod");
    if ocean < 0 || tod < 0 { return; }

    let hours = get_field(tod, "time_of_day", "time_hours");
    // Night-continuous coordinate: 0-12h reads as 24-36h, so a window
    // that crosses midnight is a single interval.
    let h = if hours < 12.0 { hours + 24.0 } else { hours };
    let night0 = 20.8;     // full dark (after the dusk key at 20.4)
    let night1 = 28.7;     // astronomical dawn (4.7)
    let in_night = h >= night0 && h <= night1;

    let glow = 0.0;
    if get_field(me, "biolum", "enabled") && in_night {
        if !rolled {
            rolled = true;
            bloom_start = -1.0;
            if random() < get_field(me, "biolum", "chance") {
                let e0 = get_field(me, "biolum", "earliest");
                let e1 = get_field(me, "biolum", "latest");
                let dur = random_range(
                    get_field(me, "biolum", "duration_min"),
                    get_field(me, "biolum", "duration_max"));
                bloom_start = random_range(e0, e1);
                bloom_end = bloom_start + dur;
                if bloom_end > night1 - 0.1 { bloom_end = night1 - 0.1; }
            }
        }
        if bloom_start > 0.0 {
            let fade = get_field(me, "biolum", "fade_hours");
            let strength = get_field(me, "biolum", "strength");
            let rise = sstep((h - bloom_start) / fade);
            let fall = 1.0 - sstep((h - (bloom_end - fade)) / fade);
            // Hard darkness envelope on top of the bloom window.
            let dark = sstep((h - night0) / 0.4)
                * (1.0 - sstep((h - (night1 - 0.5)) / 0.4));
            glow = strength * rise * fall * dark;
        }
    }
    if !in_night { rolled = false; }

    if abs(glow - last_glow) > 0.001 {
        last_glow = glow;
        set_field(ocean, "ocean", "foam_glow", glow);
    }
}
