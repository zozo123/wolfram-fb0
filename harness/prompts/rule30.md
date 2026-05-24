# Task: x86_64 NASM — Wolfram Rule 30 → PPM stdout

You will write x86_64 Linux NASM assembly. **No Python, no other language. NASM only.**

Here is an example of a valid x86_64 Linux NASM program that writes the bytes `P6\n` to stdout and exits:

```nasm
BITS 64
section .data
msg: db "P6", 10
section .text
global _start
_start:
    mov rax, 1          ; sys_write
    mov rdi, 1          ; stdout
    lea rsi, [rel msg]
    mov rdx, 3
    syscall
    mov rax, 60         ; sys_exit
    xor edi, edi
    syscall
```

That program is 312 bytes after `nasm -felf64` + `ld`. The same calling convention applies for your task.

## Your task

Write `src/rule30.s` that outputs a complete 800×320 P6 PPM image to stdout, implementing Wolfram's Rule 30 cellular automaton.

**PPM format:** literal header `P6\n800 320\n255\n` (15 bytes), then 800×320×3 = 768000 RGB bytes.

**Rule 30 algorithm:**
1. Row buffer = 800 bytes, all zero except `row[400] = 1` (the seed).
2. Emit the current row as 800 RGB triples: ON cell → `220, 60, 255`; OFF cell → `10, 10, 18`.
3. Compute the next row: `new[x] = row[(x-1) mod 800] XOR (row[x] OR row[(x+1) mod 800])`.
4. Repeat for 320 rows total.

**Constraints:** no libc, only `sys_write(1)` and `sys_exit(0)`. Pure x86_64. Match the reference byte-for-byte.

Reply with ONLY the complete `src/rule30.s` inside a triple-backtick `nasm` fenced block. No commentary before or after.
