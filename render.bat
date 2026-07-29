@echo off
setlocal
cd /d "%~dp0"
if not exist snapshots mkdir snapshots
if not exist snapshots\press mkdir snapshots\press

set FLINT=engine\target\release\flint.exe
set SCENE=scenes\float.scene.toml
set SCHEMAS=--schemas engine\schemas --schemas schemas
set QUICK=--width 1280 --height 720 --no-grid
set PRESS=--width 2560 --height 1440 --no-grid

REM ============================================================
REM  Quick validation renders (snapshots\)
REM ============================================================

echo Rendering seated view (approximate player eye, looking down at raft edge)...
%FLINT% render %SCENE% %SCHEMAS% %QUICK% --output snapshots\seated.png --distance 3.0 --pitch 30 --yaw 0 --target 0,0.2,1.0

echo Rendering raft overview...
%FLINT% render %SCENE% %SCHEMAS% %QUICK% --output snapshots\overview.png --distance 8 --pitch 25 --yaw 35 --target 0,0.3,0

echo Rendering underwater moment (render mode 5, fixture scene)...
%FLINT% render scenes\snap_underwater.scene.toml %SCHEMAS% %QUICK% --output snapshots\underwater.png --distance 3 --pitch=-35 --yaw 35 --target 0,0.5,0 --render-mode 5 --mode-mix 1.0 --mode-params 1.2,0.5,1,0

if /i "%~1"=="quick" goto :done

REM ============================================================
REM  Press set (snapshots\press\) — 2560x1440, for docs + the site
REM
REM  `flint render` runs NO SCRIPTS, which shapes every shot here:
REM    - raft.rhai's buoyancy never runs, so on a big sea the raft
REM      hangs above the surface. Storm/night frame AWAY from origin.
REM    - body.rhai never seats the body, and skinned meshes draw at
REM      bind pose, so fixtures that would show it leave it out.
REM    - script-driven events (dead calm, the visitor) are baked as
REM      their own snap_*.scene.toml.
REM  The title card, animated body and all motion need a live capture.
REM ============================================================

echo [press]  hero, mid-morning...
%FLINT% render %SCENE% %SCHEMAS% %PRESS% --output snapshots\press\hero_day.png --distance 9 --pitch 18 --yaw 35 --target 0,0.4,0

echo [press]  sunset...
%FLINT% render scenes\snap_sunset.scene.toml %SCHEMAS% %PRESS% --output snapshots\press\sunset.png --distance 9 --pitch 12 --yaw 200 --target 0,0.4,0

echo [press]  dusk...
%FLINT% render scenes\snap_dusk.scene.toml %SCHEMAS% %PRESS% --output snapshots\press\dusk.png --distance 9 --pitch 12 --yaw 200 --target 0,0.4,0

echo [press]  night, bioluminescent foam...
%FLINT% render scenes\snap_night.scene.toml %SCHEMAS% %PRESS% --output snapshots\press\night_biolum.png --distance 8 --pitch 8 --yaw 35 --target 14,0.4,9

echo [press]  storm (rain streaks + impact rings, framed clear of the raft)...
%FLINT% render scenes\snap_storm.scene.toml %SCHEMAS% %PRESS% --output snapshots\press\storm.png --distance 10 --pitch 5 --yaw 40 --target 80,1.0,55

echo [press]  whale breach...
%FLINT% render scenes\snap_breach.scene.toml %SCHEMAS% %PRESS% --output snapshots\press\whale_breach.png --distance 12 --pitch 12 --yaw 200 --target 0,1.0,0

echo [press]  dead calm (baked fixture)...
%FLINT% render scenes\snap_calm.scene.toml %SCHEMAS% %PRESS% --output snapshots\press\dead_calm.png --distance 7 --pitch 3 --yaw 15 --target 0,0.25,0

echo [press]  the visitor (baked fixture)...
%FLINT% render scenes\snap_visitor.scene.toml %SCHEMAS% %PRESS% --output snapshots\press\visitor.png --distance 16 --pitch 10 --yaw 240 --target 7,0.4,4.5

echo [press]  underwater (render mode 5)...
%FLINT% render scenes\snap_underwater.scene.toml %SCHEMAS% %PRESS% --output snapshots\press\underwater.png --distance 3 --pitch=-35 --yaw 35 --target 0,0.5,0 --render-mode 5 --mode-mix 1.0 --mode-params 1.2,0.5,1,0

REM Reality tears. Matrix and Tron read best in DAYLIGHT even though they
REM schedule at night: glyph density and edge contrast both follow scene
REM luminance, so a night scene renders them nearly black.

echo [press]  reality tear 1 — matrix...
%FLINT% render %SCENE% %SCHEMAS% %PRESS% --output snapshots\press\tear_matrix.png --distance 9 --pitch 18 --yaw 35 --target 0,0.4,0 --render-mode 1 --mode-mix 1.0 --mode-params 3,0,6,0

echo [press]  reality tear 2 — blood ocean...
%FLINT% render scenes\snap_dusk.scene.toml %SCHEMAS% %PRESS% --output snapshots\press\tear_blood.png --distance 9 --pitch 12 --yaw 200 --target 0,0.4,0 --render-mode 2 --mode-mix 1.0 --mode-params 3,0,6,0

echo [press]  reality tear 3 — drunk...
%FLINT% render %SCENE% %SCHEMAS% %PRESS% --output snapshots\press\tear_drunk.png --distance 8 --pitch 16 --yaw 35 --target 0,0.4,0 --render-mode 3 --mode-mix 1.0 --mode-params 3,0,6,0

echo [press]  reality tear 4 — tron...
%FLINT% render %SCENE% %SCHEMAS% %PRESS% --output snapshots\press\tear_tron.png --distance 9 --pitch 18 --yaw 35 --target 0,0.4,0 --render-mode 4 --mode-mix 1.0 --mode-params 3,0,6,0

:done
echo.
echo Done. Quick renders in snapshots\, press set in snapshots\press\
echo (Pass "quick" as the first argument to skip the press set.)
