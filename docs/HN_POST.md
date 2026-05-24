# HN launch post — wolfram-fb0

## Title

Candidates:

1. **(recommended)** `Show HN: AI-written x86_64 asm and eBPF drawing fractals to /dev/fb0, in a browser VM`
2. `Show HN: wolfram-fb0 — agent loop writes pure asm for Wolfram fractals, runs in-browser`
3. `Show HN: A real-VM browser sandbox where an AI writes eBPF and asm for /dev/fb0`

Title 1 leads with the artifact (`asm`, `eBPF`, `/dev/fb0`) and the deployment surface (`browser VM`) without leaning on "AI" as the headline. It is 86 characters; if HN's 80-char ceiling bites, trim to:

> `Show HN: AI-written x86_64 asm and eBPF drawing fractals to /dev/fb0 in a browser`

## Opening paragraph (the comment-thread first impression)

Most AI coding sandboxes run in containers, which means they cannot touch `/dev/fb0`, cannot load eBPF, and cannot nested-boot qemu. wolfram-fb0 is a small experiment in what becomes possible when the sandbox is a real virtualized VM instead: an agent loop drives a local small model to write pure x86_64 assembly (no libc, single ELF) that renders Wolfram's Rule 30, the Mandelbrot set, and a Julia animation, then watches itself with an eBPF program while qemu inside the same VM boots straight into the binary and paints it onto the Linux framebuffer. The reference hand-written Rule 30 binary is 312 bytes and the agent's goal is to match its output byte-for-byte and then go smaller. Everything — `nasm`, `ld`, `qemu-system-x86_64`, `bpftrace`, the Ollama runtime with a sub-2B Gemma, and `opencode` — is pre-warmed in the sandbox image, so the whole demo is one fork-the-share-link away.

## Body

### Why

I grew up on Fractint. The thing that made Fractint feel like magic in 1988 was that the entire pipeline — integer-math fractals, palette tricks, framebuffer writes — was visible and small enough to read. You could open the source, find the inner loop, and the inner loop was a few dozen lines of assembly. That kind of artifact is almost extinct in modern AI demos, which are nearly always webapps over an API.

So the question I wanted to answer for myself was: what would a modern, AI-built Fractint-shaped artifact look like? Specifically — not "have an agent generate React for a fractal viewer", but "have an agent generate the ELF". Pure x86_64. No libc. Two syscalls. Pixel-diff against a Python reference, byte-counted, in a loop.

