"""Composite the itch.io cover image for Float.

itch's cover slot is 630x500, and it is shown as small as 315x250 in browse
grids. That second number drives every decision in here: the in-game title
card is Segoe UI Light hairlines at 0.42 em tracking, which is beautiful at
1080p and close to invisible at 315 px wide.

Inputs are the candidate plates rendered by `render.bat cover` into
snapshots/cover/ at 2520x2000 (4x). `flint render` has no MSAA flag and the
ocean's cel bands alias badly, so supersample-then-LANCZOS is the only
anti-aliasing available.

Usage:
    python tools/generate_cover.py --sheet     # contact sheet of all candidates
    python tools/generate_cover.py --pick a --treatment lower --width-frac 0.72
                                               # write the final press/ deliverable

The wordmark is NOT downscaled from sprites/title_setdrift.png (2713 px wide;
a 7x reduction averages the hairlines down to faint gray). It is re-rendered
through generate_title.render_card at 2x the target width and halved, so the
strokes stay full-white.
"""

import argparse
import contextlib
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate_title as gt  # noqa: E402  — reuse the real typography

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLATE_DIR = os.path.join(ROOT, "snapshots", "cover")
OUT_DIR = os.path.join(ROOT, "press")

COVER_W, COVER_H = 630, 500
THUMB_W, THUMB_H = 315, 250        # itch's browse-grid size — the real test

# scripts/title.rhai draws the card at this tint, not pure white. Matching it
# makes the cover read as the game's actual first frame.
TINT = (255, 252, 245)
TITLE_ALPHA = 0.94

# render_card("SET + DRIFT", 280, 0.42) measures 2713 px wide. Used to solve
# for the font size that lands on a requested pixel width.
REF_SIZE, REF_WIDTH, TRACKING = 280, 2713, 0.42

PLATES = {
    "a": ("plate_a.png", "close 3/4, figure seated"),
    "b": ("plate_b.png", "wide, raft small"),
    "c": ("plate_c.png", "POV, legs over the water"),
}
TREATMENTS = ("none", "lower", "mid", "upper")


@contextlib.contextmanager
def title_font(semilight, halo):
    """Temporarily retune generate_title for cover use.

    Two overrides, both local to this call and never written back to the
    in-game sprites:

    - Segoe UI Light is the brand face, but at 315 px its stems fall under a
      pixel. Semilight is the escape hatch and is already in the candidate
      list, so this borrows it.
    - The in-game card's 0.55-alpha shadow is tuned for a card that MOVES over
      live water. A static cover on a high-key mid-morning plate has nowhere
      dark for white type to sit, so `halo` deepens and widens the shadow into
      a soft dark aura that hugs the letterforms. That beats a flat scrim
      band, which just reads as a gray bar across the picture.
    """
    saved = (gt.FONT_CANDIDATES, gt.SHADOW_ALPHA,
             gt.SHADOW_BLUR_FRAC, gt.SHADOW_DROP_FRAC)
    if semilight:
        gt.FONT_CANDIDATES = [r"C:\Windows\Fonts\segoeuisl.ttf"] + saved[0]
    if halo > 0:
        gt.SHADOW_ALPHA = min(1.0, saved[1] + halo)
        gt.SHADOW_BLUR_FRAC = saved[2] * (1.0 + 1.8 * halo)
        gt.SHADOW_DROP_FRAC = saved[3] * 0.4      # centered aura, not a drop
    try:
        yield
    finally:
        (gt.FONT_CANDIDATES, gt.SHADOW_ALPHA,
         gt.SHADOW_BLUR_FRAC, gt.SHADOW_DROP_FRAC) = saved


def wordmark(width_px, semilight=False, halo=0.35, supersample=2):
    """"SET + DRIFT" as RGBA, tinted, exactly `width_px` wide."""
    size = max(8, round(REF_SIZE * width_px * supersample / REF_WIDTH))
    with title_font(semilight, halo):
        card = gt.render_card("SET + DRIFT", size, TRACKING)

    h = max(1, round(card.height * width_px / card.width))
    card = card.resize((width_px, h), Image.LANCZOS)

    # render_card returns white glyphs over a black shadow; recolor only the
    # glyph pixels, leaving the shadow black.
    r, g, b, a = card.split()
    lum = np.asarray(r, dtype=np.float32) / 255.0          # 1 on glyphs, 0 on shadow
    px = np.asarray(card, dtype=np.float32)
    for i, c in enumerate(TINT):
        px[..., i] = lum * c
    px[..., 3] *= TITLE_ALPHA
    return Image.fromarray(px.clip(0, 255).astype(np.uint8), "RGBA")


def scrim(size, band, strength=0.28, invert=False):
    """Soft dark gradient behind the wordmark band.

    The in-game card is legible because it MOVES over live water; a static
    cover has no such help. `band` is (start, end) in 0..1 of height, eased
    with a smoothstep so no edge shows.
    """
    w, h = size
    y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    lo, hi = band
    t = np.clip((y - lo) / max(1e-6, hi - lo), 0.0, 1.0)
    t = t * t * (3.0 - 2.0 * t)
    if invert:
        t = 1.0 - t
    alpha = (t * strength * 255.0).astype(np.uint8)
    layer = np.zeros((h, w, 4), dtype=np.uint8)
    layer[..., 3] = np.repeat(alpha, w, axis=1)
    return Image.fromarray(layer, "RGBA")


