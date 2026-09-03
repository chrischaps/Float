# Float engine sync — 2026-09-02

Target: Flint main 7163db0. Previous engine: subtree squash 0632576 = Flint 6ce46b9
(single `git subtree add`, 2026-07-14). Float is PUBLISHED on itch.io — keep it working.

## Timeline

- 1. Snapshot: HEAD before 7b37e1e (master), 8 dirty entries (.gitignore, CLAUDE.md, README.md,
  render.bat modified; package.bat, press/ (240 KB, cover_630x500.png), tools/generate_cover.py,
  tools/package.py untracked). dist/ (57 MB) is gitignored and was NOT swept in.
  Committed as `wip: pre-engine-sync snapshot` = 90a0a6f.
- 2. Branch `engine-sync-2026-09` created from 90a0a6f.
- 3. Divergence before pull: last squash = 0632576 ("Squashed 'engine/' content from commit 6ce46b9").
  6ce46b9 does NOT exist in Flint's current history (upstream was force-rewritten). 27 local engine
  commits since the squash (0632576..HEAD -- engine/):

  | sha | what it does (engine side) |
  |---|---|
  | 4d51cc6 | M0 scaffold (engine untouched except CLAUDE.md) |
  | 1f27c8f | M1 ocean core: flint-core ocean.rs Gerstner spectrum, OceanPipeline + ocean_shader.wgsl, Rhai ocean_* API, debug panel |
  | 0ea0126 | M2 raft buoyancy + seated first-person camera (Rhai camera APIs) |
  | b836c9f | M3 procedural sky pipeline (sky_pipeline.rs/sky_shader.wgsl) + time-of-day controller |
  | 2d16561 | M4 legs + grab-pass refraction/turbidity (grab_blit_shader) |
  | 2431671 | M5 synthesized audio + horizon polish |
  | 4c0882d | Time-of-day debug panel (F3) |
  | 024e9be | JONSWAP wave spectrum + analytic sky reflections |
  | 97640af | fresnel-weighted sun specular |
  | 2eb8e74 | contact foam, cel-band wobble/dither, shadow + GPU-hash fixes |
  | bd355fa | M8a bioluminescent night foam |
  | e2cd4c4 | sun-gated ocean shadow dimming + sky-reflection shadowing |
  | d1b677a | biolum retune |
  | 8d07abd | skeletal scoot: rigged body, clips, animation-driven steps |
  | d6f14e0 | seed skeleton pose buffers from glTF rest pose |
  | 0834cf0 | idle library: hands, eye bone, bone_probe, eye-bone camera |
  | d27087d | additive animation layers + legs_rock |
  | c7a1e6d | water audio: wave field plays the raft |
  | 8ebee65 | weather: Markov sky with lag cascade |
  | 787b86b | reality tears: four render modes (composite_shader modes 1-4) |
  | 599bf03 | the visitor (twin raft) |
  | 343903e | dead calm (dead_calm panel) |
  | c313695 | title card + day-0 loop |
  | a934103 | body detail pass |
  | f728472 | integration: scene wiring, ocean surface, script APIs, panels, docs |
  | 1586b6c | underwater moments (render mode 5, composite underwater) |
  | 03fe62b | rustfmt (pure formatting) |
  | d8e4c67 | contact-foam uniforms renamed after the hull |
  | 62cf8f3 | debug-ui: tod_panel reads day_length_ramp from the component |
  | 610ec19 | docs: press fixtures in cli-reference |
  | 65c2560 | docs: ocean.md, sky.md, animation/audio/particles/post-processing/scripting docs + images |

- 4. Remote: `engine` -> C:\Users\chris\dev\Flint (local path). `git fetch engine main`
  = 012ec3b..7163db0 (main). Flint's `feature/ocean-pipeline` branch is also present as a remote ref.
