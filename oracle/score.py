"""Oracle: assemble an asm source, run it in --ppm mode, pixel-diff against the
Python reference, also report binary size and any toolchain errors.

This is the scalar feedback the agent loop optimizes:
  - pixel_diff_pct  (0.0 = perfect)
  - binary_size     (smaller = better, lower-bounded by hand-written reference)
  - assemble_ok     (bool — gate; nothing else matters if False)

Runs inside the islo sandbox (nasm + ld are there). The harness calls this.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import reference

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Score:
    target: str
    asm_path: str
    assemble_ok: bool
    binary_size: int
    pixel_diff_pct: float
    pixels_total: int
    pixels_off: int
    stderr: str

    def summary_line(self) -> str:
        ok = "✓" if self.assemble_ok else "✗"
        return (
            f"{ok} {self.target:8s}  size={self.binary_size:5d}B  "
            f"diff={self.pixel_diff_pct:6.2f}%  ({self.pixels_off}/{self.pixels_total} px)"
        )


def assemble(asm: Path, out_elf: Path) -> tuple[bool, str]:
    obj = out_elf.with_suffix(".o")
    r = subprocess.run(
        ["nasm", "-felf64", str(asm), "-o", str(obj)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return False, r.stderr
    r = subprocess.run(
        ["ld", "-o", str(out_elf), str(obj)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return False, r.stderr
    return True, ""


def render_elf(elf: Path) -> tuple[bytes, str]:
    """Run the ELF in --ppm mode, capture stdout (the PPM bytes)."""
    r = subprocess.run(
        [str(elf), "--ppm"],
        capture_output=True, timeout=30,
    )
    return r.stdout, r.stderr.decode("utf-8", "replace")


def pixel_diff(produced: bytes, expected: bytes) -> tuple[int, int]:
    """Returns (pixels_off, pixels_total). Skips PPM header by finding the
    pixel-data start (third newline ends the header in P6)."""
    def split_header(buf: bytes) -> bytes:
        nl = 0
        for i, b in enumerate(buf):
            if b == 0x0A:
                nl += 1
                if nl == 3:
                    return buf[i + 1:]
        return buf

    a = split_header(produced)
    b = split_header(expected)
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    total = n // 3
    off = 0
    for i in range(0, n, 3):
        if a[i] != b[i] or a[i + 1] != b[i + 1] or a[i + 2] != b[i + 2]:
            off += 1
    return off, total


def score_target(asm: Path, target: str) -> Score:
    with tempfile.TemporaryDirectory() as td:
        out_elf = Path(td) / f"{target}.elf"
        ok, err = assemble(asm, out_elf)
        if not ok:
            return Score(target, str(asm), False, 0, 100.0, 0, 0, err)

        binary_size = out_elf.stat().st_size
        produced, stderr = render_elf(out_elf)

        if target == "julia":
            expected = reference.julia(frame=0)
        else:
            expected = reference.TARGETS[target].render(**reference.TARGETS[target].args)

        off, total = pixel_diff(produced, expected)
        pct = (off / total * 100.0) if total else 100.0
        return Score(target, str(asm), True, binary_size, pct, total, off, stderr)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--target", choices=list(reference.TARGETS) + ["all"], default="all")
    p.add_argument("--src-dir", default=str(REPO_ROOT / "src"))
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    src_dir = Path(args.src_dir)
    targets = list(reference.TARGETS) if args.target == "all" else [args.target]

    scores: list[Score] = []
    for t in targets:
        asm = src_dir / f"{t}.s"
        if not asm.exists():
            print(f"⚠ {asm} missing — skipping", file=sys.stderr)
            continue
        scores.append(score_target(asm, t))

    if args.json:
        print(json.dumps([asdict(s) for s in scores], indent=2))
    else:
        for s in scores:
            print(s.summary_line())

    return 0 if all(s.assemble_ok for s in scores) else 1


if __name__ == "__main__":
    if not shutil.which("nasm") or not shutil.which("ld"):
        print("oracle: nasm/ld not on PATH — are you running this inside the islo sandbox?", file=sys.stderr)
        sys.exit(2)
    sys.exit(main())
