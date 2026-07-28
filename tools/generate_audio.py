"""Synthesize Float's audio: ocean ambience, wave laps, wood creaks.

Follows the FlintKart generate_audio.py precedent (numpy + soundfile OGG,
crossfade loop boundaries) — no samples, no AI, fully reproducible.

The ocean loop is layered filtered noise:
  - deep swell bed: brown noise through a slow band-sweeping lowpass,
    amplitude-modulated by two incommensurate swell LFOs (~0.06/0.11 Hz)
    so the loop never feels like it repeats
  - spray shimmer: pink-ish noise highpassed, modulated by the same swells
    (delayed) so crests "break" after they rise
  - sub rumble: very low lowpassed brown noise, constant

Output: audio/*.ogg
Usage:  python tools/generate_audio.py
"""

import os

import numpy as np
import soundfile as sf
from scipy import signal

SR = 44100
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "audio")
os.makedirs(OUT, exist_ok=True)

rng = np.random.default_rng(11)


def crossfade_loop(x, fade_s=1.5):
    n = int(SR * fade_s)
    fade_in = np.linspace(0, 1, n)
    y = x.copy()
    y[:n] = x[:n] * fade_in + x[-n:] * (1 - fade_in)
    return y[: len(x) - n]


def normalize(x, peak=0.85):
    m = np.max(np.abs(x))
    return x * (peak / m) if m > 0 else x


def write(name, x):
    # Stream in blocks: one-shot sf.write of multi-minute buffers can blow
    # libsndfile's vorbis encoder stack on Windows.
    path = os.path.join(OUT, name)
    data = x.astype(np.float32)
    block = SR  # 1s chunks
    with sf.SoundFile(path, "w", SR, 1, format="OGG", subtype="VORBIS") as f:
        for i in range(0, len(data), block):
            f.write(data[i : i + block])
    print(f"wrote {path}  ({len(x)/SR:.1f}s)")


def brown_noise(n):
    x = np.cumsum(rng.standard_normal(n))
    x -= np.linspace(x[0], x[-1], n)          # detrend so loops don't drift
    return x / (np.max(np.abs(x)) + 1e-9)


def lowpass(x, hz, order=4):
    sos = signal.butter(order, hz / (SR / 2), "low", output="sos")
    return signal.sosfilt(sos, x)


def highpass(x, hz, order=4):
    sos = signal.butter(order, hz / (SR / 2), "high", output="sos")
    return signal.sosfilt(sos, x)


def bandpass(x, lo, hi, order=4):
    sos = signal.butter(order, [lo / (SR / 2), hi / (SR / 2)], "band", output="sos")
    return signal.sosfilt(sos, x)


# ── Ocean ambience loop (60 s) ──────────────────────────────────────────
def gen_ocean_loop():
    dur = 60.0
    n = int(SR * dur)
    t = np.arange(n) / SR

    # Two incommensurate swell LFOs — matches the visual wave rhythm scale.
    swell = 0.55 + 0.30 * np.sin(2 * np.pi * 0.062 * t) \
                 + 0.15 * np.sin(2 * np.pi * 0.107 * t + 1.7)

    bed = lowpass(brown_noise(n), 420) * swell
    # Spray "breaks" slightly after the swell peaks (~0.8 s delay).
    delay = int(SR * 0.8)
    swell_late = np.roll(swell, delay)
    spray = bandpass(rng.standard_normal(n), 900, 5200) * 0.16 \
        * np.clip(swell_late - 0.45, 0, 1) ** 1.6
    rumble = lowpass(brown_noise(n), 90) * 0.5

    mix = bed * 0.9 + spray + rumble
    write("ocean_loop.ogg", normalize(crossfade_loop(mix), 0.8))