- 4b. **Key finding before pulling:** Flint main 7163db0 already CONTAINS all of Float's engine work.
  Checked: `crates/flint-core/src/ocean.rs` is byte-identical to Float's (`git diff engine/main
  HEAD:engine -- crates/flint-core/src/ocean.rs` empty); upstream has ocean_pipeline/ocean_shader,
  sky_pipeline, dead_calm_panel, reality_panel, ocean_panel, tod_panel with `day_length_ramp`
  (62cf8f3), the `hull_*` contact-foam uniform names (d8e4c67), docs/book concepts/ocean.md + sky.md
  + the three images (65c2560), and the player_app split (events/frame/init/transition). Zero files
  exist in Float's engine/ that don't exist upstream (`--diff-filter=A` empty). Every remaining
  "local-only" line in the 110 modified files is the OLD form of code upstream has since refactored
  (rustfmt width change, `ctx.lock()` style, common_args extraction, PostProcessConfig plumbing,
  MSAA `sample_count`, PCSS/sheen/source_radius light uniforms, wgpu-convention depth). Float's
  ocean and sky work was evidently upstreamed via `feature/ocean-pipeline` and then upstream moved on.
- 5. Pull: `git subtree pull --prefix=engine engine main --squash -m "engine: sync to Flint main 7163db0"`
  -> 25 conflicted files (content + add/add), no common base. Below the ~40 threshold, so the NORMAL
  path was used, not the fallback. Since upstream is a strict superset of local engine work, every
  conflict (and every auto-merged file, which could otherwise carry stale 3-way artefacts) was resolved
  by taking the upstream tree wholesale: `git rm -rfq engine && git read-tree --prefix=engine/ -u
  engine/main`, verified `git diff engine/main <index>:engine` is EMPTY, then committed with the
  generated message. Squash commit a166bd2, merge commit 49451bc.
- 5b. Skipped: re-applying 03fe62b (rustfmt) — pure formatting, and upstream already reformatted.

## Conflicts & resolutions

All 25 resolved identically: **upstream (theirs)** — the local side is an older form of the same
feature that upstream already carries. No game feature was deleted; none needed re-integration.

| File | Resolution |
|---|---|
| engine/CLAUDE.md | upstream |
| engine/Cargo.lock | upstream |
| engine/crates/flint-animation/src/lib.rs | upstream (additive layers present upstream) |
| engine/crates/flint-animation/src/skeletal_sync.rs | upstream |
| engine/crates/flint-cli/src/commands/play.rs | upstream |
| engine/crates/flint-cli/src/commands/render.rs | upstream (render modes / --mode-params present upstream) |
| engine/crates/flint-cli/src/main.rs | upstream (common_args.rs extraction) |
| engine/crates/flint-debug-ui/Cargo.toml | upstream |
| engine/crates/flint-debug-ui/src/lib.rs | upstream (ocean/tod/reality/dead_calm panels present) |
| engine/crates/flint-particles/src/sync.rs | upstream |
| engine/crates/flint-player/src/main.rs | upstream |
| engine/crates/flint-player/src/player_app/mod.rs | upstream (split into events/frame/init/transition) |
| engine/crates/flint-player/src/player_app/scene_loading.rs | upstream |
| engine/crates/flint-render/src/composite_shader.wgsl | upstream (modes 1-5 incl. underwater present) |
| engine/crates/flint-render/src/ocean_pipeline.rs | upstream (+ MSAA sample_count) |
| engine/crates/flint-render/src/ocean_shader.wgsl | upstream (+ PCSS, sheen, source_radius, wgpu depth) |
| engine/crates/flint-render/src/postprocess.rs | upstream |
| engine/crates/flint-render/src/scene_renderer/mod.rs | upstream |
| engine/crates/flint-render/src/scene_renderer/render_passes.rs | upstream |
| engine/crates/flint-render/src/shader.wgsl | upstream |
| engine/crates/flint-render/src/skinned_shader.wgsl | upstream |
| engine/crates/flint-render/src/sky_pipeline.rs (add/add) | upstream |
| engine/crates/flint-script/src/api.rs | upstream (ocean_*/audio/camera Rhai APIs present) |
| engine/crates/flint-script/src/context.rs | upstream |
| engine/crates/flint-script/src/lib.rs | upstream |

Superseded (dropped local form, upstream has the newer one): everything above; nothing was lost.

- 6b. `.gitignore` += `renders/` (commit `chore: ignore renders/`).

## Timeline (continued)

- 7. Build: `cargo build --release --bin flint --bin flint-player` (build.log) — Finished in 2m58s,
  exit 0, 0 errors, 0 warnings. No `engine: post-sync build fixes` commit needed.
  Game-side drift check: every Rhai function the 16 scripts call is still registered upstream
  (`ocean_height/normal/velocity_y`, `play_sound(_at)`, `set_render_mode(_params)`, `draw_sprite_ex`,
  `any_input_just_pressed`, `set_audio_lowpass`, `blend_to`, `get/set_field` ...). Game schemas use
  `type = "float"` (224) / `"integer"` (3) — upstream's own engine schemas still use `"float"` 67
  times and upstream's loader does NOT validate scene components against schemas, so this is
  harmless and left alone (FlintLeap renamed only because it carries a local loader-validation
  patch). No `game: adapt to engine 7163db0` commit needed — zero scene/script/schema edits.
- 8. Tests: `cargo test --release` exit 0 (test.log).
- 9. Launch check: PASS (see below).
- 10. Renders: hero + full render.bat (quick + press set), see `[H]` lines.
- 11. Post-pull divergence: `git diff engine/main HEAD:engine --stat` is EMPTY — engine/ is
  byte-identical to Flint main 7163db0. `git diff --stat a166bd2 HEAD -- engine/` = 0 local engine
  changes after the squash (the 745-file/183k-line figure is the squash commit itself vs. its
  parent-less tree). `diff -rq --strip-trailing-cr` shows only `docs/book/book/**` (mdbook build
  output, untracked in both repos — noise).

## Summary

1. Float `engine/` moved from Flint 6ce46b9 (2026-07-14 subtree add, no longer in Flint's rewritten
   history) to 7163db0 (2026-09-02) on branch `engine-sync-2026-09`, via the NORMAL
   `git subtree pull --squash` path (25 conflicts, under the fallback threshold).
2. Flint main already contains ALL of Float's engine work — ocean.rs byte-identical, ocean/sky
   pipelines, underwater/reality render modes, additive animation layers, the hull uniform rename,
   the tod_panel day-length-ramp refactor, and the ocean/sky docs — so every conflict resolved
   to upstream and engine/ is now byte-identical to Flint main (zero Float-only engine deltas).
3. Upstream also brings changes Float never had: MSAA on the ocean pipeline, PCSS shadows, light
   sheen/source_radius, wgpu-convention depth, common_args CLI refactor, flint-music/input-capture
   crates, arch-analyzer tooling.
4. Build clean (0 warnings), 1082 passed / 0 failed / 6 ignored, clippy 136 warnings (not gating),
   launch check PASS, hero + 16 render.bat frames produced with no errors.
5. Game side needed NO adaptation: no scene, script, schema, or bat edits.

## Build result

Finished `release` in 2m58s, exit 0, 0 errors, 0 warnings.

## Test result

`cargo test --release`: exit 0. **Totals: 1082 passed, 0 failed, 6 ignored** across 62 test binaries
(36 non-empty). Largest: flint-procgen 456 (6 ignored), flint-music 67 + 13 integration bins,
flint-render 58, flint-script 50 + 6 integration, flint-animation 49, flint-asset-gen 46,
flint-core 45 (incl. ocean CPU/GPU parity), flint-runtime 45. Identical totals to FlintLeap's sync of
the same tree. No failures, so no pre-existing-vs-merge triage needed.

## Clippy

`cargo clippy --release 2>&1 | grep -c "^warning"` = **136** (not gating; same figure as FlintLeap on
the same upstream tree, so all are upstream's).

## Launch result

`flint-player.exe scenes\float.scene.toml --schemas engine\schemas --schemas schemas` (play.bat minus
`--fullscreen`), via PowerShell Start-Process. **Alive at 12 s: yes (pid 4492). Panic/error grep:
empty. PASS.** Only WARN lines are environmental (wgpu "Unrecognized present mode", gilrs
"No mapping found for UUID 0000...", egui framebuffer format). Last 15 stdout lines: 12 x
`[script] Loaded: <entity> -> <script>.rhai` (raft, raft_visitor, raft_audio, whale, bird_flock,
water_ambience, title_controller, reality_controller, biolum_controller, dead_calm_controller,
wave_probe, music_controller), `Script system initialized (16 scripts)`, `Loaded UI sprite:
title_setdrift.png`, `Loaded UI sprite: title_presskey.png`.

## Renders

[H] renders/float_hero_sync.png — `hero` preset (scene has no `[camera]` block: engine default
distance 15, pitch 30, yaw 0, target origin, grid ON), 1280x720, mid-morning float.scene.toml.
Look for: cel-banded blue sea with hard-edged white Jacobian foam patches along the crests, the
seven-log raft near centre with the skinned body seated at bind pose (legs over the near edge), a
sun-lit sky at the top. If the sea were a flat single blue with no foam, the ocean pipeline or the
JONSWAP upload regressed; if the figure were missing or a grey box, skinned-mesh loading regressed.
Report copy: scratchpad/report/Float_hero.png (= this file, the DAYTIME main scene — it did not
render dark, so no snap_sunset substitution was needed).

[H] snapshots/press/hero_day.png — render.bat press hero (distance 9, pitch 18, yaw 35, target
0,0.4,0, --no-grid, 2560x1440). Look for: pale haze band at the horizon under a near-white sky,
the raft's refraction/turbidity patch visible through the water beside the legs, contact foam
absent (no scripts run). Failure: an opaque sky-mirror on the water or black horizon band.

[H] snapshots/press/sunset.png — snap_sunset fixture (distance 9, pitch 12, yaw 200). Look for:
low sun disc, a broken specular sun path down the swells toward the raft, pink/purple palette,
the raft's long soft shadow across the water (PCSS is new upstream — the penumbra should widen
away from the raft). Failure: hard 3x3 PCF shadow edge, or a white disc under the camera.

[H] snapshots/underwater.png — snap_underwater, --render-mode 5 --mode-mix 1 (pitch -35, deliberate
worm's-eye). Look for: Snell-window brightening at the top, two-step light shafts, banded murk,
the raft underside silhouetted. Failure: no-clip look (opaque sky mirror) or a black frame.

Also produced by render.bat (all 16 succeeded, 0 errors): snapshots/{seated,overview}.png and
snapshots/press/{dusk,night_biolum,storm,whale_breach,dead_calm,visitor,tear_matrix,tear_blood,
tear_drunk,tear_tron}.png — not individually inspected.

## Upstream candidates (post-pull divergence vs Flint 7163db0)

| # | Crate / file | Size | Class | What it is | Why upstream |
|---|---|---|---|---|---|
| — | (none) | 0 | — | engine/ is byte-identical to Flint main | Everything Float built (ocean, sky, weather panel, reality/dead-calm/visitor panels, additive layers, underwater mode, docs) is ALREADY upstream. |

Superseded (class c, deleted locally by taking upstream): the older forms of ocean_pipeline.rs
(no MSAA), ocean_shader.wgsl (legacy PCF texel size, GL-style depth, no sheen/source_radius),
player_app/mod.rs (monolith), flint-cli main.rs (pre-common_args), rustfmt-narrow formatting.
Nothing game-specific lives in engine/ (class b): Float keeps its code under scenes/scripts/schemas.

## Anything left undone

- `CLAUDE.md` (game) still says "Engine changes live on Flint branch `feature/ocean-pipeline`
  (merge to main when ready)" — now stale, they are on main; left for the orchestrator/Chris.
- Clippy count not compared against pristine Flint (would need a full build there).
- `docs/book/book/` mdbook output differs from Flint's copy — untracked on both sides, ignored.
- `press/` (240 KB, cover_630x500.png) and `tools/{package,generate_cover}.py` were swept into
  the wip snapshot commit as instructed; dist/ (57 MB) stayed ignored.
- Not pushed; not merged into master. No vault note written by this sub-task.

## Second pull, 2026-09-03

Subtree pulled to Flint main 81e54fc (schema defaults 424b981, animation PR #40, Starchild features). engine/ byte-identical to Flint main. Release build pass; flint-player launch check pass on the canonical scene (see build2.log / player2.log). Full engine suite on this exact tree: 1107 passed, 0 failed, 6 ignored (run in Flint).
