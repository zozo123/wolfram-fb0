# Task: x86_64 NASM — Wolfram Rule 30 → PPM stdout

Write `src/rule30.s` (NASM, x86_64 Linux), no libc.

**Output:** binary PPM (`P6\n800 320\n255\n` then RGB bytes) on stdout. 800×320.

**Algorithm:**
1. Row buffer = 800 bytes, all zero except `row[400] = 1`.
2. For each of 320 rows: emit the row as RGB pixels (ON cell = `220,60,255`; OFF cell = `10,10,18`), then update the row.
3. Update rule: `new[x] = row[(x-1) mod 800] XOR (row[x] OR row[(x+1) mod 800])`.

**Syscalls:** `write(fd=1, buf, len)` is `rax=1, rdi=1, rsi=buf, rdx=len, syscall`. `exit(0)` is `rax=60, rdi=0, syscall`.

**Constraints:**
- One file. `section .text` with `global _start`, plus `.bss` / `.rodata` as needed.
- Pixel-perfect match required. Minimize binary size after that.

Reply with ONLY the complete `src/rule30.s` inside a triple-backtick code fence. No commentary.
