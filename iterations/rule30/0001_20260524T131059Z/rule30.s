BITS 64
SECTION .data
msg: db "P6\n800 320\n255\n", 0  ; Row buffer
SECTION .text
GLOBAL _start

_start:
    mov rax, 1          ; sys_write
    mov rdi, 1          ; stdout
    lea rsi, [rel msg]
    mov rdx, 3
    syscall
    mov rax, 60         ; sys_exit
    xor edi, edi
    syscall
