# Show HN: AI writes x86_64 asm + eBPF for fractals on /dev/fb0, in a browser VM

Most "AI coding sandbox" products you can fork from a link are containers. Containers cannot touch `/dev/fb0`, cannot load eBPF, and cannot nested-boot qemu — no framebuffer device, no real kprobes, no `/dev/kvm`. That ceiling is what wolfram-fb0 exists to push on.

It is a real virtualized Linux VM you fork from one click in your browser. Inside, an agent loop drives a local sub-2B model to write pure x86_64 NASM (no libc, single ELF, two syscalls) that renders Wolfram's Rule 30, the Mandelbrot set, and a Julia animation. An eBPF program X-rays each agent-built binary as it runs. `qemu-system-x86_64` nested-boots a 4 MB initramfs that drops straight into the ELF and paints it onto the Linux framebuffer. The framebuffer surface and the eBPF trace stream out of the sandbox over WebSocket and land in a `<canvas>` on the GitHub Pages site. Everything — `nasm`, `ld`, `qemu-system-x86_64`, `bpftrace`, Ollama with a tiny Gemma pre-pulled, `opencode` — is in the warmed sandbox snapshot. Fork the link, you are at HEAD with the toolchain hot.

Repo: github.com/zozo123/wolfram-fb0
Live site: zozo123.github.io/wolfram-fb0

## What this is NOT

Before the comment thread asks: I want to be specific about what I am and am not claiming.

- **Not a finished demo with a converged Rule 30.** `iterations/index.json` in the repo right now reflects **three real iterations of `gemma3:1b` in an islo sandbox** (2026-05-24, ~13:11 UTC). They show the model's capability cliff in plain sight — iters 1–2 produce valid NASM that assembles (8 872 B ELF) but the model echoes the few-shot example and emits only the `P6\n` header (pixel-diff stays at 100%); iter 3 (scaffold-fill at 60 s) fails to return a parseable fence at all. Pixel-perfect Rule 30 has not been achieved by the 1B model yet. The post is the iteration record, not a polished screenshot.
- **Not a Claude or GPT-4 demo.** The agent is a sub-2B local Gemma running on Ollama inside the sandbox. That is a deliberate choice; the point is to find the capability cliff, not to flex a frontier model on a problem it would one-shot.
- **Not a single-shot codegen.** It is an oracle-feedback loop. `harness/runner.py` escalates prompt strategy (simple ask → few-shot → scaffold-fill), feeds back the previous `score.json` (binary size, pixel diff %, assemble_ok), and snapshots every iteration to disk. The value is the trajectory.
- **Not a container.** It is a real virtualized VM with its own kernel. That is the whole technical claim of the project — the three most interesting parts of the pipeline (nested qemu, eBPF, `/dev/fb0`) do not run in a container without a setup ritual that defeats the point of being a one-click fork.

## Why

I grew up on Fractint. What made Fractint feel like magic in 1988 was that the entire pipeline — integer-math fractals, palette tricks, framebuffer writes — was visible and small enough to read. You opened the source, found the inner loop, and the inner loop was a few dozen lines of assembly. That kind of artifact is almost extinct in modern AI demos, which are nearly always webapps over an API.

The question I wanted to answer for myself was: what would a modern, AI-built, Fractint-shaped artifact look like? Not "have an agent generate React for a fractal viewer" — have an agent generate the ELF. Pure x86_64. No libc. Two syscalls. Pixel-diff against a Python reference, byte-counted, in a loop.

The problem with running that experiment publicly is friction. Low-level AI demos die on install: the README rots, the model gets deprecated, the toolchain drifts, the kernel features the reader's distro doesn't ship. Browser-based sandboxes solve install friction in the general case, but every browser sandbox I tried for the asm/eBPF/framebuffer half of this was a container, and the interesting parts won't run there. A real-VM browser sandbox is the missing piece.

## What it does

Three targets, all x86_64 NASM, all `_start`-only, no libc:

- **Rule 30** — Wolfram's 1-D cellular automaton, 800×320 PPM. Integer XOR only. The hand-written reference is 312 bytes and is the gold standard the agent is measured against.
- **Mandelbrot** — 800×320, SSE2 float, 64 iterations, escape radius² ≥ 4.0, cosine palette.
- **Julia animation** — same SSE2 core; parameter `c` traces a circle in frame number. Harness concatenates frames for the framebuffer demo.

Each agent-built binary makes exactly two syscalls: `write(1, …)` and `exit_group(60)`. The oracle pixel-diffs the output against a Python reference renderer in `oracle/reference.py` and returns `(assemble_ok, binary_size, pixel_diff_pct)`.

`bpf/trace.bt` is a `bpftrace` program that hooks the binary at runtime: every syscall, every byte mmapped to fb0, streamed out as JSONL. `qemu/boot.sh` builds the ~4 MB initramfs containing the final ELF plus a minimal busybox, then nested-boots it with `qemu-system-x86_64 -vga std`. The framebuffer surface is bridged out over VNC/WebSocket into a `<canvas>` on the static Pages site.

