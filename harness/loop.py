"""Agent loop driver — runs INSIDE the islo sandbox VM.

Outer cycle (per target):
    1. Read the current src/<target>.s and last oracle score.
    2. Compose a task spec for opencode (target contract + last error + budget).
    3. Spawn `opencode run` against the local Ollama model.
    4. Capture the new asm, write it to src/<target>.s.
    5. Run oracle.score → (assemble_ok, binary_size, pixel_diff_pct).
    6. Commit the iteration (asm + score + transcript) under iterations/.
    7. If converged (pixel_diff_pct == 0 and binary_size ≤ prev), stop.
       Else, loop with the new score in the next prompt.

This file is intentionally small. The real intelligence lives in the prompts
(prompts/) and in opencode's session loop, not here.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "oracle"))
import score as oracle  # noqa: E402

ITERATIONS = REPO_ROOT / "iterations"
SRC = REPO_ROOT / "src"
PROMPTS = REPO_ROOT / "harness" / "prompts"


def now_tag() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_prompt(target: str) -> str:
    return (PROMPTS / f"{target}.md").read_text()


def call_opencode(prompt: str, model: str, workdir: Path) -> str:
    """Spawns opencode in non-interactive mode against the local Ollama model.
    Returns the model's final reply (which we expect to contain the new asm
    inside a ```nasm fence)."""
    if not shutil.which("opencode"):
        raise RuntimeError(
            "opencode binary not on PATH. Are you running inside the islo sandbox?"
        )
    r = subprocess.run(
        ["opencode", "run", "--model", f"ollama/{model}", "--cwd", str(workdir), prompt],
        capture_output=True, text=True, timeout=900,
    )
    if r.returncode != 0:
        raise RuntimeError(f"opencode failed: {r.stderr}")
    return r.stdout


def extract_asm(reply: str) -> str | None:
    """Pull the first ```nasm ... ``` (or ```asm) fenced block from the reply."""
    for fence in ("```nasm", "```asm", "```"):
        i = reply.find(fence)
        if i < 0:
            continue
        start = reply.find("\n", i) + 1
        end = reply.find("```", start)
        if end > start:
            return reply[start:end].strip() + "\n"
    return None


def snapshot_iteration(target: str, n: int, asm: str, sc: oracle.Score, reply: str) -> Path:
    d = ITERATIONS / target / f"{n:04d}_{now_tag()}"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{target}.s").write_text(asm)
    (d / "score.json").write_text(json.dumps(asdict(sc), indent=2))
    (d / "reply.md").write_text(reply)
    return d


def run_target(target: str, model: str, max_iters: int) -> None:
    print(f"=== {target} ({model}) — up to {max_iters} iterations ===")
    base_prompt = load_prompt(target)
    last_score: oracle.Score | None = None

    for n in range(1, max_iters + 1):
        prompt = base_prompt
        if last_score is not None:
            prompt += "\n\n## Previous iteration result\n```json\n"
            prompt += json.dumps(asdict(last_score), indent=2)
            prompt += "\n```\nMinimize binary_size and pixel_diff_pct."

        try:
            reply = call_opencode(prompt, model, REPO_ROOT)
        except Exception as e:
            print(f"  iter {n}: opencode error: {e}")
            return

        asm = extract_asm(reply)
        if asm is None:
            print(f"  iter {n}: no asm fence in reply, skipping")
            continue

        (SRC / f"{target}.s").write_text(asm)
        sc = oracle.score_target(SRC / f"{target}.s", target)
        snap = snapshot_iteration(target, n, asm, sc, reply)
        print(f"  iter {n}: {sc.summary_line()}  → {snap.relative_to(REPO_ROOT)}")

        last_score = sc
        if sc.assemble_ok and sc.pixel_diff_pct == 0.0:
            print(f"  iter {n}: pixel-perfect — keeping going to shrink binary.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("WOLFRAM_MODEL", "gemma4:e2b"))
    ap.add_argument("--targets", default="rule30,mandel,julia")
    ap.add_argument("--max-iters", type=int, default=40)
    args = ap.parse_args()

    for t in [x.strip() for x in args.targets.split(",") if x.strip()]:
        run_target(t, args.model, args.max_iters)
    return 0


if __name__ == "__main__":
    sys.exit(main())