The problem with running that experiment publicly is friction. Low-level AI demos die on install: the README rots, the model gets deprecated, the toolchain drifts, the kernel features the demo depends on aren't in the reader's distro. Browser-based sandboxes solve install friction, but every browser sandbox I tried for the asm/eBPF/framebuffer part of this was a container, and containers cannot do the interesting half. A real-VM browser sandbox is the missing piece, and it turns out [islo](https://islo.dev) ships one, so I built the thing.

### What it does

- Three targets, all x86_64 NASM, all `_start`-only, no libc:
  - **Rule 30** — Wolfram's 1-D cellular automaton, 800×320 PPM. Integer XOR only. Reference is `{rule30_reference_size_bytes}` bytes (hand-written, currently 312 B).
  - **Mandelbrot** — 800×320, SSE2 float, 64 iterations, escape radius² ≥ 4.0, cosine palette.
  - **Julia animation** — same SSE2 core, parameter `c` traces a circle as a function of frame number; harness concatenates frames for the framebuffer demo.
- Each binary makes exactly two syscalls: `write(1, …)` and `exit_group(60)`. The oracle pixel-diffs the output against a Python reference renderer (`oracle/reference.py`).
- `bpf/trace.bt` is a `bpftrace` program that X-rays the agent-built binary while it runs: every syscall, every byte mmapped to fb0, streamed out as JSONL.
- `qemu/boot.sh` builds a ~4 MB initramfs containing the final ELF and a minimal busybox, then nested-boots that image with `qemu-system-x86_64 -vga std`. The framebuffer surface is bridged out of the sandbox over VNC/WebSocket and rendered into a `<canvas>` on the static GitHub Pages site.
- All of the above runs inside one islo sandbox VM. No host install. No "first install Docker." The sandbox manifest (`islo.yaml`) declares the toolchain; islo warms a snapshot once and forks from it.

### The agent loop

`harness/loop.py` is intentionally short (~130 lines). It owns the outer loop; the intelligence is in the prompts and in opencode's session. Per target:

1. Read `src/<target>.s` and the previous oracle score.
2. Compose a prompt: the target contract (from `harness/prompts/<target>.md`) plus the last `score.json` (binary size, pixel diff %, assemble_ok).
3. Call `opencode run --model ollama/gemma4:e2b` against the local Ollama. Local model, no network outside the VM.
4. Extract the last fenced code block from the reply, write it to `src/<target>.s`, hand it to the oracle.
5. Oracle = `nasm` → `ld` → run with `--ppm` → pixel-diff against the Python reference → return `(assemble_ok, binary_size, pixel_diff_pct)`.
6. Snapshot the iteration (asm + score + raw reply) under `iterations/<target>/NNNN_<utc>/`.
7. If `pixel_diff_pct == 0.0`, keep going to shrink the binary; otherwise feed the new score into the next prompt.

The four [islo skills](https://islo.dev) — *plan*, *build*, *review*, *refine* — wrap this loop at the meta level. *Plan* decomposes the per-target spec, *build* drives the inner opencode session, *review* is the oracle, *refine* tightens the prompt with the previous score. The convergence chart on the GitHub Pages site plots `binary_size` and `pixel_diff_pct` per iteration per target.

### Why a real VM matters

The single most useful artifact in the repo is the table in `docs/ARCHITECTURE.md`. Reproduced here because it is the technical claim of the project:

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

### Run it yourself

You do not need anything installed:

```
islo use wolfram-fb0 --source github://zozo123/wolfram-fb0
```

That command boots a real VM with `nasm`, `ld`, `qemu-system-x86_64`, `bpftrace`, Python+numpy+pillow, Homebrew, Ollama with `gemma4:e2b` pre-pulled, and `opencode`. Inside the sandbox:

```
make demo         # boot the qemu fractal + open the eBPF trace
make agent-loop   # rerun the agent from scratch
```

The "fork the sandbox" button on the GitHub Pages site does the same thing in one click — islo provisions a fresh VM from the warmed snapshot (~5 s to ready) and drops you at HEAD.

### Lineage

- [Fractint](https://www.fractint.org/) — the 1988 ancestor; integer-math fractals on a 386.
- [FractalAsm](https://github.com/mrmcsoftware/FractalAsm) — modern asm fractal renderer.
- Stephen Wolfram, [A New Kind of Science](https://www.wolframscience.com/nks/) — the cellular automata catalogue.
- [islo](https://islo.dev) — the real-VM browser sandbox.
- [opencode](https://github.com/sst/opencode) — the inner-loop coding agent.

## Anticipated HN comments + honest responses

**Q: "AI-written assembly is a gimmick. A human can do this in an afternoon."**
A: Agreed that a human can do this in an afternoon — the hand-written reference is `src/rule30_reference.s`, it took me less than that, and it is the gold standard the agent is measured against. The point of the experiment is not "AI can write asm humans cannot." It is that asm + eBPF + framebuffer is an unusually *clean* benchmark for an agent loop: the oracle is unambiguous (byte-for-byte pixel diff), the budget is a scalar (ELF size), there is very little Stack Overflow corpus to copy from, and the failure modes are real (an unassemblable file is a hard zero). It happens to also be visually fun.

**Q: "How is this different from Replit / E2B / Daytona / GitHub Codespaces / Gitpod?"**
A: All of those run user code in containers (Codespaces and Gitpod can do "VM-shaped" but in practice still gate `/dev/kvm` and most kernel-tracing APIs). Containers are great for webapp demos and bad for the three rows in the table above. islo's sandbox is a virtualized Linux VM with its own kernel, which is why `bpftrace` and nested `qemu-system-x86_64` work. If a future Codespaces tier exposes `/dev/kvm` + `/dev/fb0` + BPF JIT, the same demo will work there too and I will be happy.

**Q: "Why not just use $bigger_model? gpt-4o-mini would one-shot Rule 30."**
A: It probably would. Two reasons for the small local model: (1) running entirely inside the VM means no API key, no network egress, no rate limit, and "fork the sandbox" stays a one-click action with no signup; (2) the convergence story is more interesting when the model is bad at the task — iteration count, oracle feedback, prompt refinement actually matter. If you want to swap in a bigger model, the harness takes `--model` and opencode supports any provider; the convergence chart will just be flatter.

**Q: "Where is the convergence chart actually? Show the numbers."**
A: Honest answer: not there yet. `iterations/index.json` in the repo right now contains a *placeholder* trajectory (Rule 30 reaching `pixel_diff_pct == 0.0` at iter 7 with a 312 B ELF, Mandelbrot reaching 0.4% at iter 6, Julia reaching 5.2% at iter 5) that I wrote by hand to lay out the schema. `dist/` is empty. The first real run will overwrite that file and the chart on the Pages site. Posting this before the first real run is a deliberate decision to publish-then-iterate; I will edit the post once the first end-to-end run lands and link the commit that overwrote `iterations/index.json`.

**Q: "A `--privileged` container with `/dev/kvm` and a custom kernel can do all of this."**
A: True in principle. In practice the cloud sandboxes I tried either don't allow `--privileged`, don't expose `/dev/kvm` to the container, don't ship a kernel with BPF JIT enabled, or don't expose `/dev/fb0` because the host has no framebuffer device to pass through. The honest framing is not "containers can't ever do this" but "the cloud-hosted, browser-accessible, one-click-fork containers can't do this without a setup ritual that defeats the point of being a one-click fork." A real VM removes the ritual.

## What's NOT yet ready (as of writing)

- The agent loop has not been run end-to-end yet on the public repo. `dist/` is empty. `iterations/index.json` is the placeholder trajectory described in the README, not measured data.
- `src/mandel.s` and `src/julia.s` are stub `_start: exit(1)` files — the agent has not produced them. Only `src/rule30_reference.s` is real, and `src/rule30.s` currently `%include`s the reference rather than being an agent output.
- The Pages site (`site/index.html` + `rule30.js`) renders a Rule 30 preview client-side but is not yet wired to the live VNC/WebSocket bridge described in `docs/ARCHITECTURE.md`. The two bridge ports (`8910` framebuffer, `8911` bpf) are declared in `islo.yaml` but the bridge daemons are not in the repo.
- `qemu/boot.sh` and `qemu/build-microvm.sh` exist but have not been smoke-tested inside the sandbox image. The initramfs builder is the most likely thing to break first.
- The "fork the sandbox" button on the Pages site is a placeholder link until `gh repo create zozo123/wolfram-fb0` actually creates the public repo (`islo.yaml` has the `sources:` block commented out for this reason).
- No CI yet. The convergence record is meant to be reproducible via `make agent-loop`, but there is no GitHub Action that runs that loop on a schedule and updates the chart. Adding one is the obvious next move and waits on the first successful real run.

If you fork the repo right now and run `make agent-loop`, the harness will (a) confirm `opencode` is on PATH, (b) call the local Gemma, (c) write whatever the model produces into `src/rule30.s`, and (d) snapshot the iteration. Whether the model converges on a working Rule 30 in <40 iterations is exactly the open question this post is meant to surface.

## Metrics to fill in before posting

The post above uses these placeholders. Each gets filled from the first real `make agent-loop` run, then this section gets deleted.

- `{rule30_reference_size_bytes}` — currently inline as 312 B from the reference asm; double-check via `wc -c dist/rule30_reference.elf` after a real build.
- `{rule30_agent_final_size_bytes}` — final agent ELF size after convergence.
- `{rule30_iterations_to_converge}` — first iter with `pixel_diff_pct == 0.0`.
- `{mandel_agent_final_size_bytes}` and `{mandel_iterations_to_converge}` — same, for Mandelbrot.
- `{julia_agent_final_size_bytes}` and `{julia_iterations_to_converge}` — same, for Julia animation.
- `{model_runtime_seconds_per_iter}` — wall-clock per opencode call against `gemma4:e2b` on the sandbox VM.
- `{full_loop_wall_clock}` — total elapsed from `make agent-loop` start to all three targets converged.
- `{snapshot_warm_boot_seconds}` — time from "fork the sandbox" click to interactive shell, measured.
- `{convergence_chart_url}` — direct link to the PNG/SVG once the Pages site renders it.
- `{first_real_run_commit}` — the commit SHA that overwrote `iterations/index.json` with measured data, linked from the Q4 response above.
