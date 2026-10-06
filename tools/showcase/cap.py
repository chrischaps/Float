"""Float showcase capture: the real game, frame by frame.

    python tools/showcase/cap.py SHOT [SHOT ...] [--preview] [--out DIR] [-j N]

Each shot runs flint-player on a patched copy of scenes/float.scene.toml:
  * `set` entries override scene fields (time of day, forced weather, event
    one-shots like dead_calm.trigger_calm or reality.trigger_mode);
  * the title card is off unless the shot asks for it;
  * with a `camera`, tools/showcase/showcase_camera.rhai takes the view and a
    temp copy of seat_camera.rhai stops writing the camera (the seat script
    still runs: body.rhai reads what it publishes). Without one, the shot is
    the real first-person seat, steered by `input` (gamepad sticks, keys);
  * the seat copy never captures the mouse, so captures can run in the
    background while the machine is in use;
  * `--frame-step 1/fps` advances the game exactly one frame per frame and
    every frame between t0 and t1 is written, so the footage is smooth however
    slow the capture runs and every run of a shot plays out identically
    (apart from the scripts' own random draws: weather, birds, scheduling).

--preview: 640x360, a frame every 0.5 s, stitched into <out>/<shot>_sheet.jpg.
Default (final): 1920x1080 at 30 fps into <out>/<shot>/f_NNNN.png, then
<out>/<shot>.mp4 (x264 CRF 14 master; site encodes are made from it).

Shots live in tools/showcase/shots.py. Temp scenes/scripts are named _cap_*
and removed afterwards.
"""

import argparse
import concurrent.futures as cf
import glob
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
PLAYER = os.path.join(ROOT, "engine", "target", "release", "flint-player.exe")
sys.path.insert(0, HERE)
from shots import SHOTS  # noqa: E402


def rhai_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return '"%s"' % v
    if isinstance(v, int):
        return str(v)
    return repr(float(v))


def toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return '"%s"' % v
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    return repr(float(v)) if isinstance(v, float) else str(v)


def camera_script(params):
    src = open(os.path.join(HERE, "showcase_camera.rhai"), encoding="utf-8").read()
    m = re.search(r"// >>> PARAMS\n(.*?)// <<< PARAMS", src, flags=re.S)
    defaults = dict(re.findall(r"let (\w+) = (.*?);", m.group(1)))
    for k, v in params.items():
        if k not in defaults:
            raise ValueError("unknown camera param %s" % k)
        defaults[k] = rhai_value(v)
    block = "".join("let %s = %s;\n" % kv for kv in defaults.items())
    return src[:m.start(1)] + block + src[m.end(1):]


def seat_script(external):
    """seat_camera.rhai without the mouse grab (and, for external cameras,
    without the camera writes and the underwater mode)."""
    src = open(os.path.join(ROOT, "scripts", "seat_camera.rhai"), encoding="utf-8").read()
    src, n = re.subn(r"set_cursor_captured\(true\);", "// (cap) no mouse grab", src)
    assert n >= 2, "seat_camera.rhai: cursor capture calls moved"
    if external:
        src, n = re.subn(r"^(\s*)(set_camera_(position|target)\()", r"\1// (cap) \2", src, flags=re.M)
        assert n == 2, "seat_camera.rhai: camera writes moved"
        src, n = re.subn(r"if uw_mix > 0\.001 \{", "if false && uw_mix > 0.001 {", src)
        assert n == 1, "seat_camera.rhai: underwater block moved"
    return src


def set_field(text, table, field, value):
    """Set `field = value` inside [table], or add it if the table lacks it."""
    v = toml_value(value)
    pat = re.compile(r"(^\[" + re.escape(table) + r"\]\s*$(?:(?!^\[).)*?^)" + re.escape(field)
                     + r"\s*=[^\n#]*", re.M | re.S)
    new, n = pat.subn(lambda m: m.group(1) + "%s = %s " % (field, v), text, count=1)
    if n:
        return new
    head = re.compile(r"^\[" + re.escape(table) + r"\]\s*$", re.M)
    m = head.search(text)
    if not m:
        raise ValueError("no table [%s]" % table)
    return text[:m.end()] + "\n%s = %s" % (field, v) + text[m.end():]


def build_variant(name, shot):
    text = open(os.path.join(ROOT, "scenes", "float.scene.toml"), encoding="utf-8").read()
    tag = "_cap_" + name
    temps = []
    external = "camera" in shot

    sets = [("entities.title_controller.title", "enabled", False)] if not shot.get("title") else []
    sets += shot.get("set", [])
    for (table, field, value) in sets:
        text = set_field(text, table, field, value)

    seat_file = tag + "_seat.rhai"
    text = set_field(text, "entities.seat_camera.script", "source", seat_file)
    p = os.path.join(ROOT, "scripts", seat_file)
    with open(p, "w", encoding="utf-8") as f:
        f.write(seat_script(external))
    temps.append(p)

    text += "\n\n# --- showcase capture (tools/showcase/cap.py) ---\n" + shot.get("append", "")
    if external:
        cam_file = tag + "_camera.rhai"
        text += ('\n[entities.showcase_camera]\n[entities.showcase_camera.script]\nsource = "%s"\n'
                 % cam_file)
        p = os.path.join(ROOT, "scripts", cam_file)
        with open(p, "w", encoding="utf-8") as f:
            f.write(camera_script(shot["camera"]))
        temps.append(p)

    scene_out = os.path.join(ROOT, "scenes", tag + ".scene.toml")
    with open(scene_out, "w", encoding="utf-8") as f:
        f.write(text)
    temps.append(scene_out)
    inp = os.path.join(ROOT, "scenes", tag + ".input.txt")
    with open(inp, "w", encoding="utf-8") as f:
        f.write(shot.get("input", "").replace(";", "\n") + "\n")
    temps.append(inp)
    return scene_out, inp, temps


