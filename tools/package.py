#!/usr/bin/env python3
"""Assemble a distributable Windows build of Float.

    python tools/package.py                # stage + zip into dist/
    python tools/package.py --no-zip       # stage only, no archive
    python tools/package.py --version 1.1  # names the archive

What ships is a deliberate subset: the player binary, the main scene, the
scripts, both schema layers, and only the assets the main scene reaches.
Dev-facing material -- tools/, specs/, docs/, the snap_*.scene.toml render
fixtures, the engine source -- stays home.

Staged layout:

    Float/
      Float.bat          the only thing a player touches
      README.txt
      LICENSE.txt
      .itch.toml         launch target for the itch.io app
      data/
        Float.exe        flint-player.exe, renamed
        scenes/ scripts/ schemas/ engine-schemas/
        models/ audio/ sprites/ textures/ config/

Asset resolution is relative to the SCENE, not the exe: the engine searches
scene_dir then scene_dir's parent. That is the whole reason everything sits
under data/ next to data/scenes/ -- the shape of the repo is load-bearing and
must be preserved, not flattened.

The reference check at the end is not ceremony. A one-shot sound whose file is
missing fails SILENTLY at runtime (a log warning, no audio), so a dropped .ogg
would ship undetected and only show up as a hole in the soundscape.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
EXE_SRC = ROOT / "engine" / "target" / "release" / "flint-player.exe"

# The scene is the entry point; everything else is what it reaches.
SCENE = "scenes/float.scene.toml"

# Models the main scene names via `asset = "..."`. legs.glb (superseded by the
# rigged body), water_placeholder.glb and the Mixamo spike are repo history.
MODELS = ["bird", "body", "buoy", "raft", "raft2", "whale"]

# Only the rain drop is loaded from disk -- the body's seven skin/fabric maps
# are embedded inside body.glb by tools/generate_body.py.
TEXTURES = ["rain_drop.png"]


# ────────────────────────────────────────────────────────────────────────
#  Text files written into the package
# ────────────────────────────────────────────────────────────────────────

# Engine stdout goes to a log rather than the console: the player binary
# announces a generic WASD/Jump/Sprint control set that belongs to Flint's
# character controller, not to a raft you sit on. Better a quiet window than a
# confidently wrong one. The error branch pulls the tail back out of the log.
LAUNCHER = r"""@echo off
title Float
cd /d "%~dp0"

set FLOAT_LOG=%TEMP%\float_log.txt

echo.
echo     F L O A T   -   set + drift
echo.
echo     Loading. The game opens in a moment; this window can sit
echo     behind it. Closing this window closes the game.
echo.

data\Float.exe data\scenes\float.scene.toml ^
  --schemas data\engine-schemas ^
  --schemas data\schemas ^
  --fullscreen > "%FLOAT_LOG%" 2>&1