All of the above runs inside one islo sandbox VM. No host install. No "first install Docker." The `islo.yaml` manifest declares the toolchain; islo warms a snapshot once and forks from it on demand.

## The agent loop

`harness/runner.py` is intentionally short. It owns the outer loop; the intelligence is in the prompts and the escalation policy. Per target, per iteration:

1. Pick a prompt strategy. The escalation ladder is `fewshot → fewshot → scaffold → scaffold → …` — early iters are a clean ask, later iters paste the near-complete reference asm with the inner loop blanked out and ask the model to fill the `[TODO]`. The escalation is the experiment: where in that ladder does a sub-2B local model start producing assemblable output?
2. Call `ollama run <model> <prompt>` under a wall-clock budget.
3. Strip ANSI, extract the last fenced code block, validate it looks like NASM (`section`/`BITS 64`/`syscall`/`_start` markers).
4. Write to `src/<target>.s`, hand it to the oracle: `nasm → ld → run → pixel-diff → (assemble_ok, binary_size, pixel_diff_pct)`.
5. Snapshot the iteration to `iterations/<target>/NNNN_<utc>/` — the produced `.s`, the raw model reply, and `score.json`.
6. Rewrite `iterations/index.json` (the chart-data file the Pages site reads) from the running results.
7. If pixel-diff hits zero, keep going to shrink the binary.

The four islo skills — *plan*, *build*, *review*, *refine* — wrap this at the meta level. *Plan* decomposes the per-target spec, *build* drives the inner opencode session, *review* is the oracle, *refine* tightens the next prompt with the previous score. The convergence chart on the Pages site plots `binary_size` and `pixel_diff_pct` per iteration per target.

## Why a real VM matters

The single most useful artifact in the repo is the table in `docs/ARCHITECTURE.md`. Reproduced because it is the technical claim:

| Component | Container? | Why |
| --- | --- | --- |
| `nasm` / `ld` | Either | Pure userspace. |
| Ollama + Gemma | Either | GPU optional. |
| `opencode` | Either | Userspace CLI. |
| `./fractal.elf --ppm` | Either | Pure userspace syscalls. |
| **`qemu-system-x86_64` (nested boot)** | VM only | Needs `/dev/kvm` or full hardware virt. Privileged containers approximate this but break in most cloud sandboxes. |
| **`./fractal.elf --fb /dev/fb0`** | VM only | No `/dev/fb0` in containers — no framebuffer device exposed. |
| **`bpftrace`** | VM only | Needs kernel kprobes + BPF JIT in a real kernel; containers share the host kernel and rarely expose this. |

The three rows that make this demo visually and technically interesting all require a real VM. Take any of them away — drop the framebuffer, drop eBPF, drop nested qemu — and what's left is "LLM writes a PPM file", which is a demo I have already seen.

## Run it

Nothing to install locally:

```
islo use wolfram-fb0 --source github://zozo123/wolfram-fb0
```

That boots a real VM with `nasm`, `ld`, `qemu-system-x86_64`, `bpftrace`, Python+numpy+pillow, Ollama with a small Gemma pre-pulled, and `opencode`. Inside the sandbox:

```
make demo         # boot the qemu fractal + open the eBPF trace
make agent-loop   # rerun the agent from scratch
```

The "fork the sandbox" button on the Pages site is the same thing in one click — islo provisions a fresh VM from the warmed snapshot and drops you at HEAD.

## Lineage

