"""Config-backed compare runner over isolated run artifacts."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Sequence

from bench.lib import output_paths
from native_compare_modules import artifact_benchmarking as artifact_benchmarking_mod
from native_compare_modules import comparability as comparability_mod
from native_compare_modules import compare_from_artifacts as compare_from_artifacts_mod
from native_compare_modules import config_support as config_support_mod
from native_compare_modules import executor_registry as executor_registry_mod
from native_compare_modules import report_assembly as report_assembly_mod
from native_compare_modules import runner as runner_mod
from native_compare_modules import workload_validation as workload_validation_mod


CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "workloads"
    / "metadata"
    / "backend-workload-catalog.json"
)


def main(argv: Sequence[str] | None = None) -> int:
    args = config_support_mod.parse_args(argv)
    args = config_support_mod.apply_config_defaults(args)
    if getattr(args, "baseline_executor_id", ""):
        args.baseline_command_template = executor_registry_mod.resolve_executor_command_template(
            args.baseline_executor_id
        )
    if getattr(args, "comparison_executor_id", ""):
        args.comparison_command_template = executor_registry_mod.resolve_executor_command_template(
            args.comparison_executor_id
        )

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
    if not args.comparison_command_template:
        raise ValueError(
            "missing comparison command template: pass "
            "--comparison-command-template or --config with "
            "comparison.commandTemplate"
        )
    if (
        args.workload_cohort in {"comparability-candidates", "doe-advantage"}
        and (not args.include_noncomparable_workloads)
    ):
        raise ValueError(
            f"workload cohort {args.workload_cohort} requires "
            "--include-noncomparable-workloads (or "
            "run.includeNoncomparableWorkloads=true)"
        )

    benchmark_policy = config_support_mod.load_benchmark_methodology_policy(
        args.benchmark_policy
    )
    workloads_path = Path(args.workloads)
    if CATALOG_PATH.exists() and workloads_path.exists():
        catalog_mtime = os.path.getmtime(CATALOG_PATH)
        workloads_mtime = os.path.getmtime(workloads_path)
        if catalog_mtime > workloads_mtime:
            print(
                f"WARNING: {workloads_path.name} may be stale — "
                "workloads/metadata/backend-workload-catalog.json was modified "
                "more recently. Run: python3 "
                "bench/tools/generate_backend_workloads.py",
                file=sys.stderr,
            )

    workloads = config_support_mod.load_workloads(
        workloads_path,
        args.workload_filter,
        include_noncomparable=bool(args.include_noncomparable_workloads),
        include_extended=bool(args.include_extended_workloads),
        workload_cohort=args.workload_cohort,
        selector=getattr(args, "selector", None),
    )
    if not workloads:
        hint = ""
        if (
            not args.include_noncomparable_workloads
            or not args.include_extended_workloads
        ):
            hint = (
                " (selected workloads may be filtered by "
                "selector/cohort/benchmarkClass or by legacy "
                "comparable=false/default=false behavior)"
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

    workload_validation_mod.enforce_host_backend_policy(
        workloads=workloads,
        baseline_command_template=args.baseline_command_template,
        comparison_command_template=args.comparison_command_template,
    )
    workload_validation_mod.enforce_strict_plan_boundary_symmetry(
        workloads=workloads,
        baseline_command_template=args.baseline_command_template,
        comparison_command_template=args.comparison_command_template,
        comparability_mode=args.comparability,
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
    workload_validation_mod.enforce_strict_doe_runtime_normalization_symmetry(
        workloads=workloads,
        baseline_command_template=args.baseline_command_template,
        comparison_command_template=args.comparison_command_template,
        comparability_mode=args.comparability,
    )
    workload_validation_mod.enforce_strict_dawn_vs_doe_direct_operation_timing(
        workloads=workloads,
        baseline_command_template=args.baseline_command_template,
        comparison_command_template=args.comparison_command_template,
        comparability_mode=args.comparability,
        required_timing_class=args.require_timing_class,
    )
    workload_validation_mod.enforce_strict_command_shape_divisor_contracts(
        workloads=workloads,
        comparability_mode=args.comparability,
        required_timing_class=args.require_timing_class,
        comparison_command_template=args.comparison_command_template,
    )

    if (
        not args.emit_shell
        and args.comparability == "strict"
        and args.require_timing_class == "operation"
    ):
        strict_upload_workload = next(
            (
                workload
                for workload in workloads
                if comparability_mod.is_dawn_writebuffer_upload_workload(workload)
            ),
            None,
        )
        if strict_upload_workload is not None:
            comparability_mod.verify_fawn_upload_runtime_contract(
                template=args.baseline_command_template,
                workload=strict_upload_workload,
                command_for_fn=runner_mod.command_for,
                runtime_source_paths=config_support_mod.FAWN_UPLOAD_RUNTIME_SOURCE_PATHS,
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
    for workload in workloads:
        if getattr(workload, "runner_type", "zig-runtime") == "compilation":
            continue
        comparability_mod.validate_upload_apples_to_apples(
            workload,
            comparability_mode=args.comparability,
        )

    timestamp = output_timestamp or str(int(time.time()))
    baseline_artifact_paths = artifact_benchmarking_mod.run_product_bundle(
        product=args.baseline_name,
        display_name=args.baseline_name,
        executor_id=getattr(args, "baseline_executor_id", "") or args.baseline_name,
        template=args.baseline_command_template,
        workloads=workloads,
        iterations=args.iterations,
        warmup=args.warmup,
        workspace=workspace,
        workload_contract_path=workloads_path,
        gpu_memory_probe=args.resource_probe,
        resource_sample_ms=args.resource_sample_ms,
        resource_sample_target_count=args.resource_sample_target_count,
        required_timing_class=args.require_timing_class,
        comparability_mode=args.comparability,
        benchmark_policy=benchmark_policy,
        benchmark_policy_path=args.benchmark_policy,
        workload_cooldown_ms=args.workload_cooldown_ms,
        emit_shell=args.emit_shell,
        timestamp=timestamp,
        doe_compilation_bin=getattr(
            args,
            "doe_compilation_bin",
            "runtime/zig/zig-out/bin/doe-compilation-bench",
        ),
        tint_bin=getattr(
            args,
            "tint_bin",
            "bench/vendor/dawn/out/Release/tint",
        ),
        run_role="baseline",
    )
    comparison_artifact_paths = artifact_benchmarking_mod.run_product_bundle(
        product=args.comparison_name,
        display_name=args.comparison_name,
        executor_id=getattr(args, "comparison_executor_id", "") or args.comparison_name,
        template=args.comparison_command_template,
        workloads=workloads,
        iterations=args.iterations,
        warmup=args.warmup,
        workspace=workspace,
        workload_contract_path=workloads_path,
        gpu_memory_probe=args.resource_probe,
        resource_sample_ms=args.resource_sample_ms,
        resource_sample_target_count=args.resource_sample_target_count,
        required_timing_class=args.require_timing_class,
        comparability_mode=args.comparability,
        benchmark_policy=benchmark_policy,
        benchmark_policy_path=args.benchmark_policy,
        workload_cooldown_ms=args.workload_cooldown_ms,
        emit_shell=args.emit_shell,
        timestamp=timestamp,
        doe_compilation_bin=getattr(
            args,
            "doe_compilation_bin",
            "runtime/zig/zig-out/bin/doe-compilation-bench",
        ),
        tint_bin=getattr(
            args,
            "tint_bin",
            "bench/vendor/dawn/out/Release/tint",
        ),
        run_role="comparison",
    )

    run_artifact_paths = [str(path) for path in baseline_artifact_paths + comparison_artifact_paths]
    artifacts = [
        compare_from_artifacts_mod.load_run_artifact(path)
        for path in run_artifact_paths
    ]
    report, comparability_failures, claimability_failures = (
        compare_from_artifacts_mod.build_legacy_compare_report_from_artifacts(
            args=args,
            artifacts=artifacts,
            baseline_product=args.baseline_name,
            comparison_product=args.comparison_name,
            benchmark_policy=benchmark_policy,
            output_timestamp=output_timestamp,
            out=out,
            workspace=workspace,
            run_artifact_paths=run_artifact_paths,
            workloads=workloads,
        )
    )
    return report_assembly_mod.write_report_and_determine_status(
        report=report,
        out=out,
        workspace=workspace,
        args=args,
        comparability_failures=comparability_failures,
        claimability_failures=claimability_failures,
        workload_count=len(report.get("workloads", [])),
    )
