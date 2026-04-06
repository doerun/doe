"""Artifact-first benchmark execution helpers."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from bench.lib import output_paths
from native_compare_modules.compilation_runner import (
    run_compilation_product_workload,
)
from native_compare_modules.run_artifact import (
    artifact_filename,
    build_run_artifact,
    write_run_artifact,
)
from native_compare_modules.runner import run_workload


def run_product_bundle(
    *,
    product: str,
    display_name: str,
    executor_id: str,
    template: str,
    workloads: list[Any],
    iterations: int,
    warmup: int,
    workspace: Path,
    workload_contract_path: Path,
    gpu_memory_probe: str,
    resource_sample_ms: int,
    resource_sample_target_count: int,
    required_timing_class: str,
    comparability_mode: str,
    benchmark_policy: Any,
    benchmark_policy_path: str | Path | None,
    workload_cooldown_ms: int,
    emit_shell: bool,
    timestamp: str,
    command_repeat_override: int = 0,
    ignore_first_ops_override: int = 0,
    timing_divisor_override: float = 0.0,
    upload_buffer_usage_override: str = "",
    upload_submit_every_override: int = 0,
    doe_compilation_bin: str = "runtime/zig/zig-out/bin/doe-compilation-bench",
    tint_bin: str = "bench/vendor/dawn/out/Release/tint",
    run_role: str = "auto",
) -> list[Path]:
    """Run one product across a workload set and emit immutable run artifacts."""
    artifact_dir = workspace / "run-artifacts" / product
    artifact_paths: list[Path] = []
    for index, workload in enumerate(workloads, 1):
        print(
            f"[run {product} {index}/{len(workloads)}] workload: {workload.id}...",
            file=sys.stderr,
            flush=True,
        )
        if run_role == "baseline":
            spec, configs = workload.to_spec_and_configs(
                baseline_product=product,
                comparison_product=f"{product}__comparison",
            )
        elif run_role == "comparison":
            spec, configs = workload.to_spec_and_configs(
                baseline_product=f"{product}__baseline",
                comparison_product=product,
            )
        elif run_role == "auto":
            if product == "doe":
                spec, configs = workload.to_spec_and_configs(
                    baseline_product=product,
                    comparison_product=f"{product}__comparison",
                )
            else:
                spec, configs = workload.to_spec_and_configs(
                    baseline_product=f"{product}__baseline",
                    comparison_product=product,
                )
        else:
            raise ValueError(
                "run_product_bundle requires run_role to be one of "
                f"['auto', 'baseline', 'comparison'], got {run_role!r}"
            )
        run_config = configs[product]
        if command_repeat_override > 0:
            run_config = run_config.__class__(
                product=run_config.product,
                command_repeat=command_repeat_override,
                ignore_first_ops=run_config.ignore_first_ops,
                upload_buffer_usage=run_config.upload_buffer_usage,
                upload_submit_every=run_config.upload_submit_every,
                timing_divisor=run_config.timing_divisor,
                allow_no_execution=run_config.allow_no_execution,
                dawn_filter=run_config.dawn_filter,
                timing_normalization_note=run_config.timing_normalization_note,
            )
        if ignore_first_ops_override > 0:
            run_config = run_config.__class__(
                product=run_config.product,
                command_repeat=run_config.command_repeat,
                ignore_first_ops=ignore_first_ops_override,
                upload_buffer_usage=run_config.upload_buffer_usage,
                upload_submit_every=run_config.upload_submit_every,
                timing_divisor=run_config.timing_divisor,
                allow_no_execution=run_config.allow_no_execution,
                dawn_filter=run_config.dawn_filter,
                timing_normalization_note=run_config.timing_normalization_note,
            )
        if timing_divisor_override > 0:
            run_config = run_config.__class__(
                product=run_config.product,
                command_repeat=run_config.command_repeat,
                ignore_first_ops=run_config.ignore_first_ops,
                upload_buffer_usage=run_config.upload_buffer_usage,
                upload_submit_every=run_config.upload_submit_every,
                timing_divisor=timing_divisor_override,
                allow_no_execution=run_config.allow_no_execution,
                dawn_filter=run_config.dawn_filter,
                timing_normalization_note=run_config.timing_normalization_note,
            )
        if upload_buffer_usage_override:
            run_config = run_config.__class__(
                product=run_config.product,
                command_repeat=run_config.command_repeat,
                ignore_first_ops=run_config.ignore_first_ops,
                upload_buffer_usage=upload_buffer_usage_override,
                upload_submit_every=run_config.upload_submit_every,
                timing_divisor=run_config.timing_divisor,
                allow_no_execution=run_config.allow_no_execution,
                dawn_filter=run_config.dawn_filter,
                timing_normalization_note=run_config.timing_normalization_note,
            )
        if upload_submit_every_override > 0:
            run_config = run_config.__class__(
                product=run_config.product,
                command_repeat=run_config.command_repeat,
                ignore_first_ops=run_config.ignore_first_ops,
                upload_buffer_usage=run_config.upload_buffer_usage,
                upload_submit_every=upload_submit_every_override,
                timing_divisor=run_config.timing_divisor,
                allow_no_execution=run_config.allow_no_execution,
                dawn_filter=run_config.dawn_filter,
                timing_normalization_note=run_config.timing_normalization_note,
            )
        workload_dir = workspace / "isolated-runs" / product / workload.id
        if workload.runner_type == "compilation":
            if emit_shell:
                raise ValueError(
                    "artifact-first emit-shell mode does not support "
                    f"compilation workload {workload.id!r}"
                )
            run_result = run_compilation_product_workload(
                product=product,
                workload=workload,
                iterations=iterations,
                warmup=warmup,
                out_dir=workload_dir,
                doe_compilation_bin=doe_compilation_bin,
                tint_bin=tint_bin,
            )
        else:
            run_result = run_workload(
                name=display_name,
                template=template,
                workload=workload,
                iterations=iterations,
                warmup=warmup,
                out_dir=workload_dir,
                gpu_memory_probe=gpu_memory_probe,
                resource_sample_ms=resource_sample_ms,
                resource_sample_target_count=resource_sample_target_count,
                timing_divisor=run_config.timing_divisor,
                command_repeat=run_config.command_repeat,
                ignore_first_ops=run_config.ignore_first_ops,
                upload_buffer_usage=run_config.upload_buffer_usage,
                upload_submit_every=run_config.upload_submit_every,
                inject_upload_runtime_flags="doe-zig-runtime" in template,
                required_timing_class=required_timing_class,
                comparability_mode=comparability_mode,
                benchmark_policy=benchmark_policy,
                emit_shell=emit_shell,
            )
        artifact = build_run_artifact(
            run_result=run_result,
            product=product,
            executor_id=executor_id,
            workload_spec=spec,
            run_config=run_config,
            iterations=iterations,
            warmup=warmup,
            resource_probe=gpu_memory_probe,
            resource_sample_ms=resource_sample_ms,
            resource_sample_target_count=resource_sample_target_count,
            workload_contract_path=workload_contract_path,
            benchmark_policy_path=benchmark_policy_path,
            comparability_mode=comparability_mode,
            required_timing_class=required_timing_class,
        )
        artifact_path = write_run_artifact(
            artifact,
            artifact_dir / artifact_filename(product, workload.id, timestamp),
        )
        artifact_paths.append(artifact_path)
        if workload_cooldown_ms > 0 and index < len(workloads):
            time.sleep(workload_cooldown_ms / 1000.0)

    output_paths.write_run_manifest_for_outputs(
        artifact_paths,
        {
            "runType": "isolated_product_benchmark",
            "product": product,
            "executorId": executor_id,
            "workloadContractPath": str(workload_contract_path),
            "artifactCount": len(artifact_paths),
            "fullRun": not emit_shell,
            "status": "passed",
        },
    )
    return artifact_paths
