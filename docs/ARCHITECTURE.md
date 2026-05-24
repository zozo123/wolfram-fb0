# Architecture

```
                         ┌──────────────────────────────────────────────┐
                         │            islo sandbox VM (real VM)          │
                         │   ubuntu:24.04 · 4 vCPU · 8 GB · KVM-able    │
                         │                                              │
   github.com/zozo123/   │   ┌─────────┐   ┌──────────┐   ┌──────────┐ │
   wolfram-fb0           │   │ harness │←─→│ opencode │←─→│  Ollama  │ │
        │                │   │ loop.py │   │  (CLI)   │   │ gemma3:1b│ │
        │  islo use      │   └────┬────┘   └──────────┘   └──────────┘ │
        ▼                │        │                                    │
   ┌──────────┐          │        ▼                                    │
   │ islo.yaml├──────────►   ┌─────────┐   writes      ┌────────────┐  │
   └──────────┘  provisions │ src/*.s │──────────────►│ nasm + ld  │  │
                         │   └────┬────┘                └─────┬──────┘  │
                         │        │                           ▼         │
                         │        │                    ┌────────────┐   │
                         │        │   ./*.elf --ppm    │  dist/*.elf │  │
                         │        │ ←──────────────────│             │  │
                         │        ▼                    └─────┬──────┘   │
                         │  ┌──────────┐                     │          │
                         │  │  oracle  │ ◄───── pixel-diff ──┘          │
                         │  │ score.py │                                │
                         │  └────┬─────┘                                │
                         │       │ scalar feedback (size, diff%)        │
                         │       └──────────► back to harness ──┐       │
                         │                                      │       │
                         │  ┌────────────┐                      │       │
                         │  │ qemu boot  │  ◄── once converged ─┘       │
                         │  │ /dev/fb0   │                              │
                         │  └────┬───────┘                              │
                         │       │ framebuffer                          │
                         │       │ VNC/WebSocket :8910 ────► islo share │
                         │       │                                      │
                         │  ┌────┴─────────┐                            │
                         │  │ bpftrace     │                            │
                         │  │ trace.bt     │ ── JSONL  :8911 ► islo share
                         │  └──────────────┘                            │
                         └──────────────────────────────────────────────┘
                                       │                  │
                                       ▼                  ▼
                                 framebuffer-stream  bpf-event-stream
                                       │                  │
                                       └──────┬───────────┘
                                              ▼
                                  zozo123.github.io/wolfram-fb0
                                  (<canvas> + <pre> render live)
```

## Why every dotted box requires a real VM (not a container)

| Component | Container? | Why |
| --- | --- | --- |
| nasm / ld | ✓ Either | Pure userspace. |
| Ollama + Gemma | ✓ Either | GPU optional. |
| opencode | ✓ Either | Userspace CLI. |
| `./fractal.elf --ppm` | ✓ Either | Pure userspace syscalls. |
| **`qemu-system-x86_64` (nested boot)** | ✗ VM only | Needs `/dev/kvm` or full hardware virt. Privileged containers approximate this but break in most cloud sandboxes. |
| **`./fractal.elf --fb /dev/fb0`** | ✗ VM only | No `/dev/fb0` in containers — no framebuffer device. |
| **`bpftrace`** | ✗ VM only | Needs kernel kprobes + BPF JIT in a real kernel; containers share host kernel and rarely expose this. |

Conclusion: the three rows that make this demo visually and technically interesting *all* require a real VM. The pitch — "a real-VM AI sandbox in the browser" — earns its keep precisely here.

## Repo layout

| Path | Contents |
| --- | --- |
| `src/` | Hand-written `*_reference.s` + agent-overwritten `*.s` |
| `bpf/` | `trace.bt` — eBPF X-ray of running fractal binary |
| `oracle/` | Python reference renderer, pixel-diff + binary-size scorer |
| `harness/` | `loop.py` (agent driver) + `prompts/*.md` (per-target specs) |
| `dist/` | Linked ELFs (gitignored except final pinned ones) |
| `iterations/` | One subdir per agent iteration, with asm + score + transcript |
| `qemu/` | `boot.sh` + microvm builder for the framebuffer demo |
| `site/` | GitHub Pages: plot, live-stream panes, convergence chart |
| `islo.yaml` | Sandbox manifest — image, cpu, mem, setup scripts |
| `Makefile` | All targets are invoked as `islo use wolfram-fb0 -- make <target>` |

## Outer loop (per target)

```
read src/<t>.s + last score
→ prompt opencode (local Gemma)
→ extract ```nasm fence
→ overwrite src/<t>.s
→ oracle.score_target  (nasm → ld → run → pixel-diff)
→ commit iteration to iterations/<t>/NNNN_<ts>/
→ if pixel_diff == 0 and binary_size <= prev: still keep going to shrink
→ else: feed score back as next prompt context
```

## What "fork the sandbox" means in practice

1. Visitor clicks the share link on the Pages site.
2. islo provisions a new VM **from the warmed snapshot** — toolchain + model cached, ~5 s to ready.
3. The visitor's VM gets a fresh clone of `wolfram-fb0` at HEAD.
4. They edit `harness/config` (model, max iters, prompts) and run `make agent-loop`.
5. Their convergence curve gets contributed back via `iterations/`-shaped PR (optional).
