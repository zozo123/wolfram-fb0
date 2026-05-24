# wolfram-fb0 — runs inside an islo sandbox VM.
# Local Mac just edits files and pushes; everything else is `islo use wolfram-fb0 -- make <target>`.

.PHONY: help demo agent-loop oracle build-rule30 build-mandel build-julia qemu-boot bpf-trace site clean

WOLFRAM_DIST ?= dist
WOLFRAM_ITER ?= iterations
WOLFRAM_MODEL ?= gemma3:1b

help:
	@echo "wolfram-fb0 — make targets (run inside the islo sandbox):"
	@echo ""
	@echo "  make demo          Boot the agent-built fractals in qemu on a real framebuffer."
	@echo "                     Streams the framebuffer + eBPF trace out via islo share."
	@echo "  make agent-loop    Run the full agent loop (opencode + Gemma → asm → oracle → commit)."
	@echo "                     Iterates until convergence on binary size + pixel-diff."
	@echo "  make oracle        Run the oracle (pixel-diff vs Python reference + size) on dist/."
	@echo "  make build-rule30  Assemble src/rule30.s → dist/rule30.elf."
	@echo "  make build-mandel  Assemble src/mandel.s → dist/mandel.elf."
	@echo "  make build-julia   Assemble src/julia.s  → dist/julia.elf."
	@echo "  make qemu-boot     Boot dist/*.elf in qemu with a real framebuffer."
	@echo "  make bpf-trace     Attach bpf/trace.bt to the next-running fractal binary."
	@echo "  make site          Build the static GitHub Pages site under site/_site/."
	@echo "  make clean         Remove dist/ artifacts and qemu build."

demo: build-rule30 build-mandel build-julia
	@bash qemu/boot.sh

agent-loop:
	python3 harness/loop.py --model "$(WOLFRAM_MODEL)" --targets rule30,mandel,julia

oracle:
	python3 oracle/score.py --dist "$(WOLFRAM_DIST)"

build-rule30:
	@mkdir -p "$(WOLFRAM_DIST)"
	nasm -felf64 src/rule30.s -o "$(WOLFRAM_DIST)/rule30.o"
	ld -o "$(WOLFRAM_DIST)/rule30.elf" "$(WOLFRAM_DIST)/rule30.o"

build-mandel:
	@mkdir -p "$(WOLFRAM_DIST)"
	nasm -felf64 src/mandel.s -o "$(WOLFRAM_DIST)/mandel.o"
	ld -o "$(WOLFRAM_DIST)/mandel.elf" "$(WOLFRAM_DIST)/mandel.o"

build-julia:
	@mkdir -p "$(WOLFRAM_DIST)"
	nasm -felf64 src/julia.s -o "$(WOLFRAM_DIST)/julia.o"
	ld -o "$(WOLFRAM_DIST)/julia.elf" "$(WOLFRAM_DIST)/julia.o"

qemu-boot:
	@bash qemu/boot.sh

bpf-trace:
	bpftrace bpf/trace.bt

site:
	@bash site/build.sh

clean:
	rm -rf "$(WOLFRAM_DIST)" qemu/build qemu/initramfs.cpio.gz qemu/bzImage site/_site
