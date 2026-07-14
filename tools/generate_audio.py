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


# ── Light wind (30 s loop) ───────────────────────────────────────────────
def gen_wind():
    dur = 30.0
    n = int(SR * dur)
    t = np.arange(n) / SR
    gust = 0.5 + 0.3 * np.sin(2 * np.pi * 0.045 * t) \
               + 0.2 * np.sin(2 * np.pi * 0.13 * t + 2.4)
    x = bandpass(rng.standard_normal(n), 300, 1800) * gust * 0.5
    write("wind_light.ogg", normalize(crossfade_loop(x, 1.0), 0.5))


GENERATORS = {
    "ocean": gen_ocean_loop,
    "laps": gen_laps,
    "creaks": gen_creaks,
    "wind": gen_wind,
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
