"""Thin config-backed compare flow: run left, run right, compare receipts."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from bench.lib import output_paths
from native_compare_modules import compare_from_artifacts as compare_from_artifacts_mod
from native_compare_modules import config_support as config_support_mod
from native_compare_modules import executor_registry as executor_registry_mod
from native_compare_modules import run_from_config as run_from_config_mod
from native_compare_modules.run_artifact import load_run_artifact


def _load_receipts(paths: list[Path]) -> list[dict]:
    receipts: list[dict] = []
    for path in paths:
        receipt = load_run_artifact(path)
        receipt["_receiptPath"] = str(path)
        receipts.append(receipt)
    return receipts


def _group_receipts_by_workload(paths: list[Path]) -> dict[str, dict[str, dict]]:
    return compare_from_artifacts_mod.group_run_artifacts_by_workload(
        _load_receipts(paths)
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = config_support_mod.parse_args(argv)
    args = config_support_mod.apply_config_defaults(args)
    if getattr(args, "baseline_executor_id", ""):
        args.baseline_command_template = (
            executor_registry_mod.resolve_executor_command_template(
                args.baseline_executor_id
            )
        )
    if getattr(args, "comparison_executor_id", ""):
        args.comparison_command_template = (
            executor_registry_mod.resolve_executor_command_template(
                args.comparison_executor_id
            )
        )
    if not args.comparison_command_template:
        raise ValueError(
            "missing comparison command template: pass "
            "--comparison-command-template or --config with "
            "comparison.commandTemplate"
        )

    benchmark_policy = config_support_mod.load_benchmark_methodology_policy(
        args.benchmark_policy
    )
    workloads_path = Path(args.workloads)
    workloads = config_support_mod.load_workloads(
        workloads_path,
        args.workload_filter,
        include_noncomparable=bool(args.include_noncomparable_workloads),
        include_extended=bool(args.include_extended_workloads),
        workload_cohort=args.workload_cohort,
        selector=getattr(args, "selector", None),
    )
    if not workloads:
        raise ValueError("no workloads selected for compare config")

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
    timestamp = output_timestamp or output_paths.utc_timestamp_now()

    baseline_paths = run_from_config_mod.run_product_from_prepared_args(
        product=args.baseline_name,
        executor_id=getattr(args, "baseline_executor_id", "") or args.baseline_name,
        display_name=args.baseline_name,
        template=args.baseline_command_template,
        workloads=workloads,
        args=args,
        workspace=workspace,
        workloads_path=workloads_path,
        benchmark_policy=benchmark_policy,
        timestamp=timestamp,
        run_role="baseline",
    )
    comparison_paths = run_from_config_mod.run_product_from_prepared_args(
        product=args.comparison_name,
        executor_id=(
            getattr(args, "comparison_executor_id", "") or args.comparison_name
        ),
        display_name=args.comparison_name,
        template=args.comparison_command_template,
        workloads=workloads,
        args=args,
        workspace=workspace,
        workloads_path=workloads_path,
        benchmark_policy=benchmark_policy,
        timestamp=timestamp,
        run_role="comparison",
    )

    receipt_paths = baseline_paths + comparison_paths
    grouped = _group_receipts_by_workload(receipt_paths)
    entries: list[dict] = []
    for workload in workloads:
        workload_group = grouped.get(workload.id, {})
        baseline_receipt = workload_group.get(args.baseline_name)
        comparison_receipt = workload_group.get(args.comparison_name)
        if baseline_receipt is None or comparison_receipt is None:
            raise ValueError(
                f"missing receipts for workload {workload.id!r}: "
                f"baseline={baseline_receipt is not None} "
                f"comparison={comparison_receipt is not None}"
            )
        entries.append(
            compare_from_artifacts_mod.compare_workload_from_artifacts(
                baseline=baseline_receipt,
                comparison=comparison_receipt,
                comparability_mode=args.comparability,
                required_timing_class=args.require_timing_class,
                resource_probe=args.resource_probe,
                resource_sample_target_count=args.resource_sample_target_count,
                primary_metric="measured_ms",
            )
        )

    baseline_receipts = _load_receipts(baseline_paths)
    comparison_receipts = _load_receipts(comparison_paths)
    report = compare_from_artifacts_mod.build_compare_report(
        workload_entries=entries,
        baseline_artifact=baseline_receipts[0],
        comparison_artifact=comparison_receipts[0],
        comparability_mode=args.comparability,
        required_timing_class=args.require_timing_class,
        primary_metric="measured_ms",
        out_path=str(out),
        run_artifact_paths=[str(path) for path in receipt_paths],
    )
    compare_from_artifacts_mod.write_compare_report(report, out)
    print(f"Compare report: {out}")
    return 0