# ── Wave laps against the logs (one-shots, ~1.4 s) ──────────────────────
def gen_laps():
    for i in range(1, 5):
        dur = rng.uniform(1.1, 1.6)
        n = int(SR * dur)
        t = np.arange(n) / SR
        # A soft "sluh": bandpassed noise burst with a pitch-falling body.
        attack = rng.uniform(0.05, 0.12)
        env = np.exp(-((t - attack) ** 2) / (2 * (attack * 0.8) ** 2)) * (t < attack * 2) \
            + np.exp(-(t - attack) * rng.uniform(3.0, 4.5)) * (t >= attack * 2)
        center = rng.uniform(600, 1000)
        sweep = center * (1 - 0.5 * t / dur)
        noise = rng.standard_normal(n)
        body = np.zeros(n)
        # time-varying bandpass approximated in 8 chunks
        for c in range(8):
            a, b = c * n // 8, (c + 1) * n // 8
            hz = float(np.clip(sweep[(a + b) // 2], 220, 2000))
            body[a:b] = bandpass(noise, hz * 0.55, hz * 1.6)[a:b]
        x = body * env
        # droplet sprinkle on the tail
        drops = highpass(rng.standard_normal(n), 3000) * np.exp(-t * 6) * 0.12
        write(f"lap_{i}.ogg", normalize(x + drops, 0.7))


# ── Wood creaks (rope + log flex, ~0.9 s) ───────────────────────────────
def gen_creaks():
    for i in range(1, 4):
        dur = rng.uniform(0.6, 1.0)
        n = int(SR * dur)
        t = np.arange(n) / SR
        f0 = rng.uniform(130, 210)
        # Stick-slip: frequency wobbles as the "joint" slips.
        wobble = f0 * (1 + 0.10 * np.sin(2 * np.pi * rng.uniform(6, 11) * t)
                       * np.exp(-t * 2.5))
        phase = 2 * np.pi * np.cumsum(wobble) / SR
        tone = (np.sin(phase) * 0.5 + np.sin(2 * phase) * 0.28
                + np.sin(3.1 * phase) * 0.12)
        grit = bandpass(rng.standard_normal(n), f0 * 1.5, f0 * 9) * 0.35
        env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.6
        write(f"creak_{i}.ogg", normalize((tone + grit) * env, 0.55))


# ── Shared splash builders ──────────────────────────────────────────────
def swept_body(n, dur, center, fall=0.5, lo_mul=0.55, hi_mul=1.6, chunks=8):
    """Band-swept noise body (the 'sluh'), pitch falling over the duration."""
    t = np.arange(n) / SR
    sweep = center * (1 - fall * t / dur)
    noise = rng.standard_normal(n)
    body = np.zeros(n)
    for c in range(chunks):
        a, b = c * n // chunks, (c + 1) * n // chunks
        hz = float(np.clip(sweep[(a + b) // 2], 120, 6500))
        body[a:b] = bandpass(noise, hz * lo_mul, hz * hi_mul)[a:b]
    return body


def droplet_grains(n, density_hz, decay, hp_hz=2800):
    """Poisson-spaced droplet ticks whose density decays over the buffer."""
    t = np.arange(n) / SR
    hits = rng.random(n) < (density_hz * np.exp(-t * decay)) / SR
    out = np.zeros(n)
    for i in np.nonzero(hits)[0]:
        gl = int(SR * rng.uniform(0.004, 0.018))
        g = rng.standard_normal(gl) * np.exp(-np.linspace(0, rng.uniform(4, 8), gl))
        end = min(i + gl, n)
        out[i:end] += g[: end - i] * rng.uniform(0.4, 1.0)
    return highpass(out, hp_hz)


def bubble_chirp(n_total, at_s, f_start, f_end, dur_s, amp):
    """A decaying falling sine — the 'bloop' of air escaping under water."""
    n = int(SR * dur_s)
    t = np.arange(n) / SR
    phase = 2 * np.pi * np.cumsum(f_start + (f_end - f_start) * t / dur_s) / SR
    g = np.sin(phase) * np.exp(-t * (5.0 / dur_s)) * amp
    out = np.zeros(n_total)
    i = int(SR * at_s)
    end = min(i + n, n_total)
    out[i:end] = g[: end - i]
    return out


# ── Splashes: three intensity tiers for the slap system ─────────────────
def gen_splashes():
    # soft — barely more than a lap: narrow falling band, faint tail
    for i in range(1, 4):
        dur = rng.uniform(0.5, 0.8)
        n = int(SR * dur)
        t = np.arange(n) / SR
        attack = rng.uniform(0.02, 0.05)
        env = np.exp(-((t - attack) ** 2) / (2 * (attack * 0.9) ** 2)) * (t < attack * 2) \
            + np.exp(-(t - attack) * 6.0) * (t >= attack * 2)
        x = swept_body(n, dur, rng.uniform(500, 900)) * env
        x += droplet_grains(n, 60, 8) * 0.08
        write(f"splash_soft_{i}.ogg", normalize(x, 0.55))

    # med — wider band, real droplet spray, a bubble or two
    for i in range(1, 4):
        dur = rng.uniform(0.8, 1.2)
        n = int(SR * dur)
        t = np.arange(n) / SR
        attack = rng.uniform(0.015, 0.04)
        env = np.exp(-((t - attack) ** 2) / (2 * (attack * 0.8) ** 2)) * (t < attack * 2) \
            + np.exp(-(t - attack) * 4.0) * (t >= attack * 2)
        x = swept_body(n, dur, rng.uniform(900, 1400), lo_mul=0.3, hi_mul=2.0) * env
        x += droplet_grains(n, 160, 5) * 0.14
        for _ in range(rng.integers(1, 3)):
            x += bubble_chirp(n, rng.uniform(0.08, dur * 0.5), 400, 150,
                              rng.uniform(0.06, 0.10), 0.12)
        write(f"splash_med_{i}.ogg", normalize(x, 0.7))

    # hard — broadband slap + sub thump (the hull hit) + long spray tail
    for i in range(1, 3):
        dur = rng.uniform(1.2, 1.6)
        n = int(SR * dur)
        t = np.arange(n) / SR
        slap_n = int(SR * rng.uniform(0.005, 0.010))
        slap = np.zeros(n)
        slap[:slap_n] = rng.standard_normal(slap_n) * np.linspace(1, 0, slap_n)
        thump = np.sin(2 * np.pi * rng.uniform(60, 80) * t) * np.exp(-t * 6) * 0.5
        spray = bandpass(rng.standard_normal(n), 1000, 6000) \
            * np.exp(-np.maximum(t - 0.05, 0) * 3.5) * 0.35
        x = slap * 0.9 + thump + spray
        x += swept_body(n, dur, rng.uniform(700, 1100), lo_mul=0.3, hi_mul=2.2) \
            * np.exp(-t * 3.0) * 0.7
        x += droplet_grains(n, 260, 3.5) * 0.16
        for _ in range(rng.integers(2, 4)):
            x += bubble_chirp(n, rng.uniform(0.1, dur * 0.6), 350, 120,
                              rng.uniform(0.07, 0.12), 0.10)
        write(f"splash_hard_{i}.ogg", normalize(x, 0.85))


# ── Leg splashes: small and bright (shins in the water) ─────────────────
def gen_leg_splashes():
    for i in range(1, 4):
        dur = rng.uniform(0.4, 0.7)
        n = int(SR * dur)
        t = np.arange(n) / SR
        env = np.exp(-t * rng.uniform(7, 10))
        x = swept_body(n, dur, rng.uniform(1500, 2400), lo_mul=0.5, hi_mul=1.8) * env
        # the "plip" of a small object breaking the surface
        x += bubble_chirp(n, rng.uniform(0.0, 0.03), 900, 300, 0.06, 0.25)
        x += droplet_grains(n, 90, 9, hp_hz=3500) * 0.10
        write(f"leg_splash_{i}.ogg", normalize(x, 0.5))


# ── Drips: the after-voice of a big slap running off the logs ───────────
def gen_drips():
    for i in range(1, 5):
        dur = rng.uniform(0.3, 0.6)
        n = int(SR * dur)
        x = droplet_grains(n, rng.uniform(25, 45), 4, hp_hz=2500) * 0.6
        x += bubble_chirp(n, rng.uniform(0.02, dur * 0.4),
                          rng.uniform(700, 1100), rng.uniform(250, 400), 0.05, 0.18)
        write(f"drip_{i}.ogg", normalize(x, 0.35))


# ── Runoff: the crest-breach voice (raft_audio.rhai) ────────────────────
# Fired when the swell drops out from under a raft edge — the downward
# zero-crossing that mirrors the slaps. A receding sheet, not an impact:
# no slap transient, a draining rush that thins into sparse trickles.
def gen_runoff():
    for i in range(1, 4):
        dur = rng.uniform(1.1, 1.6)
        n = int(SR * dur)
        t = np.arange(n) / SR
        # the sheet blooms fast, then drains away
        env = np.sin(np.pi * np.clip(t / 0.12, 0, 1)) * (t < 0.12) \
            + np.exp(-(t - 0.12) * rng.uniform(2.6, 3.6)) * (t >= 0.12)
        sheet = swept_body(n, dur, rng.uniform(700, 1100), fall=0.65,
                           lo_mul=0.4, hi_mul=1.8) * env * 0.8
        # trickles denser than drips, thinning as the wood drains
        x = sheet + droplet_grains(n, rng.uniform(120, 180),
                                   rng.uniform(2.5, 3.5)) * 0.35
        # a last bloop as the water film lets go of the log
        x += bubble_chirp(n, rng.uniform(0.3, dur * 0.6),
                          rng.uniform(500, 800), rng.uniform(180, 300),
                          rng.uniform(0.05, 0.09), 0.08)
        write(f"runoff_{i}.ogg", normalize(x, 0.5))


# ── Settles: the crest-land voice (raft_audio.rhai) ─────────────────────
# The raft flopping back onto the receding back face. Deck and water
# descend nearly together (the raft's heave is smoothed), so this is a
# gentle contact: a low wet flop and a short slosh, no spray.
def gen_settle():
    for i in range(1, 4):
        dur = rng.uniform(0.6, 0.9)
        n = int(SR * dur)
        t = np.arange(n) / SR
        thump = np.sin(2 * np.pi * rng.uniform(70, 95) * t) * np.exp(-t * 9) * 0.4
        env = np.exp(-t * rng.uniform(4.5, 6.0))
        slosh = swept_body(n, dur, rng.uniform(350, 550), fall=0.4,
                           lo_mul=0.45, hi_mul=1.7) * env * 0.8
        x = thump + slosh
        x += droplet_grains(n, 40, 7) * 0.07
        x += bubble_chirp(n, rng.uniform(0.05, 0.25), 350, 140,
                          rng.uniform(0.06, 0.10), 0.10)
        write(f"settle_{i}.ogg", normalize(x, 0.5))


# ── Dunks: the PLAYER's head going under / coming up (water_ambience) ───
# The eye-submersion moments (render mode 5). dunk_in is heard from the
# wet side of the surface: a soft entry whomp, a sub thump, and a body
# that is ALREADY muffled — the script's lowpass takes over from there.
# dunk_out is the air side snapping back: a sheet draining off the face,
# bright spray, one high plip.
def gen_dunk():
    for i in range(1, 3):
        dur = rng.uniform(0.8, 1.0)
        n = int(SR * dur)
        t = np.arange(n) / SR
        entry_n = int(SR * rng.uniform(0.012, 0.020))
        entry = np.zeros(n)
        entry[:entry_n] = rng.standard_normal(entry_n) * np.linspace(1, 0, entry_n)
        entry = lowpass(entry, 2400)          # the ear is IN the splash
        thump = np.sin(2 * np.pi * rng.uniform(55, 70) * t) * np.exp(-t * 5) * 0.6
        body = lowpass(swept_body(n, dur, rng.uniform(400, 600), fall=0.6,
                                  lo_mul=0.4, hi_mul=1.5), 900) \
            * np.exp(-t * rng.uniform(3.0, 4.0)) * 0.8
        x = entry * 0.8 + thump + body
        for _ in range(rng.integers(2, 5)):
            x += bubble_chirp(n, rng.uniform(0.05, dur * 0.6),
                              rng.uniform(300, 500), rng.uniform(100, 180),
                              rng.uniform(0.08, 0.14), 0.12)
        write(f"dunk_in_{i}.ogg", normalize(x, 0.8))

    for i in range(1, 3):
        dur = rng.uniform(1.0, 1.4)
        n = int(SR * dur)
        t = np.arange(n) / SR
        env = np.sin(np.pi * np.clip(t / 0.09, 0, 1)) * (t < 0.09) \
            + np.exp(-(t - 0.09) * rng.uniform(3.2, 4.2)) * (t >= 0.09)
        sheet = swept_body(n, dur, rng.uniform(900, 1300), fall=0.6,
                           lo_mul=0.4, hi_mul=2.0) * env * 0.9
        x = sheet + droplet_grains(n, rng.uniform(200, 280),
                                   rng.uniform(3.0, 4.0), hp_hz=3200) * 0.30
        x += bubble_chirp(n, rng.uniform(0.0, 0.04), 900, 350, 0.05, 0.18)
        write(f"dunk_out_{i}.ogg", normalize(x, 0.7))


# ── Breach splash: the whale coming down, AS HEARD FROM ~130 m ──────────
# The distance is rendered into the asset (it plays non-spatial — see
# whale.rhai): across open water, air absorption strips everything
# bright, so no slap transient, no droplet/bubble detail. What carries
# is a soft deep "whump" — the impact smeared to ~150 ms — the sub
# thump, and a low rumbling white-water collapse, like far surf.
def gen_breach_splash():
    dur = 3.2
    n = int(SR * dur)
    t = np.arange(n) / SR
    # smeared onset: at range the impact is a swell, not a transient
    onset = lowpass(rng.standard_normal(n), 480) \
        * np.sin(np.pi * np.clip(t / 0.15, 0, 1)) * (t < 0.15) * 0.9
    # the sub thump travels best over water
    sub = np.sin(2 * np.pi * 48 * t) * np.exp(-t * 2.0) * 0.8
    # white-water collapse, already muffled: a narrow low band closing down
    tail = np.zeros(n)
    noise = rng.standard_normal(n)
    for c in range(12):
        a, b = c * n // 12, (c + 1) * n // 12
        hi = 900 * np.exp(-c * 0.16) + 170
        tail[a:b] = bandpass(noise, 110, float(hi))[a:b]
    tail *= np.exp(-np.maximum(t - 0.15, 0) * 1.1)
    x = onset + sub + tail * 0.8
    write("breach_splash.ogg", normalize(x, 0.7))


# ── Wash loops: water gurgling along the logs (near-field, spatial) ─────
def gen_wash_loops():
    for i in range(1, 3):
        dur = 12.0
        n = int(SR * dur)
        t = np.arange(n) / SR
        r1, r2 = (0.14, 0.235) if i == 1 else (0.17, 0.29)
        undulate = 0.55 + 0.30 * np.sin(2 * np.pi * r1 * t) \
                        + 0.15 * np.sin(2 * np.pi * r2 * t + 2.1)
        x = bandpass(rng.standard_normal(n), 160, 900) * undulate
        # intermittent gurgle bubbles riding the undulation peaks
        for _ in range(10):
            x += bubble_chirp(n, rng.uniform(0.2, dur - 0.3),
                              rng.uniform(300, 550), rng.uniform(120, 220),
                              rng.uniform(0.08, 0.14), 0.10)
        write(f"wash_loop_{i}.ogg", normalize(crossfade_loop(x, 1.0), 0.5))


# ── Foam fizz loop: carbonation hiss for active/glowing foam ────────────
def gen_foam_fizz():
    dur = 10.0
    n = int(SR * dur)
    # dense non-decaying droplet field = carbonation, over a faint hiss bed
    x = droplet_grains(n, 220, 0.0, hp_hz=2200) * 0.5
    x += bandpass(rng.standard_normal(n), 2000, 6000) * 0.10
    write("foam_fizz_loop.ogg", normalize(crossfade_loop(x, 0.8), 0.4))


# ── Bird chirps: sparse, distant, for the dawn V ────────────────────────
def gen_bird_chirps():
    for i in range(1, 3):
        dur = rng.uniform(0.8, 1.2)
        n = int(SR * dur)
        x = np.zeros(n)
        at = rng.uniform(0.02, 0.1)
        for _ in range(rng.integers(2, 5)):
            sl = rng.uniform(0.05, 0.10)
            sn = int(SR * sl)
            st = np.arange(sn) / SR
            f0 = rng.uniform(2400, 3600)
            # quick up-then-down sweep — a gull-ish cry syllable
            f = f0 * (1 + 0.35 * np.sin(np.pi * st / sl))
            phase = 2 * np.pi * np.cumsum(f) / SR
            syl = np.sin(phase) * np.sin(np.pi * st / sl) ** 1.5
            j = int(SR * at)
            end = min(j + sn, n)
            x[j:end] += syl[: end - j] * rng.uniform(0.5, 1.0)
            at += sl + rng.uniform(0.08, 0.22)
            if at >= dur - 0.12:
                break
        write(f"bird_chirp_{i}.ogg", normalize(lowpass(x, 6000), 0.4))


# ── Light wind (30 s loop) ───────────────────────────────────────────────
def gen_wind():
    dur = 30.0
    n = int(SR * dur)
    t = np.arange(n) / SR
    gust = 0.5 + 0.3 * np.sin(2 * np.pi * 0.045 * t) \
               + 0.2 * np.sin(2 * np.pi * 0.13 * t + 2.4)
    x = bandpass(rng.standard_normal(n), 300, 1800) * gust * 0.5
    write("wind_light.ogg", normalize(crossfade_loop(x, 1.0), 0.5))


# ── Rain loop: broadband patter on water (30 s, weather system) ─────────
def gen_rain():
    dur = 30.0
    n = int(SR * dur)
    t = np.arange(n) / SR
    # Rain on open water is a steady hiss with soft surges — two
    # incommensurate LFOs so the loop never audibly repeats.
    surge = 0.75 + 0.15 * np.sin(2 * np.pi * 0.053 * t) \
                 + 0.10 * np.sin(2 * np.pi * 0.117 * t + 0.9)
    hiss = highpass(rng.standard_normal(n), 3000) * 0.35
    body = bandpass(rng.standard_normal(n), 400, 2500) * 0.22
    # individual drop ticks, dense and non-decaying
    drops = droplet_grains(n, 320, 0.0, hp_hz=3200) * 0.45
    x = (hiss + body + drops) * surge
    write("rain_loop.ogg", normalize(crossfade_loop(x, 1.2), 0.6))


# ── Storm wind howl (30 s loop, weather system) ─────────────────────────
def gen_storm_wind():
    dur = 30.0
    n = int(SR * dur)
    t = np.arange(n) / SR
    # Deeper, angrier gusting than wind_light: bigger swings, lower band.
    gust = 0.45 + 0.35 * np.sin(2 * np.pi * 0.061 * t + 0.4) \
                + 0.20 * np.sin(2 * np.pi * 0.157 * t + 2.1)
    body = bandpass(rng.standard_normal(n), 150, 900) * gust * 0.7
    # A wandering whistle partial — wind finding an edge to sing against.
    whistle_hz = 850 + 250 * np.sin(2 * np.pi * 0.031 * t + 1.2)
    whistle = np.zeros(n)
    noise = rng.standard_normal(n)
    for c in range(15):
        a, b = c * n // 15, (c + 1) * n // 15
        hz = float(whistle_hz[(a + b) // 2])
        whistle[a:b] = bandpass(noise, hz * 0.92, hz * 1.08, order=2)[a:b]
    x = body + whistle * gust ** 2 * 0.18
    write("storm_howl.ogg", normalize(crossfade_loop(x, 1.2), 0.6))


# ── Thunder: three distance tiers (weather system one-shots) ────────────
def gen_thunder():
    # near crack — the tearing snap, then the building roll
    dur = 4.5
    n = int(SR * dur)
    t = np.arange(n) / SR
    crack = np.zeros(n)
    for at, amp in [(0.0, 1.0), (0.09, 0.55)]:          # double crack
        cn = int(SR * 0.02)
        i = int(SR * at)
        crack[i : i + cn] += rng.standard_normal(cn) * np.linspace(1, 0, cn) * amp
    crack = highpass(crack, 700)
    sub = np.sin(2 * np.pi * 48 * t) * np.exp(-t * 1.6) * 0.7
    roll = lowpass(brown_noise(n), 220) \
        * np.exp(-np.maximum(t - 0.15, 0) * 0.9) \
        * (0.7 + 0.3 * np.sin(2 * np.pi * 1.3 * t + 0.5))
    x = crack * 0.9 + sub + roll * 1.1
    write("thunder_crack.ogg", normalize(x, 0.9))

    # mid — attack softened by the air, rumble dominant
    dur = 5.5
    n = int(SR * dur)
    t = np.arange(n) / SR
    onset = lowpass(rng.standard_normal(n), 900) \
        * np.exp(-t * 5.0) * (t < 0.5) * 0.8
    roll = lowpass(brown_noise(n), 160) \
        * np.exp(-np.maximum(t - 0.2, 0) * 0.65) \
        * (0.65 + 0.35 * np.sin(2 * np.pi * 0.9 * t + 1.1))
    x = onset + roll * 1.2 + np.sin(2 * np.pi * 44 * t) * np.exp(-t * 1.1) * 0.4
    write("thunder_mid.ogg", normalize(x, 0.8))

    # far — no attack at all, just a long low swell rolling around the sky
    dur = 7.0
    n = int(SR * dur)
    t = np.arange(n) / SR
    swell = np.sin(np.pi * np.clip(t / 1.2, 0, 1)) \
        * np.exp(-np.maximum(t - 1.2, 0) * 0.55)
    roll = lowpass(brown_noise(n), 110) * swell \
        * (0.6 + 0.4 * np.sin(2 * np.pi * 0.7 * t + 2.3))
    x = roll * 1.3 + np.sin(2 * np.pi * 38 * t) * swell * 0.3
    write("thunder_far.ogg", normalize(x, 0.65))


GENERATORS = {
    "ocean": gen_ocean_loop,
    "laps": gen_laps,
    "creaks": gen_creaks,
    "wind": gen_wind,
    "splashes": gen_splashes,
    "leg_splashes": gen_leg_splashes,
    "drips": gen_drips,
    "runoff": gen_runoff,
    "settle": gen_settle,
    "dunk": gen_dunk,
    "breach": gen_breach_splash,
    "wash": gen_wash_loops,
    "fizz": gen_foam_fizz,
    "birds": gen_bird_chirps,
    "rain": gen_rain,
    "storm_wind": gen_storm_wind,
    "thunder": gen_thunder,
}

if __name__ == "__main__":
    import subprocess
    import sys

    if len(sys.argv) > 1:
        GENERATORS[sys.argv[1]]()
    else:
        # libsndfile's OGG writer can crash the process after several writes;
        # isolate each generator in its own subprocess.
        for name in GENERATORS:
            r = subprocess.run([sys.executable, os.path.abspath(__file__), name])
            if r.returncode != 0:
                print(f"generator '{name}' failed (exit {r.returncode})")
                sys.exit(1)
        print("all audio generated")
