# ElevenLabs sound-effect prompts for Float

Replacements for the numpy-synthesized OGGs in `audio/`. Generate at
https://elevenlabs.io/sound-effects (or the `/v1/sound-generation` API),
then convert and drop in over the existing filenames — no code changes
needed, `scenes/float.scene.toml` and `scripts/raft_audio.rhai` reference
the files by name.

## Workflow notes

- Each generation returns **4 variations** — that conveniently matches the
  4 laps and 3 creaks. Pick the best takes rather than re-prompting.
- Set **duration** explicitly (slider / `duration_seconds`); targets below.
- For the two ambient beds, enable **looping** if available on your plan;
  otherwise generate the max length and we can crossfade the seam with a
  small script (same trick `generate_audio.py` uses).
- **Prompt influence** around 60–70% works well: high enough to stay on
  brief, low enough that it still sounds natural.
- Convert to what the engine expects (mono 44.1 kHz OGG Vorbis) by
  renaming each take to its target name (`lap_1.mp3`, `ocean_loop.mp3`, …)
  and dragging the files onto `tools\convert_audio.bat` — they land in
  `audio\` as drop-in replacements. (Equivalent by hand:
  `ffmpeg -i take.mp3 -ac 1 -ar 44100 -c:a libvorbis audio/lap_1.ogg`)

- Loudness: the current files peak around 0.8 (ocean), 0.5 (wind),
  0.7 (laps), 0.55 (creaks). Match roughly with `-filter:a volume=` or
  just A/B in game — F3 panels stay usable while sounds play.

The scene: a small hand-lashed log raft drifting on a calm, deep,
open ocean, far from any shore. Everything should feel close, quiet,
and contemplative — no surf crashing on sand, no gulls, no harbor.

---

## ocean_loop.ogg — ambient bed (target ~20–22 s, seamless loop)

Plays continuously at low volume; it's the emotional floor of the game.

> Calm open ocean ambience recorded at water level, far from shore.
> Slow, deep swells rising and falling, soft water movement all around,
> a low smooth rumble of deep water beneath, an occasional small wave
> crest softly folding over. Peaceful, meditative, steady. Seamless loop.

If a take feels too "beachy" (rhythmic crashing), retry with:

> Deep water ocean swell ambience from the middle of the sea, gentle
> rolling water with no breaking surf, low and hushed, seamless loop.

## wind_light.ogg — ambient bed (target ~15–20 s, seamless loop)

Layered quietly over the ocean loop.

> A soft, steady breeze blowing across open water, light airy wind with
> gentle gusts that slowly swell and fade, smooth and warm, no whistling,
> no objects flapping. Seamless loop.

## lap_1.ogg … lap_4.ogg — wave laps against the logs (~1.5 s one-shots)

Triggered when the raft heaves; played 3D at the waterline. These are the
most intimate sounds in the game — water touching the wood you sit on.
One generation of 4 variations should cover all four files.

> A single small wave gently slapping against the side of wooden logs,
> a soft watery slosh followed by a few light droplets trickling back
> into calm water. Very close perspective, quiet, short.

If the takes are too samey, generate again with nudges and mix picks:

- "…a slightly firmer hollow slap under the wooden logs…"
- "…a very soft lap, barely a ripple against the wood…"
- "…with a sparkle of droplets dripping off the wood afterwards…"

## creak_1.ogg … creak_3.ogg — raft creaks (~0.8–1 s one-shots)

Triggered when the raft rolls; played 3D just above deck height.

> An old wooden raft creaking softly as it rocks: wet rope lashings
> straining and rough logs flexing against each other, a slow low
> wooden groan. Close, quiet, short, no footsteps.

Variation nudges for the three files:

- lap 1 replacement: as written above (balanced rope + wood)
- "…a higher, thin rope squeak as the lashing tightens…"
- "…a deeper, slower groan of two heavy logs shifting…"

---

## Splash tiers — the edge-slap system (scripts/raft_audio.rhai)

Each raft edge fires one of three intensity tiers when the water crosses
the log underside moving upward; the tier is picked from the measured
approach speed. Soft shares a pool with the laps; med and hard escalate.

### splash_soft_1..3 (~0.6 s one-shots, peak ~0.55)

> A small wave folding gently against the side of wooden logs, a soft
> watery push with a faint droplet tail, close, quiet, very short.

### splash_med_1..3 (~1 s one-shots, peak ~0.7)

> A wave slapping firmly against floating wooden logs: a wet smack, a
> burst of droplets scattering on water, one or two soft bubbles
> surfacing after. Close perspective, short, no surf.

### splash_hard_1..2 (~1.4 s one-shots, peak ~0.85)

> A heavy wave hitting the underside of a wooden raft: a deep hollow
> thump through the logs, a hard splash with spray, dense droplets
> raining back onto the water, a low resonance fading. Very close,
> physical, short.

### leg_splash_1..3 (~0.5 s one-shots, peak ~0.5)

Fires when the water reaches the sitter's shins at the raft edge.

> Bare lower legs dipping suddenly into calm water: a small bright
> "plip" splash, light and playful, a few droplets, very close and
> quiet.

### drip_1..4 (~0.4 s one-shots, peak ~0.35)

The after-voice of a big slap — water running off the logs.

> A few water droplets dripping off wet wood into calm water, sparse
> and quiet, one soft plip among them, very close.

### runoff_1..3 (~1.4 s one-shots, peak ~0.5)

The crest breach: the swell drops out from under the raft and the logs
come clear, water sheeting off the wood. A receding sound, not an impact.

> An oar blade lifted slowly out of calm water: water streaming and
> trickling off the wet wood back into the water, a thin draining sheet
> that gradually thins into scattered drips. Close, quiet.

KNOWN TRAP: any prompt containing "logs/raft + sea/wave" pulls the
generator into its wave-hits-wood category — takes come back ~0.4 s,
deep and thuddy, like a wave under a dock, regardless of the duration
setting. Negations ("no splash impact") don't rescue it. Describe an
object LEAVING the water instead (oar, plank, hull) so the event is a
draining process with no impact in it, set duration LONGER than target
(2–2.5 s, trim down), and let "streaming/trickling/draining" lead the
prompt. Alternate action if the oar reads too small:

> A wet wooden plank raised slowly from a still lake, water running off
> it in a light stream, dribbling and trickling back into the water,
> ending with a few soft drips. Very close.

Last resort: generate "water trickling and dripping into a pond, close,
quiet" and slice 1.4 s bodies — the in-game drip tails already finish
the gesture.

### settle_1..3 (~0.7 s one-shots, peak ~0.5)

The land after the breach: the raft flops gently back onto the receding
back face of the swell.

> A wooden raft settling softly back onto calm water: a low gentle wet
> flop, a short slosh along the logs, one soft bubble surfacing, no
> spray, very close, quiet, short.

## Near-field loops (scripts/water_ambience.rhai)

### wash_loop_1..2 (~12 s seamless loops, peak ~0.5)

Four spatial emitters ride the raft edges (two assets at four pitches);
volume follows local water activity.

> Water gurgling and washing gently along the side of floating wooden
> logs: a soft continuous slosh with small bubbles surfacing now and
> then, intimate and close, no waves breaking. Seamless loop.

### foam_fizz_loop.ogg (~10 s seamless loop, peak ~0.4)

Follows local wave steepness; swells with the bioluminescent bloom.

> The fine fizz of sea foam dissolving on calm water: dense tiny
> bubbles popping softly, airy and bright, like gentle carbonation,
> steady and quiet. Seamless loop.

## Wildlife (hooked)

### breach_splash.ogg (~3 s one-shot, peak ~0.9)

Played non-spatial by `whale.rhai` at splash-down, delayed by distance
at the speed of sound (the boom arrives after the sight).

> A huge whale crashing back into the sea far away across open water:
> a distant deep splash, a low boom rolling over the sea, a faint
> lingering white-water hiss, then calm.

### bird_chirp_1..2 (~1 s one-shots, peak ~0.4)

Sparse cries while the dawn V crosses (`birds.rhai`).

> Two or three distant seabird cries over open ocean at dawn, sparse
> and far away, soft and airy, no flocks squawking, no people.

---

## Music (M7) — serene background beds

For ElevenLabs Music (not the SFX generator). Aim for 2–3 minute pieces;
long enough to not feel loopy, short enough that a gentle crossfade back
to the start goes unnoticed under the ocean bed. Keep music *under* the
ocean — it should feel like the sea is humming, not like a soundtrack.

### Day drift (main bed)

> Serene ambient instrumental, very slow and spacious. Warm soft synth
> pads that swell and recede like ocean swells, a gentle felt piano
> playing sparse, unhurried notes with long silences between phrases,
> subtle shimmering high textures like sunlight on water. No drums, no
> vocals. Peaceful, contemplative, weightless — music for drifting alone
> on a calm sea. Major key, but wistful.

### Golden hour / dusk

> Quiet, tender ambient piece. A single warm acoustic guitar playing
> slow, sparse fingerpicked phrases over a soft low drone, with faint
> pad swells underneath. Unhurried, nostalgic, a little melancholy —
> the feeling of watching the sun sink into the ocean. No percussion,
> no vocals, lots of space between notes.

### Deep water (serene + mysterious — the "Says" direction)

Reference feel: Nils Frahm, "Says" — one hypnotic pattern, slowly
gathering weight. The mystery comes from repetition that never quite
resolves; describe the technique, not the artist.

> Hypnotic minimalist ambient piece built on a single soft analog synth
> arpeggio that repeats steadily throughout, warm and slightly detuned,
> like a vintage synthesizer through tape. The pattern never resolves —
> harmonically ambiguous, circling between calm and quietly ominous.
> Around it, very slow layers gather: a deep sustained bass drone,
> distant airy pads swelling and receding, faint high harmonics. Builds
> extremely gradually in intensity, then thins back to almost nothing.
> Serene on the surface with a vast, mysterious undercurrent — the
> feeling of deep open water and not knowing what is beneath. No drums,
> no vocals, meditative, patient.

If the takes come back too bright or pleasant, push with "minor mode,
unresolved suspended harmony, a faint sense of foreboding"; if too dark,
pull back to "more warmth than dread — awe, not fear."

### Night / starfield

> Minimal ambient soundscape, dark but comforting. Deep slow drone,
> distant soft bell-like tones that appear rarely like stars, a faint
> ethereal choir pad far in the background. Almost static, glacial pace,
> meditative and vast. No melody in a hurry, no drums, no vocals —
> the sound of floating under an enormous night sky.

Workflow: the M7 wiring exists — `scripts/music.rhai` crossfades four
looping sources on the time-of-day clock, with a swell/ebb gate so the
music comes and goes (tunable via the `music` component in
`scenes/float.scene.toml`; `ebb_seconds = 0` makes it continuous).
Target filenames: `music_day.ogg`, `music_dusk.ogg`, `music_night.ogg`,
`music_deep.ogg`. Rename takes to those names and drag them onto
`tools\convert_music.bat` (STEREO — not the mono SFX converter).
The current `audio/music_*.ogg` files are **placeholders** (copies of the
ambience loops) so the scene loads and the crossfade logic is audible —
overwrite them with real takes.

## Weather system (rain, storm wind, thunder)

Wired by `scripts/weather.rhai`: the two loops are volume-faded beds
(rain follows the rain state, howl follows wind speed 8→24 m/s), the
thunder one-shots are chosen by virtual strike distance and played
non-spatially, delayed by distance/340 s after the lightning flash.

### rain_loop.ogg — ambient bed (target ~20–30 s, seamless loop)

> Steady rain falling on open deep water, a broad soft hiss of
> countless drops striking the sea surface, gentle surges in intensity,
> individual close droplets pattering, no thunder, no surfaces, no
> gutters or pavement — only rain on water. Seamless loop.

If takes sound urban (rain on roofs/streets), push with "middle of the
ocean, nothing but water in every direction."

### storm_howl.ogg — ambient bed (target ~20–30 s, seamless loop)

Layered over `wind_light.ogg` (which stays); this is only the storm's
extra voice, so it can be dramatic.

> Strong storm wind howling across open ocean, deep powerful gusts
> rising and falling, a low moan with an occasional thin whistle as the
> wind tears at the water, no rain, no thunder, no debris. Seamless loop.

### thunder_crack.ogg — near strike (~4–5 s one-shot, peak ~0.9)

> A sudden violent thunder crack directly overhead: a sharp tearing
> snap, immediately followed by a deep chest-shaking boom and a long
> rolling rumble that fades across the sky. Close, huge, startling.

### thunder_mid.ogg — middle distance (~5–6 s one-shot, peak ~0.8)

> Thunder a few kilometers away over the sea: a muffled deep boom with
> no sharp crack, rolling and echoing across open water, fading slowly.

### thunder_far.ogg — distant rumble (~6–8 s one-shot, peak ~0.65)

> Very distant thunder rumbling low on the horizon over the ocean, a
> soft long roll with slow swells of low frequency, no crack, barely
> more than a vibration, fading into the sound of the sea.

### dunk_in_1/2.ogg — head under (~0.9 s one-shot, peak ~0.8)

Played by `water_ambience.rhai` the instant a swell buries the eye
(render mode 5). Heard from the WET side — the script's lowpass takes
over immediately after, so the asset itself should already sound half
underwater.

> A head plunging under the ocean surface, heard from underwater: a
> soft muffled whomp of entry, a deep sub thump, bubbles streaming past
> the ears, everything dark and pressure-muffled, no bright splash, no
> voice. Very short.

### dunk_out_1/2.ogg — head clear (~1.2 s one-shot, peak ~0.7)

> Surfacing from underwater: water sheeting and draining off a head as
> it breaks the surface, bright close droplet spray, a single high
> plip, the open air rushing back in, no gasp, no voice. Very short.

## Future milestones (generate later, no hooks yet)

- **M6 scooting:** "Hands and fabric shuffling slowly across rough
  weathered wooden planks, small scrapes and soft cloth movement, close,
  short." (several 0.5–1 s one-shots)
- **M8 whale song (optional):** "A faint, low whale song heard from above
  the surface, muffled and distant, melancholic, two slow calls." (~8 s)
