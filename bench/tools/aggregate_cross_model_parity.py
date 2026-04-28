#!/usr/bin/env python3
"""Aggregate Gemma 4 31B + Qwen 3.6 27B pre-hardware parity evidence.

The receipt joins the r3-1-* and r3-2-* evidence trees and gates the
pre-hardware claim that both model bundles are bound to the same Doe CSL
lowering surface. It is intentionally stricter than a status summary:
missing evidence, stale host-plan hashes, compile failures, or version/hash
skew all produce ``verdict=unbound``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_OUT = REPO_ROOT / "bench/out/r3-cross-model-parity/receipt.json"

MODEL_DEFAULTS = {
    "gemma4_31b": {
        "modelId": "gemma-4-31b-it-text-q4k-ehf16-af32",
        "compileReceipt": REPO_ROOT / "bench/out/r3-1-31b-full-graph-compile-attempt/receipt.json",
        "hostPlan": REPO_ROOT / "bench/out/r3-1-31b-manifest-fullgraph-compile-steps/host-plan.json",
        "compileRoot": REPO_ROOT / "bench/out/r3-1-31b-manifest-fullgraph-compile-steps/compile",
        "driverResult": REPO_ROOT / "bench/out/r3-1-31b-manifest-fullgraph-compile-steps/trace.json.driver-result.json",
        "budget": REPO_ROOT / "bench/out/r3-1-31b-manifest-simfabric-predicted-wallclock/budget.json",
    },
    "qwen3_6_27b": {
        "modelId": "qwen-3-6-27b-q4k-ehaf16",
        "compileReceipt": REPO_ROOT / "bench/out/r3-2-27b-full-graph-compile-attempt/receipt.json",
        "hostPlan": REPO_ROOT / "bench/out/r3-2-27b-manifest-fullgraph-compile-steps/host-plan.json",
        "compileRoot": REPO_ROOT / "bench/out/r3-2-27b-manifest-fullgraph-compile-steps/compile",
        "driverResult": REPO_ROOT / "bench/out/r3-2-27b-manifest-fullgraph-compile-steps/trace.json.driver-result.json",
        "budget": REPO_ROOT / "bench/out/r3-2-27b-manifest-simfabric-predicted-wallclock/budget.json",
    },
}

SHARED_KERNELS = (
    ("gemv", "gemv", "gemv"),
    ("rmsnorm", "rmsnorm", "rmsnorm"),
    ("rope", "rope", "rope_partial"),
)
PER_KERNEL_FILES = ("layout.csl", "pe_program.csl", "pe_program.metadata.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--allow-unbound",
        action="store_true",
        help="Write the receipt but exit 0 even when verdict=unbound.",
    )
    return parser.parse_args()


def _rel(path: Path | str | None) -> str | None:
    if path is None:
        return None
    p = Path(path)
    try:
        return str(p.resolve().relative_to(REPO_ROOT))
    except (ValueError, OSError):
        return str(path)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path, issues: list[str], label: str) -> dict[str, Any] | None:
    if not path.is_file():
        issues.append(f"{label}: missing {_rel(path)}")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(f"{label}: invalid JSON at {_rel(path)}: {exc}")
        return None
    if not isinstance(payload, dict):
        issues.append(f"{label}: expected JSON object at {_rel(path)}")
        return None
    return payload


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _parse_tsir_contract_version(schema_path: Path) -> int | None:
    if not schema_path.is_file():
        return None
    match = re.search(
        r"pub const CONTRACT_VERSION:\s*u32\s*=\s*(\d+);",
        schema_path.read_text(encoding="utf-8"),
    )
    return int(match.group(1)) if match else None


def _driver_targets(driver_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(driver_result, dict):
        return []
    compile_section = driver_result.get("compile")
    if not isinstance(compile_section, dict):
        return []
    targets = compile_section.get("targets")
    return [t for t in targets if isinstance(t, dict)] if isinstance(targets, list) else []


def _cslc_hash_from_driver(driver_path: Path, driver: dict[str, Any] | None) -> dict[str, Any]:
    targets = _driver_targets(driver)
    command = None
    for target in targets:
        raw_command = target.get("command")
        if isinstance(raw_command, list) and raw_command:
            command = raw_command
            break
    executable = str(command[0]) if command else None
    exe_path = Path(executable) if executable else None
    executable_hash = _sha256_file(exe_path) if exe_path is not None else None
    fallback_hash = _sha256_bytes(
        json.dumps(
            {
                "driverResult": _rel(driver_path),
                "executable": executable,
                "sdkMinVersionSource": "runtime/zig/src/doe_wgsl/csl_spec.zig",
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    return {
        "driverResultPath": _rel(driver_path),
        "executable": executable,
        "executableSha256": executable_hash,
        "toolchainHash": executable_hash or fallback_hash,
        "hashSource": "cslc_executable_sha256" if executable_hash else "driver_command_fallback",
    }


def _compile_receipt_summary(payload: dict[str, Any] | None, issues: list[str], label: str) -> dict[str, Any]:
    if payload is None:
        return {"bound": False}
    attempted = bool(payload.get("compileAttempted"))
    failed_count = int(payload.get("compileFailedCount") or 0)
    blocked_count = int(payload.get("compileBlockedCount") or 0)
    accepted_blocked_count = int(payload.get("compileAcceptedBlockedCount") or 0)
    succeeded_count = int(payload.get("compileSucceededCount") or 0)
    target_count = int(payload.get("compileTargetCount") or 0)
    blocker = payload.get("blocker")
    accepted_blockers = payload.get("acceptedCompileBlockers")
    if accepted_blockers is None:
        accepted_blockers = []
    if not isinstance(accepted_blockers, list):
        issues.append(f"{label}: acceptedCompileBlockers is not a list")
        accepted_blockers = []
    bound = attempted and failed_count == 0 and target_count > 0
    if not attempted:
        issues.append(f"{label}: compileAttempted is false")
    if failed_count != 0:
        issues.append(f"{label}: compileFailedCount={failed_count}")
    if accepted_blocked_count > blocked_count:
        issues.append(
            f"{label}: compileAcceptedBlockedCount exceeds compileBlockedCount"
        )
    if accepted_blocked_count != len(accepted_blockers):
        issues.append(
            f"{label}: acceptedCompileBlockers length does not match count"
        )
    if target_count <= 0:
        issues.append(f"{label}: compileTargetCount is empty")
    return {
        "artifactKind": payload.get("artifactKind"),
        "hostPlanHash": payload.get("hostPlanHash"),
        "compileAttempted": attempted,
        "compileTargetCount": target_count,
        "compileSucceededCount": succeeded_count,
        "compileBlockedCount": blocked_count,
        "compileAcceptedBlockedCount": accepted_blocked_count,
        "compileFailedCount": failed_count,
        "acceptedCompileBlockers": accepted_blockers,
        "blocker": blocker,
        "bound": bound,
    }


def _budget_summary(payload: dict[str, Any] | None, issues: list[str], label: str) -> dict[str, Any]:
    if payload is None:
        return {"bound": False}
    calibrated = bool(payload.get("calibrated"))
    grand = payload.get("grandPredictedCycles")
    issues_list = payload.get("issues") if isinstance(payload.get("issues"), list) else []
    bound = calibrated and isinstance(grand, int) and not issues_list
    if not calibrated:
        issues.append(f"{label}: simfabric budget is not calibrated")
    if not isinstance(grand, int):
        issues.append(f"{label}: grandPredictedCycles missing")
    if issues_list:
        issues.append(f"{label}: budget has issues: {issues_list}")
    return {
        "artifactKind": payload.get("artifactKind"),
        "hostPlanHash": payload.get("hostPlanHash"),
        "calibrated": calibrated,
        "grandPredictedCycles": grand,
        "phaseTotals": payload.get("phaseTotals"),
        "bound": bound,
    }


def _compare_kernel_files(
    gemma_root: Path,
    qwen_root: Path,
    logical_name: str,
    gemma_name: str,
    qwen_name: str,
    issues: list[str],
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "logicalKernel": logical_name,
        "gemmaKernel": gemma_name,
        "qwenKernel": qwen_name,
        "artifacts": {},
    }
    match_all = True
    for filename in PER_KERNEL_FILES:
        gemma_path = gemma_root / gemma_name / filename
        qwen_path = qwen_root / qwen_name / filename
        gemma_hash = _sha256_file(gemma_path)
        qwen_hash = _sha256_file(qwen_path)
        match = gemma_hash is not None and gemma_hash == qwen_hash
        if not match:
            match_all = False
        record["artifacts"][filename] = {
            "gemmaSha256": gemma_hash,
            "qwenSha256": qwen_hash,
            "match": match,
        }
    record["match"] = match_all
    record["enforcement"] = (
        "observational: compile artifacts may differ because model compile "
        "params differ; invoker byte identity is enforced by "
        "runtime/zig/tests/wgsl/exec_v1_paired_gate_canary_test.zig"
    )
    return record


def build_receipt() -> dict[str, Any]:
    issues: list[str] = []
    git_head = _git_head()
    if git_head is None:
        issues.append("unable to resolve Doe git HEAD")

    op_to_spec_path = REPO_ROOT / "runtime/zig/src/doe_wgsl/emit_csl_exec_v1.zig"
    tsir_schema_path = REPO_ROOT / "runtime/zig/src/tsir/schema.zig"
    csl_spec_path = REPO_ROOT / "runtime/zig/src/doe_wgsl/csl_spec.zig"
    toolchains_path = REPO_ROOT / "config/toolchains.json"

    versions = {
        "doeGpuCommit": git_head,
        "runtimeZigCommit": git_head,
        "opToSpecTableVersion": _sha256_file(op_to_spec_path),
        "opToSpecTablePath": _rel(op_to_spec_path),
        "tsirSchemaVersion": _parse_tsir_contract_version(tsir_schema_path),
        "tsirSchemaSha256": _sha256_file(tsir_schema_path),
        "tsirSchemaPath": _rel(tsir_schema_path),
        "cslSpecSha256": _sha256_file(csl_spec_path),
        "toolchainsSha256": _sha256_file(toolchains_path),
    }
    for key, value in versions.items():
        if value is None and key.endswith(("Version", "Commit", "Sha256")):
            issues.append(f"version field {key} is unresolved")

    model_records: dict[str, Any] = {}
    toolchain_hashes: dict[str, str] = {}
    for model_key, cfg in MODEL_DEFAULTS.items():
        model_issues: list[str] = []
        compile_receipt = _load_json(cfg["compileReceipt"], model_issues, f"{model_key}.compileReceipt")
        host_plan = _load_json(cfg["hostPlan"], model_issues, f"{model_key}.hostPlan")
        driver_result = _load_json(cfg["driverResult"], model_issues, f"{model_key}.driverResult")
        budget = _load_json(cfg["budget"], model_issues, f"{model_key}.budget")

        compile_summary = _compile_receipt_summary(compile_receipt, model_issues, model_key)
        budget_record = _budget_summary(budget, model_issues, model_key)
        host_plan_hash = _sha256_file(cfg["hostPlan"])
        if compile_summary.get("hostPlanHash") != host_plan_hash:
            model_issues.append(
                f"{model_key}: compile receipt hostPlanHash does not match host-plan file"
            )
        if budget_record.get("hostPlanHash") != host_plan_hash:
            model_issues.append(
                f"{model_key}: budget hostPlanHash does not match host-plan file"
            )

        cslc_record = _cslc_hash_from_driver(cfg["driverResult"], driver_result)
        toolchain_hashes[model_key] = str(cslc_record["toolchainHash"])

        targets = host_plan.get("compileTargets") if isinstance(host_plan, dict) else []
        model_records[model_key] = {
            "modelId": cfg["modelId"],
            "compileReceiptPath": _rel(cfg["compileReceipt"]),
            "hostPlanPath": _rel(cfg["hostPlan"]),
            "hostPlanSha256": host_plan_hash,
            "compileRoot": _rel(cfg["compileRoot"]),
            "compileTargetNames": [
                str(t.get("name"))
                for t in targets
                if isinstance(t, dict) and isinstance(t.get("name"), str)
            ],
            "compileReceipt": compile_summary,
            "simfabricBudget": budget_record,
            "cslcToolchain": cslc_record,
            "issues": model_issues,
            "bound": not model_issues,
        }
        issues.extend(model_issues)

    if len(set(toolchain_hashes.values())) != 1:
        issues.append(f"cslc toolchain hash mismatch: {toolchain_hashes}")

    shared_kernel_records = [
        _compare_kernel_files(
            MODEL_DEFAULTS["gemma4_31b"]["compileRoot"],
            MODEL_DEFAULTS["qwen3_6_27b"]["compileRoot"],
            logical,
            gemma_name,
            qwen_name,
            issues,
        )
        for logical, gemma_name, qwen_name in SHARED_KERNELS
    ]

    verdict = "bound" if not issues else "unbound"
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_cross_model_parity_receipt",
        "receiptClass": "r3_gemma4_31b_qwen3_6_27b_prehardware_joint_gate",
        "verdict": verdict,
        "issues": issues,
        "versions": versions,
        "sharedCslcToolchainHash": next(iter(set(toolchain_hashes.values())), None),
        "models": model_records,
        "sharedKernelArtifactComparison": shared_kernel_records,
        "claim": {
            "scope": (
                "Pre-hardware joint gate for Gemma 4 31B and Qwen 3.6 27B. "
                "Bound means both r3 evidence trees are present, host-plan hashes "
                "match their compile and simfabric-budget receipts, cslc toolchain "
                "identity is shared, Doe runtime/TSIR/opToSpec versions are shared, "
                "and shared-kernel invoker byte identity is pinned by the paired-gate canary."
            ),
            "notWhat": (
                "Not a Cerebras hardware receipt and not a performance claim. "
                "Hardware parity, TTFT, prefill tok/s, decode tok/s, and cost/token "
                "remain gated on governed WSE receipts."
            ),
        },
    }


def main() -> int:
    args = parse_args()
    receipt = build_receipt()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {_rel(args.out)} verdict={receipt['verdict']} issues={len(receipt['issues'])}")
    if receipt["verdict"] == "bound" or args.allow_unbound:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