def run_shot(name, out, preview, keep=False):
    shot = SHOTS[name]
    scene, inp, temps = build_variant(name, shot)
    fps = shot.get("fps", 30)
    step = shot.get("step", 1.0 / fps)        # game seconds per frame (> 1/fps = time-lapse)
    t0, t1 = shot["t"]
    if shot.get("still"):
        return run_still(name, shot, scene, inp, temps, out, t0, preview)
    if preview:
        w, h = 640, 360
        every = shot.get("preview_every", 0.5) * step * fps
        frames_dir = os.path.join(out, "_prev_" + name)
    else:
        w, h = shot.get("size", (1920, 1080))
        every, frames_dir = step, os.path.join(out, name)
    shutil.rmtree(frames_dir, ignore_errors=True)
    os.makedirs(frames_dir)
    cmd = [PLAYER, scene, "--schemas", "engine/schemas", "--schemas", "schemas",
           "--width", str(w), "--height", str(h), "--music-volume", "0", "--sfx-volume", "0",
           "--frame-step", repr(step), "--input-script", inp,
           "--screenshot", os.path.join(frames_dir, "f.png"), "--screenshot-at", repr(t0),
           "--screenshot-every", repr(every), "--exit-after", repr(t1)]
    if not preview:
        cmd += ["--msaa", "4"]
    env = dict(os.environ, FLINT_VSYNC="0", RUST_LOG="warn,script=info")
    try:
        r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    finally:
        if not keep:
            for p in temps:
                try:
                    os.remove(p)
                except OSError:
                    pass
    log = r.stdout + r.stderr
    with open(os.path.join(out, name + "_log.txt"), "w", encoding="utf-8") as f:
        f.write(log)
    errs = [l for l in log.splitlines() if ("rror" in l or "panic" in l) and "atlas" not in l]
    frames = sorted(glob.glob(os.path.join(frames_dir, "f_*.png")))
    msg = "%s: %d frames%s" % (name, len(frames), ("; " + " | ".join(errs[:4])) if errs else "")
    if preview:
        sheet(frames, os.path.join(out, name + "_sheet.jpg"), t0, every)
    elif frames:
        mp4 = os.path.join(out, name + ".mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i",
                        os.path.join(frames_dir, "f_%04d.png"), "-c:v", "libx264", "-crf", "14",
                        "-preset", "slow", "-pix_fmt", "yuv420p", mp4], check=True)
    return msg


def run_still(name, shot, scene, inp, temps, out, t0, preview):
    """One frame at game time t0 -> <out>/<name>.png."""
    w, h = (960, 540) if preview else shot.get("size", (2560, 1440))
    png = os.path.join(out, name + ".png")
    cmd = [PLAYER, scene, "--schemas", "engine/schemas", "--schemas", "schemas",
           "--width", str(w), "--height", str(h), "--music-volume", "0", "--sfx-volume", "0",
           "--frame-step", repr(1.0 / shot.get("fps", 30)), "--input-script", inp,
           "--screenshot", png, "--screenshot-at", repr(t0), "--exit-after", repr(t0 + 0.2)]
    if not preview:
        cmd += ["--msaa", "4"]
    try:
        r = subprocess.run(cmd, cwd=ROOT, env=dict(os.environ, FLINT_VSYNC="0"),
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    finally:
        for p in temps:
            try:
                os.remove(p)
            except OSError:
                pass
    return "%s: %s" % (name, "ok" if os.path.exists(png) else "NO FRAME " + r.stderr[-300:])


def sheet(frames, path, t0, every, per_page=16):
    """Contact sheets, 4x4 per page: <path>, <path stem>_2.jpg, ..."""
    from PIL import Image, ImageDraw
    cols, tw, th = 4, 400, 225
    for page in range(0, len(frames), per_page):
        chunk = frames[page:page + per_page]
        rows = (len(chunk) + cols - 1) // cols
        S = Image.new("RGB", (cols * tw, rows * th), (0, 0, 0))
        d = ImageDraw.Draw(S)
        for i, f in enumerate(chunk):
            im = Image.open(f).convert("RGB").resize((tw, th))
            x, y = (i % cols) * tw, (i // cols) * th
            S.paste(im, (x, y))
            d.text((x + 4, y + 4), "t=%.1f" % (t0 + (page + i) * every), fill=(255, 255, 0))
        n = page // per_page + 1
        S.save(path if n == 1 else path.replace(".jpg", "_%d.jpg" % n), quality=80)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shots", nargs="+")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--keep", action="store_true", help="leave the _cap_ temp files")
    ap.add_argument("--out", default=os.path.join(ROOT, "renders", "showcase"))
    ap.add_argument("-j", type=int, default=2)
    a = ap.parse_args()
    names = list(SHOTS) if a.shots == ["all"] else a.shots
    os.makedirs(a.out, exist_ok=True)
    with cf.ThreadPoolExecutor(a.j) as ex:
        for msg in ex.map(lambda n: run_shot(n, a.out, a.preview, a.keep), names):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
