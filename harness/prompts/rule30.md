# Task: x86_64 assembly — Wolfram Rule 30 → PPM stdout

Write a complete `src/rule30.s` (NASM, x86_64 Linux) that:

- Outputs an 800×320 P6 PPM image on stdout.
- Matches `oracle/reference.py:rule30()` **byte-for-byte** after the PPM header.
- Implements Wolfram **Rule 30**: `new = left XOR (center OR right)`.
- Seeds the first row with a single `1` at column 400 (`W/2`).
- Wraps at the row edges (toroidal: `row[-1] ≡ row[W-1]`, `row[W] ≡ row[0]`).
- Uses **no libc** — only `sys_write(1)` and `sys_exit(0)` via the `syscall` instruction.
- Uses palette: ON cells `RGB(220, 60, 255)`, OFF cells `RGB(10, 10, 18)`.

Build expectation:
```
nasm -felf64 src/rule30.s -o /tmp/rule30.o
ld -o /tmp/rule30.elf /tmp/rule30.o
./tmp/rule30.elf --ppm > /tmp/out.ppm
```

The oracle then pixel-diffs `/tmp/out.ppm` against `oracle/reference.py:rule30()`.

**Constraints you are optimizing:**
- `pixel_diff_pct` must reach `0.00`.
- After that, minimize `binary_size` (in bytes of the linked ELF).

Reply with **only** the complete contents of `src/rule30.s` inside a single ` ```nasm ` fenced block. Do not include any other text outside the code fence.
