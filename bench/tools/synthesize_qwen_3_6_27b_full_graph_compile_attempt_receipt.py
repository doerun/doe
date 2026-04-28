#!/usr/bin/env python3
"""Synthesize the Qwen 3.6 27B full-graph compile attempt receipt.

Parallel to ``bench/tools/synthesize_full_graph_compile_attempt_receipt.py``
(the Gemma 4 31B synthesizer). Same shape, same WSE-3 per-PE residency
classifier, same hash-spine guard. Different defaults, different
invocation, plus a ``scopeRestrictions`` block lifted from the smoke
config so receipts cite Qwen-specific named blockers (linear-attention
layers, mrope-interleaved RoPE, causal prefill) instead of silently
working around them.

This synthesizer reads a steps-mode Qwen host-plan, enumerates
compileTargets, and emits a typed-blocker receipt that:
  - lists every compile target by name with its layout + pe_program paths;
  - records actual cslc verdicts when the driver-result exists;
  - falls back to ``not_attempted`` per-target when the bundle has not
    been materialized yet (the expected pre-bundle state on this branch);
  - cites the smoke config's named blockers in claim.notWhat so the
    receipt cannot be misread as a full-coverage Qwen claim.

Receipt does not invent compile verdicts. When ``host-plan.json`` is
absent the synthesizer exits 2 with a typed pointer to the host-plan
tool invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools._receipt_hash_guard import (  # noqa: E402
    ReceiptHashSpineError,
    enforce_receipt_hash_spine,
)
from bench.tools.synthesize_full_graph_compile_attempt_receipt import (  # noqa: E402
    _sha256_file,
    compute_residency_analysis,
    load_driver_targets,
    rel,
)

DEFAULT_SMOKE_CONFIG = (
    REPO_ROOT / "runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json"
)
DEFAULT_BUNDLE_ROOT = (
    REPO_ROOT / "bench/out/r3-2-27b-manifest-fullgraph-compile-steps"
)
DEFAULT_HOSTPLAN = DEFAULT_BUNDLE_ROOT / "host-plan.json"
DEFAULT_DRIVER_RESULT = (
    DEFAULT_BUNDLE_ROOT / "trace.json.driver-result.json"
)
DEFAULT_OUT = (
    REPO_ROOT / "bench/out/r3-2-27b-full-graph-compile-attempt/receipt.json"
)

ACCEPTED_COMPILE_BLOCKERS: dict[str, str] = {}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host-plan", type=Path, default=DEFAULT_HOSTPLAN)
    p.add_argument("--driver-result", type=Path, default=DEFAULT_DRIVER_RESULT)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "--bundle-root",
        type=Path,
        default=DEFAULT_BUNDLE_ROOT,
        help=(
            "Bundle root containing per-target compile/<name>/pe_program.metadata.json. "
            "Used to compute per-PE residency byte math for failed targets."
        ),
    )
    p.add_argument(
        "--smoke-config",
        type=Path,
        default=DEFAULT_SMOKE_CONFIG,
        help=(
            "Qwen smoke config (execution-v1). Its scopeRestrictions block "
            "is lifted into the receipt so named blockers travel with the "
            "claim."
        ),
    )
    p.add_argument(
        "--manifest-size",
        type=int,
        default=4096,
        help=(
            "Sequence-size context to record for the manifest-shaped "
            "compile attempt."
        ),
    )
    return p.parse_args()


def _load_smoke_scope_restrictions(smoke_path: Path) -> dict | None:
    if not smoke_path.is_file():
        return None
    try:
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    scope = smoke.get("scopeRestrictions")
    return scope if isinstance(scope, dict) else None


def _target_base_name(target: dict) -> str | None:
    layout = target.get("layout")
    if not isinstance(layout, str) or "/" not in layout:
        return None
    base = layout.split("/", 1)[0]
    name = str(target.get("name", ""))
    return base if base and base != name else None


def _driver_target_for_host_target(
    target: dict, driver_targets: dict[str, dict] | None
) -> tuple[dict | None, str | None]:
    if driver_targets is None:
        return None, None
    name = str(target.get("name", "unknown"))
    exact = driver_targets.get(name)
    if isinstance(exact, dict):
        return exact, "exact"
    base = _target_base_name(target)
    if base is not None:
        alias = driver_targets.get(base)
        if isinstance(alias, dict) and alias.get("status") == "succeeded":
            return alias, "base_kernel_alias"
    return None, None


def _is_accepted_compile_blocker(target: dict) -> bool:
    name = str(target.get("name", ""))
    expected = ACCEPTED_COMPILE_BLOCKERS.get(name)
    return (
        expected is not None
        and target.get("compileVerdict") == "blocked"
        and target.get("failureCode") == expected
    )


def main() -> int:
    args = parse_args()
    if not args.host_plan.is_file():
        sys.stderr.write(
            f"synthesize_qwen_3_6_27b_full_graph_compile_attempt_receipt: "
            f"host-plan {args.host_plan} not found\n"
            f"Materialize first with:\n"
            f"  runtime/zig/zig-out/bin/doe-csl-host-plan-tool \\\n"
            f"    --input {rel(args.smoke_config)} \\\n"
            f"    --bundle-root {rel(args.bundle_root)} \\\n"
            f"    --mode steps\n"
        )
        return 2
    host_plan = json.loads(args.host_plan.read_text(encoding="utf-8"))
    compile_targets = host_plan.get("compileTargets") or []
    if not compile_targets:
        sys.stderr.write(
            "synthesize_qwen_3_6_27b_full_graph_compile_attempt_receipt: "
            "host-plan has no compileTargets\n"
        )
        return 2
    driver_targets = load_driver_targets(args.driver_result)
    scope_restrictions = _load_smoke_scope_restrictions(args.smoke_config)

    target_records = []
    for target in compile_targets:
        if not isinstance(target, dict):
            continue
        name = str(target.get("name", "unknown"))
        driver_target, verdict_source = _driver_target_for_host_target(
            target, driver_targets
        )
        compile_verdict = "not_attempted"
        failure_code = None
        stderr_path = None
        stdout_path = None
        command = None
        if isinstance(driver_target, dict):
            compile_verdict = str(driver_target.get("status", "unknown"))
            failure_code = driver_target.get("failureCode")
            stderr_path = driver_target.get("stderrPath")
            stdout_path = driver_target.get("stdoutPath")
            command = driver_target.get("command")
        elif driver_targets is not None:
            compile_verdict = "missing_driver_target"
            failure_code = "driver_result_target_missing"
            verdict_source = "missing"
        params_dict = target.get("compileParams") or {}
        residency = None
        if compile_verdict not in ("succeeded", "not_attempted", "blocked"):
            residency = compute_residency_analysis(
                name,
                args.bundle_root,
                {
                    k: int(v)
                    for k, v in params_dict.items()
                    if isinstance(v, (int, str))
                    and str(v).lstrip("-").isdigit()
                },
                stderr_path,
            )
        target_records.append(
            {
                "name": name,
                "layout": target.get("layout", ""),
                "peProgram": target.get("peProgram", ""),
                "compileVerdict": compile_verdict,
                **({"verdictSource": verdict_source} if verdict_source else {}),
                **(
                    {"driverTargetName": driver_target.get("name")}
                    if isinstance(driver_target, dict)
                    and verdict_source == "base_kernel_alias"
                    else {}
                ),
                "compileSize": args.manifest_size,
                "compileParams": params_dict,
                **({"failureCode": failure_code} if failure_code else {}),
                **({"stderrPath": rel(stderr_path)} if stderr_path else {}),
                **({"stdoutPath": rel(stdout_path)} if stdout_path else {}),
                **({"command": command} if isinstance(command, list) else {}),
                **({"residencyAnalysis": residency} if residency else {}),
            }
        )

    attempted = driver_targets is not None
    accepted_blocked_targets = [
        target for target in target_records if _is_accepted_compile_blocker(target)
    ]
    blocked_targets = [
        target for target in target_records if target.get("compileVerdict") == "blocked"
    ]
    failed_targets = [
        target
        for target in target_records
        if target.get("compileVerdict") not in ("succeeded", "not_attempted")
        and not _is_accepted_compile_blocker(target)
    ]
    succeeded_targets = [
        target
        for target in target_records
        if target.get("compileVerdict") == "succeeded"
    ]
    target_count_label = str(len(target_records))

    redesign_summary: dict[str, list[str]] = {}
    for target in failed_targets:
        ra = target.get("residencyAnalysis")
        if not isinstance(ra, dict):
            continue
        cls = ra.get("redesignClass")
        if not isinstance(cls, str):
            continue
        redesign_summary.setdefault(cls, []).append(target["name"])
    source_driver_result = (
        rel(args.driver_result) if args.driver_result.is_file() else None
    )

    host_plan_hash = _sha256_file(args.host_plan)

    qwen_named_blockers_summary = (
        "Qwen 3.6 27B is a hybrid full + linear-attention architecture. "
        "This receipt covers the manifest host-plan inventory, including "
        "the SSM body sequence. Hardware execution and scale remain gated "
        "on R3-2 WSE receipts."
    )
    if attempted and not failed_targets and not accepted_blocked_targets:
        blocker_detail = (
            "steps-mode layout materialization and cslc iteration both ran; "
            "every compile target succeeded."
        )
        claim_not_what = (
            "Not a hardware receipt. Not a manifest-shape inference success. "
            "Not a WSE runtime or throughput claim; those remain gated on "
            "R3-2 hardware receipts."
        )
        claim_summary = (
            f"Qwen 3.6 27B steps-mode host-plan names "
            f"{target_count_label} compile targets at manifest shape; "
            "driver-result cslc verdicts succeeded for every target."
        )
    elif attempted:
        blocker_detail = (
            "steps-mode layout materialization and cslc iteration both ran. "
            "Non-accepted failed targets carry measured failureCode values "
            "in compileTargets[]. Accepted blocked targets are listed in "
            "acceptedCompileBlockers[]."
        )
        claim_not_what = (
            "Not a hardware receipt. Not a manifest-shape inference success. "
            "Accepted compile blockers mean cslc was intentionally skipped "
            "for named manifest-shape targets in this non-hardware gate. A "
            "failed compile target is a typed blocker, not a runtime result."
        )
        claim_summary = (
            f"Qwen 3.6 27B steps-mode host-plan names "
            f"{target_count_label} compile targets at manifest shape; "
            "cslc verdicts are attached when driver-result.json is present, "
            "and accepted blockers are surfaced explicitly."
        )
    else:
        blocker_detail = (
            "steps-mode host-plan materialization is the expected path, but "
            "driver-result.json is absent, so no measured cslc verdicts are "
            "attached to this receipt."
        )
        claim_not_what = (
            "Not a hardware receipt. Not a manifest-shape inference success. "
            "Not a cslc success claim; no driver-result verdicts are attached."
        )
        claim_summary = (
            f"Qwen 3.6 27B steps-mode host-plan names "
            f"{target_count_label} compile targets at manifest shape; "
            "measured cslc verdicts require driver-result.json."
        )

    receipt = {
        "schemaVersion": 1,
        "artifactKind": "doe_full_graph_compile_attempt_receipt",
        "modelId": host_plan.get("modelId")
        or (
            host_plan.get("contract")
            if isinstance(host_plan.get("contract"), str)
            else "qwen-3-6-27b-q4k-ehaf16"
        ),
        "modelFamily": "qwen3",
        "target": host_plan.get("target", "wse3"),
        "manifestSize": args.manifest_size,
        "sourceHostPlan": rel(args.host_plan),
        "hostPlanPath": rel(args.host_plan),
        "hostPlanHash": host_plan_hash,
        "sourceDriverResult": source_driver_result,
        "sourceSmokeConfig": rel(args.smoke_config)
        if args.smoke_config.is_file()
        else None,
        **(
            {"scopeRestrictions": scope_restrictions}
            if scope_restrictions
            else {}
        ),
        "layoutMaterialization": {
            "tool": "runtime/zig/zig-out/bin/doe-csl-host-plan-tool",
            "invocation": (
                f"--input {rel(args.smoke_config)} "
                f"--bundle-root {rel(args.bundle_root)} --mode steps"
            ),
            "status": "succeeded",
        },
        "compileTargetCount": len(target_records),
        "compileAttempted": attempted,
        "compileSucceededCount": len(succeeded_targets),
        "compileBlockedCount": len(blocked_targets),
        "compileAcceptedBlockedCount": len(accepted_blocked_targets),
        "acceptedCompileBlockers": [
            {
                "name": target["name"],
                "failureCode": target.get("failureCode"),
                "reason": (
                    "accepted Qwen manifest-shape non-hardware compile "
                    "blocker; target is still covered by semantic CSL "
                    "emission and reference parity, but cslc invocation is "
                    "intentionally skipped in this gate"
                ),
            }
            for target in accepted_blocked_targets
        ],
        "compileFailedCount": len(failed_targets),
        "compileTargets": target_records,
        **({"redesignSummary": redesign_summary} if redesign_summary else {}),
        "blocker": {
            "class": (
                "manifest_shape_compile_targets_failed"
                if attempted and failed_targets
                else (
                    "accepted_manifest_shape_compile_blockers"
                    if attempted and accepted_blocked_targets
                    else (
                        "none"
                        if attempted
                        else "full_graph_compile_loop_absent"
                    )
                )
            ),
            "detail": (
                blocker_detail
            ),
            "hostPlanToolFailure": {
                "tool": "runtime/zig/zig-out/bin/doe-csl-host-plan-tool",
                "invocation": (
                    f"--input {rel(args.smoke_config)} "
                    f"--bundle-root {rel(args.bundle_root)} --mode steps"
                ),
                "exitClass": "none",
                "site": None,
                "implication": (
                    "Layout materialization is expected to succeed once "
                    "the host-plan tool runs against the Qwen smoke config; "
                    "this receipt lists targets that materialize and the "
                    "cslc verdicts attached when the driver result lands."
                ),
            },
            "namedRunnerExtensions": [
                "(optional) bench/gates/full_graph_compile_attempt_gate.py: "
                "block release until the receipt has measured verdicts for "
                "every target and the accepted failure taxonomy is explicit. "
                "Same gate as Gemma 4 31B; per-model receipts share the "
                "schema.",
            ],
        },
        "claim": {
            "scope": (
                "Qwen 3.6 27B steps-mode full-graph compile target "
                f"inventory is pinned. The receipt records {target_count_label} "
                "named targets and measured compile verdicts when present. "
                f"{qwen_named_blockers_summary}"
            ),
            "notWhat": (
                claim_not_what
            ),
            "summary": claim_summary,
        },
    }

    try:
        enforce_receipt_hash_spine(receipt, repo_root=REPO_ROOT)
    except ReceiptHashSpineError as err:
        sys.stderr.write(
            "synthesize_qwen_3_6_27b_full_graph_compile_attempt_receipt: "
            f"receipt hash spine rejected emit:\n  {err}\n"
        )
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {args.out} ("
        f"compileTargetCount={len(target_records)}, "
        f"compileAttempted={attempted})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
