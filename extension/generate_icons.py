#!/usr/bin/env python3
"""Generate the Trade Bridge extension icons (16/32/48/128 px PNG).

Design: a "stash-bronze" currency coin on a dark stash-tab tile, bearing a
bold "1" (PoE *1* -- also distinguishes this from the PoE2 sibling and
reinforces the one-identity trust rule). Drawn at 8x supersample and
downscaled with LANCZOS for crisp antialiased edges at every store size.

Palette pulled from the stash UI skin (bpc/ui/stash.html) + popup accent:
  tile dark   #15100a / #1a140d
  bronze coin #e6c074 -> #b07f34 (light->dark), midtone #c8aa6e
  coin rim    #7a5a28
  glyph dark  #160f08

Run:  python extension/generate_icons.py
Writes: extension/icons/icon{16,32,48,128}.png
Only depends on Pillow. Re-run any time; output is deterministic.
"""
import os
from PIL import Image, ImageDraw, ImageFont

SS = 8  # supersample factor
SIZES = [16, 32, 48, 128]
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")

TILE_DARK   = (26, 20, 13, 255)     # #1a140d
TILE_DARK2  = (18, 13, 8, 255)      # #120d08 (corner shade)
TILE_BORDER = (122, 90, 40, 255)    # #7a5a28
COIN_LIGHT  = (230, 192, 116, 255)  # #e6c074
COIN_MID    = (200, 170, 110, 255)  # #c8aa6e
COIN_DARK   = (176, 127, 52, 255)   # #b07f34
COIN_RIM    = (122, 90, 40, 255)    # #7a5a28
GLYPH_DARK  = (22, 15, 8, 255)      # #160f08


def _font(px):
    """Bold TrueType if we can find one, else Pillow's bundled default."""
    for name in ("arialbd.ttf", "seguisb.ttf", "segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except Exception:
            continue
    try:
        return ImageFont.load_default(px)
    except Exception:
        return ImageFont.load_default()


def _rounded_tile(draw, box, radius, fill, outline, width):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _radial_coin(size, cx, cy, r):
    """A soft radial-shaded bronze disc (light top-left -> dark bottom-right)."""
    coin = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    cd = ImageDraw.Draw(coin)
    steps = max(24, r // 2)
    for i in range(steps, 0, -1):
        t = i / steps                      # 1 at edge -> 0 at center
        # blend light(center) -> dark(edge)
        col = tuple(
            int(COIN_LIGHT[k] * (1 - t) + COIN_DARK[k] * t) for k in range(3)
        ) + (255,)
        rr = int(r * t)
        # offset the highlight toward top-left for a lit-coin feel
        ox = int(r * 0.10 * (1 - t))
        oy = int(r * 0.10 * (1 - t))
        cd.ellipse([cx - rr - ox, cy - rr - oy, cx + rr - ox, cy + rr - oy], fill=col)
    return coin


def render(px):
    size = px * SS
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # --- stash-tab tile ---
    margin = int(size * 0.04)
    radius = int(size * 0.20)
    _rounded_tile(
        d, [margin, margin, size - margin, size - margin],
        radius=radius, fill=TILE_DARK, outline=TILE_BORDER, width=max(SS, int(size * 0.03)),
    )

    # --- bronze coin ---
    cx = cy = size // 2
    r = int(size * 0.34)
    # rim
    d.ellipse([cx - r - int(size * 0.02), cy - r - int(size * 0.02),
               cx + r + int(size * 0.02), cy + r + int(size * 0.02)], fill=COIN_RIM)
    coin = _radial_coin(size, cx, cy, r)
    img = Image.alpha_composite(img, coin)
    d = ImageDraw.Draw(img)
    # subtle inner ring for a minted-coin read
    d.ellipse([cx - int(r * 0.82), cy - int(r * 0.82),
               cx + int(r * 0.82), cy + int(r * 0.82)],
              outline=COIN_RIM, width=max(SS // 2, int(size * 0.012)))

    # --- glyph: bold "1" ---
    fpx = int(r * 1.5)
    font = _font(fpx)
    txt = "1"
    try:
        bbox = d.textbbox((0, 0), txt, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = cx - tw / 2 - bbox[0]
        ty = cy - th / 2 - bbox[1]
    except Exception:
        tw, th = d.textsize(txt, font=font)
        tx, ty = cx - tw / 2, cy - th / 2
    d.text((tx, ty), txt, font=font, fill=GLYPH_DARK)

    return img.resize((px, px), Image.LANCZOS)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for px in SIZES:
        out = os.path.join(OUT_DIR, "icon%d.png" % px)
        render(px).save(out, "PNG")
        print("wrote", out)


if __name__ == "__main__":
    main()