# Where the wordmark can sit, per plate — driven by where each composition
# leaves quiet space, not by a shared rule. A's raft occupies the middle, B's
# sea is busy with foam everywhere but the low water, C's clean cyan gap
# between the horizon foam and the knees is the whole point of the shot.
PLACEMENT = {
    "a": {"lower": 0.88, "upper": 0.11, "mid": 0.62},
    "b": {"lower": 0.86, "upper": 0.10, "mid": 0.62},
    "c": {"lower": 0.72, "upper": 0.10, "mid": 0.45},
}


def compose(plate, treatment="lower", width_frac=0.72, semilight=False,
            scrim_strength=0.0, key="a", halo=0.35):
    """One 630x500 candidate."""
    img = plate.convert("RGBA").resize((COVER_W, COVER_H), Image.LANCZOS)
    if treatment == "none":
        return img

    center_y = PLACEMENT.get(key, PLACEMENT["a"])[treatment]
    if scrim_strength > 0:
        band = (0.0, 0.34) if treatment == "upper" else (0.58, 1.0)
        img.alpha_composite(
            scrim(img.size, band, scrim_strength, treatment == "upper"))

    mark = wordmark(round(COVER_W * width_frac), semilight, halo)
    img.alpha_composite(mark, ((COVER_W - mark.width) // 2,
                               round(COVER_H * center_y) - mark.height // 2))
    return img


# ---------------------------------------------------------------- contact sheet

PAGE_BG = (58, 60, 64)
LABEL = (232, 234, 238)


def _label(draw, xy, text, font):
    draw.text(xy, text, font=font, fill=LABEL)


def contact_sheet(width_fracs=(0.72, 0.84, 0.90), semilight=False):
    """Every candidate at 630x500 beside the same image at 315x250, plus a
    mock browse-grid row. A cover that wins at full size and dies in the grid
    is the wrong cover, so both have to be visible at once.
    """
    from PIL import ImageDraw, ImageFont

    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 17)
        small = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 14)
    except OSError:
        font = small = ImageFont.load_default()

    pad, gap, head = 28, 20, 46
    rows = []
    for key, (fname, desc) in PLATES.items():
        path = os.path.join(PLATE_DIR, fname)
        if not os.path.exists(path):
            print(f"  missing plate: {path}")
            continue
        plate = Image.open(path)
        for treatment in TREATMENTS:
            fracs = (0.0,) if treatment == "none" else width_fracs
            for wf in fracs:
                rows.append((key, desc, treatment, wf,
                             compose(plate, treatment, wf or 0.72, semilight,
                                     key=key)))

    if not rows:
        raise SystemExit("no plates found — run `render.bat cover` first")

    row_h = COVER_H + head + gap
    sheet_w = pad * 2 + COVER_W + gap + THUMB_W + gap + THUMB_W * 3 + gap * 2
    sheet = Image.new("RGB", (sheet_w, pad * 2 + row_h * len(rows)), PAGE_BG)
    draw = ImageDraw.Draw(sheet)

    for i, (key, desc, treatment, wf, img) in enumerate(rows):
        y = pad + i * row_h
        tag = f"{key.upper()} — {desc}   ·   wordmark: {treatment}"
        if treatment != "none":
            tag += f" @ {wf:.2f}"
        _label(draw, (pad, y + 12), tag, font)
        y += head

        flat = img.convert("RGB")
        sheet.paste(flat, (pad, y))
        _label(draw, (pad, y + COVER_H + 3), "630x500", small)

        thumb = flat.resize((THUMB_W, THUMB_H), Image.LANCZOS)
        x = pad + COVER_W + gap
        sheet.paste(thumb, (x, y))
        _label(draw, (x, y + THUMB_H + 3), "315x250  <- judge here", small)

        # mock browse grid: the same tile repeated, so it is read against
        # neighbours rather than in isolation
        gx = x + THUMB_W + gap
        for n in range(3):
            sheet.paste(thumb, (gx + n * (THUMB_W + 8), y + THUMB_H // 2))

    out = os.path.join(PLATE_DIR, "contact_sheet.png")
    sheet.save(out)
    print(f"contact sheet: {out}  ({sheet.width}x{sheet.height}, {len(rows)} candidates)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", action="store_true", help="build the contact sheet")
    ap.add_argument("--pick", choices=sorted(PLATES), help="write the final cover")
    ap.add_argument("--treatment", choices=TREATMENTS, default="lower")
    ap.add_argument("--width-frac", type=float, default=0.72)
    ap.add_argument("--scrim", type=float, default=0.0,
                    help="flat gradient band behind the type; the halo is "
                         "usually the better tool on a high-key plate")
    ap.add_argument("--halo", type=float, default=0.35,
                    help="extra shadow alpha/blur under the glyphs")
    ap.add_argument("--semilight", action="store_true",
                    help="use Segoe UI Semilight — heavier stems at 315 px")
    args = ap.parse_args()

    if args.sheet:
        contact_sheet(semilight=args.semilight)
    if args.pick:
        os.makedirs(OUT_DIR, exist_ok=True)
        plate = Image.open(os.path.join(PLATE_DIR, PLATES[args.pick][0]))
        img = compose(plate, args.treatment, args.width_frac,
                      args.semilight, args.scrim, args.pick, args.halo)
        out = os.path.join(OUT_DIR, "cover_630x500.png")
        img.convert("RGB").save(out)
        print(f"cover: {out}  ({img.width}x{img.height})")
    if not args.sheet and not args.pick:
        ap.print_help()


if __name__ == "__main__":
    main()
