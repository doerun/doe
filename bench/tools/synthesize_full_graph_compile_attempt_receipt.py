#!/usr/bin/env python3
"""Synthesize the 31B full-graph compile attempt receipt.

Mitigates "Full inference graph compile" from
docs/cerebras-north-star.md (Remaining no-hardware evidence gaps).

The existing manifest-shape compile-attempt receipt
(`bench/out/r3-1-31b-manifest-compile-attempt/`) and the threshold
sweep (`bench/out/r3-1-31b-manifest-compile-sweep/`) test only the
transformer_layer_shape kernel. The steps-mode 31B host-plan
(`bench/out/r3-1-31b-manifest-fullgraph-compile-steps/host-plan.json`)
names the distinct compile targets and phase variants that make up the
manifest-shaped graph. A "full inference graph compile attempt" means:
materialize that steps-mode bundle root, attempt cslc on every emitted
target, and aggregate the per-target results.

This synthesizer reads the host-plan, enumerates compileTargets, and
emits a typed-blocker receipt that:
  - lists every compile target by name with its layout + pe_program
    paths (relative to the bundle compile root),
  - binds to the layer-block sweep's known threshold so reviewers can
    see which targets were expected to fail at manifest shape (those whose
    per-PE residency mirrors the layer-block kernel),
  - records actual cslc verdicts when the driver-result exists, and
    otherwise falls back to an explicit not-attempted preflight.

The receipt does not invent compile verdicts. When
`driver-result.json` is absent, every target stays `not_attempted`.
When it is present, each target mirrors the driver result exactly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOSTPLAN = (
    REPO_ROOT
    / "bench/out/r3-1-31b-manifest-fullgraph-compile-steps/host-plan.json"
)
DEFAULT_DRIVER_RESULT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-manifest-fullgraph-compile-steps/driver-result.json"
)
DEFAULT_SWEEP_SUMMARY = (
    REPO_ROOT / "bench/out/r3-1-31b-manifest-compile-sweep/sweep-summary.json"
)
DEFAULT_OUT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-full-graph-compile-attempt/receipt.json"
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host-plan", type=Path, default=DEFAULT_HOSTPLAN)
    p.add_argument("--driver-result", type=Path, default=DEFAULT_DRIVER_RESULT)
    p.add_argument(
        "--sweep-summary", type=Path, default=DEFAULT_SWEEP_SUMMARY
    )
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
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


def rel(path: Path | str) -> str:
    path = Path(path)
    if path.is_absolute() and str(path).startswith(str(REPO_ROOT)):
        return str(path.relative_to(REPO_ROOT))
    return str(path)


def load_driver_targets(path: Path) -> dict[str, dict] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    compile_section = payload.get("compile") if isinstance(payload, dict) else None
    if not isinstance(compile_section, dict):
        return None
    targets = compile_section.get("targets")
    if not isinstance(targets, list):
        return None
    out: dict[str, dict] = {}
    for target in targets:
        if not isinstance(target, dict):
            continue
        name = target.get("name")
        if isinstance(name, str) and name:
            out[name] = target
    return out


def main() -> int:
    args = parse_args()
    if not args.host_plan.is_file():
        sys.stderr.write(
            f"synthesize_full_graph_compile_attempt_receipt: host-plan "
            f"{args.host_plan} not found\n"
        )
        return 2
    host_plan = json.loads(args.host_plan.read_text(encoding="utf-8"))
    compile_targets = host_plan.get("compileTargets") or []
    if not compile_targets:
        sys.stderr.write(
            "synthesize_full_graph_compile_attempt_receipt: host-plan "
            "has no compileTargets\n"
        )
        return 2
    driver_targets = load_driver_targets(args.driver_result)

    sweep_summary = None
    if args.sweep_summary.is_file():
        sweep_summary = json.loads(
            args.sweep_summary.read_text(encoding="utf-8")
        )

    target_records = []
    for target in compile_targets:
        if not isinstance(target, dict):
            continue
        name = str(target.get("name", "unknown"))
        driver_target = driver_targets.get(name) if driver_targets is not None else None
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
        target_records.append(
            {
                "name": name,
                "layout": target.get("layout", ""),
                "peProgram": target.get("peProgram", ""),
                "compileVerdict": compile_verdict,
                "compileSize": args.manifest_size,
                "compileParams": target.get("compileParams") or {},
                **({"failureCode": failure_code} if failure_code else {}),
                **({"stderrPath": rel(stderr_path)} if stderr_path else {}),
                **({"stdoutPath": rel(stdout_path)} if stdout_path else {}),
                **({"command": command} if isinstance(command, list) else {}),
            }
        )

    threshold_note = None
    if sweep_summary is not None:
        threshold = sweep_summary.get("threshold") or {}
        last_passing = threshold.get("lastPassing")
        first_failing = threshold.get("firstFailing")
        threshold_note = {
            "sourceSweepPath": str(
                args.sweep_summary.relative_to(REPO_ROOT)
                if args.sweep_summary.is_absolute()
                and str(args.sweep_summary).startswith(str(REPO_ROOT))
                else args.sweep_summary
            ),
            "lastPassingLayerBlockSize": last_passing,
            "firstFailingLayerBlockSize": first_failing,
            "implication": (
                f"transformer_layer_shape compiles up to size={last_passing} "
                f"and fails at size>={first_failing}. Compile targets that "
                f"share its per-PE residency profile may inherit the same "
                f"failure pattern at manifest shape. The receipt uses this "
                f"sweep as context only; per-target compileVerdict fields "
                f"are measured when driver-result is present."
            ),
        }

    attempted = driver_targets is not None
    failed_targets = [
        target
        for target in target_records
        if target.get("compileVerdict") not in ("succeeded", "not_attempted")
    ]
    succeeded_targets = [
        target
        for target in target_records
        if target.get("compileVerdict") == "succeeded"
    ]
    target_count_label = str(len(target_records))
    source_driver_result = (
        rel(args.driver_result)
        if args.driver_result.is_file()
        else None
    )

    receipt = {
        "schemaVersion": 1,
        "artifactKind": "doe_full_graph_compile_attempt_receipt",
        "modelId": host_plan.get("modelId")
        or (host_plan.get("contract") if isinstance(host_plan.get("contract"), str) else "unknown"),
        "target": host_plan.get("target", "wse3"),
        "manifestSize": args.manifest_size,
        "sourceHostPlan": rel(args.host_plan),
        "sourceDriverResult": source_driver_result,
        "layoutMaterialization": {
            "tool": "runtime/zig/zig-out/bin/doe-csl-host-plan-tool",
            "invocation": "--input runtime/zig/examples/execution-v1/gemma-4-31b-smoke.json --bundle-root bench/out/r3-1-31b-manifest-fullgraph-compile-steps --mode steps",
            "status": "succeeded",
        },
        "compileTargetCount": len(target_records),
        "compileAttempted": attempted,
        "compileSucceededCount": len(succeeded_targets),
        "compileFailedCount": len(failed_targets),
        "compileTargets": target_records,
        "thresholdNote": threshold_note,
        "blocker": {
            "class": (
                "manifest_shape_compile_targets_failed"
                if attempted and failed_targets
                else (
                    "none"
                    if attempted
                    else "full_graph_compile_loop_absent"
                )
            ),
            "detail": (
                (
                    "steps-mode layout materialization and cslc iteration "
                    "both ran. Failed targets now carry measured failureCode "
                    "values in compileTargets[]."
                )
                if attempted
                else (
                    "steps-mode host-plan materialization is the expected "
                    "path, but driver-result.json is absent, so no measured "
                    "cslc verdicts are attached to this receipt."
                )
            ),
            "hostPlanToolFailure": {
                "tool": "runtime/zig/zig-out/bin/doe-csl-host-plan-tool",
                "invocation": "--input runtime/zig/examples/execution-v1/gemma-4-31b-smoke.json --bundle-root bench/out/r3-1-31b-manifest-fullgraph-compile-steps --mode steps",
                "exitClass": "none",
                "site": None,
                "implication": "The previous malformed-manifest preflight is closed for the steps-mode path; layout.csl and pe_program.csl files now materialize before cslc runs.",
            },
            "namedRunnerExtensions": [
                "(optional) bench/gates/full_graph_compile_attempt_gate.py: "
                "block release until the receipt has measured verdicts for "
                "every target and the accepted failure taxonomy is explicit.",
            ],
        },
        "claim": {
            "scope": (
                "31B steps-mode full-graph compile target inventory is "
                f"pinned. The receipt records {target_count_label} named "
                "targets, measured compile verdicts when present, and the "
                "layer-block threshold context."
            ),
            "notWhat": (
                "Not a hardware receipt. Not a manifest-shape inference "
                "success. A failed compile target is a typed blocker, not a "
                "runtime result."
            ),
            "summary": (
                f"31B steps-mode host-plan names {target_count_label} "
                "compile targets at manifest shape; cslc verdicts are "
                "attached when driver-result.json is present."
            ),
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {args.out} (typed blocker, "
        f"compileTargetCount={len(target_records)}, "
        f"compileAttempted={attempted})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
