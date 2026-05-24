; rule30.s — agent target. The agent loop replaces this file iteration by
; iteration. The hand-written reference in rule30_reference.s is the upper
; bound on quality (pixel-perfect against the Python reference) and a soft
; upper bound on size (the agent should beat it, eventually).
;
; Contract this file MUST honor:
;   - Built with: nasm -felf64 rule30.s ; ld -o rule30.elf rule30.o
;   - Invoked as: ./rule30.elf --ppm  (or with no args; --ppm is the default)
;   - Output:     binary PPM (P6) on stdout, 800×320, exactly matching
;                 oracle.reference.rule30() byte-for-byte after the header.
;   - Palette:    ON cells RGB(220,60,255), OFF cells RGB(10,10,18).
;   - Rule:       Wolfram Rule 30 — new = left XOR (center OR right).
;   - Seed:       Single 1 at column W/2 in row 0.
;   - Boundary:   Wrap (toroidal): row[-1] ≡ row[W-1], row[W] ≡ row[0].
;   - Exit:       sys_exit(0) (no libc).
;
; Placeholder until the first agent iteration overwrites it.
%include "rule30_reference.s"
