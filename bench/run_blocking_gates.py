#!/usr/bin/env python3
"""Canonical entrypoint for schema/correctness/trace/drop-in/claim gates with optional parity verification."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
import output_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        default="bench/out/dawn-vs-doe.json",
        help="Comparison report produced by compare_dawn_vs_doe.py",
    )
    parser.add_argument(
        "--timestamp",
        default="",
        help=(
            "UTC suffix for drop-in gate outputs (YYYYMMDDTHHMMSSZ). "
            "Defaults to current UTC time when --timestamp-output is enabled."
        ),
    )
    parser.add_argument(
        "--timestamp-output",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Stamp drop-in gate report paths with a UTC timestamp suffix.",
    )
    parser.add_argument(
        "--gates",
        default="config/gates.json",
        help="Gate policy config path passed to check_correctness.py",
    )
    parser.add_argument(
        "--quirk",
        default="examples/quirks/intel_gen12_temp_buffer.json",
        help="Reference quirk path passed to check_correctness.py",
    )
    parser.add_argument(
        "--with-comparability-parity-gate",
        action="store_true",
        help=(
            "Run comparability_obligation_parity_gate.py as a verification-lane gate "
            "before correctness/trace."
        ),
    )
    parser.add_argument(
        "--with-claim-gate",
        action="store_true",
        help="Run claim_gate.py after schema/correctness/trace gates.",
    )
    parser.add_argument(
        "--with-backend-selection-gate",
        action="store_true",
        help="Run backend_selection_gate.py after trace gate.",
    )
    parser.add_argument(
        "--backend-runtime-policy",
        default="config/backend-runtime-policy.json",
        help="Backend runtime policy path passed to backend_selection_gate.py.",
    )
    parser.add_argument(
        "--backend-selection-lane",
        default="",
        help="Optional lane override passed to backend_selection_gate.py.",
    )
    parser.add_argument(
        "--with-shader-artifact-gate",
        action="store_true",
        help="Run shader_artifact_gate.py after trace gate.",
    )
    parser.add_argument(
        "--shader-artifact-schema",
        default="config/shader-artifact.schema.json",
        help="Shader artifact schema path passed to shader_artifact_gate.py.",
    )
    parser.add_argument(
        "--shader-artifact-require-manifest",
        action="store_true",
        help="Pass --require-manifest to shader_artifact_gate.py.",
    )
    parser.add_argument(
        "--shader-artifact-spirv-val",
        default="",
        help="Optional spirv-val executable passed to shader_artifact_gate.py.",
    )
    parser.add_argument(
        "--shader-artifact-require-spirv-validation",
        action="store_true",
        help="Fail shader artifact gate when SPIR-V artifacts are present but not validated.",
    )
    parser.add_argument(
        "--with-metal-sync-conformance-gate",
        action="store_true",
        help="Run metal_sync_conformance.py after trace gate.",
    )
    parser.add_argument(
        "--backend-timing-policy",
        default="config/backend-timing-policy.json",
        help="Backend timing policy path passed to sync/timing gates.",
    )
    parser.add_argument(
        "--with-metal-timing-policy-gate",
        action="store_true",
        help="Run metal_timing_policy_gate.py after trace gate.",
    )
    parser.add_argument(
        "--with-vulkan-sync-conformance-gate",
        action="store_true",
        help="Run vulkan_sync_conformance.py after trace gate.",
    )
    parser.add_argument(
        "--with-vulkan-timing-policy-gate",
        action="store_true",
        help="Run vulkan_timing_policy_gate.py after trace gate.",
    )
    parser.add_argument(
        "--with-comparable-runtime-invariants-gate",
        action="store_true",
        help="Run comparable_runtime_invariants_gate.py after trace gate.",
    )
    parser.add_argument(
        "--with-modules",
        action="store_true",
        help="Run promoted module blocking gates after trace gate.",
    )
    parser.add_argument(
        "--with-browser-gate",
        action="store_true",
        help="Run promoted browser gate after trace gate.",
    )
    parser.add_argument(
        "--with-browser-claim-gate",
        action="store_true",
        help="Run the repeated-window browser claim gate after trace gate.",
    )
    parser.add_argument(
        "--with-structural-equivalence-gate",
        action="store_true",
        help="Run structural_equivalence_gate.py after trace gate.",
    )
    parser.add_argument(
        "--with-file-size-gate",
        action="store_true",
        help="Run file_size_gate.py to enforce line-count limits on source files.",
    )
    parser.add_argument(
        "--with-split-coverage-gate",
        action="store_true",
        help="Run split_coverage_gate.py to validate core/full coverage ledgers.",
    )
    parser.add_argument(
        "--split-coverage-surface",
        choices=["core", "full", "both"],
        default="both",
        help="Which surface(s) to validate in the split coverage gate.",
    )
    parser.add_argument(
        "--with-dropin-proc-resolution-gate",
        action="store_true",
        help="Run dropin_proc_resolution_tests.py in the drop-in phase.",
    )
    parser.add_argument(
        "--dropin-symbol-ownership",
        default="config/dropin-symbol-ownership.json",
        help="Drop-in symbol ownership contract for proc-resolution checks.",
    )
    parser.add_argument(
        "--require-claim-gate",
        action="store_true",
        help=(
            "Fail unless --with-claim-gate is set. "
            "Use this when the run is intended as release-claim readiness evidence."
        ),
    )
    parser.add_argument(
        "--trace-semantic-parity-mode",
        choices=["off", "auto", "required"],
        default="auto",
        help="Semantic parity mode passed to trace_gate.py.",
    )
    parser.add_argument(
        "--with-dropin-gate",
        action="store_true",
        help="Run dropin_gate.py after schema/correctness/trace gates.",
    )
    parser.add_argument(
        "--dropin-artifact",
        default="zig/zig-out/lib/libwebgpu_doe.so",
        help="Shared library artifact path passed to dropin_gate.py when --with-dropin-gate is set.",
    )
    parser.add_argument(
        "--dropin-symbols",
        default="config/dropin_abi.symbols.txt",
        help="Required symbol list passed to dropin_gate.py.",
    )
    parser.add_argument(
        "--dropin-report",
        default="bench/out/dropin_report.json",
        help="Top-level drop-in report path passed to dropin_gate.py.",
    )
    parser.add_argument(
        "--dropin-symbol-report",
        default="bench/out/dropin_symbol_report.json",
        help="Drop-in symbol report path passed to dropin_gate.py.",
    )
    parser.add_argument(
        "--dropin-behavior-report",
        default="bench/out/dropin_behavior_report.json",
        help="Drop-in behavior report path passed to dropin_gate.py.",
    )
    parser.add_argument(
        "--dropin-benchmark-report",
        default="bench/out/dropin_benchmark_report.json",
        help="Drop-in benchmark report path passed to dropin_gate.py.",
    )
    parser.add_argument(
        "--dropin-benchmark-html",
        default="bench/out/dropin_benchmark_report.html",
        help="Drop-in benchmark HTML path passed to dropin_gate.py.",
    )
    parser.add_argument(
        "--dropin-micro-iterations",
        type=int,
        default=30,
        help="Micro benchmark iteration count passed to dropin_gate.py.",
    )
    parser.add_argument(
        "--dropin-e2e-iterations",
        type=int,
        default=10,
        help="End-to-end benchmark iteration count passed to dropin_gate.py.",
    )
    parser.add_argument(
        "--dropin-skip-benchmarks",
        action="store_true",
        help="Pass --skip-benchmarks to dropin_gate.py.",
    )
    parser.add_argument(
        "--claim-require-comparison-status",
        default="comparable",
        help="Required top-level comparisonStatus when --with-claim-gate is set.",
    )
    parser.add_argument(
        "--claim-require-claim-status",
        default="claimable",
        help="Required top-level claimStatus when --with-claim-gate is set.",
    )
    parser.add_argument(
        "--claim-require-claimability-mode",
        default="release",
        help="Required claimabilityPolicy.mode when --with-claim-gate is set.",
    )
    parser.add_argument(
        "--claim-require-min-timed-samples",
        type=int,
        default=15,
        help="Required claimabilityPolicy.minTimedSamples lower bound when --with-claim-gate is set.",
    )
    parser.add_argument(
        "--claim-expected-workload-contract",
        default="",
        help=(
            "Optional workload contract path forwarded to claim_gate.py "
            "for workload hash/ID-set checks."
        ),
    )
    parser.add_argument(
        "--claim-require-workload-contract-hash",
        action="store_true",
        help="Forward --require-workload-contract-hash to claim_gate.py.",
    )
    parser.add_argument(
        "--claim-require-workload-id-set-match",
        action="store_true",
        help="Forward --require-workload-id-set-match to claim_gate.py.",
    )
    parser.add_argument(
        "--claim-require-backend-telemetry",
        action="store_true",
        help="Forward --require-backend-telemetry to claim_gate.py.",
    )
    parser.add_argument(
        "--claim-expected-backend-id",
        default="",
        help="Forward --expected-backend-id to claim_gate.py.",
    )
    return parser.parse_args()


def run_gate(label: str, command: list[str]) -> None:
    print(f"[gate] {label}: {' '.join(command)}", flush=True)
    subprocess.run(command, check=True)


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.exists():
        print(f"FAIL: missing report: {report_path}")
        return 1

    if args.claim_require_min_timed_samples < 0:
        print(
            "FAIL: invalid --claim-require-min-timed-samples="
            f"{args.claim_require_min_timed_samples} expected >= 0"
        )
        return 1
    if args.require_claim_gate and not args.with_claim_gate:
        print("FAIL: --require-claim-gate requires --with-claim-gate")
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

    output_timestamp = (
        output_paths.resolve_timestamp(args.timestamp)
        if args.timestamp_output
        else ""
    )

    bench_dir = Path(__file__).resolve().parent
    schema_gate = bench_dir / "schema_gate.py"
    file_size_gate = bench_dir / "file_size_gate.py"
    split_coverage_gate = bench_dir / "split_coverage_gate.py"
    backend_workload_catalog_gate = bench_dir / "generate_backend_workloads.py"
    backend_workload_catalog_tests = bench_dir / "test_backend_workload_catalog.py"
    comparability_parity_gate = bench_dir / "comparability_obligation_parity_gate.py"
    correctness_gate = bench_dir / "check_correctness.py"
    trace_gate = bench_dir / "trace_gate.py"
    backend_selection_gate = bench_dir / "backend_selection_gate.py"
    shader_artifact_gate = bench_dir / "shader_artifact_gate.py"
    metal_sync_conformance = bench_dir / "metal_sync_conformance.py"
    metal_timing_policy_gate = bench_dir / "metal_timing_policy_gate.py"
    vulkan_sync_conformance = bench_dir / "vulkan_sync_conformance.py"
    vulkan_timing_policy_gate = bench_dir / "vulkan_timing_policy_gate.py"
    comparable_runtime_invariants_gate = (
        bench_dir / "comparable_runtime_invariants_gate.py"
    )
    browser_gate = bench_dir / "browser_gate.py"
    browser_claim_gate = bench_dir / "browser_claim_gate.py"
    module_gate = bench_dir / "module_gate.py"
    structural_equivalence_gate = bench_dir / "structural_equivalence_gate.py"
    dropin_gate = bench_dir / "dropin_gate.py"
    dropin_proc_resolution_tests = bench_dir / "dropin_proc_resolution_tests.py"
    claim_gate = bench_dir / "claim_gate.py"

    if not args.with_claim_gate:
        print(
            "INFO: claim gate not requested; this run validates blocking gates only "
            "(schema/correctness/trace[/drop-in]) and is not release-claim readiness evidence."
        )
    if not args.with_comparability_parity_gate:
        print(
            "INFO: comparability parity gate not requested; verification-lane Lean/Python "
            "fixture parity is not checked in this run."
        )
    if args.with_claim_gate and not args.with_structural_equivalence_gate:
        print(
            "INFO: enabling structural equivalence gate because --with-claim-gate "
            "was requested."
        )
        args.with_structural_equivalence_gate = True

    try:
        run_gate("schema", [sys.executable, str(schema_gate)])
        if args.with_file_size_gate:
            run_gate("file-size", [sys.executable, str(file_size_gate)])
        if args.with_split_coverage_gate:
            run_gate(
                "split-coverage",
                [
                    sys.executable,
                    str(split_coverage_gate),
                    "--surface",
                    args.split_coverage_surface,
                ],
            )
        run_gate(
            "backend-workload-catalog",
            [sys.executable, str(backend_workload_catalog_gate), "--verify"],
        )
        run_gate(
            "backend-workload-catalog-tests",
            [sys.executable, str(backend_workload_catalog_tests)],
        )
        if args.with_comparability_parity_gate:
            run_gate("comparability-parity", [sys.executable, str(comparability_parity_gate)])
        run_gate(
            "correctness",
            [
                sys.executable,
                str(correctness_gate),
                "--gates",
                args.gates,
                "--quirk",
                args.quirk,
                "--report",
                str(report_path),
            ],
        )
        run_gate(
            "trace",
            [
                sys.executable,
                str(trace_gate),
                "--report",
                str(report_path),
                "--semantic-parity-mode",
                args.trace_semantic_parity_mode,
            ],
        )
        if args.with_comparable_runtime_invariants_gate:
            run_gate(
                "comparable-runtime-invariants",
                [
                    sys.executable,
                    str(comparable_runtime_invariants_gate),
                    "--report",
                    str(report_path),
                ],
            )

        if args.with_modules:
            run_gate(
                "modules",
                [
                    sys.executable,
                    str(module_gate),
                ],
            )

        if args.with_browser_claim_gate:
            run_gate(
                "browser-claim",
                [
                    sys.executable,
                    str(browser_claim_gate),
                ],
            )
        elif args.with_browser_gate:
            run_gate(
                "browser",
                [
                    sys.executable,
                    str(browser_gate),
                ],
            )

        if args.with_structural_equivalence_gate:
            run_gate(
                "structural-equivalence",
                [
                    sys.executable,
                    str(structural_equivalence_gate),
                    "--report",
                    str(report_path),
                    "--require-all-pass",
                ],
            )

        if args.with_backend_selection_gate:
            backend_policy_path = Path(args.backend_runtime_policy)
            if not backend_policy_path.exists():
                print(f"FAIL: missing --backend-runtime-policy: {backend_policy_path}")
                return 1
            backend_selection_command = [
                sys.executable,
                str(backend_selection_gate),
                "--report",
                str(report_path),
                "--policy",
                str(backend_policy_path),
            ]
            if args.backend_selection_lane.strip():
                backend_selection_command.extend(
                    ["--lane", args.backend_selection_lane.strip()]
                )
            run_gate("backend-selection", backend_selection_command)

        if args.with_shader_artifact_gate:
            shader_schema_path = Path(args.shader_artifact_schema)
            if not shader_schema_path.exists():
                print(f"FAIL: missing --shader-artifact-schema: {shader_schema_path}")
                return 1
            if args.shader_artifact_require_spirv_validation:
                spirv_val = args.shader_artifact_spirv_val.strip()
                if not spirv_val:
                    print(
                        "FAIL: --shader-artifact-require-spirv-validation "
                        "requires --shader-artifact-spirv-val"
                    )
                    return 1
                if shutil.which(spirv_val) is None:
                    print(f"FAIL: missing --shader-artifact-spirv-val executable: {spirv_val}")
                    return 1
            shader_artifact_command = [
                sys.executable,
                str(shader_artifact_gate),
                "--report",
                str(report_path),
                "--schema",
                str(shader_schema_path),
            ]
            if args.shader_artifact_require_manifest:
                shader_artifact_command.append("--require-manifest")
            if args.shader_artifact_spirv_val.strip():
                shader_artifact_command.extend(
                    ["--spirv-val", args.shader_artifact_spirv_val.strip()]
                )
            if args.shader_artifact_require_spirv_validation:
                shader_artifact_command.append("--require-spirv-validation")
            run_gate("shader-artifact", shader_artifact_command)

        if args.with_metal_sync_conformance_gate:
            timing_policy_path = Path(args.backend_timing_policy)
            if not timing_policy_path.exists():
                print(f"FAIL: missing --backend-timing-policy: {timing_policy_path}")
                return 1
            run_gate(
                "metal-sync",
                [
                    sys.executable,
                    str(metal_sync_conformance),
                    "--report",
                    str(report_path),
                    "--timing-policy",
                    str(timing_policy_path),
                ],
            )

        if args.with_metal_timing_policy_gate:
            timing_policy_path = Path(args.backend_timing_policy)
            if not timing_policy_path.exists():
                print(f"FAIL: missing --backend-timing-policy: {timing_policy_path}")
                return 1
            run_gate(
                "metal-timing-policy",
                [
                    sys.executable,
                    str(metal_timing_policy_gate),
                    "--report",
                    str(report_path),
                    "--timing-policy",
                    str(timing_policy_path),
                ],
            )

        if args.with_vulkan_sync_conformance_gate:
            timing_policy_path = Path(args.backend_timing_policy)
            if not timing_policy_path.exists():
                print(f"FAIL: missing --backend-timing-policy: {timing_policy_path}")
                return 1
            run_gate(
                "vulkan-sync",
                [
                    sys.executable,
                    str(vulkan_sync_conformance),
                    "--report",
                    str(report_path),
                    "--timing-policy",
                    str(timing_policy_path),
                ],
            )

        if args.with_vulkan_timing_policy_gate:
            timing_policy_path = Path(args.backend_timing_policy)
            if not timing_policy_path.exists():
                print(f"FAIL: missing --backend-timing-policy: {timing_policy_path}")
                return 1
            run_gate(
                "vulkan-timing-policy",
                [
                    sys.executable,
                    str(vulkan_timing_policy_gate),
                    "--report",
                    str(report_path),
                    "--timing-policy",
                    str(timing_policy_path),
                ],
            )

        if args.with_dropin_gate:
            if not args.dropin_artifact.strip():
                print("FAIL: --with-dropin-gate requires --dropin-artifact")
                return 1
            artifact_path = Path(args.dropin_artifact)
            if not artifact_path.exists():
                print(f"FAIL: missing --dropin-artifact: {artifact_path}")
                return 1
            dropin_report = output_paths.with_timestamp(
                args.dropin_report,
                output_timestamp,
                enabled=args.timestamp_output,
            )
            dropin_symbol_report = output_paths.with_timestamp(
                args.dropin_symbol_report,
                output_timestamp,
                enabled=args.timestamp_output,
            )
            dropin_behavior_report = output_paths.with_timestamp(
                args.dropin_behavior_report,
                output_timestamp,
                enabled=args.timestamp_output,
            )
            dropin_benchmark_report = output_paths.with_timestamp(
                args.dropin_benchmark_report,
                output_timestamp,
                enabled=args.timestamp_output,
            )
            dropin_benchmark_html = output_paths.with_timestamp(
                args.dropin_benchmark_html,
                output_timestamp,
                enabled=args.timestamp_output,
            )
            dropin_command = [
                sys.executable,
                str(dropin_gate),
                "--artifact",
                args.dropin_artifact,
                "--symbols",
                args.dropin_symbols,
                "--report",
                str(dropin_report),
                "--symbol-report",
                str(dropin_symbol_report),
                "--behavior-report",
                str(dropin_behavior_report),
                "--benchmark-report",
                str(dropin_benchmark_report),
                "--benchmark-html",
                str(dropin_benchmark_html),
                "--micro-iterations",
                str(args.dropin_micro_iterations),
                "--e2e-iterations",
                str(args.dropin_e2e_iterations),
            ]
            if args.timestamp_output:
                dropin_command.extend(["--timestamp", output_timestamp])
            else:
                dropin_command.append("--no-timestamp-output")
            if args.dropin_skip_benchmarks:
                dropin_command.append("--skip-benchmarks")
            if args.with_dropin_proc_resolution_gate:
                ownership_path = Path(args.dropin_symbol_ownership)
                if not ownership_path.exists():
                    print(f"FAIL: missing --dropin-symbol-ownership: {ownership_path}")
                    return 1
                dropin_command.extend(
                    [
                        "--with-proc-resolution-gate",
                        "--symbol-ownership",
                        str(ownership_path),
                    ]
                )
            run_gate("dropin", dropin_command)

        elif args.with_dropin_proc_resolution_gate:
            if not args.dropin_artifact.strip():
                print("FAIL: --with-dropin-proc-resolution-gate requires --dropin-artifact")
                return 1
            artifact_path = Path(args.dropin_artifact)
            if not artifact_path.exists():
                print(f"FAIL: missing --dropin-artifact: {artifact_path}")
                return 1
            ownership_path = Path(args.dropin_symbol_ownership)
            if not ownership_path.exists():
                print(f"FAIL: missing --dropin-symbol-ownership: {ownership_path}")
                return 1
            run_gate(
                "dropin-proc-resolution",
                [
                    sys.executable,
                    str(dropin_proc_resolution_tests),
                    "--artifact",
                    str(artifact_path),
                    "--ownership",
                    str(ownership_path),
                ],
            )

        if args.with_claim_gate:
            claim_command = [
                sys.executable,
                str(claim_gate),
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
            ]
            if args.claim_expected_workload_contract.strip():
                claim_command.extend(
                    [
                        "--expected-workload-contract",
                        args.claim_expected_workload_contract,
                    ]
                )
            if args.claim_require_workload_contract_hash:
                claim_command.append("--require-workload-contract-hash")
            if args.claim_require_workload_id_set_match:
                claim_command.append("--require-workload-id-set-match")
            if args.claim_require_backend_telemetry:
                claim_command.append("--require-backend-telemetry")
            if args.claim_expected_backend_id.strip():
                claim_command.extend(
                    ["--expected-backend-id", args.claim_expected_backend_id.strip()]
                )
            run_gate("claim", claim_command)
    except subprocess.CalledProcessError as exc:
        print(f"FAIL: gate command failed with return code {exc.returncode}")
        return exc.returncode

    print("PASS: blocking gate sequence completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
