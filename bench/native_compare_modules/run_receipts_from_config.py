"""Expand a compare config into explicit one-side run receipts."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from bench.lib import output_paths
from native_compare_modules import artifact_benchmarking as artifact_benchmarking_mod
from native_compare_modules import config_support as config_support_mod
from native_compare_modules import config_support_defaults
from native_compare_modules import executor_registry as executor_registry_mod


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--side",
        required=True,
        choices=("baseline", "comparison"),
        help="Which side of the compare config to execute as standalone run receipts.",
    )
    known_args, remaining = parser.parse_known_args(argv)
    args = config_support_mod.parse_args(remaining)
    args.side = known_args.side
    return args


def _resolve_side_details(args: argparse.Namespace) -> tuple[str, str, str]:
    if args.side == "baseline":
        product = args.baseline_name
        executor_id = getattr(args, "baseline_executor_id", "") or product
        template = getattr(args, "baseline_command_template", "")
        if getattr(args, "baseline_executor_id", ""):
            template = executor_registry_mod.resolve_executor_command_template(
                args.baseline_executor_id
            )
        return product, executor_id, template
    product = args.comparison_name
    executor_id = getattr(args, "comparison_executor_id", "") or product
    template = getattr(args, "comparison_command_template", "")
    if getattr(args, "comparison_executor_id", ""):
        template = executor_registry_mod.resolve_executor_command_template(
            args.comparison_executor_id
        )
    return product, executor_id, template


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    args = config_support_defaults.apply_config_defaults(args)
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
        raise ValueError("no workloads selected for run-config")

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
    timestamp = output_timestamp or output_paths.utc_timestamp_now()
    product, executor_id, template = _resolve_side_details(args)
    written = artifact_benchmarking_mod.run_product_bundle(
        product=product,
        display_name=product,
        executor_id=executor_id,
        template=template,
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
        run_role=args.side,
    )
    for artifact_path in written:
        print(f"  {artifact_path}")
    print(f"\n{len(written)} run artifact(s) written under {workspace}/")
    return 0
