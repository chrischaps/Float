"""Generate the title-card sprites for Float.

Renders two tightly-cropped RGBA PNGs into sprites/ (the engine's UI
sprite search path is scene_dir/sprites -> game_root/sprites):

  sprites/title_adrift.png    "ADRIFT" — Segoe UI Light, generous tracking
  sprites/title_presskey.png  "Press Any Key" — smaller, softer tracking

Both are pure white glyphs over a soft drop shadow (so the card reads on
bright noon skies AND star fields); scripts/title.rhai tints and fades
them. The script hardcodes each sprite's aspect ratio — this tool prints
them on every run; keep title.rhai in sync if the text or font changes.

Usage: python tools/generate_title.py
"""

import os

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
        draw.text((x, pad), ch, font=font, fill=255)
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


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    cards = [
        # ADRIFT: wide-open tracking — the word itself drifts apart.
        ("title_adrift.png", "ADRIFT", 280, 0.55),
        # As typed by design: title case, quieter tracking.
        ("title_presskey.png", "Press Any Key", 92, 0.24),
    ]
    for name, text, size, tracking in cards:
        img = render_card(text, size, tracking)
        path = os.path.join(OUT_DIR, name)
        img.save(path)
        print(
            f"{name}: {img.width}x{img.height}  "
            f"aspect(h/w) = {img.height / img.width:.5f}"
        )


if __name__ == "__main__":
    main()
