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
    # Dated status shards often document rule changes by quoting the
    # rejected phrase. Treat them the same as the claim-discipline
    # doc itself: rule-enumerating prose, not claim-making.
    "docs/status/",
    # Cerebras-evidence-bundle source docs are rule-enumerating by
    # design (they list what the bundle does NOT back). Their archive-
    # root names (CLAIM_SCOPE.md, CEREBRAS_ASK.md, etc.) are already
    # skip-listed in the archive verifier; mirror the same policy at
    # the repo level for their source paths.
    "docs/cerebras-evidence-bundle-claim-scope.md",
    "docs/cerebras-evidence-bundle-readme.md",
    "docs/cerebras-evidence-bundle-ask.md",
    "docs/cerebras-evidence-bundle-local-inspection.md",
    "docs/hardware-validation-appendix.md",
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

HARDWARE_GATED_RULES: list[Rule] = [
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

# 26B / A4B MoE subject tokens. Narrow — only fires when the subject
# is unambiguously a Gemma-4 MoE variant, not incidental mentions of
# "MoE architecture" or "mixture of experts" in generic discussion.
_MOE_SUBJECTS = rb"(?:Gemma[- ]?4[- ]?26B|\b26B[- ]?A4B\b|\bA4B\b|\b26B MoE\b)"

# "runs" / "is working" / "executing" / "succeeded" — the claim verbs
# that assert the MoE is operational on a Doe/Cerebras lane.
_MOE_OPERATIONAL_VERBS = (
    rb"(?:runs|running|works|working|executes|executing|succeeded|"
    rb"passes|passing|operational|live|validated|supported)"
)

# MoE claims: until a doe_moe_*_receipt or moe_router_evidence artifact
# lands, 26B/A4B MoE cannot be claimed to run/work on any Cerebras or
# Doe lane. This gate rejects those claims independently of the
# hardware-receipt gate (MoE architecture claims aren't unlocked by a
# 31B-dense hardware receipt; they need MoE-specific evidence).
MOE_GATED_RULES: list[Rule] = [
    Rule(
        "26B/A4B MoE operational-on-Cerebras claim (needs MoE receipt)",
        re.compile(
            rb"\b" + _MOE_SUBJECTS + rb"\b[^.\n]{0,120}?"
            rb"\b" + _MOE_OPERATIONAL_VERBS + rb"\b[^.\n]{0,40}?"
            rb"\b(?:on|through|under|via)\b[^.\n]{0,20}?"
            rb"\b" + _LANE_SUBJECTS + rb"\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "26B/A4B MoE operational standalone claim",
        re.compile(
            rb"\b" + _MOE_SUBJECTS + rb"\b[^.\n]{0,40}?"
            rb"\b(?:is|are)\b\s+(?:now\s+)?(?:running|working|"
            rb"operational|live|validated|supported)\b",
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


def find_moe_receipt() -> Path | None:
    """Return the first on-disk artifact that proves 26B/A4B MoE has
    been executed (router + expert dispatch + combine receipts). Today
    no such receipt exists; this function is the unlock path. Looks
    for artifactKind values that signal MoE-specific evidence:
    doe_moe_router_receipt, doe_moe_expert_dispatch_receipt,
    doe_moe_combine_receipt, or a model-runtime receipt whose
    modelId contains '26b' or 'a4b' with executionStatus in the
    simulator_success / real_weight_layer_block_success set."""
    # MoE-specific receipt files by artifactKind.
    for p in REPO_ROOT.glob("bench/out/**/*moe*receipt*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ak = (data.get("artifactKind") or "").lower()
        if ak.startswith("doe_moe_") and ak.endswith("_receipt"):
            return p
    # Model-runtime receipts for a Gemma-4 MoE model that have
    # promoted past not_attempted.
    for p in REPO_ROOT.glob("bench/out/*/gemma-*-runtime-receipt.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        mid = (data.get("modelId") or "").lower()
        status = data.get("executionStatus")
        if (
            ("26b" in mid or "a4b" in mid)
            and status in {
                "simulator_success",
                "real_weight_layer_block_success",
                "hardware_success",
            }
        ):
            return p
    return None


def scan(path: str, rules: list[Rule]) -> list[tuple[str, int, str]]:
    full = REPO_ROOT / path
    try:
        data = full.read_bytes()
    except OSError:
        return []
    hits: list[tuple[str, int, str]] = []
    for rule in rules:
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
    moe_receipt = find_moe_receipt()

    # Build the active rule set. Hardware-gated rules are skipped when
    # a hardware_success receipt exists; MoE-gated rules are skipped
    # when a MoE-specific receipt exists. The two gates are
    # independent — 31B-dense hardware does not unlock 26B MoE claims,
    # and vice versa.
    active_rules: list[Rule] = []
    hw_gate_active = hw_receipt is None
    moe_gate_active = moe_receipt is None
    if hw_gate_active:
        active_rules.extend(HARDWARE_GATED_RULES)
    if moe_gate_active:
        active_rules.extend(MOE_GATED_RULES)

    if not active_rules:
        print(
            "PASS: claim-discipline gate INACTIVE on both fronts "
            f"(hardware_success at {hw_receipt.relative_to(REPO_ROOT)}, "
            f"MoE receipt at {moe_receipt.relative_to(REPO_ROOT)}). "
            "Specific claims may now cite these receipts; other "
            "disciplines still gate on their own artifacts."
        )
        return 0

    violations: list[tuple[str, str, int, str]] = []
    for path in tracked_files():
        if not is_text_path(path) or is_skipped(path):
            continue
        for label, line_no, snippet in scan(path, active_rules):
            violations.append((path, label, line_no, snippet))

    hw_tag = "ACTIVE" if hw_gate_active else "inactive"
    moe_tag = "ACTIVE" if moe_gate_active else "inactive"
    header_context = (
        f"hardware-claim gate {hw_tag}"
        + (
            f" (receipt at {hw_receipt.relative_to(REPO_ROOT)})"
            if not hw_gate_active else ""
        )
        + f"; MoE-claim gate {moe_tag}"
        + (
            f" (receipt at {moe_receipt.relative_to(REPO_ROOT)})"
            if not moe_gate_active else ""
        )
    )

    if not violations:
        print(
            f"PASS: claim-discipline gate — {header_context}; "
            "no forbidden-claim patterns found in tracked text files. "
            "Portability and parity claims are in scope; other "
            "claims are gated per docs/claim-discipline.md."
        )
        return 0

    print(
        f"FAIL: claim-discipline gate found {len(violations)} "
        f"forbidden-claim pattern(s). {header_context}. See "
        f"docs/claim-discipline.md for the allowed-claims policy."
    )
    limit = len(violations) if args.show_all else 40
    for path, label, line_no, snippet in violations[:limit]:
        print(f"  {path}:{line_no}: {label}: {snippet!r}")
    if len(violations) > limit:
        print(f"  ... and {len(violations) - limit} more")
    return 1


if __name__ == "__main__":
    sys.exit(main())
