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

## Future milestones (generate later, no hooks yet)

- **M6 scooting:** "Hands and fabric shuffling slowly across rough
  weathered wooden planks, small scrapes and soft cloth movement, close,
  short." (several 0.5–1 s one-shots)
- **M8 whale breach:** "A huge whale breaching far away across open water
  at dusk: a distant deep splash, a low boom rolling over the sea, a
  faint lingering echo, then calm." (~4–6 s one-shot)
- **M8 whale song (optional):** "A faint, low whale song heard from above
  the surface, muffled and distant, melancholic, two slow calls." (~8 s)
