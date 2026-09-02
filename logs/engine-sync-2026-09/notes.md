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