This sits in a line that runs through [Fractint](https://www.fractint.org/) (1988, integer-math fractals on a 386), [FractalAsm](https://github.com/mrmcsoftware/FractalAsm) (modern asm fractal renderer), Stephen Wolfram's [A New Kind of Science](https://www.wolframscience.com/nks/) (the cellular automata catalogue), and [opencode](https://github.com/sst/opencode) (the inner-loop coding agent). The sandbox is [islo](https://islo.dev), which ships every new account **$50 of free credit with no card required** — enough to spin a real-VM sandbox like the one this demo runs in and reproduce the full convergence loop end-to-end.

## What's NOT yet ready

Honesty calls, preserved so reviewers don't have to find them by reading the code:

- The agent loop has run end-to-end three times for Rule 30 with gemma3:1b (committed under `iterations/rule30/`). It has **not** converged on a pixel-perfect Rule 30. `dist/` is empty (no pinned binaries yet — every iteration produces its own ELF in tmp and the snapshot keeps the source).
- `src/mandel.s` and `src/julia.s` are stub `_start: exit(1)` files — the agent has not been pointed at them yet. Their entries in `iterations/index.json` are empty arrays, not placeholder rows. Only `src/rule30_reference.s` is the hand-written gold standard; `src/rule30.s` is the agent's most recent output.
- The Pages site renders a Rule 30 preview client-side but is not yet wired to the live VNC/WebSocket bridge. The bridge ports (`8910` framebuffer, `8911` bpf) are declared in `islo.yaml`; the bridge daemons land next.
- `qemu/boot.sh` and `qemu/build-microvm.sh` exist but have not been smoke-tested inside the sandbox image. The initramfs builder is the most likely thing to break first.
- No CI yet. The convergence record is meant to be reproducible via `make agent-loop`; an Action that runs the loop on a schedule and refreshes the chart is the obvious next move, gated on the first successful real run.

If you fork the repo right now and run `make agent-loop` inside the sandbox, the runner will confirm `ollama` and `nasm` are on PATH, call the local Gemma, write whatever it produces into `src/rule30.s`, score it, and snapshot the iteration. Whether the model converges on a working Rule 30 inside the iteration budget is exactly the open question this post is meant to surface.

## Anticipated comments

**Q: AI-written assembly is a gimmick. A human can do this in an afternoon.**
Agreed — the hand-written reference is `src/rule30_reference.s` and it took me less than that. The experiment isn't "AI can write asm humans cannot." It's that asm + eBPF + framebuffer is an unusually clean benchmark for an agent loop: the oracle is unambiguous (byte-for-byte pixel diff), the budget is a scalar (ELF size), and there is almost no Stack Overflow corpus to copy from.

**Q: How is this different from Replit / E2B / Daytona / Codespaces / Gitpod?**
All of those run user code in containers. Codespaces and Gitpod can do "VM-shaped" but in practice still gate `/dev/kvm` and most kernel-tracing APIs. Containers are great for webapp demos and bad for the three "VM only" rows in the table above. If a future Codespaces tier exposes `/dev/kvm` + `/dev/fb0` + BPF JIT, the same demo will work there and I will be happy.

**Q: A `--privileged` container with `/dev/kvm` and a custom kernel can do all of this.**
True in principle. In practice the cloud sandboxes I tried either don't allow `--privileged`, don't expose `/dev/kvm`, don't ship a kernel with BPF JIT enabled, or don't expose `/dev/fb0`. The framing isn't "containers can't ever do this" — it's "the cloud-hosted, browser-accessible, one-click-fork containers can't, without a setup ritual that defeats the point of being a one-click fork."

**Q: Why a small model? Why not Claude?**
Two reasons. First, capability-cliff testing — the convergence story is more interesting when the model is bad at the task. Iteration count, prompt-strategy escalation, and oracle feedback only matter when the model can't one-shot it. A frontier model would flatten the chart to a single dot at iter 1. Second, local-only repro: a sub-2B Gemma in Ollama inside the sandbox means no API key, no network egress, no rate limit, and "fork the sandbox" stays a one-click action with no signup. The harness takes `--model`; swap in a bigger one and the chart should compress.

**Q: Where is the convergence chart? Show the numbers.**
Three real iterations are in the chart now (see [the live site](https://zozo123.github.io/wolfram-fb0/#convergence)). Numbers: iter 1 (fewshot, 10.5 s) → 8 872 B ELF, assemble_ok=true, pixel-diff 100 %. Iter 2 (fewshot, 10.2 s) → identical output, gemma3:1b at ~0 temperature is deterministic on a stable prompt. Iter 3 (scaffold-fill, 60 s) → no valid `nasm` fence in the reply, assemble_ok=false. The model is hitting its capability cliff: it can produce valid NASM (the echo of the few-shot example assembles cleanly) but cannot yet generalize from the scaffold to the Rule 30 inner loop. Pixel-perfect convergence is still open at iter 3 of 8.

**Q: Why post a Show HN before the demo converges?**
Because the artifact I want feedback on is the loop and the sandbox shape, not iter 1 of the model output. The iteration record is the deliverable. If the loop's first public run converges on Rule 30 in 7 iters and stalls on Mandelbrot at 30% diff, that is still the answer and still worth shipping with.

## Measured so far (gemma3:1b, 3 iters, 2026-05-24)

| | |
| --- | --- |
| Reference hand-written Rule 30 ELF | **312 B** (from `src/rule30_reference.s`) |
| Best agent-built `assemble_ok=true` ELF | **8 872 B** (iter 1/2, fewshot — model echoes the example PPM-header) |
| Pixel-perfect Rule 30 from the agent | **not yet** — pixel-diff stays at 100 % across iters 1–3 |
| Strategies attempted | `fewshot` (×2), `scaffold` (×1) |
| Median `ollama run` wall-clock | **10.4 s** for `fewshot`, **60 s** (budget exhausted) for `scaffold` |
| Snapshot warm-boot (fork → shell) | not yet timed — `islo snapshot save` was failing on this account at write time |
| Convergence chart | [live on the Pages site](https://zozo123.github.io/wolfram-fb0/#convergence) |
| First-real-run commit | see `iterations/rule30/0001_20260524T131059Z/` and the `harness: persistent runner.py` commit |

Mandelbrot and Julia are not yet attempted by the agent (empty arrays in `iterations/index.json`). The next public run extends the chart in both axes.

## About

Built by **Yossi Eliaz** ([linkedin.com/in/yossi-eliaz](https://www.linkedin.com/in/yossi-eliaz), GitHub [@zozo123](https://github.com/zozo123)) for **[islo.dev](https://www.islo.dev)**. MIT licensed. Fork freely.
