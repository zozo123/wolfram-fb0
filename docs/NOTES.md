# wolfram-fb0: design notes and status

wolfram-fb0 is an experiment by Yossi Eliaz: can a small local model write pure x86_64 NASM (no libc, single ELF, two syscalls) for Wolfram's Rule 30, the Mandelbrot set and a Julia animation, when an oracle pixel-diffs every attempt? It runs in an [islo.dev](https://islo.dev) VM rather than a container, because the planned later steps (eBPF tracing, a framebuffer, a nested qemu boot) need a real kernel.

So far only the first part has run: 3 iterations of `gemma3:1b` on Rule 30, on 24 May 2026. None produced a correct image. The rest of this page separates what has run from what is designed but not yet run.

Repo: [github.com/zozo123/wolfram-fb0](https://github.com/zozo123/wolfram-fb0) · Page: [zozo123.github.io/wolfram-fb0](https://zozo123.github.io/wolfram-fb0/)

## What this is not

- **Not a finished demo with a converged Rule 30.** `iterations/index.json` reflects **three real iterations of `gemma3:1b` in an islo sandbox** (2026-05-24, ~13:11 UTC). Iterations 1–2 produce valid NASM that assembles (8,872-byte ELF), but the model echoes the few-shot example and writes only 3 bytes of output, so the pixel diff stays at 100%. Iteration 3 (scaffold-fill, 60 s budget) returns the scaffold with the `[TODO]` unfilled and does not assemble. The iteration record is the result, not a polished screenshot.
- **Not a frontier-model demo.** The model is a 1B local Gemma running on Ollama inside the sandbox. That is deliberate: the point is to find the capability cliff, not to have a frontier model one-shot the problem.
- **Not a single-shot codegen.** It is an oracle loop. `harness/runner.py` escalates the prompt strategy on a fixed schedule (few-shot → scaffold-fill), scores every attempt, and snapshots every iteration to disk. Feeding the previous score back into the next prompt is designed (`harness/loop.py`) but not yet run.
- **Not a container.** It runs in a VM with its own kernel. The three most interesting parts of the planned pipeline (nested qemu, eBPF, `/dev/fb0`) do not run in a typical container.

## Why

I grew up on Fractint. What made Fractint feel like magic in 1988 was that the entire pipeline — integer-math fractals, palette tricks, framebuffer writes — was visible and small enough to read. You opened the source, found the inner loop, and the inner loop was a few dozen lines of assembly. That kind of artifact is almost extinct in modern AI demos, which are nearly always webapps over an API.

The question I wanted to answer for myself was: what would a modern, AI-built, Fractint-shaped artifact look like? Not "have an agent generate React for a fractal viewer" — have an agent generate the ELF. Pure x86_64. No libc. Two syscalls. Pixel-diff against a Python reference, byte-counted, in a loop.

The problem with running that experiment publicly is friction. Low-level AI demos die on install: the README rots, the model gets deprecated, the toolchain drifts, the reader's distro doesn't ship the kernel features. Hosted sandboxes solve install friction in the general case, but the ones I tried for the asm/eBPF/framebuffer half of this were containers, and the interesting parts won't run there.

## Design (targets)

Three targets, all x86_64 NASM, all `_start`-only, no libc:

- **Rule 30** — Wolfram's 1-D cellular automaton, 800×320 PPM. Integer XOR only. The hand-written `src/rule30_reference.s` is the target the agent is measured against.
- **Mandelbrot** — 800×320, SSE2 float, 64 iterations, escape radius² ≥ 4.0, cosine palette.
- **Julia animation** — same SSE2 core; parameter `c` traces a circle in frame number. The harness would concatenate frames for the framebuffer demo.

Each agent-built binary should make exactly two syscalls: `write(1, …)` and `exit_group(60)`. The oracle pixel-diffs the output against a Python reference renderer in `oracle/reference.py` and returns `(assemble_ok, binary_size, pixel_diff_pct)`.

Planned, not yet run: `bpf/trace.bt` is a `bpftrace` program that traces the binary's `openat`, `mmap` and `write` syscalls at runtime and emits JSONL. `qemu/boot.sh` builds a small initramfs containing the final ELF plus a minimal busybox, then nested-boots it with `qemu-system-x86_64 -vga std`. The framebuffer and the trace would be bridged out over WebSocket (`harness/bridge_fb.py`, `harness/bridge_bpf.py`) into the panes on the Pages site. The `islo.yaml` manifest declares the toolchain.

## The agent loop (what ran)

`harness/runner.py` is intentionally short. It owns the outer loop; the intelligence is in the prompts and the escalation policy. Per target, per iteration:

1. Pick a prompt strategy. The escalation ladder is `fewshot → fewshot → scaffold → scaffold → …` — early iterations are a clean ask, later ones paste the near-complete reference asm with the inner loop blanked out and ask the model to fill the `[TODO]`. The escalation is the experiment: where in that ladder does a 1B local model start producing correct output?
2. Call `ollama run <model> <prompt>` under a wall-clock budget.
3. Strip ANSI, extract the last fenced code block, check it looks like NASM (`section`/`BITS 64`/`syscall`/`_start` markers).
4. Write to `src/<target>.s`, hand it to the oracle: `nasm → ld → run → pixel-diff → (assemble_ok, binary_size, pixel_diff_pct)`.
5. Snapshot the iteration to `iterations/<target>/NNNN_<utc>/` — the produced `.s`, the raw model reply, and `score.json`.
6. Rewrite this target's entry in `iterations/index.json` (the chart-data file the Pages site reads).
7. If pixel diff hits zero, keep going to shrink the binary.

Planned, not yet run: `harness/loop.py` drives [opencode](https://github.com/anomalyco/opencode) instead of calling `ollama run` directly, and feeds the previous score into the next prompt. The convergence chart on the Pages site plots `binary_size` and `pixel_diff_pct` per iteration per target.

## Why a real VM matters

From `docs/ARCHITECTURE.md`:

| Component | Container? | Why |
| --- | --- | --- |
| `nasm` / `ld` | Either | Pure userspace. |
| Ollama + Gemma | Either | GPU optional. |
| `opencode` | Either | Userspace CLI. |
| `./fractal.elf --ppm` | Either | Pure userspace syscalls. |
| **`qemu-system-x86_64` (nested boot)** | VM only | Needs `/dev/kvm` or full hardware virt. Privileged containers approximate this but break in most cloud sandboxes. |
| **`./fractal.elf --fb /dev/fb0`** | VM only | No `/dev/fb0` in containers — no framebuffer device exposed. |
| **`bpftrace`** | VM only | Needs kernel kprobes + BPF JIT in a real kernel; containers share the host kernel and rarely expose this. |

The three rows that make this experiment visually and technically interesting all require a VM. Take any of them away and what's left is "LLM writes a PPM file". The committed runs so far only exercise the `--ppm` rows.

## Run it

Runs on islo.dev (the author's employer); needs an islo account.

```
islo use wolfram-fb0 --source https://github.com/zozo123/wolfram-fb0
```

That provisions the VM in `islo.yaml` with `nasm`, `ld`, `qemu-system-x86_64`, `bpftrace`, Python + numpy + pillow, Ollama with `gemma3:1b`, and `opencode`. Inside the sandbox:

```
python3 harness/runner.py --target rule30 --max-iters 8   # the loop behind the committed runs
make agent-loop   # harness/loop.py (opencode driver) — not yet run
make demo         # qemu framebuffer boot — not yet smoke-tested
```

## Lineage

This sits in a line that runs through [Fractint](https://www.fractint.org/) (1988, integer-math fractals on a 386), [FractalAsm](https://github.com/mrmcsoftware/FractalAsm) (modern asm fractal renderer), Stephen Wolfram's [A New Kind of Science](https://www.wolframscience.com/nks/) (the cellular automata catalogue), and [opencode](https://github.com/anomalyco/opencode) (the coding agent `harness/loop.py` is written to drive). The sandbox is [islo](https://islo.dev).

## What's not ready yet

- The loop has run three iterations for Rule 30 with `gemma3:1b` (committed under `iterations/rule30/`). It has **not** produced a pixel-perfect Rule 30. There is no `dist/` directory with pinned binaries; each iteration builds its ELF in a temp directory and the snapshot keeps the source.
- `src/mandel.s` and `src/julia.s` are stub `_start: exit(1)` files — the agent has not been pointed at them yet. Their entries in `iterations/index.json` are empty arrays. `src/rule30_reference.s` is the hand-written target; the committed `src/rule30.s` is a placeholder that `%include`s it.
- The Pages site draws a Rule 30 preview client-side but is not wired to a live framebuffer or eBPF stream. The bridge ports (`8910` framebuffer, `8911` bpf) are declared in `islo.yaml`; the bridges have not been run end to end.
- `qemu/boot.sh` and `qemu/build-microvm.sh` exist but have not been smoke-tested inside the sandbox image. The initramfs builder is the most likely thing to break first.
- No CI. The convergence record is meant to be reproducible by rerunning `harness/runner.py` inside the sandbox.

If you run `harness/runner.py` inside the sandbox, it checks that `ollama` and `nasm` are on PATH, calls the local Gemma, writes whatever it produces into `src/rule30.s`, scores it, and snapshots the iteration. Whether the model converges on a working Rule 30 inside the iteration budget is the open question.

## FAQ

**AI-written assembly is a gimmick. A human can do this in an afternoon.**
Agreed — the hand-written reference is `src/rule30_reference.s`. The experiment isn't "AI can write asm humans cannot." It's that asm + pixel diff is an unusually clean benchmark for an agent loop: the oracle is unambiguous (pixel diff against a reference), the budget is a scalar (ELF size), and there is almost no Stack Overflow corpus to copy from.

**Why a small model?**
Two reasons. First, capability-cliff testing — the convergence story is more interesting when the model is bad at the task. Iteration count, prompt-strategy escalation, and oracle feedback only matter when the model can't one-shot it. Second, local-only repro: a 1B Gemma in Ollama inside the sandbox means no model API key, no rate limit. The harness takes `--model`; a bigger model should need fewer iterations.

**Show the numbers.**
Iteration 1 (few-shot, 10.5 s) → 8,872-byte ELF, `assemble_ok=true`, pixel diff 100%. Iteration 2 (few-shot, 10.2 s) → the same program apart from comments. Iteration 3 (scaffold-fill, 60 s) → the reply repeats the scaffold with the `[TODO]` unfilled, `assemble_ok=false`. The model can produce NASM that assembles (an echo of the few-shot example) but has not yet generalized from the scaffold to the Rule 30 inner loop. The chart is on [the page](https://zozo123.github.io/wolfram-fb0/#convergence).

## Measured so far (gemma3:1b, 3 iterations, 2026-05-24)

| | |
| --- | --- |
| Best agent-built `assemble_ok=true` ELF | **8,872 B** (iterations 1–2, few-shot — the model echoes the example and writes only 3 bytes of output) |
| Pixel-perfect Rule 30 from the agent | **not yet** — pixel diff stays at 100% across iterations 1–3 |
| Strategies attempted | `fewshot` (×2), `scaffold` (×1) |
| `ollama run` wall-clock | **10.2–10.5 s** for `fewshot`, **60 s** (budget exhausted) for `scaffold` |
| Snapshot warm-boot (provision → shell) | not timed — `islo snapshot save` was failing on this account at the time |
| Raw data | `iterations/rule30/0001_20260524T131059Z/` … `0003_20260524T131209Z/` |

Mandelbrot and Julia have not been attempted by the agent (empty arrays in `iterations/index.json`).

## About

Built by [Yossi Eliaz](https://yossieliaz.netlify.app/), who works on islo.dev. More experiments: [zozo123.github.io](https://zozo123.github.io/). MIT licensed.
