# Foam follow-ups (from the dusk-foam diagnosis, 2026-07-16)

Context: dusk foam read as jarring blue-gray slabs on the purple night sea.
Root causes were (1) foam lit by raw desaturated hemisphere ambient while
`foam_color` stays constant white, (2) foam:water contrast exploding at night,
and (3) foam rendering as solid convex masses. Cause 1 is FIXED: foam ambient
in `ocean_shader.wgsl` is now pulled toward the sky snapshot
(`mix(sky_horizon, sky_haze, haze.a)`, 60% blend), so foam inherits the
time-of-day palette automatically. Two follow-ups remain:

## 1. Lacy foam structure — DONE (2026-07-16)

Implemented in `ocean_shader.wgsl`: a second fbm at 6× `foam_noise_scale`
punches holes in the foam mass (hole threshold eases from 0.52 at the mass
edge to 0.30 deep in, via `foam_depth`, so the crest core stays solid and
the skirt goes ragged); the old smooth `foam_halo` gradient was replaced by
`foam_flecks` — the same noise thresholded into full-strength dots that
thin with distance from the crest (`fleck_cut` 0.55→0.78 across the band);
the contact-foam ring is broken by the same lace (floor 0.30 so the lap
stays visible). Tuning knobs if it ever needs adjusting: the 6× lace scale,
the hole/fleck cut ranges, and the 0.35 `foam_depth` divisor.

## 1b. Cel band edge treatment — live-tunable (2026-07-16)

The razor "water level" contours between ramp bands are now controlled by
three `ocean` component fields (F3 → Ocean Debug → Color & Style, committable):

- `band_wobble` (0-1): world-anchored two-scale noise raggedizes the band
  contour — printed-ink line. 0 = original razor edge. Scene ships 0.2.
- `band_dither` (0-1): halftone transition zone at each edge — a 45°-rotated
  world-space dot grid; dots of the upper band grow and merge across the
  zone. Falls back to the plain hard edge where dots go subpixel. 0 = off.
- `band_dither_scale`: dot grid frequency, dots per meter (default 1.5).

Wobble and dither compose (dither zone follows the wobbled contour).
Chris is experimenting with the mix; comparison renders:
`snapshots/edge_A_wobble.png`, `edge_B_dither.png`, `edge_C_both.png`.

## 2. Night ambient hue keyframes — DONE (2026-07-16)

The dusk/night ambient keys in `time_of_day.rhai` were desaturated blue
while the sky keys are pink-purple; everything ambient-lit at night sat
slightly outside the palette. Retuned into the sky's hue family:
dusk ambS `[0.09, 0.06, 0.13]` / ambG `[0.04, 0.028, 0.055]`, midnight
ambS `[0.05, 0.06, 0.14]` / ambG `[0.025, 0.024, 0.055]` (indigo-violet,
green pulled down), astro dawn and sunset nudged to match. The baked
fixtures `snap_dusk` / `snap_night` carry the same values (keep them in
sync with the keyframes when retuning). Verified: raft wood reads warm
mauve at dusk, violet-slate at midnight.

General principle (worth keeping for M8 wildlife etc.): every new element
must be lit from TOD-driven sources — never a constant color, or it will
break the single-hue-family cohesion that makes dusk/night work.
