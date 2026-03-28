"""Executor-id registry for benchmark runners.

Keeps executor identity explicit in config while preserving command-template
compatibility for the existing compare stack.
"""

from __future__ import annotations

from dataclasses import dataclass


_DOE_RUNTIME_PREFIX = (
    "env DYLD_LIBRARY_PATH=bench/vendor/dawn/out/Release:$DYLD_LIBRARY_PATH "
    "runtime/zig/zig-out/bin/doe-zig-runtime --commands {commands} --quirks {quirks} "
    "--vendor {vendor} --api {api} --family {family} --driver {driver} "
    "--backend native --execute --trace --queue-sync-mode {queue_sync_mode} "
    "--upload-buffer-usage {upload_buffer_usage} --upload-submit-every {upload_submit_every} "
    "--trace-jsonl {trace_jsonl} --trace-meta {trace_meta} --gpu-timestamp-mode auto "
    "--kernel-root bench/kernels {extra_args}"
)

_DOE_PLAN_PREFIX = (
    "env DYLD_LIBRARY_PATH=bench/vendor/dawn/out/Release:$DYLD_LIBRARY_PATH "
    "runtime/zig/zig-out/bin/doe-plan-executor --plan {plan} "
    "--trace-jsonl {trace_jsonl} --trace-meta {trace_meta} --workload {workload} "
    "--vendor {vendor} --api {api} --family {family} --driver {driver} "
    "--queue-sync-mode {queue_sync_mode} --upload-buffer-usage {upload_buffer_usage} "
    "--upload-submit-every {upload_submit_every} --gpu-timestamp-mode auto {extra_args}"
)

_DAWN_DIRECT_PREFIX = (
    "env DYLD_LIBRARY_PATH=bench/vendor/dawn/out/Release:$DYLD_LIBRARY_PATH "
    "runtime/zig/zig-out/bin/dawn-plan-executor --plan {plan} "
    "--trace-jsonl {trace_jsonl} --trace-meta {trace_meta} --workload {workload}"
)


@dataclass(frozen=True)
class ExecutorSpec:
    executor_id: str
    command_template: str
    execution_boundary: str