if errorlevel 1 (
  echo.
  echo   -------------------------------------------------------------
  echo    Float stopped with an error. The end of the log:
  echo   -------------------------------------------------------------
  powershell -NoProfile -Command "Get-Content '%FLOAT_LOG%' -Tail 20" 2>nul
  echo   -------------------------------------------------------------
  echo    Full log: %FLOAT_LOG%
  echo    Most often this is a graphics driver older than Vulkan or
  echo    DirectX 12 -- see README.txt.
  echo.
  pause
)
"""

ITCH_MANIFEST = """# Launch target for the itch.io desktop app.
[[actions]]
name = "play"
path = "Float.bat"
"""

README = """\
                              F L O A T

                            SET + DRIFT


  You are adrift. The raft is small and honest -- logs you lashed
  yourself -- and the ocean is enormous and indifferent.

  Nothing is asked of you.


  ---------------------------------------------------------------------
  STARTING
  ---------------------------------------------------------------------

  Double-click  Float.bat

  A small black window opens first and stays behind the game. Leave it
  alone -- closing it closes the game. If anything goes wrong it will
  tell you, and it keeps a full log at %TEMP%\\float_log.txt.


  ---------------------------------------------------------------------
  CONTROLS
  ---------------------------------------------------------------------

  Mouse, or right stick .... look
  A / D, or left stick ..... scoot around the edge of the raft
  Any key .................. begin (dismisses the title)
  Escape ................... let go of the mouse -- click to take it back
  Escape again ............. quit
  F11 ...................... fullscreen / windowed
  F3 ....................... the developer panels, if you are curious:
                             time of day, weather, the wave spectrum.
                             Everything out here is a dial, and you are
                             welcome to turn them.

  That is all of them. There is nothing to collect.


  ---------------------------------------------------------------------
  WHAT HAPPENS OUT THERE
  ---------------------------------------------------------------------

  Nothing, mostly. That is the design.

  The first few days pass in a blur and then time settles down to about
  ten minutes a day. The sun sets properly. The weather drifts on its
  own -- clear to scattered to overcast to rain -- and the sea takes a
  couple of minutes to answer the wind and twice that to lie back down,
  so a storm leaves a swell behind long after the clouds have gone.

  Stay out a while and you may see things that are not scheduled for
  you: something surfaces at dusk, birds cross at dawn, the sea goes to
  glass before sunrise, another raft finds you around noon.

  They happen whether or not you are looking.


  ---------------------------------------------------------------------
  IF SOMETHING GOES WRONG
  ---------------------------------------------------------------------

  Windows 10 or 11, 64-bit. The renderer needs DirectX 12 or Vulkan --
  any GPU from roughly 2016 on. It runs at whatever your desktop
  resolution is.

  Black screen, or it closes immediately
      Update your graphics drivers. Float.bat prints the reason before
      it waits for you, and the whole log is in %TEMP%\\float_log.txt.

  "VCRUNTIME140.dll was not found"
      Install the Microsoft Visual C++ 2015-2022 Redistributable (x64),
      free from Microsoft.

  No sound
      Float opens the default output device at startup. If you changed
      devices while it was running, restart it.

  Rough framerate
      The ocean is the expensive part. F3 opens the Ocean Debug panel;
      a smaller grid or fewer waves buys back a lot.


  ---------------------------------------------------------------------
  ABOUT
  ---------------------------------------------------------------------

  Built on Flint, an open-source Rust engine.

  Every asset here is generated rather than authored -- the raft, the
  body, the sea, the sound of the sea. There are no recorded samples in
  this package and no painted textures. The water is the honest part:
  the waves are a real Gerstner spectrum with real dispersion, and the
  raft is floating on the same surface you are looking at.

  MIT licensed. See LICENSE.txt.
"""


# ────────────────────────────────────────────────────────────────────────
#  Staging
# ────────────────────────────────────────────────────────────────────────


def stage(dest: Path) -> None:
    """Copy the payload into `dest`, mirroring the repo's directory shape."""
    if dest.exists():
        shutil.rmtree(dest)
    data = dest / "data"
    data.mkdir(parents=True)

    shutil.copy2(EXE_SRC, data / "Float.exe")

    (data / "scenes").mkdir()
    shutil.copy2(ROOT / SCENE, data / "scenes" / "float.scene.toml")

    shutil.copytree(ROOT / "scripts", data / "scripts", ignore=shutil.ignore_patterns("*.bak"))
    shutil.copytree(ROOT / "schemas", data / "schemas")
    shutil.copytree(ROOT / "engine" / "schemas", data / "engine-schemas")
    shutil.copytree(ROOT / "audio", data / "audio", ignore=shutil.ignore_patterns("*.wav"))
    shutil.copytree(ROOT / "sprites", data / "sprites")
    shutil.copytree(ROOT / "config", data / "config")

    (data / "models").mkdir()
    for name in MODELS:
        shutil.copy2(ROOT / "models" / f"{name}.glb", data / "models" / f"{name}.glb")

    (data / "textures").mkdir()
    for name in TEXTURES:
        shutil.copy2(ROOT / "textures" / name, data / "textures" / name)

    (dest / "Float.bat").write_text(LAUNCHER, encoding="utf-8", newline="\r\n")
    (dest / "README.txt").write_text(README, encoding="utf-8", newline="\r\n")
    (dest / ".itch.toml").write_text(ITCH_MANIFEST, encoding="utf-8", newline="\r\n")

    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    (dest / "LICENSE.txt").write_text(
        license_text
        + "\n\nFloat is built on the Flint engine (MIT), included in the source\n"
        "repository as a git subtree: https://github.com/chrischaps/Flint\n",
        encoding="utf-8",
        newline="\r\n",
    )


# ────────────────────────────────────────────────────────────────────────
#  Validation
# ────────────────────────────────────────────────────────────────────────


