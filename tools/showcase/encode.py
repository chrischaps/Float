"""Site media for the chaps.dev Float page, from cap.py's frame folders.

    python tools/showcase/encode.py [--dest DIR]

Hero: the `day` shot as a seamless loop (its first two seconds are crossfaded
under its last two, and playback starts just after them, so frame 0 is clean).
Clips: trimmed shots, plus the reality tears cut together with crossfades.
Posters and stills: single frames as JPEG.
"""

import argparse
import os
import subprocess

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "renders", "showcase")
FPS = 30
SIZE = "1280:720"

# name -> (shot, capture t0, start s, end s)
CLIPS = {
    "where-you-sit": ("seat", 1.0, 1.0, 17.0),
    "the-deck-hesitates": ("swell", 2.0, 2.0, 12.0),
    "weather": ("storm", 1.5, 1.5, 19.5),
    "dead-calm": ("calm", 1.0, 1.0, 19.0),
    "the-whale": ("whale", 0.5, 0.5, 9.5),
    "the-visitor": ("visitor", 92.0, 92.0, 104.0),
}
TEARS = [("tear_matrix", 0.3, 0.3, 3.8), ("tear_blood", 0.3, 0.6, 5.4),
         ("tear_tron", 0.3, 0.6, 5.4)]
XFADE = 0.5

# poster/still name -> (shot, frame number)
STILLS = {
    "poster-day": ("day", 765),
    "poster-where-you-sit": ("seat", 345),
    "poster-the-deck-hesitates": ("swell", 75),
    "poster-weather": ("storm", 165),
    "poster-dead-calm": ("calm", 400),
    "poster-the-whale": ("whale", 90),
    "poster-the-visitor": ("visitor", 120),
    "poster-reality-tears": ("tear_tron", 111),
    "sunrise": ("day", 60),
    "noon": ("day", 450),
    "the-whale-at-dusk": ("day", 930),
    "night": ("day", 1110),
    "whale-breach": ("whale", 90),
    "dead-calm": ("calm", 400),
    "storm": ("storm", 360),
    "lightning": ("storm", 165),
    "the-swell": ("swell", 75),
    "feet-in-the-water": ("seat", 345),
    "the-visitor": ("visitor", 120),
    "tear-matrix": ("tear_matrix", 30),
    "tear-blood": ("tear_blood", 111),
    "tear-tron": ("tear_tron", 111),
}

X264 = ["-c:v", "libx264", "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-an"]


def frames(shot):
    return os.path.join(SRC, shot, "f_%04d.png")


def first(t0, start):
    return int(round((start - t0) * FPS)) + 1


def ff(args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + args, check=True)


def hero(dest, crf):
    n = len([f for f in os.listdir(os.path.join(SRC, "day")) if f.endswith(".png")])
    blend = 2 * FPS
    body_s = (n - blend) / FPS
    ff(["-framerate", str(FPS), "-i", frames("day"), "-filter_complex",
        "[0]split[a][b];[a]trim=start_frame=%d,setpts=PTS-STARTPTS[body];"
        "[b]trim=end_frame=%d,setpts=PTS-STARTPTS[head];"
        "[body][head]xfade=transition=fade:duration=%g:offset=%g,scale=%s:flags=lanczos[v]"
        % (blend, blend, blend / FPS, body_s - blend / FPS, SIZE),
        "-map", "[v]", "-crf", str(crf)] + X264 + [os.path.join(dest, "a-day-at-sea.mp4")])


def clip(dest, name, shot, t0, start, end, crf):
    ff(["-framerate", str(FPS), "-start_number", str(first(t0, start)), "-i", frames(shot),
        "-frames:v", str(int(round((end - start) * FPS))), "-vf", "scale=%s:flags=lanczos" % SIZE,
        "-crf", str(crf)] + X264 + [os.path.join(dest, name + ".mp4")])


def tears(dest, crf):
    args, chain, offset = [], "", 0.0
    for i, (shot, t0, start, end) in enumerate(TEARS):
        args += ["-framerate", str(FPS), "-start_number", str(first(t0, start)),
                 "-t", "%g" % (end - start), "-i", frames(shot)]
    durs = [e - s for (_, _, s, e) in TEARS]
    prev = "[0]"
    for i in range(1, len(TEARS)):
        offset += durs[i - 1] - XFADE
        out = "[x%d]" % i
        chain += "%s[%d]xfade=transition=fade:duration=%g:offset=%g%s;" % (prev, i, XFADE, offset, out)
        prev = out
    chain += "%sscale=%s:flags=lanczos[v]" % (prev, SIZE)
    ff(args + ["-filter_complex", chain, "-map", "[v]", "-crf", str(crf)] + X264
       + [os.path.join(dest, "reality-tears.mp4")])


def stills(dest):
    for name, (shot, n) in STILLS.items():
        im = Image.open(os.path.join(SRC, shot, "f_%04d.png" % n)).convert("RGB")
        im.save(os.path.join(dest, name + ".jpg"), quality=88, optimize=True)
    im = Image.open(os.path.join(SRC, "under_still.png")).convert("RGB")
    im.save(os.path.join(dest, "underwater.jpg"), quality=88, optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=os.path.join(ROOT, "renders", "showcase", "site"))
    ap.add_argument("--crf", type=int, default=28)
    a = ap.parse_args()
    os.makedirs(a.dest, exist_ok=True)
    hero(a.dest, a.crf + 1)
    for name, spec in CLIPS.items():
        clip(a.dest, name, *spec, a.crf)
    tears(a.dest, a.crf + 3)
    stills(a.dest)
    for f in sorted(os.listdir(a.dest)):
        print("%-34s %6.0f KB" % (f, os.path.getsize(os.path.join(a.dest, f)) / 1024))


if __name__ == "__main__":
    main()
