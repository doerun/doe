#!/usr/bin/env python3
"""Canonical entrypoint for schema/correctness/pipeline/trace/drop-in/claim gates with optional parity verification."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)


import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from bench.lib import compare_claim_artifacts as artifacts_mod
from bench.lib import output_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        default="bench/out/dawn-vs-doe.json",
        help="Comparison report produced by the compare lane.",
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
        "--with-tracked-ignore-gate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Run check_no_new_tracked_under_gitignore.py before the normal "
            "gate sequence. Default: enabled. The guard scans staged "
            "additions only, so legacy tracked files under ignored paths do "
            "not block unrelated gate runs."
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
        "--with-comparability-coherence-gate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Run comparability_coherence_gate.py after trace gate. Default: enabled. "
            "Pass --no-with-comparability-coherence-gate only for diagnostic report "
            "audits that are not claim evidence."
        ),
    )
    parser.add_argument(
        "--comparability-coherence-benchmark-policy",
        default="config/benchmark-methodology-thresholds.json",
        help="Benchmark policy path passed to comparability_coherence_gate.py.",
    )
    parser.add_argument(
        "--with-structural-equivalence-gate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Run structural_equivalence_gate.py after trace gate. Default: enabled. "
            "Pass --no-with-structural-equivalence-gate to opt out for diagnostic-only "
            "runs that legitimately fail structural parity (e.g. workloads exercising "
            "Doe-only coverage where Dawn reports unsupported)."
        ),
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
        "--with-dxil-validate-gate",
        action="store_true",
        help="Run dxil_validate_gate.py to validate DXIL structural correctness.",
    )
    parser.add_argument(
        "--dxil-validate-zig",
        default="zig",
        help="Path to the Zig compiler for DXIL validation gate.",
    )
    parser.add_argument(
        "--dxil-validate-skip-zig-tests",
        action="store_true",
        help="Pass --skip-zig-tests to dxil_validate_gate.py.",
    )
    parser.add_argument(
        "--with-spirv-val-gate",
        action="store_true",
        help="Run spirv_val_gate.py to validate SPIR-V artifacts with spirv-val.",
    )
    parser.add_argument(
        "--with-pilot-evidence-gate",
        action="store_true",
        help="Run pilot_evidence_gate.py to audit registered pilot-evidence receipts + their artifact bundles.",
    )
    parser.add_argument(
        "--with-cross-model-parity-gate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Run aggregate_cross_model_parity.py as a blocking two-model Cerebras "
            "parity gate. Default: enabled."
        ),
    )
    parser.add_argument(
        "--cross-model-parity-out",
        default="bench/out/r3-cross-model-parity/receipt.json",
        help="Receipt path written by aggregate_cross_model_parity.py.",
    )
    parser.add_argument(
        "--spirv-val-require",
        action="store_true",
        help="Fail if spirv-val is not available (default: skip with warning).",
    )
    parser.add_argument(
        "--spirv-val-compile",
        action="store_true",
        help="Compile WGSL kernels to SPIR-V before validation.",
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
        "--with-cts-baseline-gate",
        action="store_true",
        help="Run cts_baseline_compare.py to detect CTS conformance regressions.",
    )
    parser.add_argument(
        "--with-csl-governed-lane-gate",
        action="store_true",
        help="Run csl_governed_lane_gate.py to validate governed CSL compile/run/parity reports.",
    )
    parser.add_argument(
        "--with-csl-simulator-gate",
        action="store_true",
        help="Run csl_simulator_gate.py to validate governed CSL simulator/run receipts.",
    )
    parser.add_argument(
        "--with-sdklayout-streaming-hardening-gate",
        action="store_true",
        help=(
            "Run sdklayout_streaming_hardening_gate.py on explicit SdkLayout "
            "streaming traces."
        ),
    )
    parser.add_argument(
        "--with-wgsl-backend-matrix-gate",
        action="store_true",
        help=(
            "Run wgsl_backend_matrix_gate.py to lock cross-backend parity. "
            "Vulkan/Metal/D3D12 readiness is required unconditionally; the CSL "
            "runtime-ready threshold is enforced only when the Cerebras SDK is "
            "detected (DOE_CSL_SDK_ROOT / DOE_CSLC_EXECUTABLE / cslc on PATH). "
            "Prevents Doe regressions on the shared WGSL emitter path across "
            "SDK-absent dev hosts and SDK-present lane runners."
        ),
    )
    parser.add_argument(
        "--with-model-runtime-receipt",
        action="append",
        default=[],
        help=(
            "Run model_runtime_receipt_gate.py on the given doe_model_runtime_receipt "
            "JSON. Repeatable — one invocation per model. Each receipt is gated with "
            "--require-fits --require-structural-full-coverage "
            "--min-kernel-coverage-pct 100 --min-chain-parity-patterns "
            "(--model-runtime-receipt-min-chain-parity, default 0)."
        ),
    )
    parser.add_argument(
        "--model-runtime-receipt-min-chain-parity",
        type=int,
        default=0,
        help="Chain-parity coverage floor applied to every --with-model-runtime-receipt receipt.",
    )
    parser.add_argument(
        "--with-kernel-chain-parity",
        action="append",
        default=[],
        help=(
            "Run kernel_chain_parity_gate.py on the given doe_kernel_chain_parity "
            "JSON. Repeatable — one invocation per chain receipt. Each receipt "
            "gated with --require-bit-close; tighten to --require-bit-exact via "
            "--kernel-chain-parity-bit-exact."
        ),
    )
    parser.add_argument(
        "--kernel-chain-parity-bit-exact",
        action="store_true",
        help="Upgrade --with-kernel-chain-parity from --require-bit-close to --require-bit-exact.",
    )
    parser.add_argument(
        "--wgsl-backend-matrix-report",
        default="bench/out/cross-backend-matrix/wgsl-backend-matrix.json",
    )
    parser.add_argument(
        "--wgsl-backend-matrix-schema",
        default="config/wgsl-backend-matrix-report.schema.json",
    )
    parser.add_argument(
        "--wgsl-backend-matrix-min-csl-runtime-ready",
        type=int,
        default=0,
        help="Enforced only when the Cerebras SDK is detected locally.",
    )
    parser.add_argument(
        "--csl-governed-report",
        default="bench/out/csl-governed-lane.report.json",
        help="Governed CSL lane report path passed to csl_governed_lane_gate.py.",
    )
    parser.add_argument(
        "--csl-governed-schema",
        default="config/csl-governed-lane-report.schema.json",
        help="Governed CSL lane schema path passed to csl_governed_lane_gate.py.",
    )
    parser.add_argument(
        "--csl-governed-require-compile-success",
        action="store_true",
        help="Require compile.status=succeeded in the CSL governed lane gate.",
    )
    parser.add_argument(
        "--csl-governed-require-run-success",
        action="store_true",
        help="Require run.status=succeeded in the CSL governed lane gate.",
    )
    parser.add_argument(
        "--csl-simulator-report",
        default="bench/out/csl-governed-lane.report.json",
        help="Governed CSL lane report path passed to csl_simulator_gate.py.",
    )
    parser.add_argument(
        "--csl-simulator-report-schema",
        default="config/csl-governed-lane-report.schema.json",
        help="Governed CSL lane schema path passed to csl_simulator_gate.py.",
    )
    parser.add_argument(
        "--csl-simulator-require-ready",
        action="store_true",
        help="Require laneStatus=ready in csl_simulator_gate.py.",
    )
    parser.add_argument(
        "--sdklayout-streaming-hardening-trace",
        action="append",
        default=[],
        help=(
            "SdkLayout streaming trace passed to "
            "sdklayout_streaming_hardening_gate.py. Repeatable and required "
            "when --with-sdklayout-streaming-hardening-gate is set."
        ),
    )
    parser.add_argument(
        "--sdklayout-streaming-hardening-fail-on-overalloc",
        action="store_true",
        help=(
            "Forward --fail-on-overalloc to "
            "sdklayout_streaming_hardening_gate.py."
        ),
    )
    parser.add_argument(
        "--cts-baseline-snapshot",
        default="",
        help="Path to the baseline CTS snapshot JSON for regression comparison.",
    )
    parser.add_argument(
        "--cts-baseline-current",
        default="",
        help="Path to the current CTS snapshot JSON. When omitted, latest in bench/out/cts-baseline/ is used.",
    )
    parser.add_argument(
        "--cts-baseline-policy",
        default="config/cts-baseline-policy.json",
        help="CTS baseline policy config path.",
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
        default="runtime/zig/zig-out/lib/libwebgpu_doe.so",
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
        help="Required claimPolicy.mode when --with-claim-gate is set.",
    )
    parser.add_argument(
        "--claim-require-min-timed-samples",
        type=int,
        default=15,
        help="Required claimPolicy.minTimedSamples lower bound when --with-claim-gate is set.",
    )
    parser.add_argument(
        "--claim-config",
        default="",
        help="Optional compare config forwarded to `bench/cli.py claim` before claim gate evaluation.",
    )
    parser.add_argument(
        "--claim-benchmark-policy",
        default="config/benchmark-methodology-thresholds.json",
        help="Benchmark policy path forwarded to `bench/cli.py claim`.",
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

    try:
        report_payload = artifacts_mod.load_compare_report(report_path)
        artifacts_mod.ensure_release_strict_comparability(
            report_payload,
            report_path,
            surface="run_blocking_gates",
        )
    except RuntimeError as exc:
        print(f"FAIL: {exc}")
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
    if args.with_claim_gate:
        claim_benchmark_policy_path = Path(args.claim_benchmark_policy)
        if not claim_benchmark_policy_path.exists():
            print(f"FAIL: missing --claim-benchmark-policy: {claim_benchmark_policy_path}")
            return 1
    if args.with_comparability_coherence_gate:
        comparability_coherence_policy_path = Path(
            args.comparability_coherence_benchmark_policy
        )
        if not comparability_coherence_policy_path.exists():
            print(
                "FAIL: missing --comparability-coherence-benchmark-policy: "
                f"{comparability_coherence_policy_path}"
            )
            return 1

    output_timestamp = (
        output_paths.resolve_timestamp(args.timestamp)
        if args.timestamp_output
        else ""
    )

    gates_dir = BENCH_ROOT / "gates"
    tools_dir = BENCH_ROOT / "tools"
    tests_dir = BENCH_ROOT / "tests"
    browser_dir = BENCH_ROOT / "browser"
    dropin_dir = BENCH_ROOT / "drop-in"
    schema_gate = gates_dir / "schema_gate.py"
    file_size_gate = gates_dir / "file_size_gate.py"
    split_coverage_gate = gates_dir / "split_coverage_gate.py"
    backend_workload_catalog_gate = tools_dir / "generate_backend_workloads.py"
    workload_overlap_map = tools_dir / "generate_workload_overlap_map.py"
    comparability_parity_gate = gates_dir / "comparability_obligation_parity_gate.py"
    correctness_gate = gates_dir / "check_correctness.py"
    trace_gate = gates_dir / "trace_gate.py"
    backend_selection_gate = gates_dir / "backend_selection_gate.py"
    shader_artifact_gate = gates_dir / "shader_artifact_gate.py"
    spirv_val_gate = gates_dir / "spirv_val_gate.py"
    dxil_validate_gate = gates_dir / "dxil_validate_gate.py"
    sync_conformance_gate = gates_dir / "sync_conformance_gate.py"
    timing_policy_gate = gates_dir / "timing_policy_gate.py"
    comparable_runtime_invariants_gate = (
        gates_dir / "comparable_runtime_invariants_gate.py"
    )
    browser_gate = browser_dir / "browser_gate.py"
    browser_claim_gate = browser_dir / "browser_claim_gate.py"
    module_gate = gates_dir / "module_gate.py"
    comparability_coherence_gate = gates_dir / "comparability_coherence_gate.py"
    structural_equivalence_gate = gates_dir / "structural_equivalence_gate.py"
    dropin_gate = dropin_dir / "dropin_gate.py"
    dropin_proc_resolution_tests = dropin_dir / "dropin_proc_resolution_tests.py"
    cts_baseline_compare = tools_dir / "cts_baseline_compare.py"
    csl_governed_lane_gate = gates_dir / "csl_governed_lane_gate.py"
    csl_simulator_gate = gates_dir / "csl_simulator_gate.py"
    sdklayout_streaming_hardening_gate = (
        gates_dir / "sdklayout_streaming_hardening_gate.py"
    )
    cerebras_artifact_gate = gates_dir / "cerebras_artifact_gate.py"
    doe_private_strategy_leak_gate = gates_dir / "doe_private_strategy_leak_gate.py"
    wgsl_backend_matrix_gate = gates_dir / "wgsl_backend_matrix_gate.py"
    model_runtime_receipt_gate = gates_dir / "model_runtime_receipt_gate.py"
    kernel_chain_parity_gate = gates_dir / "kernel_chain_parity_gate.py"
    csl_fixture_mirror_gate = gates_dir / "csl_fixture_mirror_gate.py"
    csl_operation_graph_gate = gates_dir / "csl_operation_graph_gate.py"
    cross_model_parity_gate = tools_dir / "aggregate_cross_model_parity.py"
    tracked_ignore_gate = tools_dir / "check_no_new_tracked_under_gitignore.py"
    pilot_evidence_gate = gates_dir / "pilot_evidence_gate.py"
    claim_gate = gates_dir / "claim_gate.py"
    bench_cli = BENCH_ROOT / "cli.py"

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
    if not args.with_comparability_coherence_gate:
        print(
            "INFO: comparability coherence gate disabled via "
            "--no-with-comparability-coherence-gate; this run does NOT validate "
            "that workload matching, obligations, structural checks, timing "
            "phase checks, and sample-floor policy agree at report scope."
        )
    if not args.with_structural_equivalence_gate:
        print(
            "INFO: structural equivalence gate disabled via "
            "--no-with-structural-equivalence-gate; this run does NOT validate "
            "dispatch-count parity, timing-phase symmetry, or zero-phase "
            "anomalies. Use only for diagnostic-only runs that legitimately "
            "fail structural parity (e.g. directional coverage lanes)."
        )
    if args.with_claim_gate and not args.with_comparability_coherence_gate:
        print(
            "FAIL: --with-claim-gate requires comparability coherence gate "
            "(remove --no-with-comparability-coherence-gate)."
        )
        return 1
    if args.with_claim_gate and not args.with_structural_equivalence_gate:
        # --with-claim-gate cannot coexist with structural opt-out; CLAUDE.md
        # non-negotiable #10 requires structural parity for any claim-eligible
        # workload.
        print(
            "FAIL: --with-claim-gate requires structural equivalence gate "
            "(remove --no-with-structural-equivalence-gate)."
        )
        return 1

    try:
        if args.with_tracked_ignore_gate:
            run_gate(
                "tracked-ignore",
                [sys.executable, str(tracked_ignore_gate)],
            )
        run_gate("schema", [sys.executable, str(schema_gate)])
        run_gate("cerebras-artifact", [sys.executable, str(cerebras_artifact_gate)])
        run_gate("doe-private-strategy-leak", [sys.executable, str(doe_private_strategy_leak_gate)])
        run_gate("csl-fixture-mirrors", [sys.executable, str(csl_fixture_mirror_gate)])
        run_gate("csl-operation-graph", [sys.executable, str(csl_operation_graph_gate)])
        if args.with_cross_model_parity_gate:
            run_gate(
                "cross-model-parity",
                [
                    sys.executable,
                    str(cross_model_parity_gate),
                    "--out",
                    args.cross_model_parity_out,
                ],
            )
        if args.with_pilot_evidence_gate:
            run_gate("pilot-evidence", [sys.executable, str(pilot_evidence_gate)])
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
            [
                sys.executable,
                "-m",
                "unittest",
                "bench.tests.test_backend_workload_catalog",
            ],
        )
        run_gate(
            "backend-workload-overlap-map",
            [
                sys.executable,
                str(workload_overlap_map),
                "--verify",
            ],
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
        if args.with_csl_governed_lane_gate:
            gate_cmd = [
                sys.executable,
                str(csl_governed_lane_gate),
                "--report",
                args.csl_governed_report,
                "--schema",
                args.csl_governed_schema,
            ]
            if args.csl_governed_require_compile_success:
                gate_cmd.append("--require-compile-success")
            if args.csl_governed_require_run_success:
                gate_cmd.append("--require-run-success")
            run_gate("csl-governed-lane", gate_cmd)

        if args.with_csl_simulator_gate:
            gate_cmd = [
                sys.executable,
                str(csl_simulator_gate),
                "--report",
                args.csl_simulator_report,
                "--report-schema",
                args.csl_simulator_report_schema,
            ]
            if args.csl_simulator_require_ready:
                gate_cmd.append("--require-ready")
            run_gate("csl-simulator", gate_cmd)

        if args.with_sdklayout_streaming_hardening_gate:
            gate_cmd = [
                sys.executable,
                str(sdklayout_streaming_hardening_gate),
            ]
            for trace_path in args.sdklayout_streaming_hardening_trace:
                gate_cmd.extend(["--trace", trace_path])
            if args.sdklayout_streaming_hardening_fail_on_overalloc:
                gate_cmd.append("--fail-on-overalloc")
            run_gate("sdklayout-streaming-hardening", gate_cmd)

        if args.with_wgsl_backend_matrix_gate:
            gate_cmd = [
                sys.executable,
                str(wgsl_backend_matrix_gate),
                "--report",
                args.wgsl_backend_matrix_report,
                "--schema",
                args.wgsl_backend_matrix_schema,
                "--require-vulkan-ready",
                "--require-metal-ready",
                "--require-d3d12-ready",
                "--sdk-optional",
                "--min-csl-runtime-ready",
                str(args.wgsl_backend_matrix_min_csl_runtime_ready),
            ]
            run_gate("wgsl-backend-matrix", gate_cmd)

        for receipt_path in args.with_model_runtime_receipt:
            gate_cmd = [
                sys.executable,
                str(model_runtime_receipt_gate),
                "--receipt", receipt_path,
                "--require-fits",
                "--require-structural-full-coverage",
                "--min-kernel-coverage-pct", "100",
                "--min-chain-parity-patterns",
                str(args.model_runtime_receipt_min_chain_parity),
            ]
            stem = Path(receipt_path).stem
            run_gate(f"model-runtime-receipt:{stem}", gate_cmd)

        for receipt_path in args.with_kernel_chain_parity:
            gate_cmd = [sys.executable, str(kernel_chain_parity_gate), "--receipt", receipt_path]
            if args.kernel_chain_parity_bit_exact:
                gate_cmd.append("--require-bit-exact")
            else:
                gate_cmd.append("--require-bit-close")
            stem = Path(receipt_path).stem
            run_gate(f"kernel-chain-parity:{stem}", gate_cmd)

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

        if args.with_comparability_coherence_gate:
            run_gate(
                "comparability-coherence",
                [
                    sys.executable,
                    str(comparability_coherence_gate),
                    "--report",
                    str(report_path),
                    "--benchmark-policy",
                    args.comparability_coherence_benchmark_policy,
                    "--require-pass",
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
            spirv_val = args.shader_artifact_spirv_val.strip()
            if not spirv_val:
                spirv_val = shutil.which("spirv-val") or ""
            if args.shader_artifact_require_spirv_validation and not spirv_val:
                print(
                    "FAIL: --shader-artifact-require-spirv-validation "
                    "requires --shader-artifact-spirv-val or spirv-val on PATH"
                )
                return 1
            if spirv_val and shutil.which(spirv_val) is None:
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
            if spirv_val:
                shader_artifact_command.extend(["--spirv-val", spirv_val])
            if args.shader_artifact_require_spirv_validation and not spirv_val:
                shader_artifact_command.append("--require-spirv-validation")
            run_gate("shader-artifact", shader_artifact_command)

        if args.with_spirv_val_gate:
            spirv_val_command = [
                sys.executable,
                str(spirv_val_gate),
            ]
            if args.spirv_val_require:
                spirv_val_command.append("--require")
            if args.spirv_val_compile:
                spirv_val_command.append("--compile")
            run_gate("spirv-val", spirv_val_command)

        if args.with_dxil_validate_gate:
            dxil_validate_command = [
                sys.executable,
                str(dxil_validate_gate),
                "--zig",
                args.dxil_validate_zig,
            ]
            if args.dxil_validate_skip_zig_tests:
                dxil_validate_command.append("--skip-zig-tests")
            run_gate("dxil-validate", dxil_validate_command)

        sync_gate_runs = (
            ("metal-sync", "metal", args.with_metal_sync_conformance_gate),
            ("vulkan-sync", "vulkan", args.with_vulkan_sync_conformance_gate),
        )
        for label, backend, enabled in sync_gate_runs:
            if not enabled:
                continue
            timing_policy_path = Path(args.backend_timing_policy)
            if not timing_policy_path.exists():
                print(f"FAIL: missing --backend-timing-policy: {timing_policy_path}")
                return 1
            run_gate(
                label,
                [
                    sys.executable,
                    str(sync_conformance_gate),
                    "--backend",
                    backend,
                    "--report",
                    str(report_path),
                    "--timing-policy",
                    str(timing_policy_path),
                ],
            )

        timing_gate_runs = (
            ("metal-timing-policy", "metal", args.with_metal_timing_policy_gate),
            ("vulkan-timing-policy", "vulkan", args.with_vulkan_timing_policy_gate),
        )
        for label, backend, enabled in timing_gate_runs:
            if not enabled:
                continue
            timing_policy_path = Path(args.backend_timing_policy)
            if not timing_policy_path.exists():
                print(f"FAIL: missing --backend-timing-policy: {timing_policy_path}")
                return 1
            run_gate(
                label,
                [
                    sys.executable,
                    str(timing_policy_gate),
                    "--backend",
                    backend,
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

        if args.with_cts_baseline_gate:
            if not args.cts_baseline_snapshot.strip():
                print("FAIL: --with-cts-baseline-gate requires --cts-baseline-snapshot")
                return 1
            baseline_snapshot_path = Path(args.cts_baseline_snapshot)
            if not baseline_snapshot_path.exists():
                print(f"FAIL: missing --cts-baseline-snapshot: {baseline_snapshot_path}")
                return 1
            cts_compare_command = [
                sys.executable,
                str(cts_baseline_compare),
                "--baseline",
                str(baseline_snapshot_path),
                "--policy",
                args.cts_baseline_policy,
                "--gate",
            ]
            if args.cts_baseline_current.strip():
                cts_compare_command.extend(["--current", args.cts_baseline_current])
            else:
                cts_compare_command.extend(["--current-dir", "bench/out/cts-baseline"])
            run_gate("cts-baseline", cts_compare_command)

        if args.with_claim_gate:
            claim_report_path = artifacts_mod.claim_report_candidate_path(report_path)
            claim_build_command = [
                sys.executable,
                str(bench_cli),
                "claim",
                str(report_path),
                "--mode",
                args.claim_require_claimability_mode,
                "--min-timed-samples",
                str(args.claim_require_min_timed_samples),
                "--benchmark-policy",
                args.claim_benchmark_policy,
                "--out",
                str(claim_report_path),
            ]
            if args.claim_config.strip():
                claim_build_command.extend(["--config", args.claim_config.strip()])
            print(f"[gate] claim-report: {' '.join(claim_build_command)}", flush=True)
            claim_build_proc = subprocess.run(claim_build_command, check=False)
            if claim_build_proc.returncode not in (0, 2) or not claim_report_path.exists():
                raise subprocess.CalledProcessError(
                    claim_build_proc.returncode,
                    claim_build_command,
                )

            claim_command = [
                sys.executable,
                str(claim_gate),
                "--report",
                str(report_path),
                "--claim-report",
                str(claim_report_path),
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
