#!/usr/bin/env python3
"""Canonical release/smoke pipeline runner for benchmark + gates (drop-in optional)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
import output_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="bench/compare_dawn_vs_fawn.config.amd.vulkan.release.json",
        help="compare_dawn_vs_fawn.py config path for this pipeline run.",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Override report path. Defaults to run.out from --config.",
    )
    parser.add_argument(
        "--workspace",
        default="",
        help="Override workspace path. Defaults to run.workspace from --config.",
    )
    parser.add_argument(
        "--strict-amd-vulkan",
        action="store_true",
        help="Run strict AMD Vulkan host preflight before benchmark execution.",
    )
    parser.add_argument(
        "--verify-smoke-report",
        default="",
        help="Optional smoke report path to validate with verify_smoke_gpu_usage.py.",
    )
    parser.add_argument(
        "--verify-smoke-require-comparable",
        action="store_true",
        help="Pass --require-comparable to verify_smoke_gpu_usage.py.",
    )
    parser.add_argument(
        "--with-claim-gate",
        action="store_true",
        help="Run claim gate in addition to schema/correctness/trace gates.",
    )
    parser.add_argument(
        "--with-comparability-parity-gate",
        action="store_true",
        help=(
            "Run comparability_obligation_parity_gate.py in run_blocking_gates.py "
            "before correctness/trace."
        ),
    )
    parser.add_argument(
        "--trace-semantic-parity-mode",
        choices=["off", "auto", "required"],
        default="auto",
        help="Semantic parity mode forwarded to trace gate execution.",
    )
    parser.add_argument(
        "--with-dropin-gate",
        action="store_true",
        help="Run drop-in compatibility gate in addition to schema/correctness/trace gates.",
    )
    parser.add_argument(
        "--dropin-artifact",
        default="zig/zig-out/lib/libdoe_webgpu.so",
        help="Shared library artifact path for drop-in gate when --with-dropin-gate is set.",
    )
    parser.add_argument(
        "--dropin-symbols",
        default="config/dropin_abi.symbols.txt",
        help="Required symbol list for drop-in gate.",
    )
    parser.add_argument(
        "--dropin-report",
        default="bench/out/dropin_report.json",
        help="Drop-in consolidated report path.",
    )
    parser.add_argument(
        "--dropin-symbol-report",
        default="bench/out/dropin_symbol_report.json",
        help="Drop-in symbol report path.",
    )
    parser.add_argument(
        "--dropin-behavior-report",
        default="bench/out/dropin_behavior_report.json",
        help="Drop-in behavior report path.",
    )
    parser.add_argument(
        "--dropin-benchmark-report",
        default="bench/out/dropin_benchmark_report.json",
        help="Drop-in benchmark report path.",
    )
    parser.add_argument(
        "--dropin-benchmark-html",
        default="bench/out/dropin_benchmark_report.html",
        help="Drop-in benchmark HTML path.",
    )
    parser.add_argument(
        "--dropin-micro-iterations",
        type=int,
        default=30,
        help="Micro benchmark iterations for drop-in gate.",
    )
    parser.add_argument(
        "--dropin-e2e-iterations",
        type=int,
        default=10,
        help="End-to-end benchmark iterations for drop-in gate.",
    )
    parser.add_argument(
        "--dropin-skip-benchmarks",
        action="store_true",
        help="Skip drop-in benchmark execution while still running symbol + behavior checks.",
    )
    parser.add_argument(
        "--compare-html-output",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Generate Dawn-vs-Fawn visualization HTML from the compare report. "
            "Enabled by default."
        ),
    )
    parser.add_argument(
        "--compare-html-out",
        default="",
        help="Optional HTML output path override (default: report path with .html suffix).",
    )
    parser.add_argument(
        "--compare-analysis-out",
        default="",
        help=(
            "Optional distribution-analysis JSON path for visualize_dawn_vs_fawn.py "
            "(default: disabled)."
        ),
    )
    parser.add_argument(
        "--claim-require-comparison-status",
        default="comparable",
        help="Required comparisonStatus for claim gate.",
    )
    parser.add_argument(
        "--claim-require-claim-status",
        default="claimable",
        help="Required claimStatus for claim gate.",
    )
    parser.add_argument(
        "--claim-require-claimability-mode",
        default="release",
        help="Required claimability mode for claim gate.",
    )
    parser.add_argument(
        "--claim-require-min-timed-samples",
        type=int,
        default=15,
        help="Minimum timed sample floor for claim gate.",
    )
    parser.add_argument(
        "--with-claim-rehearsal-artifacts",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Generate claim rehearsal artifacts (claim gate result, tail health, "
            "timing invariant audit, contract hash manifest) after gates. "
            "Enabled by default."
        ),
    )
    parser.add_argument(
        "--claim-rehearsal-prefix",
        default="",
        help=(
            "Optional output prefix for claim rehearsal artifacts. "
            "Defaults to <report-without-suffix>.claim-rehearsal."
        ),
    )
    parser.add_argument(
        "--with-cycle-gate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Run cycle_gate.py for claim-lane cycle-lock/rollback enforcement after "
            "blocking gates (default: enabled)."
        ),
    )
    parser.add_argument(
        "--cycle-contract",
        default="config/claim-cycle.active.json",
        help="Cycle contract path passed to cycle_gate.py.",
    )
    parser.add_argument(
        "--cycle-gate-out",
        default="bench/out/cycle_gate_report.json",
        help="Cycle-gate report output path.",
    )
    parser.add_argument(
        "--cycle-artifact-class",
        choices=["claim", "diagnostic"],
        default="claim",
        help="Artifact class passed to cycle_gate.py namespace policy checks.",
    )
    parser.add_argument(
        "--cycle-comparability-obligations",
        default="config/comparability-obligations.json",
        help="Comparability-obligation contract path passed to cycle_gate.py.",
    )
    parser.add_argument(
        "--cycle-substantiation-report",
        default="",
        help="Optional substantiation gate report path passed to cycle_gate.py.",
    )
    parser.add_argument(
        "--cycle-enforce-rollbacks",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enforce enabled rollback criteria in cycle_gate.py (default: enabled).",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip host preflight step.",
    )
    parser.add_argument(
        "--skip-compare",
        action="store_true",
        help="Skip compare_dawn_vs_fawn.py execution.",
    )
    parser.add_argument(
        "--skip-gates",
        action="store_true",
        help="Skip run_blocking_gates.py execution.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them.",
    )
    parser.add_argument(
        "--timestamp",
        default="",
        help=(
            "UTC suffix for artifact paths (YYYYMMDDTHHMMSSZ). "
            "Defaults to current UTC time when --timestamp-output is enabled."
        ),
    )
    parser.add_argument(
        "--timestamp-output",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Stamp compare/drop-in artifact paths with a UTC timestamp suffix.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def resolve_report_path(config_path: Path, explicit_report: str) -> Path:
    if explicit_report:
        return Path(explicit_report)

    config_payload = load_json(config_path)
    run_payload = config_payload.get("run")
    if not isinstance(run_payload, dict):
        raise ValueError(f"invalid config {config_path}: missing object field run")
    out_value = run_payload.get("out")
    if not isinstance(out_value, str) or not out_value.strip():
        raise ValueError(f"invalid config {config_path}: missing non-empty run.out")
    return Path(out_value)


def resolve_workspace_path(config_path: Path, explicit_workspace: str) -> Path:
    if explicit_workspace:
        return Path(explicit_workspace)

    config_payload = load_json(config_path)
    run_payload = config_payload.get("run")
    if not isinstance(run_payload, dict):
        raise ValueError(f"invalid config {config_path}: missing object field run")
    workspace_value = run_payload.get("workspace")
    if not isinstance(workspace_value, str) or not workspace_value.strip():
        raise ValueError(f"invalid config {config_path}: missing non-empty run.workspace")
    return Path(workspace_value)


def resolve_workloads_contract_path(config_path: Path) -> Path:
    config_payload = load_json(config_path)
    workloads_value = config_payload.get("workloads")
    if not isinstance(workloads_value, str) or not workloads_value.strip():
        raise ValueError(f"invalid config {config_path}: missing non-empty workloads path")
    candidate = Path(workloads_value)
    if candidate.is_absolute():
        return candidate
    repo_root = Path(__file__).resolve().parent.parent
    repo_relative = (repo_root / candidate).resolve()
    if repo_relative.exists():
        return repo_relative
    config_relative = (config_path.parent / candidate).resolve()
    if config_relative.exists():
        return config_relative
    return repo_relative


def run_step(label: str, command: list[str], *, dry_run: bool) -> None:
    print(f"[pipeline] {label}: {' '.join(command)}", flush=True)
    if dry_run:
        return
    subprocess.run(command, check=True)


def main() -> int:
    args = parse_args()

    if args.claim_require_min_timed_samples < 0:
        print(
            "FAIL: invalid --claim-require-min-timed-samples="
            f"{args.claim_require_min_timed_samples} expected >= 0"
        )
        return 1
    if args.dropin_micro_iterations < 0:
        print(
            "FAIL: invalid --dropin-micro-iterations="
            f"{args.dropin_micro_iterations} expected >= 0"
        )
        return 1
    if args.dropin_e2e_iterations < 0:
        print(
            "FAIL: invalid --dropin-e2e-iterations="
            f"{args.dropin_e2e_iterations} expected >= 0"
        )
        return 1

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"FAIL: missing config: {config_path}")
        return 1
    if args.with_dropin_gate and not args.dropin_artifact.strip():
        print("FAIL: --with-dropin-gate requires --dropin-artifact")
        return 1
    if args.with_dropin_gate and not args.dry_run:
        artifact_path = Path(args.dropin_artifact)
        if not artifact_path.exists():
            print(f"FAIL: missing --dropin-artifact: {artifact_path}")
            return 1
    cycle_contract_path = Path(args.cycle_contract)
    cycle_obligations_path = Path(args.cycle_comparability_obligations)
    if (
        args.with_cycle_gate
        and args.with_claim_gate
        and not args.skip_gates
        and not args.dry_run
        and not cycle_contract_path.exists()
    ):
        print(
            "FAIL: --with-cycle-gate requires --cycle-contract to exist in claim lanes: "
            f"{cycle_contract_path}"
        )
        return 1
    if (
        args.with_cycle_gate
        and args.with_claim_gate
        and not args.skip_gates
        and not args.dry_run
        and not cycle_obligations_path.exists()
    ):
        print(
            "FAIL: --with-cycle-gate requires --cycle-comparability-obligations to exist in claim lanes: "
            f"{cycle_obligations_path}"
        )
        return 1
    if (
        args.with_cycle_gate
        and args.with_claim_gate
        and not args.skip_gates
        and not args.dry_run
        and args.cycle_substantiation_report.strip()
        and not Path(args.cycle_substantiation_report.strip()).exists()
    ):
        print(
            "FAIL: --cycle-substantiation-report path does not exist: "
            f"{args.cycle_substantiation_report.strip()}"
        )
        return 1

    raw_report_path = resolve_report_path(config_path, args.report)
    raw_workspace_path = resolve_workspace_path(config_path, args.workspace)
    workloads_contract_path = resolve_workloads_contract_path(config_path)
    if args.with_claim_gate and not args.dry_run and not workloads_contract_path.exists():
        print(
            "FAIL: --with-claim-gate requires workload contract from config to exist: "
            f"{workloads_contract_path}"
        )
        return 1
    output_timestamp = (
        output_paths.resolve_timestamp(args.timestamp)
        if args.timestamp_output
        else ""
    )
    report_path = output_paths.with_timestamp(
        raw_report_path,
        output_timestamp,
        enabled=args.timestamp_output,
    )
    workspace_path = output_paths.with_timestamp(
        raw_workspace_path,
        output_timestamp,
        enabled=args.timestamp_output,
    )
    cycle_gate_report_path = output_paths.with_timestamp(
        Path(args.cycle_gate_out),
        output_timestamp,
        enabled=args.timestamp_output,
    )
    if args.compare_html_out.strip():
        compare_html_path = output_paths.with_timestamp(
            Path(args.compare_html_out.strip()),
            output_timestamp,
            enabled=args.timestamp_output,
        )
    else:
        compare_html_path = report_path.with_suffix(".html")
    compare_analysis_path: Path | None = None
    if args.compare_analysis_out.strip():
        compare_analysis_path = output_paths.with_timestamp(
            Path(args.compare_analysis_out.strip()),
            output_timestamp,
            enabled=args.timestamp_output,
        )

    bench_dir = Path(__file__).resolve().parent
    python_exe = sys.executable
    preflight = bench_dir / "preflight_bench_host.py"
    compare = bench_dir / "compare_dawn_vs_fawn.py"
    visualize = bench_dir / "visualize_dawn_vs_fawn.py"
    smoke_verify = bench_dir / "verify_smoke_gpu_usage.py"
    gates = bench_dir / "run_blocking_gates.py"
    claim_rehearsal = bench_dir / "build_claim_rehearsal_artifacts.py"
    cycle_gate = bench_dir / "cycle_gate.py"
    preflight_ran = False
    compare_ran = False
    compare_html_ran = False
    smoke_verify_ran = False
    gates_ran = False
    claim_rehearsal_ran = False
    cycle_gate_ran = False
    claim_rehearsal_manifest_path: Path | None = None
    current_step = ""

    try:
        if args.strict_amd_vulkan and not args.skip_preflight:
            preflight_ran = True
            current_step = "preflight"
            run_step(
                "preflight",
                [python_exe, str(preflight), "--strict-amd-vulkan"],
                dry_run=args.dry_run,
            )

        if not args.skip_compare:
            compare_ran = True
            current_step = "compare"
            compare_command = [
                python_exe,
                str(compare),
                "--config",
                str(config_path),
                "--out",
                str(report_path),
                "--workspace",
                str(workspace_path),
            ]
            if args.timestamp_output:
                compare_command.extend(["--timestamp", output_timestamp])
            else:
                compare_command.append("--no-timestamp-output")
            run_step("compare", compare_command, dry_run=args.dry_run)
        if args.compare_html_output:
            compare_html_ran = True
            current_step = "visualize"
            visualize_cmd = [
                python_exe,
                str(visualize),
                "--report",
                str(report_path),
                "--out",
                str(compare_html_path),
            ]
            if compare_analysis_path is not None:
                visualize_cmd.extend(["--analysis-out", str(compare_analysis_path)])
            run_step("visualize", visualize_cmd, dry_run=args.dry_run)

        if args.verify_smoke_report:
            smoke_verify_ran = True
            current_step = "verify-smoke"
            smoke_report_path = Path(args.verify_smoke_report)
            if args.timestamp_output and smoke_report_path == raw_report_path:
                smoke_report_path = report_path
            verify_cmd = [
                python_exe,
                str(smoke_verify),
                "--report",
                str(smoke_report_path),
            ]
            if args.verify_smoke_require_comparable:
                verify_cmd.append("--require-comparable")
            run_step("verify-smoke", verify_cmd, dry_run=args.dry_run)

        if not args.skip_gates:
            gates_ran = True
            current_step = "gates"
            gates_cmd = [python_exe, str(gates), "--report", str(report_path)]
            gates_cmd.extend(["--trace-semantic-parity-mode", args.trace_semantic_parity_mode])
            if args.with_comparability_parity_gate:
                gates_cmd.append("--with-comparability-parity-gate")
            if args.timestamp_output:
                gates_cmd.extend(["--timestamp", output_timestamp])
            else:
                gates_cmd.append("--no-timestamp-output")
            if args.with_dropin_gate:
                gates_cmd.extend(
                    [
                        "--with-dropin-gate",
                        "--dropin-artifact",
                        args.dropin_artifact,
                        "--dropin-symbols",
                        args.dropin_symbols,
                        "--dropin-report",
                        args.dropin_report,
                        "--dropin-symbol-report",
                        args.dropin_symbol_report,
                        "--dropin-behavior-report",
                        args.dropin_behavior_report,
                        "--dropin-benchmark-report",
                        args.dropin_benchmark_report,
                        "--dropin-benchmark-html",
                        args.dropin_benchmark_html,
                        "--dropin-micro-iterations",
                        str(args.dropin_micro_iterations),
                        "--dropin-e2e-iterations",
                        str(args.dropin_e2e_iterations),
                    ]
                )
                if args.dropin_skip_benchmarks:
                    gates_cmd.append("--dropin-skip-benchmarks")
            if args.with_claim_gate:
                gates_cmd.extend(
                    [
                        "--with-claim-gate",
                        "--claim-require-comparison-status",
                        args.claim_require_comparison_status,
                        "--claim-require-claim-status",
                        args.claim_require_claim_status,
                        "--claim-require-claimability-mode",
                        args.claim_require_claimability_mode,
                        "--claim-require-min-timed-samples",
                        str(args.claim_require_min_timed_samples),
                        "--claim-expected-workload-contract",
                        str(workloads_contract_path),
                        "--claim-require-workload-contract-hash",
                        "--claim-require-workload-id-set-match",
                    ]
                )
            run_step("gates", gates_cmd, dry_run=args.dry_run)

        if args.with_claim_rehearsal_artifacts and args.with_claim_gate and gates_ran:
            claim_rehearsal_ran = True
            current_step = "claim-rehearsal-artifacts"
            rehearsal_cmd = [
                python_exe,
                str(claim_rehearsal),
                "--report",
                str(report_path),
                "--require-comparison-status",
                args.claim_require_comparison_status,
                "--require-claim-status",
                args.claim_require_claim_status,
                "--require-claimability-mode",
                args.claim_require_claimability_mode,
                "--require-min-timed-samples",
                str(args.claim_require_min_timed_samples),
                "--expected-workload-contract",
                str(workloads_contract_path),
            ]
            if args.claim_rehearsal_prefix.strip():
                claim_rehearsal_prefix = output_paths.with_timestamp(
                    Path(args.claim_rehearsal_prefix.strip()),
                    output_timestamp,
                    enabled=args.timestamp_output,
                )
                rehearsal_cmd.extend(["--out-prefix", str(claim_rehearsal_prefix)])
                claim_rehearsal_manifest_path = Path(
                    f"{claim_rehearsal_prefix}.manifest.json"
                )
            else:
                claim_rehearsal_manifest_path = Path(
                    f"{report_path.with_suffix('')}.claim-rehearsal.manifest.json"
                )
            rehearsal_cmd.append(
                "--require-workload-contract-hash"
            )
            rehearsal_cmd.append(
                "--require-workload-id-set-match"
            )
            run_step(
                "claim-rehearsal-artifacts",
                rehearsal_cmd,
                dry_run=args.dry_run,
            )

        if args.with_cycle_gate and args.with_claim_gate and gates_ran:
            cycle_gate_ran = True
            current_step = "cycle-gate"
            cycle_cmd = [
                python_exe,
                str(cycle_gate),
                "--cycle",
                args.cycle_contract,
                "--report",
                str(report_path),
                "--artifact-class",
                args.cycle_artifact_class,
                "--comparability-obligations",
                args.cycle_comparability_obligations,
                "--out",
                args.cycle_gate_out,
            ]
            if args.cycle_substantiation_report.strip():
                cycle_cmd.extend(
                    [
                        "--substantiation-report",
                        args.cycle_substantiation_report.strip(),
                    ]
                )
            if args.timestamp_output:
                cycle_cmd.extend(["--timestamp", output_timestamp])
            else:
                cycle_cmd.append("--no-timestamp-output")
            if not args.cycle_enforce_rollbacks:
                cycle_cmd.append("--no-enforce-rollbacks")
            run_step("cycle-gate", cycle_cmd, dry_run=args.dry_run)
    except subprocess.CalledProcessError as exc:
        print(f"FAIL: pipeline step failed with return code {exc.returncode}")
        if not args.dry_run:
            manifest_payload: dict[str, Any] = {
                "runType": "release_pipeline",
                "config": str(config_path),
                "fullRun": (
                    (not args.skip_compare)
                    and (not args.skip_gates)
                    and ((not args.strict_amd_vulkan) or (not args.skip_preflight))
                ),
                "claimGateRan": bool(args.with_claim_gate and gates_ran),
                "dropinGateRan": bool(args.with_dropin_gate and gates_ran),
                "compareHtmlRan": bool(compare_html_ran),
                "preflightRan": preflight_ran,
                "compareRan": compare_ran,
                "gatesRan": gates_ran,
                "smokeVerifyRan": smoke_verify_ran,
                "claimRehearsalRan": claim_rehearsal_ran,
                "cycleGateRan": cycle_gate_ran,
                "reportPath": str(report_path),
                "workspacePath": str(workspace_path),
                "compareHtmlPath": str(compare_html_path) if args.compare_html_output else "",
                "compareAnalysisPath": (
                    str(compare_analysis_path) if compare_analysis_path is not None else ""
                ),
                "cycleGateReportPath": (
                    str(cycle_gate_report_path) if cycle_gate_ran else ""
                ),
                "claimRehearsalManifestPath": (
                    str(claim_rehearsal_manifest_path)
                    if claim_rehearsal_manifest_path is not None
                    else ""
                ),
                "status": "failed",
                "failedStep": current_step or "unknown",
            }
            manifest_outputs: list[str | Path] = [
                report_path,
                workspace_path,
                compare_html_path,
            ]
            if claim_rehearsal_manifest_path is not None:
                manifest_outputs.append(claim_rehearsal_manifest_path)
            if cycle_gate_ran:
                manifest_outputs.append(cycle_gate_report_path)
            output_paths.write_run_manifest_for_outputs(
                manifest_outputs,
                manifest_payload,
            )
        return exc.returncode

    if not args.dry_run:
        manifest_payload = {
            "runType": "release_pipeline",
            "config": str(config_path),
            "fullRun": (
                (not args.skip_compare)
                and (not args.skip_gates)
                and ((not args.strict_amd_vulkan) or (not args.skip_preflight))
            ),
            "claimGateRan": bool(args.with_claim_gate and gates_ran),
            "dropinGateRan": bool(args.with_dropin_gate and gates_ran),
            "compareHtmlRan": bool(compare_html_ran),
            "preflightRan": preflight_ran,
            "compareRan": compare_ran,
            "gatesRan": gates_ran,
            "smokeVerifyRan": smoke_verify_ran,
            "claimRehearsalRan": claim_rehearsal_ran,
            "cycleGateRan": cycle_gate_ran,
            "reportPath": str(report_path),
            "workspacePath": str(workspace_path),
            "compareHtmlPath": str(compare_html_path) if args.compare_html_output else "",
            "compareAnalysisPath": (
                str(compare_analysis_path) if compare_analysis_path is not None else ""
            ),
            "cycleGateReportPath": str(cycle_gate_report_path) if cycle_gate_ran else "",
            "claimRehearsalManifestPath": (
                str(claim_rehearsal_manifest_path)
                if claim_rehearsal_manifest_path is not None
                else ""
            ),
            "status": "passed",
            "failedStep": "",
        }
        manifest_outputs: list[str | Path] = [report_path, workspace_path, compare_html_path]
        if claim_rehearsal_manifest_path is not None:
            manifest_outputs.append(claim_rehearsal_manifest_path)
        if cycle_gate_ran:
            manifest_outputs.append(cycle_gate_report_path)
        output_paths.write_run_manifest_for_outputs(
            manifest_outputs,
            manifest_payload,
        )

    print("PASS: release pipeline completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
