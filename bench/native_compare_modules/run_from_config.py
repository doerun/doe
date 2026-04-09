"""Thin config expansion for run-receipt generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from native_compare_modules import artifact_benchmarking as artifact_benchmarking_mod


def run_product_from_prepared_args(
    *,
    product: str,
    executor_id: str,
    display_name: str,
    template: str,
    workloads: list[Any],
    args: Any,
    workspace: Path,
    workloads_path: Path,
    benchmark_policy: Any,
    timestamp: str,
    run_role: str,
) -> list[Path]:
    """Expand prepared config values into one product run."""
    return artifact_benchmarking_mod.run_product_bundle(
        product=product,
        display_name=display_name,
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
        run_role=run_role,
    )
