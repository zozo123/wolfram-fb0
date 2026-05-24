# Task: x86_64 assembly — Mandelbrot → PPM stdout

Write a complete `src/mandel.s` (NASM, x86_64 Linux) that:

- Outputs an 800×320 P6 PPM image on stdout.
- Matches `oracle/reference.py:mandelbrot()` byte-for-byte.
- Window: re ∈ [-2.2, 1.0], im ∈ [-1.2, 1.2].
- Iteration cap: 64. Escape when `|z|² ≥ 4.0`.
- In-set pixel: `RGB(0, 0, 0)`.
- Out-of-set: cosine palette identical to `reference.py` (see source).
- Uses **SSE2** for floating point (`movsd`, `mulsd`, `addsd`, …). No x87. No libm.
- No libc — `sys_write(1)` + `sys_exit(0)` only.

For the cosine palette without libm, use a small polynomial / lookup-table approximation that still produces byte-exact matches against the Python reference. Confirm by running the oracle.

Reply with only the complete `src/mandel.s` inside a single ` ```nasm ` fenced block.
