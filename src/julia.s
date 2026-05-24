; julia.s — agent target: Julia set animation, frame N to stdout as PPM.
;
; Contract:
;   - Accept --frame N on the command line (or env WOLFRAM_FRAME).
;   - 800×320 PPM (P6) on stdout, matches oracle.reference.julia(frame=N).
;   - c traces a circle: cr = 0.7885 cos(θ), ci = 0.7885 sin(θ), θ = N/120 · 2π.
;   - The harness drives multiple frames and concatenates them for the
;     framebuffer demo (qemu/boot.sh streams them at ~30 fps).
;   - SSE2 only; no libm/libc.
;
; Empty until the agent loop fills it.

BITS 64
section .text
global _start
_start:
    mov rax, 60
    mov rdi, 1
    syscall