_REGISTRY: dict[str, ExecutorSpec] = {
    "doe_direct_metal": ExecutorSpec(
        executor_id="doe_direct_metal",
        command_template=_DOE_RUNTIME_PREFIX.replace(
            "--backend native --execute",
            "--backend native --backend-lane metal_doe_comparable --execute",
        ),
        execution_boundary="commands",
    ),
    "doe_direct_vulkan": ExecutorSpec(
        executor_id="doe_direct_vulkan",
        command_template=_DOE_RUNTIME_PREFIX.replace(
            "--backend native --execute",
            "--backend native --backend-lane vulkan_doe_comparable --execute",
        ),
        execution_boundary="commands",
    ),
    "doe_direct_d3d12": ExecutorSpec(
        executor_id="doe_direct_d3d12",
        command_template=_DOE_RUNTIME_PREFIX.replace(
            "--backend native --execute",
            "--backend native --backend-lane d3d12_doe_comparable --execute",
        ),
        execution_boundary="commands",
    ),
    "doe_direct_plan_metal": ExecutorSpec(
        executor_id="doe_direct_plan_metal",
        command_template=_DOE_PLAN_PREFIX + " --backend-lane metal_doe_comparable",
        execution_boundary="plan",
    ),
    "dawn_delegate_metal": ExecutorSpec(
        executor_id="dawn_delegate_metal",
        command_template=_DOE_RUNTIME_PREFIX.replace(
            "--backend native --execute",
            "--backend native --backend-lane metal_dawn_release --execute",
        ),
        execution_boundary="commands",
    ),
    "dawn_delegate_vulkan": ExecutorSpec(
        executor_id="dawn_delegate_vulkan",
        command_template=_DOE_RUNTIME_PREFIX.replace(
            "--backend native --execute",
            "--backend native --backend-lane vulkan_dawn_release --execute",
        ),
        execution_boundary="commands",
    ),
    "dawn_delegate_d3d12": ExecutorSpec(
        executor_id="dawn_delegate_d3d12",
        command_template=_DOE_RUNTIME_PREFIX.replace(
            "--backend native --execute",
            "--backend native --backend-lane d3d12_dawn_release --execute",
        ),
        execution_boundary="commands",
    ),
    "dawn_direct_metal": ExecutorSpec(
        executor_id="dawn_direct_metal",
        command_template=_DAWN_DIRECT_PREFIX,
        execution_boundary="plan",
    ),
    "dawn_node_webgpu": ExecutorSpec(
        executor_id="dawn_node_webgpu",
        command_template=(
            "node bench/executors/run-node-webgpu-plan.js "
            "--provider dawn --plan {plan} --trace-jsonl {trace_jsonl} "
            "--trace-meta {trace_meta} --workload {workload}"
        ),
        execution_boundary="plan",
    ),
    "doe_node_webgpu": ExecutorSpec(
        executor_id="doe_node_webgpu",
        command_template=(
            "node bench/executors/run-node-webgpu-plan.js "
            "--provider doe --plan {plan} --trace-jsonl {trace_jsonl} "
            "--trace-meta {trace_meta} --workload {workload}"
        ),
        execution_boundary="plan",
    ),
    "dawn_node_webgpu_prepared": ExecutorSpec(
        executor_id="dawn_node_webgpu_prepared",
        command_template=(
            "node bench/executors/run-node-webgpu-plan.js "
            "--provider dawn --prepared-session --plan {plan} --trace-jsonl {trace_jsonl} "
            "--trace-meta {trace_meta} --workload {workload}"
        ),
        execution_boundary="plan",
    ),
    "doe_node_webgpu_prepared": ExecutorSpec(
        executor_id="doe_node_webgpu_prepared",
        command_template=(
            "node bench/executors/run-node-webgpu-plan.js "
            "--provider doe --prepared-session --plan {plan} --trace-jsonl {trace_jsonl} "
            "--trace-meta {trace_meta} --workload {workload}"
        ),
        execution_boundary="plan",
    ),
    "bun_webgpu_package": ExecutorSpec(
        executor_id="bun_webgpu_package",
        command_template=(
            "bun bench/executors/run-bun-webgpu-plan.js "
            "--provider bun-webgpu --plan {plan} --trace-jsonl {trace_jsonl} "
            "--trace-meta {trace_meta} --workload {workload}"
        ),
        execution_boundary="plan",
    ),
    "doe_bun_package": ExecutorSpec(
        executor_id="doe_bun_package",
        command_template=(
            "bun bench/executors/run-bun-webgpu-plan.js "
            "--provider doe --plan {plan} --trace-jsonl {trace_jsonl} "
            "--trace-meta {trace_meta} --workload {workload}"
        ),
        execution_boundary="plan",
    ),
    "bun_webgpu_package_prepared": ExecutorSpec(
        executor_id="bun_webgpu_package_prepared",
        command_template=(
            "bun bench/executors/run-bun-webgpu-plan.js "
            "--provider bun-webgpu --prepared-session --plan {plan} --trace-jsonl {trace_jsonl} "
            "--trace-meta {trace_meta} --workload {workload}"
        ),
        execution_boundary="plan",
    ),
    "doe_bun_package_prepared": ExecutorSpec(
        executor_id="doe_bun_package_prepared",
        command_template=(
            "bun bench/executors/run-bun-webgpu-plan.js "
            "--provider doe --prepared-session --plan {plan} --trace-jsonl {trace_jsonl} "
            "--trace-meta {trace_meta} --workload {workload}"
        ),
        execution_boundary="plan",
    ),
}


def resolve_executor_command_template(executor_id: str) -> str:
    normalized = executor_id.strip()
    if not normalized:
        return ""
    try:
        return _REGISTRY[normalized].command_template
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"unknown executor id {executor_id!r}; expected one of [{known}]"
        ) from exc


def resolve_executor_boundary(executor_id: str) -> str:
    normalized = executor_id.strip()
    if not normalized:
        return ""
    try:
        return _REGISTRY[normalized].execution_boundary
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"unknown executor id {executor_id!r}; expected one of [{known}]"
        ) from exc
