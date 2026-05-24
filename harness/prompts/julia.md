# Task: x86_64 assembly — Julia animation frame N → PPM stdout

Write a complete `src/julia.s` (NASM, x86_64 Linux) that:

- Accepts `--frame N` on argv (or env var `WOLFRAM_FRAME`).
- Outputs an 800×320 P6 PPM image on stdout for that frame.
- Matches `oracle/reference.py:julia(frame=N)` byte-for-byte for every N in 0..119.
- c traces a circle: `cr = 0.7885·cos(θ)`, `ci = 0.7885·sin(θ)`, θ = `N/120·2π`.
- Window: re ∈ [-1.6, 1.6], im ∈ [-1.0, 1.0]. Iteration cap 64. Escape r² ≥ 4.0.
- Palette: `r = 255·t`, `g = 255·(1-t)`, `b = 255·(0.5 + 0.5·sin(2π·t))` where t = i/64.
- SSE2 only; no libm/libc.

Reply with only the complete `src/julia.s` inside a single ` ```nasm ` fenced block.