def referenced_paths(data: Path) -> set[str]:
    """Every asset path the shipped scene and scripts ask for, data-relative."""
    scene_text = (data / "scenes" / "float.scene.toml").read_text(encoding="utf-8")
    script_texts = [p.read_text(encoding="utf-8") for p in sorted((data / "scripts").glob("*.rhai"))]

    refs: set[str] = set()

    # Scene: `asset = "raft"` resolves to models/raft.glb
    for m in re.finditer(r'^\s*asset\s*=\s*"([^"]+)"', scene_text, re.M):
        refs.add(f"models/{m.group(1)}.glb")
    # Scene: `source = "raft.rhai"` resolves to scripts/
    for m in re.finditer(r'^\s*source\s*=\s*"([^"]+\.rhai)"', scene_text, re.M):
        refs.add(f"scripts/{m.group(1)}")
    # Both: explicit directory-qualified paths (audio/, textures/, sprites/)
    for text in [scene_text, *script_texts]:
        for m in re.finditer(r'"((?:audio|textures|sprites|config)/[^"]+)"', text):
            refs.add(m.group(1))
    # Scripts: draw_sprite("title_setdrift.png") -- bare name, sprites/ implied
    for text in script_texts:
        for m in re.finditer(r'draw_sprite\w*\(\s*"([^"]+\.png)"', text):
            refs.add(f"sprites/{m.group(1)}")

    return refs


def external_glb_textures(glb: Path) -> list[str]:
    """Image URIs a GLB expects as sibling FILES rather than embedded buffers."""
    raw = glb.read_bytes()
    if raw[:4] != b"glTF":
        return []
    chunk_len, _chunk_type = struct.unpack("<II", raw[12:20])
    doc = json.loads(raw[20 : 20 + chunk_len])
    return [img["uri"] for img in doc.get("images", []) if "uri" in img]


def validate(data: Path) -> list[str]:
    problems = []

    for ref in sorted(referenced_paths(data)):
        target = data / ref
        if target.suffix:
            if not target.exists():
                problems.append(f"missing: data/{ref} (referenced by the scene or a script)")
        # No extension means the script builds the name -- `"audio/lap_" + n`
        # for the numbered variant tiers. One survivor is enough to prove the
        # family shipped; the engine picks whichever indices exist.
        elif not list(target.parent.glob(f"{target.name}*")):
            problems.append(f"missing: data/{ref}* (a script builds names from this prefix)")

    for glb in sorted((data / "models").glob("*.glb")):
        for uri in external_glb_textures(glb):
            if not (glb.parent / uri).exists():
                problems.append(f"missing: {glb.name} wants an external texture '{uri}'")

    # The two schema layers must both survive -- the game layer overrides the
    # engine layer, and a missing engine component makes the scene fail to load.
    for layer in ("schemas/components", "engine-schemas/components"):
        if not any((data / layer).glob("*.toml")):
            problems.append(f"missing: data/{layer}/ has no component schemas")

    return problems


# ────────────────────────────────────────────────────────────────────────
#  Archive
# ────────────────────────────────────────────────────────────────────────


def make_zip(stage_dir: Path, archive: Path) -> None:
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(stage_dir.rglob("*")):
            if path.is_file():
                zf.write(path, Path(stage_dir.name) / path.relative_to(stage_dir))


def human(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB"


def tree_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def main() -> int:
    ap = argparse.ArgumentParser(description="Package Float for distribution (Windows).")
    ap.add_argument("--version", default="1.0", help="version string used in the archive name")
    ap.add_argument("--no-zip", action="store_true", help="stage the folder but skip the archive")
    args = ap.parse_args()

    if not EXE_SRC.exists():
        print(f"error: {EXE_SRC.relative_to(ROOT)} not found -- run build.bat first")
        return 1

    # The exe is the one thing here that can silently go stale.
    newest_src = max(
        (p.stat().st_mtime for p in (ROOT / "engine" / "crates").rglob("*.rs")),
        default=0.0,
    )
    if newest_src > EXE_SRC.stat().st_mtime:
        print("warning: engine sources are newer than flint-player.exe -- run build.bat\n")

    stage_dir = DIST / "Float"
    print(f"staging  {stage_dir.relative_to(ROOT)}")
    stage(stage_dir)

    problems = validate(stage_dir / "data")
    if problems:
        print("\nPACKAGE IS INCOMPLETE:")
        for p in problems:
            print(f"  {p}")
        return 1

    data = stage_dir / "data"
    for name in ("audio", "models", "scripts", "scenes", "sprites", "textures", "schemas", "engine-schemas", "config"):
        print(f"  {name:<16}{human(tree_size(data / name)):>10}")
    print(f"  {'Float.exe':<16}{human((data / 'Float.exe').stat().st_size):>10}")
    print(f"  {'staged total':<16}{human(tree_size(stage_dir)):>10}")

    if not args.no_zip:
        archive = DIST / f"Float-{args.version}-win64.zip"
        print(f"\nzipping  {archive.relative_to(ROOT)}")
        make_zip(stage_dir, archive)
        print(f"  {'archive':<16}{human(archive.stat().st_size):>10}")

    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
