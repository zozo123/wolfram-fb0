# wolfram-fb0

An experiment: an oracle loop asks a 1B local model (`gemma3:1b` via Ollama) to write pure x86_64 NASM that renders Wolfram's Rule 30, then pixel-diffs the output against a Python reference, all inside an [islo.dev](https://islo.dev) VM. The first 3 iterations (24 May 2026) did not produce a correct image; Mandelbrot and Julia have not been attempted. Page: [zozo123.github.io/wolfram-fb0](https://zozo123.github.io/wolfram-fb0/).

![Rule 30 drawn from the reference algorithm (not model output)](media/rule30.gif)

---

## What this is

Most AI coding sandboxes are containers. The full design here needs things a container usually can't give you: `bpftrace` against kernel probes, a framebuffer device (`/dev/fb0`), and a nested `qemu-system-x86_64` boot. So the plan is to run everything in an islo.dev VM: a small open-weight model writes pure x86_64 assembly (no libc) for Stephen Wolfram's Rule 30, the Mandelbrot set and a Julia animation; an oracle scores each attempt; qemu boots the result onto a framebuffer while bpftrace traces it; and both streams show up on the page.

What has actually run so far is the first part, for Rule 30 only. See [Status](#status).

## Why this exists

* Fractint (1988) and [FractalAsm](https://github.com/mrmcsoftware/FractalAsm) showed that hand-tuned assembly + framebuffer is one of the most visually rewarding low-level art forms in computing.
* Almost every AI-coding demo today is a webapp. The opposite of a webapp — pure ELF, no libc, kernel ABI only — is exactly the kind of work that's *hard* for LLMs (no Stack Overflow corpus to copy) and *easy* to verify (pixel-diff is unforgiving, byte-count is a scalar).
* And every "reproducible" AI demo dies on install friction. The README rots. The toolchain drifts. The model gets deprecated. A cloud sandbox that anyone can re-provision from the repo is one way around that.

## What's in the box

```
src/        — rule30_reference.s (hand-written target); rule30.s, mandel.s, julia.s (agent targets, currently placeholders)
bpf/        — trace.bt, a bpftrace tracer for the planned framebuffer run
oracle/     — Python reference renderer + pixel-diff + binary-size scorer
harness/    — runner.py (the loop behind the committed runs), loop.py (opencode driver, not yet run), stream bridges
iterations/ — every loop iteration, committed (the convergence record)
qemu/       — boot.sh + tiny initramfs builder for the framebuffer demo (not yet smoke-tested)
media/      — Rule 30 GIF drawn from the reference algorithm
docs/       — design notes and status
index.html, *.js, style.css — GitHub Pages site
islo.yaml   — declares the VM sandbox shape
```

## Run it

Runs on [islo.dev](https://islo.dev) (the author's employer); needs an islo account.

```bash
islo use wolfram-fb0 --source https://github.com/zozo123/wolfram-fb0
# → provisions the VM in islo.yaml: nasm, qemu, bpftrace, Ollama + gemma3:1b, opencode.
```

Inside the sandbox, the loop that produced the committed iterations:

```bash
python3 harness/runner.py --target rule30 --max-iters 8
```

`make agent-loop` runs `harness/loop.py` (the opencode driver), which has no committed run yet.

Running it on your own Linux machine needs `nasm`, `ld`, `qemu-system-x86_64`, `bpftrace`, Python 3 (`pillow`, `numpy`) and Ollama with `gemma3:1b`.

## Targets

| Target | Asm budget | Math | Why it's interesting |
| --- | --- | --- | --- |
| Rule 30 | ~256 B | integer XOR | Wolfram's signature 1-D automaton. Trivial math, ruthless on byte budget. |
| Mandelbrot | ~1 KB | SSE float, no libc | Forces the model to use raw SSE; no `sin`/`cos`, no libm. |
| Julia animation | ~1.5 KB | SSE + frame loop | Adds time as a dimension; tests state-machine discipline. |

## Status

* **Rule 30:** 3 real iterations of `gemma3:1b` via `harness/runner.py` on 24 May 2026 ([`iterations/rule30/`](iterations/rule30/), chart on [the page](https://zozo123.github.io/wolfram-fb0/#convergence)). Iterations 1–2 (few-shot prompt) assembled to an 8,872-byte ELF but echoed the prompt's example and wrote only a 3-byte `P6\n` header, so the pixel diff stayed at 100%. Iteration 3 (scaffold-fill prompt) returned the scaffold with the TODO unfilled and did not assemble.
* **Mandelbrot, Julia:** not attempted. `src/mandel.s` and `src/julia.s` are `exit(1)` stubs.
* `src/rule30.s` is a placeholder that includes the hand-written `src/rule30_reference.s`.
* The qemu boot, the bpftrace run and the browser stream bridges are written but have not been run end to end.

More detail: [docs/NOTES.md](docs/NOTES.md).

## Provenance & lineage

* **[Fractint](https://www.fractint.org/)** — the 1988 ancestor; integer-math fractals on a 386.
* **[FractalAsm](https://github.com/mrmcsoftware/FractalAsm)** — modern asm fractal renderer.
* **Stephen Wolfram, [A New Kind of Science](https://www.wolframscience.com/nks/)** — the cellular automata.
* **[islo](https://islo.dev)** — the VM sandbox the experiment runs in.
* **[opencode](https://github.com/anomalyco/opencode)** — the coding agent `harness/loop.py` is written to drive.

## About

Built by [Yossi Eliaz](https://yossieliaz.netlify.app/), who works on islo.dev. More experiments: [zozo123.github.io](https://zozo123.github.io/).

## License

MIT. Fork freely.
