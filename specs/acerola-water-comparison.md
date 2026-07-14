# Float vs. Acerola's water trilogy

A comparison of Float's ocean tech against the techniques in the three
Acerola videos (transcripts in `reference/text/`): *How Games Fake Water*
(sum of sines), *Do Video Games Fake Buoyancy*, and *I Tried Simulating
The Entire Ocean* (Tessendorf FFT).

## Where we sit

Float is a **hybrid of his video 1 and video 3**: sum-of-trochoids animation
(video 1's family) but with video 3's physics (deep-water dispersion
ω = √gk from Tessendorf) and video 3's foam detector (displacement
Jacobian). The deliberate difference: everything stays **analytic and tiny**
(≤16 waves) instead of texture-baked and massive (his 4M), because our two
hard requirements — cel-styled flat shading and exact CPU buoyancy — both
push against a big FFT spectrum.

## Same techniques, independently arrived at

| Technique | Acerola | Float |
|---|---|---|
| Vertex-shader displacement | video 1 | `ocean_shader.wgsl` vs_main |
| Analytic derivatives (not central difference) | video 1's "pixel-perfect normals" | analytic normal + Jacobian per fragment |
| Half-vector specular | Blinn-Phong | same H·N, pow 220, then cel-stepped |
| Deep-water dispersion ω=√(gk) | video 3 (Tessendorf) | `flint-core/src/ocean.rs` |
| Foam from displacement Jacobian | video 3 (J < bias) | J < `foam_threshold` (same idea, threshold = his bias) |
| Horizontal (choppy) displacement | video 3, extra FFT | built into Gerstner Q terms |
| Height-based fake subsurface scattering | video 3 (Atlas approximation) | `sss_color · rim · toward-sun · height01` |
| Distance fog to hide the horizon cutoff | video 1 | composite fog + ocean self-fog |
| HDR + bloom + filmic tonemap | video 1 | engine post pipeline (ACES) |
| Plane-fit + spring-smoothed "fake" buoyancy | video 2 (Atlas method) | `raft.rhai` 5-point sample + exp smoothing |

## Where we disagree with him — and why we're comfortable

**Gerstner waves.** He avoids them ("finicky, easy to curl in on itself",
and video 3 notes oceanography downplays them). His complaint is real but
solvable: our spectrum generator normalizes steepness analytically
(Qᵢ = choppiness/(kᵢAᵢN) ⇒ Σ QkA ≤ 1), so self-intersection is impossible
*by construction* rather than by hand-tuning — the exact failure mode he
describes can't occur. We keep Gerstner because trochoidal crests read
beautifully at our stylization level and the horizontal displacement doubles
as his video-1 "domain warping" for free (that trick is literally what the
Q·cos term does).

**Tiling.** His sum-of-sines tiles because it's baked into repeating
textures. We never bake — waves are evaluated analytically in world space
with random directions/phases, so there is no tile period at all. Our
far-field limit is vertex density instead, handled by the warped radial grid
plus displacement fade (his equivalent: GPU tessellation + cascades).

**Wave count.** 12–16 vs his 4 million. Sea of Thieves kept the water
*realistic* and stylized only the foam because, with realistic shading,
reducing sim detail looked bad. Our shading quantizes to 3 cel bands —
micro-detail has nowhere to live, so a huge spectrum would be invisible.
The waves we do have go entirely into *motion*, which is what the deck and
your stomach read.

## Video 2 is the best validation of our architecture

His whole buoyancy video is a fight against one problem: the ocean lives on
the GPU in FFT textures, so the CPU needs **async readbacks** (laggy, noisy)
or voxel grids, then denoising. He explicitly names the escape hatch:
*"with the sum of signs you could very easily calculate a simplified version
on the CPU to get perfectly accurate height data."* That sentence is Float's
architecture. `flint-core::ocean` is the single source of truth; the GPU
only sums the array the CPU generated; `ocean_height()` is exact, zero
latency. His plane-fit rotation "didn't look good" because his inputs were
noisy readbacks — ours is the same math with clean inputs, and it works.
We also go one step further than any of the videos: Eulerian inversion
(fixed-point) so height queries account for Gerstner's horizontal drift.

## Ideas worth stealing later (ranked)

1. ~~**JONSWAP-shaped spectrum sampling**~~ — **DONE.** Amplitudes now draw
   from the JONSWAP density (A² /2 = S(ω)·Δω per log-spaced bin) with
   `wind_speed` / `fetch_km` / `peak_enhancement` params; `amplitude` still
   scales the total. Steepness is distributed by energy share
   (Qᵢ = choppiness/(kᵢ·ΣA)) — the old equal split gave dead waves full
   horizontal pinch, which JONSWAP exposed as phantom foam mist.
2. **Foam accumulation buffer** (video 3). He injects foam where J < 0 and
   exponentially decays it over time, so foam *lingers* behind crests. Ours
   is stateless (foam exists only while pinched). Needs a persistent texture
   + decay pass — moderate engine work, big realism-per-effort at high
   choppiness.
3. ~~**Analytic sky reflection with Fresnel**~~ — **DONE.** The ocean
   uniform carries a per-frame snapshot of the sky gradient (zenith/
   horizon/haze); the fragment evaluates it with the reflected ray and
   blends by Schlick Fresnel (F0 = 0.02), suppressed by foam and shadow.
   Deliberately no sun disc in the reflection — the cel specular already IS
   the sun's reflection. `sky_reflection_strength` in the schema/panel;
   auto-disabled for scenes without a procedural sky.
4. **Sea spray particles** (video 3 cut it; we deferred it) — emit from
   fragments/regions where J crosses the threshold, already planned as M8.
5. **Screen-space reflections** — he's right that they're a sham; skip.
   (Our grab pass shares the "screen-space only" limitation but for
   *refraction* under your own feet the refracted content is on screen by
   construction, so the failure mode doesn't bite.)
