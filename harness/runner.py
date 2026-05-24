"""Persistent agent-loop runner. Runs entirely INSIDE the islo sandbox.

Survives `islo use` disconnects via nohup. Each iteration:
  1. Calls `ollama run <model> <prompt>` with a budget.
  2. Strips ANSI, extracts the LAST fenced code block.
  3. Validates it looks like NASM (must contain `section`/`BITS`/`syscall` markers).
  4. Writes to src/rule30.s.
  5. Runs the oracle (nasm → ld → run → pixel-diff vs Python reference).
  6. Snapshots the iteration under iterations/rule30/NNNN_<utc>/.
  7. Appends to iterations/index.json (the chart-data file).
  8. Picks the next prompt strategy and loops.

Prompt strategies escalate from "simple ask" → "few-shot" → "scaffold-fill".
The escalation gives the model progressively more help; the convergence curve
shows where the model's capability cliff lives.

Run: WOLFRAM_MODEL=gemma3:1b python3 harness/runner.py --target rule30 --max-iters 8
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "oracle"))
import score as oracle  # noqa: E402

ITER_DIR = REPO / "iterations"
SRC = REPO / "src"
PROMPT_DIR = REPO / "harness" / "prompts"
INDEX_JSON = ITER_DIR / "index.json"

ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
FENCE_PAT = re.compile(r"```[a-zA-Z0-9_+\-]*\s*\n(.*?)```", re.S)


def now_tag() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def looks_like_nasm(text: str) -> bool:
    return any(m in text for m in ("section", "BITS 64", "syscall", "_start"))


def run_ollama(model: str, prompt: str, budget_s: int) -> tuple[str, int]:
    """Returns (raw_output, return_code). Strips ANSI inside output."""
    cmd = ["timeout", str(budget_s), "ollama", "run", model, prompt]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return ANSI.sub("", r.stdout + r.stderr).replace("\r", ""), r.returncode


def extract_fence(text: str) -> str | None:
    matches = FENCE_PAT.findall(text)
    return matches[-1].strip() + "\n" if matches else None


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.md").read_text()


def make_scaffold_prompt(target: str) -> str:
    """Hardest-mode helper: paste the reference asm with the inner loop blanked
    and ask the model to complete the [TODO]. Used as the final escalation
    when simpler prompts fail."""
    ref = (SRC / f"{target}_reference.s").read_text()
    # Find the inner-loop section and replace with a TODO marker.
    blanked = re.sub(
        r"(\.compute:.*?(?=\.done:|\s*; --- copy))",
        "    ; [TODO: implement Rule 30 update — new[x] = left XOR (center OR right)]\n    ; replace this comment with real NASM that fills row_b from row_a.\n",
        ref, count=1, flags=re.S,
    )
    return (
        "Here is a near-complete x86_64 NASM program. Replace the [TODO] block with the missing Rule 30 update logic, leave everything else unchanged. Reply with ONLY the complete program inside a triple-backtick `nasm` fence.\n\n"
        "```nasm\n" + blanked + "\n```\n"
    )


@dataclass
class IterResult:
    iter: int
    strategy: str
    duration_s: float
    fence_found: bool
    nasm_looking: bool
    assemble_ok: bool
    binary_size: int
    pixel_diff_pct: float
    pixels_off: int
    pixels_total: int


def update_index(target: str, results: list[IterResult]) -> None:
    """Rewrite iterations/index.json from real results, preserving other targets'
    placeholder/real data."""
    idx: dict = json.loads(INDEX_JSON.read_text()) if INDEX_JSON.exists() else {"targets": {}}
    idx.setdefault("targets", {})
    idx["targets"][target] = [
        {
            "iter": r.iter,
            "strategy": r.strategy,
            "binary_size": r.binary_size,
            "pixel_diff_pct": round(r.pixel_diff_pct, 2),
            "assemble_ok": r.assemble_ok,
        }
        for r in results
    ]
    idx["_note"] = f"Real data. Last updated {now_tag()} by harness/runner.py."
    INDEX_JSON.write_text(json.dumps(idx, indent=2))


def snapshot(target: str, n: int, asm: str | None, raw_reply: str, result: IterResult) -> Path:
    d = ITER_DIR / target / f"{n:04d}_{now_tag()}"
    d.mkdir(parents=True, exist_ok=True)
    if asm is not None:
        (d / f"{target}.s").write_text(asm)
    (d / "reply.raw").write_text(raw_reply)
    (d / "score.json").write_text(json.dumps(asdict(result), indent=2))
    return d


def run_target(target: str, model: str, max_iters: int, budget_s: int) -> None:
    print(f"[runner] target={target} model={model} max_iters={max_iters} budget={budget_s}s")
    strategies = ["fewshot", "fewshot", "scaffold", "scaffold", "scaffold", "scaffold", "scaffold", "scaffold"]
    results: list[IterResult] = []

    for n in range(1, max_iters + 1):
        strat = strategies[min(n - 1, len(strategies) - 1)]
        if strat == "scaffold":
            prompt = make_scaffold_prompt(target)
        else:
            prompt = load_prompt(target)

        print(f"[runner] iter {n} ({strat}) ...")
        t0 = dt.datetime.now()
        raw, rc = run_ollama(model, prompt, budget_s)
        elapsed = (dt.datetime.now() - t0).total_seconds()
        print(f"[runner]   ollama rc={rc} {elapsed:.1f}s")

        asm = extract_fence(raw)
        nasm_ok = bool(asm and looks_like_nasm(asm))

        if asm and nasm_ok:
            (SRC / f"{target}.s").write_text(asm)
            sc = oracle.score_target(SRC / f"{target}.s", target)
            res = IterResult(
                iter=n, strategy=strat, duration_s=elapsed,
                fence_found=True, nasm_looking=True,
                assemble_ok=sc.assemble_ok,
                binary_size=sc.binary_size,
                pixel_diff_pct=sc.pixel_diff_pct,
                pixels_off=sc.pixels_off,
                pixels_total=sc.pixels_total,
            )
        else:
            res = IterResult(
                iter=n, strategy=strat, duration_s=elapsed,
                fence_found=bool(asm), nasm_looking=False,
                assemble_ok=False, binary_size=0,
                pixel_diff_pct=100.0, pixels_off=0, pixels_total=0,
            )

        results.append(res)
        d = snapshot(target, n, asm if nasm_ok else None, raw, res)
        update_index(target, results)
        print(f"[runner]   {'✓' if res.assemble_ok else '✗'} size={res.binary_size} "
              f"diff={res.pixel_diff_pct:.2f}% → {d.relative_to(REPO)}")

        if res.assemble_ok and res.pixel_diff_pct == 0.0:
            print("[runner] pixel-perfect. continuing to shrink…")

    print("[runner] done.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="rule30")
    ap.add_argument("--model", default=os.environ.get("WOLFRAM_MODEL", "gemma3:1b"))
    ap.add_argument("--max-iters", type=int, default=8)
    ap.add_argument("--budget-s", type=int, default=180)
    args = ap.parse_args()

    if not shutil.which("ollama") or not shutil.which("nasm"):
        print("ERROR: ollama or nasm not on PATH — run inside the islo sandbox.")
        return 2

    ITER_DIR.mkdir(parents=True, exist_ok=True)
    (ITER_DIR / args.target).mkdir(parents=True, exist_ok=True)

    run_target(args.target, args.model, args.max_iters, args.budget_s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
