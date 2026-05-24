# wolfram-fb0

> **AI wrote x86_64 assembly + eBPF for Wolfram fractals direct to `/dev/fb0` — every step (build, kernel trace, qemu boot, framebuffer) runs in a real Linux VM in your browser via [islo](https://islo.dev). No install. No drift. Fork-and-rerun in one click.**

[![Live demo (islo sandbox)](https://img.shields.io/badge/live%20demo-islo%20sandbox-7c3aed)](https://zozo123.github.io/wolfram-fb0)
[![Fork the sandbox](https://img.shields.io/badge/fork%20the%20sandbox-one%20click-22c55e)](https://zozo123.github.io/wolfram-fb0#fork)

---

## The pitch in one paragraph

Most AI coding sandboxes are containers. You can't write eBPF, touch `/dev/fb0`, or run nested qemu in a container — no kernel modules, no real kprobes, no framebuffer. **islo gives you a real virtualized VM in your browser**, which is what makes this demo legal: an AI (smallest open-weight model we could fit) writes pure x86_64 assembly and eBPF programs that render Stephen Wolfram's cellular automata (Rule 30, 90, 110), the Mandelbrot set, and a Julia animation directly to the Linux framebuffer. Inside the same sandbox: `qemu-system-x86_64` boots a 4 MB Linux straight into the agent-built ELF. eBPF traces every syscall and every byte mmapped to fb0. Both stream out to your browser tab as the fractal blooms.

## Why this exists

* Fractint (1988) and [FractalAsm](https://github.com/mrmcsoftware/FractalAsm) showed that hand-tuned assembly + framebuffer is one of the most visually rewarding low-level art forms in computing.
* Almost every AI-coding demo today is a webapp. The opposite of a webapp — pure ELF, no libc, kernel ABI only — is exactly the kind of work that's *hard* for LLMs (no Stack Overflow corpus to copy) and *easy* to verify (pixel-diff is unforgiving, byte-count is a scalar).
* And every "reproducible" AI demo dies on install friction. The README rots. The toolchain drifts. The model gets deprecated. **The cloud-sandbox-as-replay-link is the reproducibility primitive these demos have been missing.**

## What's in the box

```
src/        — x86_64 assembly (rule30.s, mandel.s, julia.s)
bpf/        — bpftrace programs that X-ray the asm at runtime
oracle/     — Python reference renderer + pixel-diff + binary-size scorer
harness/    — agent loop: islo skills orchestrate, opencode codes, oracle judges
dist/       — final agent-built ELFs
iterations/ — every loop iteration, committed (the convergence record)
qemu/       — boot.sh + tiny initramfs for the framebuffer demo
site/       — GitHub Pages: plot, live viewer, charts, fork link
docs/       — design notes
islo.yaml   — declares the real-VM sandbox shape
```

## Run it (the islo way)

You don't need anything installed. Click the **Fork the sandbox** button at the top, or:

```bash
islo use wolfram-fb0 --source github://zozo123/wolfram-fb0
# → boots a real VM with nasm, qemu, bpftrace, opencode, model, all warmed.
# Inside: `make demo` boots the fractal, opens the eBPF trace, streams to your browser.
```

To watch the agent rebuild from scratch:

```bash
islo use wolfram-fb0 -- make agent-loop
```

## Run it (the hard way, on your own Linux box)

You'll need `nasm`, `ld`, `qemu-system-x86_64`, `bpftrace`, Python 3 with `pillow`/`numpy`, an Ollama with a small Gemma pulled, and `opencode`. We support this for masochists. The full sandbox image is one `make sandbox-snapshot-import` away if you really want it.

## Targets

| Target | Asm budget | Math | Why it's interesting |
| --- | --- | --- | --- |
| Rule 30 | ~256 B | integer XOR | Wolfram's signature 1-D automaton. Trivial math, ruthless on byte budget. |
| Mandelbrot | ~1 KB | SSE float, no libc | Forces the model to use raw SSE; no `sin`/`cos`, no libm. |
| Julia animation | ~1.5 KB | SSE + frame loop | Adds time as a dimension; tests state-machine discipline. |

## Convergence

After the agent loop finishes, this section will embed the charts: binary size descent over iterations and pixel-diff convergence, by target. *(Will appear after first full run.)*

## Provenance & lineage

* **[Fractint](https://www.fractint.org/)** — the 1988 ancestor; integer-math fractals on a 386.
* **[FractalAsm](https://github.com/mrmcsoftware/FractalAsm)** — modern asm fractal renderer.
* **Stephen Wolfram, [A New Kind of Science](https://www.wolframscience.com/nks/)** — the cellular automata.
* **[islo](https://islo.dev)** — the real-VM sandbox that makes the whole thing one click.
* **[opencode](https://github.com/sst/opencode)** — the inner-loop coding agent.

## License

MIT. Fork freely.
