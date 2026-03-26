#!/usr/bin/env python3
"""
Dawn/Doe side-by-side benchmark runner.

This script executes shared workload command templates for both runtimes and emits
timing traces where available, with wall-time as a fallback.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)


import json
import os
import time
from typing import Any

CATALOG_PATH = BENCH_ROOT / "workloads" / "metadata" / "backend-workload-catalog.json"

from bench.lib import output_paths
from native_compare_modules import config_support as config_support_mod
from native_compare_modules import claimability as claimability_mod
from native_compare_modules import comparability as comparability_mod
from native_compare_modules import reporting as reporting_mod
from native_compare_modules import timing_interpretation as timing_interpretation_mod
from native_compare_modules import timing_selection as timing_selection_mod
from native_compare_modules import runner as runner_mod
from native_compare_modules import workload_validation as workload_validation_mod
from native_compare_modules import report_assembly as report_assembly_mod

DEFAULT_WORKLOADS_PATH = config_support_mod.DEFAULT_WORKLOADS_PATH
DEFAULT_LEFT_NAME = config_support_mod.DEFAULT_LEFT_NAME
DEFAULT_RIGHT_NAME = config_support_mod.DEFAULT_RIGHT_NAME
DEFAULT_LEFT_COMMAND_TEMPLATE = config_support_mod.DEFAULT_LEFT_COMMAND_TEMPLATE
DEFAULT_ITERATIONS = config_support_mod.DEFAULT_ITERATIONS
DEFAULT_WARMUP = config_support_mod.DEFAULT_WARMUP
DEFAULT_OUT_PATH = config_support_mod.DEFAULT_OUT_PATH
DEFAULT_WORKSPACE_PATH = config_support_mod.DEFAULT_WORKSPACE_PATH
DEFAULT_WORKLOAD_FILTER = config_support_mod.DEFAULT_WORKLOAD_FILTER
DEFAULT_WORKLOAD_COHORT = config_support_mod.DEFAULT_WORKLOAD_COHORT
DEFAULT_COMPARABILITY_MODE = config_support_mod.DEFAULT_COMPARABILITY_MODE
DEFAULT_REQUIRED_TIMING_CLASS = config_support_mod.DEFAULT_REQUIRED_TIMING_CLASS
DEFAULT_RESOURCE_PROBE = config_support_mod.DEFAULT_RESOURCE_PROBE
DEFAULT_RESOURCE_SAMPLE_MS = config_support_mod.DEFAULT_RESOURCE_SAMPLE_MS
DEFAULT_RESOURCE_SAMPLE_TARGET_COUNT = config_support_mod.DEFAULT_RESOURCE_SAMPLE_TARGET_COUNT
DEFAULT_WORKLOAD_COOLDOWN_MS = config_support_mod.DEFAULT_WORKLOAD_COOLDOWN_MS
DEFAULT_CLAIMABILITY_MODE = config_support_mod.DEFAULT_CLAIMABILITY_MODE
DEFAULT_CLAIM_MIN_TIMED_SAMPLES = config_support_mod.DEFAULT_CLAIM_MIN_TIMED_SAMPLES
DEFAULT_BENCHMARK_POLICY_PATH = config_support_mod.DEFAULT_BENCHMARK_POLICY_PATH
DEFAULT_BENCHMARK_POLICY_CANDIDATES = config_support_mod.DEFAULT_BENCHMARK_POLICY_CANDIDATES
VALID_COMPARABILITY_MODES = config_support_mod.VALID_COMPARABILITY_MODES
VALID_REQUIRED_TIMING_CLASSES = config_support_mod.VALID_REQUIRED_TIMING_CLASSES
VALID_RESOURCE_PROBES = config_support_mod.VALID_RESOURCE_PROBES
VALID_CLAIMABILITY_MODES = config_support_mod.VALID_CLAIMABILITY_MODES
VALID_UPLOAD_BUFFER_USAGES = config_support_mod.VALID_UPLOAD_BUFFER_USAGES
VALID_WORKLOAD_COHORTS = config_support_mod.VALID_WORKLOAD_COHORTS
NON_APPLES_TO_APPLES_DOMAINS = config_support_mod.NON_APPLES_TO_APPLES_DOMAINS
FAWN_UPLOAD_RUNTIME_SOURCE_PATHS = config_support_mod.FAWN_UPLOAD_RUNTIME_SOURCE_PATHS
NATIVE_EXECUTION_OPERATION_TIMING_SOURCES = config_support_mod.NATIVE_EXECUTION_OPERATION_TIMING_SOURCES
KNOWN_GPU_BACKENDS = config_support_mod.KNOWN_GPU_BACKENDS
GPU_BACKEND_ALIASES = config_support_mod.GPU_BACKEND_ALIASES
HOST_ALLOWED_GPU_BACKENDS = config_support_mod.HOST_ALLOWED_GPU_BACKENDS
Workload = config_support_mod.Workload
BenchmarkMethodologyPolicy = config_support_mod.BenchmarkMethodologyPolicy
parse_args = config_support_mod.parse_args
load_json = config_support_mod.load_json
get_nested = config_support_mod.get_nested
first_config_value = config_support_mod.first_config_value
as_str = config_support_mod.as_str
as_int = config_support_mod.as_int
as_float = config_support_mod.as_float
as_bool = config_support_mod.as_bool
apply_config_defaults = config_support_mod.apply_config_defaults
resolve_benchmark_policy_path = config_support_mod.resolve_benchmark_policy_path
load_benchmark_methodology_policy = config_support_mod.load_benchmark_methodology_policy
safe_int = config_support_mod.safe_int
percent_delta = config_support_mod.percent_delta
parse_extra_args = config_support_mod.parse_extra_args
parse_comparability_candidate = config_support_mod.parse_comparability_candidate
safe_float = runner_mod.safe_float
parse_int = runner_mod.parse_int
dawn_metric_median_ms = runner_mod.dawn_metric_median_ms
extract_timing_metrics_ms = runner_mod.extract_timing_metrics_ms
normalize_timing_metrics_ms = runner_mod.normalize_timing_metrics_ms
read_process_rss_kb = runner_mod.read_process_rss_kb
read_rocm_vram_snapshot = runner_mod.read_rocm_vram_snapshot
assert_json_object = runner_mod.assert_json_object
parse_trace_meta = runner_mod.parse_trace_meta
materialize_repeated_commands = runner_mod.materialize_repeated_commands
command_for = runner_mod.command_for
max_rss_time_prefix = runner_mod.max_rss_time_prefix
run_once = runner_mod.run_once
run_workload = runner_mod.run_workload
run_compilation_workload = runner_mod.run_compilation_workload
run_js_pipeline_workload = runner_mod.run_js_pipeline_workload
load_workloads = config_support_mod.load_workloads

# Re-exports from workload_validation
parse_positive_int_command_field = workload_validation_mod.parse_positive_int_command_field
command_shape_multiplier = workload_validation_mod.command_shape_multiplier
infer_command_shape_operation_count = workload_validation_mod.infer_command_shape_operation_count
infer_command_shape_dispatch_count = workload_validation_mod.infer_command_shape_dispatch_count
enforce_strict_command_shape_divisor_contracts = workload_validation_mod.enforce_strict_command_shape_divisor_contracts
template_uses_doe_runtime = workload_validation_mod.template_uses_doe_runtime
expected_divisor_units = workload_validation_mod.expected_divisor_units
template_backend_lane = workload_validation_mod.template_backend_lane
enforce_strict_doe_runtime_normalization_symmetry = workload_validation_mod.enforce_strict_doe_runtime_normalization_symmetry
enforce_strict_dawn_vs_doe_direct_operation_timing = workload_validation_mod.enforce_strict_dawn_vs_doe_direct_operation_timing
backend_from_token = workload_validation_mod.backend_from_token
infer_backend_from_lane_name = workload_validation_mod.infer_backend_from_lane_name
extract_backends_from_command = workload_validation_mod.extract_backends_from_command
infer_workload_queue_sync_mode = workload_validation_mod.infer_workload_queue_sync_mode
infer_workload_backends = workload_validation_mod.infer_workload_backends
enforce_host_backend_policy = workload_validation_mod.enforce_host_backend_policy

# Re-exports from existing modules
format_stats = reporting_mod.format_stats
format_distribution = reporting_mod.format_distribution
summarize_timing_metric_stats = reporting_mod.summarize_timing_metric_stats
summarize_resource_stats = reporting_mod.summarize_resource_stats

command_sample_field_values_ms = timing_interpretation_mod.command_sample_field_values_ms
delta_percent_from_stats = timing_interpretation_mod.delta_percent_from_stats
build_timing_interpretation = timing_interpretation_mod.build_timing_interpretation

parse_trace_rows = timing_selection_mod.parse_trace_rows
maybe_adjust_timing_for_ignored_first_ops = timing_selection_mod.maybe_adjust_timing_for_ignored_first_ops
canonical_timing_source = timing_selection_mod.canonical_timing_source
classify_timing_source = timing_selection_mod.classify_timing_source
pick_measured_timing_ms = timing_selection_mod.pick_measured_timing_ms

is_dawn_writebuffer_upload_workload = comparability_mod.is_dawn_writebuffer_upload_workload
validate_upload_apples_to_apples = comparability_mod.validate_upload_apples_to_apples
compare_assessment = comparability_mod.compare_assessment

default_claim_min_timed_samples = claimability_mod.default_claim_min_timed_samples
required_positive_percentiles = claimability_mod.required_positive_percentiles
assess_upload_timing_scope_consistency = claimability_mod.assess_upload_timing_scope_consistency
assess_claimability = claimability_mod.assess_claimability

# Re-exports from report_assembly
build_report_header = report_assembly_mod.build_report_header
compute_workload_delta = report_assembly_mod.compute_workload_delta
build_workload_report_entry = report_assembly_mod.build_workload_report_entry
build_claim_row_context = report_assembly_mod.build_claim_row_context
build_overall_stats = report_assembly_mod.build_overall_stats
build_report_summaries = report_assembly_mod.build_report_summaries
summarize_operator_diff = report_assembly_mod.summarize_operator_diff
write_report_and_determine_status = report_assembly_mod.write_report_and_determine_status

# Re-exports from runner
file_sha256 = runner_mod.file_sha256
json_sha256 = runner_mod.json_sha256
collect_trace_meta_hashes = runner_mod.collect_trace_meta_hashes


def main() -> int:
    args = parse_args()
    args = apply_config_defaults(args)

    if args.iterations < 0 or args.warmup < 0:
        raise ValueError("--iterations and --warmup must be >= 0")
    if args.resource_sample_ms < 1:
        raise ValueError("--resource-sample-ms must be >= 1")
    if args.resource_sample_target_count < 0:
        raise ValueError("--resource-sample-target-count must be >= 0")
    if args.workload_cooldown_ms < 0:
        raise ValueError("--workload-cooldown-ms must be >= 0")
    if args.claim_min_timed_samples < 0:
        raise ValueError("--claim-min-timed-samples must be >= 0")
    if not args.right_command_template:
        raise ValueError(
            "missing right command template: pass --right-command-template or "
            "--config with right.commandTemplate"
        )
    if (
        args.workload_cohort in {"comparability-candidates", "doe-advantage"}
        and (not args.include_noncomparable_workloads)
    ):
        raise ValueError(
            f"workload cohort {args.workload_cohort} requires "
            "--include-noncomparable-workloads (or run.includeNoncomparableWorkloads=true)"
        )
    benchmark_policy = load_benchmark_methodology_policy(args.benchmark_policy)

    workloads_path = Path(args.workloads)
    if CATALOG_PATH.exists() and workloads_path.exists():
        catalog_mtime = os.path.getmtime(CATALOG_PATH)
        workloads_mtime = os.path.getmtime(workloads_path)
        if catalog_mtime > workloads_mtime:
            print(
                f"WARNING: {workloads_path.name} may be stale — "
                f"workloads/metadata/backend-workload-catalog.json was modified more recently. "
                f"Run: python3 bench/tools/generate_backend_workloads.py",
                file=sys.stderr,
            )
    workloads = load_workloads(
        workloads_path,
        args.workload_filter,
        include_noncomparable=bool(args.include_noncomparable_workloads),
        include_extended=bool(args.include_extended_workloads),
        workload_cohort=args.workload_cohort,
        selector=getattr(args, "selector", None),
    )
    if not workloads:
        hint = ""
        if not args.include_noncomparable_workloads or not args.include_extended_workloads:
            hint = (
                " (selected workloads may be filtered by selector/cohort/benchmarkClass or by "
                "legacy comparable=false/default=false behavior)"
            )
        if args.workload_cohort == "comparability-candidates":
            hint += (
                " (workload cohort comparability-candidates requires "
                "comparabilityCandidate.enabled=true entries)"
            )
        if args.workload_cohort == "doe-advantage":
            hint += (
                " (workload cohort doe-advantage requires "
                "benchmarkClass=directional entries)"
            )
        print(f"FAIL: no workloads selected{hint}")
        return 1
    enforce_host_backend_policy(
        workloads=workloads,
        left_command_template=args.left_command_template,
        right_command_template=args.right_command_template,
    )
    if args.claimability in {"local", "release"}:
        non_comparable_contract_ids = [
            workload.id
            for workload in workloads
            if workload.benchmark_class != "comparable"
        ]
        if non_comparable_contract_ids:
            raise ValueError(
                "claimability mode requires comparable-only workload contracts "
                "(benchmarkClass=comparable). Directional workloads selected: "
                + ", ".join(non_comparable_contract_ids)
            )
    enforce_strict_doe_runtime_normalization_symmetry(
        workloads=workloads,
        left_command_template=args.left_command_template,
        right_command_template=args.right_command_template,
        comparability_mode=args.comparability,
    )
    enforce_strict_dawn_vs_doe_direct_operation_timing(
        workloads=workloads,
        left_command_template=args.left_command_template,
        right_command_template=args.right_command_template,
        comparability_mode=args.comparability,
        required_timing_class=args.require_timing_class,
    )
    enforce_strict_command_shape_divisor_contracts(
        workloads=workloads,
        comparability_mode=args.comparability,
        required_timing_class=args.require_timing_class,
        right_command_template=args.right_command_template,
    )

    if (
        not args.emit_shell
        and args.comparability == "strict"
        and args.require_timing_class == "operation"
    ):
        strict_upload_workload = next(
            (workload for workload in workloads if is_dawn_writebuffer_upload_workload(workload)),
            None,
        )
        if strict_upload_workload is not None:
            comparability_mod.verify_fawn_upload_runtime_contract(
                template=args.left_command_template,
                workload=strict_upload_workload,
                command_for_fn=command_for,
                runtime_source_paths=FAWN_UPLOAD_RUNTIME_SOURCE_PATHS,
            )

    output_timestamp = (
        output_paths.resolve_timestamp(args.timestamp)
        if args.timestamp_output
        else ""
    )
    run_group = output_paths.derive_bench_out_group(args.out)
    workspace = output_paths.with_timestamp(
        args.workspace,
        output_timestamp,
        enabled=args.timestamp_output,
        group=run_group,
    )
    out = output_paths.with_timestamp(
        args.out,
        output_timestamp,
        enabled=args.timestamp_output,
        group=run_group,
    )
    report = build_report_header(
        args=args,
        workloads_path=workloads_path,
        benchmark_policy=benchmark_policy,
        output_timestamp=output_timestamp,
        out=out,
        workspace=workspace,
    )

    overall_left: list[float] = []
    overall_right: list[float] = []
    overall_headline_left: list[float] = []
    overall_headline_right: list[float] = []
    comparability_failures: list[dict[str, Any]] = []
    claimability_failures: list[dict[str, Any]] = []
    previous_claim_row_hash = "0" * 64
    claim_row_hashes: list[str] = []

    for idx, workload in enumerate(workloads, 1):
        print(f"[{idx}/{len(workloads)}] Running workload: {workload.id}...", file=sys.stderr, flush=True)
        workload_dir = workspace / workload.id
        runner_type = getattr(workload, "runner_type", "zig-runtime")

        if runner_type == "compilation":
            try:
                both = run_compilation_workload(
                    workload=workload,
                    iterations=args.iterations,
                    warmup=args.warmup,
                    out_dir=workload_dir,
                    doe_compilation_bin=getattr(args, "doe_compilation_bin", "runtime/zig/zig-out/bin/doe-compilation-bench"),
                    tint_bin=getattr(args, "tint_bin", "bench/vendor/dawn/out/Release/tint"),
                )
            except RuntimeError as exc:
                print(f"  SKIP ({exc})", file=sys.stderr, flush=True)
                continue
            left = both["left"]
            right = both["right"]
        elif runner_type == "js-pipeline":
            try:
                both = run_js_pipeline_workload(
                    workload=workload,
                    iterations=args.iterations,
                    warmup=args.warmup,
                    out_dir=workload_dir,
                    js_runtime=getattr(args, "js_runtime", "node"),
                )
            except RuntimeError as exc:
                print(f"  SKIP ({exc})", file=sys.stderr, flush=True)
                continue
            left = both["left"]
            right = both["right"]
        else:
            validate_upload_apples_to_apples(
                workload,
                comparability_mode=args.comparability,
            )
            left = run_workload(
                name=args.left_name,
                template=args.left_command_template,
                workload=workload,
                iterations=args.iterations,
                warmup=args.warmup,
                out_dir=workload_dir / "left",
                gpu_memory_probe=args.resource_probe,
                resource_sample_ms=args.resource_sample_ms,
                resource_sample_target_count=args.resource_sample_target_count,
                timing_divisor=workload.left_timing_divisor,
                command_repeat=workload.left_command_repeat,
                ignore_first_ops=workload.left_ignore_first_ops,
                upload_buffer_usage=workload.left_upload_buffer_usage,
                upload_submit_every=workload.left_upload_submit_every,
                inject_upload_runtime_flags=True,
                required_timing_class=args.require_timing_class,
                comparability_mode=args.comparability,
                benchmark_policy=benchmark_policy,
                emit_shell=args.emit_shell,
            )
            right = run_workload(
                name=args.right_name,
                template=args.right_command_template,
                workload=workload,
                iterations=args.iterations,
                warmup=args.warmup,
                out_dir=workload_dir / "right",
                gpu_memory_probe=args.resource_probe,
                resource_sample_ms=args.resource_sample_ms,
                resource_sample_target_count=args.resource_sample_target_count,
                timing_divisor=workload.right_timing_divisor,
                command_repeat=workload.right_command_repeat,
                ignore_first_ops=workload.right_ignore_first_ops,
                upload_buffer_usage=workload.right_upload_buffer_usage,
                upload_submit_every=workload.right_upload_submit_every,
                inject_upload_runtime_flags=False,
                required_timing_class=args.require_timing_class,
                comparability_mode=args.comparability,
                benchmark_policy=benchmark_policy,
                emit_shell=args.emit_shell,
            )

        left_stats = left["stats"]
        right_stats = right["stats"]
        left_timings = left.get("timingsMs", [])
        right_timings = right.get("timingsMs", [])
        if not isinstance(left_timings, list):
            left_timings = []
        if not isinstance(right_timings, list):
            right_timings = []
        delta = compute_workload_delta(left_stats, right_stats)
        timing_interpretation = build_timing_interpretation(left=left, right=right)
        comparability = compare_assessment(
            workload_id=workload.id,
            workload_comparable=workload.comparable,
            workload_domain=workload.domain,
            workload_path_asymmetry=workload.path_asymmetry,
            workload_path_asymmetry_note=workload.path_asymmetry_note,
            left_command_repeat=workload.left_command_repeat,
            right_command_repeat=workload.right_command_repeat,
            left=left,
            right=right,
            required_timing_class=args.require_timing_class,
            allow_left_no_execution=(
                args.allow_left_no_execution or workload.allow_left_no_execution
            ),
            resource_probe=args.resource_probe,
            comparability_mode=args.comparability,
            resource_sample_target_count=args.resource_sample_target_count,
        )
        claimability = assess_claimability(
            mode=args.claimability,
            min_timed_samples=args.claim_min_timed_samples,
            workload=workload,
            left=left,
            right=right,
            delta=delta,
            timing_interpretation=timing_interpretation,
            comparability=comparability,
            benchmark_policy=benchmark_policy,
        )
        if not comparability["comparable"]:
            comparability_failures.append(
                {
                    "workloadId": workload.id,
                    "failedBlockingObligations": comparability.get(
                        "blockingFailedObligations", []
                    ),
                    "reasons": comparability["reasons"],
                }
            )
        if claimability.get("evaluated") is True and not claimability.get("claimable", False):
            claimability_failures.append(
                {
                    "workloadId": workload.id,
                    "reasons": claimability.get("reasons", []),
                }
            )

        if comparability.get("comparable"):
            if left_stats["count"] >= 7:
                overall_left.extend([safe_float(v) for v in left_timings if safe_float(v) is not None])
                overall_headline_left.extend(
                    command_sample_field_values_ms(left.get("commandSamples", []), "elapsedMs")
                )
            if right_stats["count"] >= 7:
                overall_right.extend([safe_float(v) for v in right_timings if safe_float(v) is not None])
                overall_headline_right.extend(
                    command_sample_field_values_ms(right.get("commandSamples", []), "elapsedMs")
                )

        left_trace_meta_hashes = collect_trace_meta_hashes(left.get("commandSamples", []))
        right_trace_meta_hashes = collect_trace_meta_hashes(right.get("commandSamples", []))
        claim_row_context = build_claim_row_context(
            workload=workload,
            report=report,
            left_trace_meta_hashes=left_trace_meta_hashes,
            right_trace_meta_hashes=right_trace_meta_hashes,
            delta=delta,
            comparability=comparability,
            claimability=claimability,
        )
        claim_row_hash = json_sha256(
            {
                "previousHash": previous_claim_row_hash,
                "context": claim_row_context,
            }
        )
        operator_diff = summarize_operator_diff(left, right)

        report["workloads"].append(
            build_workload_report_entry(
                workload=workload,
                left=left,
                right=right,
                delta=delta,
                timing_interpretation=timing_interpretation,
                comparability=comparability,
                claimability=claimability,
                left_trace_meta_hashes=left_trace_meta_hashes,
                right_trace_meta_hashes=right_trace_meta_hashes,
                claim_row_hash=claim_row_hash,
                previous_claim_row_hash=previous_claim_row_hash,
                claim_row_context=claim_row_context,
                operator_diff=operator_diff,
            )
        )
        claim_row_hashes.append(claim_row_hash)
        previous_claim_row_hash = claim_row_hash
        if args.workload_cooldown_ms > 0 and idx < len(workloads):
            time.sleep(args.workload_cooldown_ms / 1000.0)

    build_overall_stats(
        overall_left=overall_left,
        overall_right=overall_right,
        overall_headline_left=overall_headline_left,
        overall_headline_right=overall_headline_right,
        report=report,
    )
    build_report_summaries(
        report=report,
        workloads=workloads,
        comparability_failures=comparability_failures,
        claimability_failures=claimability_failures,
        claim_row_hashes=claim_row_hashes,
        claimability_mode=args.claimability,
    )
    return write_report_and_determine_status(
        report=report,
        out=out,
        workspace=workspace,
        args=args,
        comparability_failures=comparability_failures,
        claimability_failures=claimability_failures,
        workload_count=len(workloads),
    )


if __name__ == "__main__":
    raise SystemExit(main())
