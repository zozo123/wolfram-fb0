"""Render the US flag for Memorial Day, in the same framebuffer aesthetic as
the rest of the project. Outputs:

  media/flag.png  — static, 760×400, official Old-Glory colours, 50 stars
                    laid out per Executive Order 10834 (1959).
  media/flag.gif  — subtle 1.5 s fade-in from black, then hold, then loop.
                    No "drawing" animation — Memorial Day deserves quiet.

Run: python3 media/make_flag.py
"""
from __future__ import annotations
import math
from pathlib import Path
from PIL import Image, ImageDraw

# Flag canvas — 1:1.9 ratio per the official spec.
W, H = 760, 400

# Old Glory colours.
RED = (178, 34, 52)        # Pantone 193 → #B22234
WHITE = (255, 255, 255)
BLUE = (60, 59, 110)       # Pantone 282 → #3C3B6E
BLACK = (0, 0, 0)

# Geometry.
STRIPE_H = H / 13.0
CANTON_W = W * 0.40        # 2/5 of flag length
CANTON_H = STRIPE_H * 7    # 7 stripes tall


def draw_star(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill) -> None:
    """5-pointed star centred at (cx, cy), outer radius r."""
    pts: list[tuple[float, float]] = []
    inner = r * 0.382  # golden-ratio inner radius for a clean 5-pointed star
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else inner
        pts.append((cx + rr * math.cos(angle), cy + rr * math.sin(angle)))
    draw.polygon(pts, fill=fill)


def render_flag() -> Image.Image:
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    # 13 stripes — red, white, red, ..., starting and ending with red.
    for i in range(13):
        color = RED if i % 2 == 0 else WHITE
        y0 = round(i * STRIPE_H)
        y1 = round((i + 1) * STRIPE_H)
        d.rectangle((0, y0, W, y1), fill=color)

    # Canton (union) — solid blue field, top-left.
    d.rectangle((0, 0, round(CANTON_W), round(CANTON_H)), fill=BLUE)

    # 50 stars: 9 rows alternating 6-5-6-5-6-5-6-5-6.
    # 12-column half-spacing grid horizontally; 10-row half-spacing vertically.
    col_w = CANTON_W / 12.0
    row_h = CANTON_H / 10.0
    star_r = row_h * 0.45    # star outer radius ~ 4/10 of row spacing

    for row_idx in range(1, 10):
        if row_idx % 2 == 1:        # 6-star row: cols 1, 3, 5, 7, 9, 11
            cols = [1, 3, 5, 7, 9, 11]
        else:                        # 5-star row: cols 2, 4, 6, 8, 10
            cols = [2, 4, 6, 8, 10]
        cy = row_h * row_idx
        for c in cols:
            cx = col_w * c
            draw_star(d, cx, cy, star_r, WHITE)

    return img


def main() -> None:
    here = Path(__file__).parent
    flag = render_flag()
    flag.save(here / "flag.png", optimize=True)
    print(f"wrote {here/'flag.png'}")

    # Subtle fade-in GIF: 18 fade frames + 12 hold frames at ~16 fps = ~1.9 s.
    n_fade, n_hold = 18, 12
    duration_ms = 60
    black = Image.new("RGB", (W, H), BLACK)
    frames: list[Image.Image] = []
    for f in range(n_fade + n_hold):
        if f < n_fade:
            alpha = (f + 1) / n_fade
            frames.append(Image.blend(black, flag, alpha))
        else:
            frames.append(flag.copy())

    out_gif = here / "flag.gif"
    frames[0].save(
        out_gif,
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"wrote {out_gif} ({out_gif.stat().st_size / 1024:.1f} KB, {len(frames)} frames)")


if __name__ == "__main__":
    main()
