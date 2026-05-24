"""Pure-Python reference renderers for the three targets.

These produce the ground-truth PPM bytes the asm versions must match exactly,
pixel-for-pixel. The oracle pixel-diffs the agent-built ELF's --ppm output
against these.

Kept short and readable on purpose — anyone debugging the agent loop reads this
first to confirm what "correct" means.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

W, H = 800, 320

ON_RGB = (220, 60, 255)
OFF_RGB = (10, 10, 18)


def _ppm_header(w: int, h: int) -> bytes:
    return f"P6\n{w} {h}\n255\n".encode()


def rule30(w: int = W, h: int = H) -> bytes:
    """Wolfram Rule 30: new = left XOR (center OR right). Single seed at center."""
    row = bytearray(w)
    row[w // 2] = 1
    out = bytearray(_ppm_header(w, h))
    on = bytes(ON_RGB)
    off = bytes(OFF_RGB)
    for _ in range(h):
        out.extend(b"".join(on if c else off for c in row))
        nxt = bytearray(w)
        for x in range(w):
            l = row[(x - 1) % w]
            c = row[x]
            r = row[(x + 1) % w]
            nxt[x] = l ^ (c | r)
        row = nxt
    return bytes(out)


def mandelbrot(w: int = W, h: int = H, max_iter: int = 64) -> bytes:
    """Classical escape-time Mandelbrot. Color from iteration count; matches the
    palette the asm version must reproduce."""
    out = bytearray(_ppm_header(w, h))
    re_min, re_max = -2.2, 1.0
    im_min, im_max = -1.2, 1.2
    for py in range(h):
        cy = im_min + (im_max - im_min) * py / (h - 1)
        for px in range(w):
            cx = re_min + (re_max - re_min) * px / (w - 1)
            zr, zi = 0.0, 0.0
            i = 0
            while i < max_iter and zr * zr + zi * zi < 4.0:
                zr, zi = zr * zr - zi * zi + cx, 2.0 * zr * zi + cy
                i += 1
            if i == max_iter:
                out += bytes((0, 0, 0))
            else:
                t = i / max_iter
                r = int(255 * (0.5 + 0.5 * math.cos(6.28318 * (t + 0.0))))
                g = int(255 * (0.5 + 0.5 * math.cos(6.28318 * (t + 0.33))))
                b = int(255 * (0.5 + 0.5 * math.cos(6.28318 * (t + 0.66))))
                out += bytes((r, g, b))
    return bytes(out)


def julia(frame: int, w: int = W, h: int = H, max_iter: int = 64) -> bytes:
    """One frame of a Julia animation. c traces a circle in the parameter plane.
    Frame index drives the angle so the agent's animated asm matches frame-for-frame."""
    angle = (frame / 120.0) * 2.0 * math.pi
    cr = 0.7885 * math.cos(angle)
    ci = 0.7885 * math.sin(angle)
    out = bytearray(_ppm_header(w, h))
    re_min, re_max = -1.6, 1.6
    im_min, im_max = -1.0, 1.0
    for py in range(h):
        zy0 = im_min + (im_max - im_min) * py / (h - 1)
        for px in range(w):
            zx = re_min + (re_max - re_min) * px / (w - 1)
            zy = zy0
            i = 0
            while i < max_iter and zx * zx + zy * zy < 4.0:
                zx, zy = zx * zx - zy * zy + cr, 2.0 * zx * zy + ci
                i += 1
            t = i / max_iter
            r = int(255 * t)
            g = int(255 * (1.0 - t))
            b = int(255 * (0.5 + 0.5 * math.sin(6.28318 * t)))
            out += bytes((r, g, b))
    return bytes(out)


@dataclass
class Target:
    name: str
    render: Callable[..., bytes]
    args: dict


TARGETS = {
    "rule30": Target("rule30", rule30, {}),
    "mandel": Target("mandel", mandelbrot, {}),
    "julia": Target("julia", julia, {"frame": 0}),
}


if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "rule30"
    extra = {}
    if name == "julia" and len(sys.argv) > 2:
        extra["frame"] = int(sys.argv[2])
    t = TARGETS[name]
    sys.stdout.buffer.write(t.render(**{**t.args, **extra}))
