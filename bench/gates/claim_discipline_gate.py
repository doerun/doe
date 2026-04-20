#!/usr/bin/env python3
"""Fail the build if public docs make Gemma-4-on-Cerebras claims that
aren't yet backed by an executionStatus=hardware_success receipt.

This gate enforces docs/claim-discipline.md. Specifically it keeps
the "any performance or efficiency claim" rule from drifting into
prose before a hardware receipt exists.

Gate state:

  ACTIVE  — no model-runtime-receipt on disk has
            executionStatus=hardware_success. Performance claims are
            forbidden until one does.

  INACTIVE — at least one hardware_success receipt found. Performance
            claims may reference it, but other disciplines (real-weight,
            full-model, Doppler-production-path) remain gated by their
            own artifacts. This gate does not reason about those.

While ACTIVE, the gate scans tracked text files (same set as
doe_private_strategy_leak_gate) for high-confidence performance-claim
patterns. Patterns are deliberately narrow to avoid false positives
on legitimate methodology or benchmarking discussion. The gate is NOT
a replacement for human review; it's a tripwire for the obvious drift.

Exit 0 on PASS (inactive, or active with no violations).
Exit 1 on FAIL (active + violations found).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

TEXT_SUFFIXES = {
    ".md", ".txt", ".py", ".js", ".mjs", ".ts", ".tsx", ".html",
    ".json",
}

SKIP_PREFIXES: tuple[str, ...] = (
    "browser/chromium/src/",
    "browser/chromium/node_modules/",
    "browser/chromium/depot_tools/",
    "node_modules/",
    "packages/doe-gpu/node_modules/",
    "demos/gaussian-splat-viewer/data/",
    # The gate, its doc, and precedent leak-gate reference these
    # phrases verbatim as the rules they enforce.
    "bench/gates/claim_discipline_gate.py",
    "bench/gates/doe_private_strategy_leak_gate.py",
    "docs/claim-discipline.md",
    "docs/numeric-stability-claim-ladder.md",
    # docs/performance-strategy.md is methodology discussion, not
    # claim-making. It's allowed to name the tokens the gate rejects.
    "docs/performance-strategy.md",
)


@dataclass(frozen=True)
class Rule:
    label: str
    pattern: re.Pattern[bytes]


# High-confidence performance-claim patterns SCOPED TO THE GEMMA-4 /
# CEREBRAS LANE. This gate is not about generic Doe-vs-Dawn WebGPU
# backend claims — those are governed by run_blocking_gates.py's
# apples-to-apples comparability discipline and have their own artifact
# backing. This gate ONLY fires when the subject is Gemma / Cerebras /
# CSL / simfabric / WSE / WSC, because those are the lanes whose
# performance claims require a hardware_success receipt per
# docs/claim-discipline.md.
_LANE_SUBJECTS = rb"(?:Gemma(?:[- ]?\d)?|Cerebras|CSL|simfabric|WSE|WSC|SdkLayout)"
_PERF_TOKENS = rb"(?:faster|fastest|speed[- ]?up|outperforms?|beats)"

RULES: list[Rule] = [
    Rule(
        "Gemma/Cerebras lane speed claim",
        re.compile(
            rb"\b" + _LANE_SUBJECTS + rb"\b[^.\n]{0,120}?"
            rb"\b(?:is|runs|executes|delivers|achieves)\b[^.\n]{0,60}?"
            rb"\b" + _PERF_TOKENS + rb"\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "Nx speedup claim on Gemma/Cerebras lane",
        re.compile(
            rb"\b\d+(?:\.\d+)?\s?x\s+(?:faster|speed[- ]?up|"
            rb"throughput|performance)\b[^.\n]{0,120}?"
            rb"\b" + _LANE_SUBJECTS + rb"\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "Gemma/Cerebras lane production-grade claim",
        re.compile(
            rb"\b(?:production[- ]grade|market[- ]leading|"
            rb"best[- ]in[- ]class|state[- ]of[- ]the[- ]art)\s+"
            rb"(?:speed|performance|throughput|latency)\b"
            rb"[^.\n]{0,120}?\b" + _LANE_SUBJECTS + rb"\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "outperforms named runtime on Gemma/Cerebras lane",
        re.compile(
            rb"\b" + _LANE_SUBJECTS + rb"\b[^.\n]{0,80}?"
            rb"\boutperforms?\s+(?:Dawn|WebGPU|Metal|Vulkan|D3D12|"
            rb"CUDA|PyTorch|ONNX|TensorRT|vLLM)\b",
            re.IGNORECASE,
        ),
    ),
]


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files"],
        capture_output=True, text=True, check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def is_text_path(path: str) -> bool:
    return Path(path).suffix.lower() in TEXT_SUFFIXES


def is_skipped(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in SKIP_PREFIXES)


def find_hardware_success_receipt() -> Path | None:
    """Return the first on-disk model-runtime receipt whose
    executionStatus is 'hardware_success', or None if none exists."""
    for p in REPO_ROOT.glob("bench/out/*/gemma-*-runtime-receipt.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("executionStatus") == "hardware_success":
            return p
    return None


def scan(path: str) -> list[tuple[str, int, str]]:
    full = REPO_ROOT / path
    try:
        data = full.read_bytes()
    except OSError:
        return []
    hits: list[tuple[str, int, str]] = []
    for rule in RULES:
        for match in rule.pattern.finditer(data):
            line_no = data.count(b"\n", 0, match.start()) + 1
            snippet = match.group(0).decode("utf-8", "replace")
            hits.append((rule.label, line_no, snippet))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--show-all", action="store_true",
        help="Print every violation. Default shows first 40 then counts.",
    )
    args = parser.parse_args()

    hw_receipt = find_hardware_success_receipt()
    if hw_receipt is not None:
        rel = hw_receipt.relative_to(REPO_ROOT)
        print(
            f"PASS: claim-discipline gate INACTIVE "
            f"(hardware_success receipt found at {rel}). "
            f"Performance claims may cite this receipt, but real-"
            f"weight / Doppler-production / full-model claims remain "
            f"gated by their own artifacts."
        )
        return 0

    violations: list[tuple[str, str, int, str]] = []
    for path in tracked_files():
        if not is_text_path(path) or is_skipped(path):
            continue
        for label, line_no, snippet in scan(path):
            violations.append((path, label, line_no, snippet))

    if not violations:
        print(
            "PASS: claim-discipline gate ACTIVE (no hardware_success "
            "receipt); no performance-claim patterns found in tracked "
            "text files. Portability and parity claims are in scope; "
            "performance claims are gated per docs/claim-discipline.md."
        )
        return 0

    print(
        f"FAIL: claim-discipline gate found {len(violations)} "
        f"performance-claim pattern(s) while ACTIVE (no "
        f"hardware_success receipt exists). See docs/claim-"
        f"discipline.md for the allowed-claims policy."
    )
    limit = len(violations) if args.show_all else 40
    for path, label, line_no, snippet in violations[:limit]:
        print(f"  {path}:{line_no}: {label}: {snippet!r}")
    if len(violations) > limit:
        print(f"  ... and {len(violations) - limit} more")
    return 1


if __name__ == "__main__":
    sys.exit(main())
