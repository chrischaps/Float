"""Generate the title-card sprites for Float.

Renders two tightly-cropped RGBA PNGs into sprites/ (the engine's UI
sprite search path is scene_dir/sprites -> game_root/sprites):

  sprites/title_setdrift.png  "SET + DRIFT" — Segoe UI Light, wide tracking
  sprites/title_presskey.png  "PRESS ANY KEY" — smaller caps, wider tracking

Both are pure white glyphs over a soft drop shadow (so the card reads on
bright noon skies AND star fields); scripts/title.rhai tints and fades
them. The script hardcodes each sprite's aspect ratio AND the prompt's
width relative to the title — this tool prints all three on every run and
checks them against scripts/title.rhai, because a stale const does not
error, it silently stretches the sprite.

Usage: python tools/generate_title.py
"""

import os
import re

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "sprites")

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\segoeuil.ttf",   # Segoe UI Light — the intended face
    r"C:\Windows\Fonts\segoeuisl.ttf",  # Semilight fallback
    r"C:\Windows\Fonts\segoeui.ttf",
]

SHADOW_BLUR_FRAC = 0.055   # gaussian radius as a fraction of font size
SHADOW_DROP_FRAC = 0.030   # vertical offset as a fraction of font size
SHADOW_ALPHA = 0.55        # shadow strength under the white glyphs

# "+" sits on the font's math axis, which is noticeably below the optical
# center of a line of caps. Lift it so it floats level between the two
# words instead of sagging.
RISE_EM = {"+": 0.05}      # per-glyph baseline lift, in em


def load_font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    raise FileNotFoundError("no candidate title font found in C:\\Windows\\Fonts")


def render_card(text, font_size, tracking_em):
    """Tightly-cropped RGBA image: white text + soft shadow, letter-spaced."""
    font = load_font(font_size)
    tracking = font_size * tracking_em

    # Lay out per-glyph so tracking is exact (PIL has no tracking control).
    advances = [font.getlength(ch) for ch in text]
    total_w = sum(advances) + tracking * (len(text) - 1)

    pad = int(font_size * 0.6)  # room for shadow blur + descenders
    w = int(total_w) + 2 * pad
    h = int(font_size * 1.6) + 2 * pad

    glyphs = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(glyphs)
    x = float(pad)
    for ch, adv in zip(text, advances):
        rise = font_size * RISE_EM.get(ch, 0.0)
        draw.text((x, pad - rise), ch, font=font, fill=255)
        x += adv + tracking

    blur = font_size * SHADOW_BLUR_FRAC
    drop = int(round(font_size * SHADOW_DROP_FRAC))
    shadow = glyphs.filter(ImageFilter.GaussianBlur(blur)).point(
        lambda v: int(v * SHADOW_ALPHA)
    )

    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste((0, 0, 0, 255), (0, drop), mask=shadow)
    out.paste((255, 255, 255, 255), (0, 0), mask=glyphs)

    bbox = out.getbbox()
    margin = max(2, int(blur * 2))
    out = out.crop(
        (
            max(0, bbox[0] - margin),
            max(0, bbox[1] - margin),
            min(w, bbox[2] + margin),
            min(h, bbox[3] + margin),
        )
    )
    return out


def check_script(consts):
    """Compare the sprites just written against title.rhai's hardcoded
    consts and print the exact replacement lines on any drift.

    Worth the 20 lines: the script SCALES each sprite by these numbers, so
    a stale one doesn't error — it silently stretches the art. Dropping the
    descender from "Press Any Key" to "PRESS ANY KEY" shortened the prompt
    sprite and left it drawing 30% too tall until someone noticed by eye.
    """
    path = os.path.join(ROOT, "scripts", "title.rhai")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as exc:  # not fatal — the sprites are already written
        print(f"\n  could not check title.rhai ({exc})")
        return

    stale = []
    for name, (value, places) in consts.items():
        found = re.search(rf"const\s+{name}\s*=\s*([0-9.]+)", src)
        want = round(value, places)
        if found is None or abs(float(found.group(1)) - want) > 10 ** -places:
            stale.append((name, found and found.group(1), want, places))

    if not stale:
        print("\nscripts/title.rhai: consts match")   # ASCII: cp1252 console
        return
    print("\nscripts/title.rhai IS STALE - sprites will draw distorted.")
    for name, had, want, places in stale:
        print(f"  {name}: script has {had or '(missing)'}, needs "
              f"{want:.{places}f}")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    cards = [
        # SET + DRIFT: the navigator's pair — the direction a current
        # carries you and how fast. Tracking is pulled in from ADRIFT's
        # 0.55 because 11 glyphs at that width outgrow the screen; the
        # words still breathe, and the "+" holds the gap between them.
        ("title_setdrift.png", "SET + DRIFT", 280, 0.42),
        # All caps, so the size drops from the title-case 92: a line of
        # caps carries its mass at CAP height where mixed case carried it
        # at x-height, and at equal point size the prompt shouted. 72 puts
        # the caps back at roughly the old x-height; the opened-up
        # tracking keeps it quiet and echoes the title above it.
        ("title_presskey.png", "PRESS ANY KEY", 72, 0.34),
    ]
    widths = {}
    aspects = {}
    for name, text, size, tracking in cards:
        img = render_card(text, size, tracking)
        path = os.path.join(OUT_DIR, name)
        img.save(path)
        widths[name] = img.width
        aspects[name] = img.height / img.width
        print(
            f"{name}: {img.width}x{img.height}  "
            f"aspect(h/w) = {img.height / img.width:.5f}"
        )

    check_script(
        {
            "TITLE_ASPECT": (aspects["title_setdrift.png"], 5),
            "SUB_ASPECT": (aspects["title_presskey.png"], 5),
            "SUB_REL_W": (
                widths["title_presskey.png"] / widths["title_setdrift.png"],
                4,
            ),
        }
    )


if __name__ == "__main__":
    main()
