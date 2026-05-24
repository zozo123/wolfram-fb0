; mandel.s — agent target: Mandelbrot via SSE float, output PPM to stdout.
;
; Contract:
;   - 800×320 PPM (P6) on stdout, matches oracle.reference.mandelbrot() exactly.
;   - Window: re ∈ [-2.2, 1.0], im ∈ [-1.2, 1.2].
;   - Iteration cap: 64. Escape radius² ≥ 4.0.
;   - In-set pixel: RGB(0,0,0).
;   - Out-of-set pixel uses a cosine palette identical to reference.py.
;   - Pure x86_64 + SSE2 (no libm, no libc, no x87).
;   - Built: nasm -felf64 mandel.s ; ld -o mandel.elf mandel.o
;
; Empty until the agent loop fills it. Stub is here so the Makefile doesn't
; choke.

BITS 64
section .text
global _start
_start:
    mov rax, 60         ; sys_exit
    mov rdi, 1          ; non-zero — "not implemented yet" sentinel
    syscall
