"""Generate media/rule30.gif — a simple Rule 30 animation for LinkedIn.

Pillow-only (no numpy), runs anywhere with python3 + Pillow installed.
Pure visual, no text overlay, loops infinitely. Matches project palette.

Run: python3 media/make_rule30_gif.py
"""
from pathlib import Path
from PIL import Image

W, H = 800, 320
GROW_FRAMES = 40
HOLD_FRAMES = 8
N_FRAMES = GROW_FRAMES + HOLD_FRAMES
DURATION_MS = 55         # ~18 fps → ~2.6 s loop

ON = (220, 60, 255)
OFF = (10, 10, 18)
FRONTIER = (255, 180, 255)

# Simulate the full Rule 30 grid as a list of bitstrings (rows).
row = [0] * W
row[W // 2] = 1
grid: list[list[int]] = [row[:]]
for _ in range(H - 1):
    nxt = [0] * W
    for x in range(W):
        l = row[(x - 1) % W]
        c = row[x]
        r = row[(x + 1) % W]
        nxt[x] = l ^ (c | r)
    grid.append(nxt)
    row = nxt

# Build the FINAL fully-rendered image once (slow Python loop, runs ×1).
full_buf = bytearray(W * H * 3)
ON_b = bytes(ON)
OFF_b = bytes(OFF)
for y in range(H):
    base = y * W * 3
    grow = grid[y]
    for x in range(W):
        i = base + x * 3
        full_buf[i:i + 3] = ON_b if grow[x] else OFF_b
full_img = Image.frombytes("RGB", (W, H), bytes(full_buf))

# Helper: build a frontier-coloured 1-row strip for a given row index.
def frontier_strip(y: int) -> Image.Image:
    buf = bytearray(W * 3)
    front_b = bytes(FRONTIER)
    grow = grid[y]
    for x in range(W):
        i = x * 3
        buf[i:i + 3] = front_b if grow[x] else OFF_b
    return Image.frombytes("RGB", (W, 1), bytes(buf))

# Cache frontier strips to avoid rebuilding them per frame.
strip_cache: dict[int, Image.Image] = {}

frames: list[Image.Image] = []
for f in range(N_FRAMES):
    if f < GROW_FRAMES:
        rows_shown = max(1, int((f + 1) * H / GROW_FRAMES))
    else:
        rows_shown = H

    frame = Image.new("RGB", (W, H), OFF)
    if rows_shown > 0:
        frame.paste(full_img.crop((0, 0, W, rows_shown)), (0, 0))

    # Brighter frontier line during growth.
    if f < GROW_FRAMES and rows_shown < H:
        y = rows_shown - 1
        if y not in strip_cache:
            strip_cache[y] = frontier_strip(y)
        frame.paste(strip_cache[y], (0, y))

    frames.append(frame)

out = Path(__file__).parent / "rule30.gif"
frames[0].save(
    out,
    save_all=True,
    append_images=frames[1:],
    duration=DURATION_MS,
    loop=0,
    optimize=True,
    disposal=2,
)
print(f"wrote {out} ({out.stat().st_size / 1024:.1f} KB, {len(frames)} frames)")
