#!/usr/bin/env python3
"""Dawn benchmark adapter for compare_dawn_vs_doe.py.

This script maps a fawn workload id to a GoogleTest filter for `dawn_perf_tests`
and runs the selected test while keeping a minimal JSONL trace and compact meta
artifact for the compare pipeline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import statistics
import subprocess
import time
from pathlib import Path

RESULT_METRIC_RE = re.compile(
    r"\*RESULT\s+[^\n]*?\.(wall_time|cpu_time|gpu_time):\s+[^\n]*?=\s*([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)\s*(ns|us|ms|s)\b"
)
RUNNING_TESTS_RE = re.compile(
    r"\[=+\]\s+Running\s+([0-9]+)\s+tests?\s+from\s+[0-9]+\s+test suites?\."
)
FILTER_NO_MATCH_RE = re.compile(
    r'WARNING:\s+filter\s+".*?"\s+did not match any test;\s+no tests were run'
)
SKIPPED_SUMMARY_RE = re.compile(r"\[\s*SKIPPED\s*\]\s+([0-9]+)\s+tests?")
TEST_UNSUPPORTED_RE = re.compile(r"Info:\s+Test unsupported:", re.IGNORECASE)
ADAPTER_HEADER_RE = re.compile(r'^\s*-\s+"(?P<name>[^"]+)"\s+-\s+"(?P<driver>.+)"\s*$')
ADAPTER_FIELD_RE = re.compile(r'^\s*(?P<key>\w+):\s*(?P<value>.+?)\s*$')
INCOMPATIBLE_DRIVER_RE = re.compile(r"Could not open device (?P<device>/dev/dri/[^:]+): Permission denied")
AUTO_DISCOVER_TOKEN = "@autodiscover"
AUTODISCOVER_WORKLOAD_PATTERNS: dict[str, tuple[str, str | None]] = {
    "upload_write_buffer_1kb": ("BufferUploadPerf", "WriteBuffer_BufferSize_1KB"),
    "upload_write_buffer_64kb": ("BufferUploadPerf", "WriteBuffer_BufferSize_64KB"),
    "upload_write_buffer_1mb": ("BufferUploadPerf", "WriteBuffer_BufferSize_1MB"),
    "upload_write_buffer_4mb": ("BufferUploadPerf", "WriteBuffer_BufferSize_4MB"),
    "upload_write_buffer_16mb": ("BufferUploadPerf", "WriteBuffer_BufferSize_16MB"),
    "upload_write_buffer_256mb": ("BufferUploadPerf", "WriteBuffer_BufferSize_256MB"),
    "upload_write_buffer_1gb": ("BufferUploadPerf", "WriteBuffer_BufferSize_1GB"),
    "upload_write_buffer_4gb": ("BufferUploadPerf", "WriteBuffer_BufferSize_4GB"),
    "compute_workgroup_atomic_1024": ("WorkgroupAtomicPerf", "WorkgroupTypeAtomic"),
    "compute_workgroup_non_atomic_1024": ("WorkgroupAtomicPerf", "WorkgroupTypeNonAtomic"),
    "compute_matvec_32768x2048_f32": (
        "MatrixVectorMultiplyPerf",
        "Rows_32768_Cols_2048_StoreType_F32_AccType_F32_Impl_Naive_Swizzle_0",
    ),
    "compute_matvec_32768x2048_f32_swizzle1": (
        "MatrixVectorMultiplyPerf",
        "Rows_32768_Cols_2048_StoreType_F32_AccType_F32_Impl_Naive_Swizzle_1",
    ),
    "compute_matvec_32768x2048_f32_workgroupshared_swizzle1": (
        "MatrixVectorMultiplyPerf",
        "Rows_32768_Cols_2048_StoreType_F32_AccType_F32_Impl_WorkgroupShared_Swizzle_1",
    ),
    "pipeline_compile_stress": (
        "ShaderRobustnessPerf",
        "MatMulMethod_MatMulFloatOneDimSharedArray_ElemType_f32",
    ),
    "render_draw_throughput_baseline": ("DrawCallPerf", None),
    "render_draw_state_bindings": ("DrawCallPerf", "DynamicBindGroup"),
    "render_draw_redundant_pipeline_bindings": (
        "DrawCallPerf",
        "RedundantPipeline_RedundantBindGroups",
    ),
    "render_bundle_dynamic_bindings": ("DrawCallPerf", "DynamicBindGroup_RenderBundle"),
    "render_bundle_dynamic_pipeline_bindings": (
        "DrawCallPerf",
        "DynamicPipeline_DynamicBindGroup_RenderBundle",
    ),
    "render_draw_indexed_baseline": ("DrawCallPerf", "DynamicVertexBuffer_DrawIndexed"),
    "texture_sampling_raster_baseline": ("SubresourceTrackingPerf", "arrayLayer_16_mipLevel_3"),
    "texture_sampler_write_query_destroy": (
        "SubresourceTrackingPerf",
        "arrayLayer_16_mipLevel_3",
    ),
    "texture_sampler_write_query_destroy_mip8": (
        "SubresourceTrackingPerf",
        "arrayLayer_16_mipLevel_8",
    ),
    "pipeline_async_diagnostics": (
        "ShaderRobustnessPerf",
        "MatMulMethod_MatMulFloatOneDimSharedArray_ElemType_f32",
    ),
    "capability_introspection": (
        "ShaderRobustnessPerf",
        "MatMulMethod_MatMulFloatOneDimSharedArray_ElemType_f32",
    ),
    "resource_table_immediates": (
        "ShaderRobustnessPerf",
        "MatMulMethod_MatMulFloatOneDimSharedArray_ElemType_f32",
    ),
    "lifecycle_refcount": (
        "ShaderRobustnessPerf",
        "MatMulMethod_MatMulFloatOneDimSharedArray_ElemType_f32",
    ),
    "capability_introspection_500": (
        "ShaderRobustnessPerf",
        "MatMulMethod_MatMulFloatOneDimSharedArray_ElemType_f32",
    ),
    "resource_table_immediates_500": (
        "ShaderRobustnessPerf",
        "MatMulMethod_MatMulFloatOneDimSharedArray_ElemType_f32",
    ),
    "lifecycle_refcount_200": (
        "ShaderRobustnessPerf",
        "MatMulMethod_MatMulFloatOneDimSharedArray_ElemType_f32",
    ),
    "render_draw_throughput_200k": ("DrawCallPerf", None),
    "render_draw_indexed_200k": ("DrawCallPerf", "DynamicVertexBuffer_DrawIndexed"),
    "texture_sampler_write_query_destroy_500": (
        "SubresourceTrackingPerf",
        "arrayLayer_16_mipLevel_3",
    ),
    "resource_lifecycle": ("BufferUploadPerf", "WriteBuffer_BufferSize_4MB"),
    "compute_indirect_timestamp": (
        "WorkgroupAtomicPerf",
        "WorkgroupTypeAtomic",
    ),
    "render_multidraw": ("DrawCallPerf", None),
    "render_multidraw_indexed": ("DrawCallPerf", "DynamicVertexBuffer_DrawIndexed"),
    "render_pixel_local_storage_barrier": (
        "ShaderRobustnessPerf",
        "MatMulMethod_MatMulFloatOneDimSharedArray_ElemType_f32",
    ),
    "render_pixel_local_storage_barrier_500": (
        "ShaderRobustnessPerf",
        "MatMulMethod_MatMulFloatOneDimSharedArray_ElemType_f32",
    ),
    "render_uniform_buffer_update_writebuffer_partial_single": (
        "UniformBufferUpdatePerf",
        "WriteBuffer_PartialSize_SingleUniformBuffer",
    ),
    "compute_zero_initialize_workgroup_memory_256": (
        "VulkanZeroInitializeWorkgroupMemoryExtensionTest",
        "workgroupSize_256",
    ),
    "surface_presentation": (
        "ConcurrentExecutionTest",
        "ConcurrentExecutionType_RunSingle",
    ),
    "compute_concurrent_execution_single": (
        "ConcurrentExecutionTest",
        "ConcurrentExecutionType_RunSingle",
    ),
    "compute_kernel_dispatch_100": ("DrawCallPerf", "__e_skip_validation"),
}
TIME_UNIT_TO_MS = {
    "ns": 1.0 / 1_000_000.0,
    "us": 1.0 / 1_000.0,
    "ms": 1.0,
    "s": 1000.0,
}
REPLAY_SEED = "0x9e3779b97f4a7c15"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dawn-binary", default=None)
    parser.add_argument(
        "--dawn-state",
        default="fawn/bench/dawn_runtime_state.json",
        help="Optional state file emitted by bootstrap_dawn.py.",
    )
    parser.add_argument("--workload", default="")
    parser.add_argument("--dawn-filter", default="")
    parser.add_argument("--dawn-filter-map", default=None)
    parser.add_argument(
        "--dawn-extra-args",
        action="append",
        default=[],
        help=(
            "Extra arguments forwarded to dawn_perf_tests (for example, "
            "--backend=vulkan --adapter-vendor-id=0x1002)."
        ),
    )
    parser.add_argument("--trace-jsonl", default="")
    parser.add_argument("--trace-meta", default="")
    parser.add_argument(
        "--timing-metric",
        choices=("wall_time", "cpu_time", "gpu_time"),
        default="wall_time",
        help="Benchmark metric to use as primary timing (from Dawn *RESULT output).",
    )
    parser.add_argument("--queue-sync-mode", default="none")
    parser.add_argument("--upload-buffer-usage", default="none")
    parser.add_argument("--upload-submit-every", type=int, default=0)
    return parser.parse_args()


def read_mapping(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        return {}
    filters = payload.get("filters")
    if not isinstance(filters, dict):
        return {}
    return {str(k): str(v) for k, v in filters.items() if isinstance(v, str)}


def resolve_filter(
    workload: str,
    explicit: str,
    mapping_path: str,
) -> tuple[str, str]:
    if explicit:
        return explicit, "explicit"
    mapping = read_mapping(Path(mapping_path)) if mapping_path else {}
    if workload in mapping:
        selected = mapping[workload].strip()
        if selected == AUTO_DISCOVER_TOKEN:
            return "", "autodiscover"
        if selected:
            return selected, "mapped"
        return "", "missing"
    return "", "missing"


def resolve_binary(explicit_binary: str | None, state_path: str) -> str:
    if explicit_binary:
        return explicit_binary
    state_file = Path(state_path)
    if state_file.exists():
        try:
            payload = json.loads(state_file.read_text(encoding="utf-8"))
            binaries = payload.get("binaries", {})
            if isinstance(binaries, dict):
                resolved = binaries.get("dawn_perf_tests", "")
                if isinstance(resolved, str) and resolved:
                    return resolved
        except json.JSONDecodeError:
            pass
    return os.environ.get("DAWN_PERF_TEST_BIN", "")


def parse_result_metrics_ms(stdout: str) -> dict[str, list[float]]:
    matches = RESULT_METRIC_RE.findall(stdout)
    metrics: dict[str, list[float]] = {
        "wall_time": [],
        "cpu_time": [],
        "gpu_time": [],
    }
    for metric, value, unit in matches:
        try:
            raw = float(value)
        except ValueError:
            continue
        factor = TIME_UNIT_TO_MS.get(unit)
        if factor is None:
            continue
        samples = metrics.get(metric)
        if samples is None:
            continue
        samples.append(raw * factor)
    return metrics


def parse_running_test_count(stdout: str) -> int | None:
    match = RUNNING_TESTS_RE.search(stdout)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def parse_skipped_test_count(stdout: str) -> int:
    match = SKIPPED_SUMMARY_RE.search(stdout)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def parse_listed_filters(output: str) -> list[str]:
    filters: list[str] = []
    current_suite = ""
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.endswith(".") and not line.startswith("Run/"):
            current_suite = line[:-1]
            continue
        if not current_suite or not line.startswith("Run/"):
            continue
        test_name = line.split("#", 1)[0].strip()
        if not test_name:
            continue
        filters.append(f"{current_suite}.{test_name}")
    return filters


def parse_adapter_requirements(extra_args: list[str]) -> tuple[str | None, str | None]:
    backend = None
    vendor_id = None
    index = 0
    while index < len(extra_args):
        arg = extra_args[index]
        if arg == "--backend" and index + 1 < len(extra_args):
            backend = extra_args[index + 1].strip().lower()
            index += 1
        elif arg.startswith("--backend="):
            backend = arg.split("=", 1)[1].strip().lower()
        elif arg == "--adapter-vendor-id" and index + 1 < len(extra_args):
            vendor_id = extra_args[index + 1].strip().lower()
            index += 1
        elif arg.startswith("--adapter-vendor-id="):
            vendor_id = arg.split("=", 1)[1].strip().lower()
        index += 1
    return backend, vendor_id


def strip_adapter_vendor_id_args(extra_args: list[str]) -> tuple[list[str], bool]:
    stripped: list[str] = []
    removed = False
    index = 0
    while index < len(extra_args):
        arg = extra_args[index]
        if arg == "--adapter-vendor-id":
            removed = True
            index += 2
            continue
        if arg.startswith("--adapter-vendor-id="):
            removed = True
            index += 1
            continue
        stripped.append(arg)
        index += 1
    return stripped, removed


def parse_dawn_adapters(stdout: str) -> list[dict[str, str]]:
    adapters: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in stdout.splitlines():
        header = ADAPTER_HEADER_RE.match(raw_line)
        if header:
            if current is not None:
                adapters.append(current)
            current = {
                "name": header.group("name").strip(),
                "driver": header.group("driver").strip(),
            }
            continue

        field = ADAPTER_FIELD_RE.match(raw_line)
        if field is None or current is None:
            continue
        key = field.group("key").strip()
        value = field.group("value").strip()
        current[key] = value
        if "," in value:
            for segment in value.split(", "):
                nested_field = ADAPTER_FIELD_RE.match(segment)
                if nested_field is None:
                    continue
                current[nested_field.group("key").strip()] = nested_field.group("value").strip()

    if current is not None:
        adapters.append(current)
    return adapters


def find_matching_adapter(
    adapters: list[dict[str, str]],
    backend: str | None,
    vendor_id: str | None,
) -> bool:
    if not backend or not vendor_id:
        return True
    normalized_backend = backend.lower()
    normalized_vendor = vendor_id.lower()
    for adapter in adapters:
        adapter_backend = str(adapter.get("backend", "")).strip().lower()
        adapter_vendor = str(adapter.get("vendorId", "")).split(",")[0].strip().lower()
        if adapter_backend == normalized_backend and adapter_vendor == normalized_vendor:
            return True
    return False


def format_adapter_summary(adapters: list[dict[str, str]]) -> str:
    if not adapters:
        return "  (no adapters reported)"
    lines = []
    for adapter in adapters:
        name = adapter.get("name", "")
        backend = adapter.get("backend", "")
        vendor_id = adapter.get("vendorId", "")
        adapter_type = adapter.get("type", "")
        architecture = adapter.get("architecture", "")
        lines.append(
            f"  - {name} (backend={backend}, vendorId={vendor_id}, type={adapter_type}, architecture={architecture})"
        )
    return "\n".join(lines)


def backend_name_to_gtest_prefix(backend: str | None) -> str:
    if not backend:
        return ""
    normalized = backend.strip().lower()
    mapping = {
        "vulkan": "Vulkan",
        "metal": "Metal",
        "d3d12": "D3D12",
        "opengl": "OpenGL",
        "opengles": "OpenGLES",
        "webgpu": "WebGPU",
        "null": "Null",
    }
    token = mapping.get(normalized, backend)
    return f"Run/{token}_"


def autodiscover_filter(dawn_binary: str, extra_args: list[str], workload: str) -> str:
    pattern = AUTODISCOVER_WORKLOAD_PATTERNS.get(workload)
    if pattern is None:
        raise SystemExit(
            f"Autodiscover requested for workload '{workload}', but no discovery pattern is defined."
        )

    suite, required_fragment = pattern
    requested_backend, requested_vendor_id = parse_adapter_requirements(extra_args)

    def list_filters(list_extra_args: list[str]) -> tuple[list[str], str, list[dict[str, str]]]:
        list_cmd = [dawn_binary, "--gtest_list_tests"]
        list_cmd.extend(list_extra_args)
        listed = subprocess.run(list_cmd, text=True, capture_output=True)
        if listed.returncode != 0:
            raise SystemExit(
                "Autodiscover failed: could not list Dawn tests "
                f"(rc={listed.returncode}) with command: {shlex.join(list_cmd)}"
            )
        combined_output = f"{listed.stdout}\n{listed.stderr}"
        available = parse_listed_filters(combined_output)
        adapters = parse_dawn_adapters(combined_output)
        return available, combined_output, adapters

    available_filters, combined_output, adapters = list_filters(extra_args)
    missing_requested_adapter = (
        requested_vendor_id is not None
        and requested_backend is not None
        and not find_matching_adapter(adapters, requested_backend, requested_vendor_id)
    )
    if missing_requested_adapter:
        message = (
            "Autodiscover failed: requested Dawn adapter is unavailable. "
            f"Requested backend={requested_backend}, vendor-id={requested_vendor_id}.\n"
            "Detected adapters:\n"
            f"{format_adapter_summary(adapters)}"
        )
        if INCOMPATIBLE_DRIVER_RE.search(combined_output):
            message += (
                "\nHint: Vulkan backend reported permission denied opening /dev/dri devices."
            )
        raise SystemExit(message)

    if not available_filters:
        relaxed_args, removed_vendor_constraint = strip_adapter_vendor_id_args(extra_args)
        if removed_vendor_constraint:
            available_filters, _, _ = list_filters(relaxed_args)

    suite_prefix = f"{suite}.Run/"
    candidates = [name for name in available_filters if name.startswith(suite_prefix)]
    if required_fragment:
        candidates = [name for name in candidates if required_fragment in name]
    if not candidates:
        fragment_text = required_fragment if required_fragment is not None else "(none)"
        raise SystemExit(
            f"Autodiscover failed for workload '{workload}': "
            f"no Dawn filter matched suite='{suite}' fragment='{fragment_text}'."
        )

    backend_prefix = backend_name_to_gtest_prefix(requested_backend)

    def score_filter(filter_name: str) -> tuple[int, int]:
        score = 0
        if backend_prefix and f".{backend_prefix}" in filter_name:
            score += 4
        if "SwiftShader" in filter_name:
            score -= 2
        if "llvmpipe" in filter_name:
            score -= 2
        if "Null" in filter_name:
            score -= 2
        if workload == "render_draw_throughput_baseline":
            score -= filter_name.count("__")
        return (score, -len(filter_name))

    candidates.sort(key=score_filter, reverse=True)
    return candidates[0]


def trace_hash(previous_hash: str, payload: str) -> str:
    digest = hashlib.blake2b(f"{previous_hash}|{payload}".encode("utf-8"), digest_size=8).hexdigest()
    return f"0x{digest}"


def build_trace_row(
    *,
    workload: str,
    selected_filter: str,
    command: list[str],
    elapsed_ms: float,
    rc: int,
    timing_source: str,
    timing_class: str,
    timing_ms: float,
) -> dict[str, object]:
    command_text = shlex.join(command)
    payload = "|".join(
        [
            workload,
            selected_filter,
            command_text,
            timing_source,
            f"{timing_ms:.12f}",
            f"{elapsed_ms:.6f}",
            str(rc),
        ]
    )
    row_hash = trace_hash(REPLAY_SEED, payload)
    execution_status = "ok" if rc == 0 else "error"
    return {
        "traceVersion": 1,
        "module": "dawn-perf-tests",
        "opCode": "dispatch",
        "seq": 0,
        "timestampMonoNs": time.monotonic_ns(),
        "hash": row_hash,
        "previousHash": REPLAY_SEED,
        "command": workload or "dawn-perf-tests",
        "executionBackend": "dawn-perf-tests",
        "executionStatus": execution_status,
        "executionStatusMessage": "" if rc == 0 else f"dawn_perf_tests exited with rc={rc}",
        "executionDurationNs": int(round(elapsed_ms * 1_000_000.0)),
    }


def write_meta(
    path: Path,
    *,
    workload: str,
    selected_filter: str,
    command: list[str],
    elapsed_ms: float,
    timing_source: str,
    timing_class: str,
    timing_ms: float,
    selected_timing_metric: str,
    benchmark_metric_samples_ms: dict[str, list[float]],
    benchmark_metric_medians_ms: dict[str, float],
    trace_row: dict[str, object],
    include_trace_row: bool,
    return_code: int,
    running_test_count: int | None,
    filter_no_match: bool,
    skipped_test_count: int,
    test_unsupported: bool,
    filter_resolution: str,
    queue_sync_mode: str,
    upload_buffer_usage: str,
    upload_submit_every: int,
) -> None:
    row_count = 1 if include_trace_row else 0
    seq_max = int(trace_row.get("seq", 0)) if include_trace_row else 0
    final_hash = str(trace_row.get("hash", REPLAY_SEED)) if include_trace_row else REPLAY_SEED
    previous_hash = str(trace_row.get("previousHash", REPLAY_SEED)) if include_trace_row else REPLAY_SEED
    payload = {
        "traceVersion": 1,
        "module": "dawn-perf-tests",
        "schema": "adapter-meta",
        "seqMax": seq_max,
        "rowCount": row_count,
        "hash": final_hash,
        "previousHash": previous_hash,
        "commandCount": row_count,
        "workload": workload,
        "gtestFilter": selected_filter,
        "selectedFilter": selected_filter,
        "filterResolution": filter_resolution,
        "command": shlex.join(command),
        "queueSyncMode": queue_sync_mode,
        "uploadBufferUsage": upload_buffer_usage,
        "uploadSubmitEvery": upload_submit_every,
        "timingSource": timing_source,
        "timingClass": timing_class,
        "timingMs": timing_ms,
        "timingMetric": selected_timing_metric,
        "elapsedMs": elapsed_ms,
        "processWallMs": elapsed_ms,
        "dawnTimingMetricRequested": selected_timing_metric,
        "dawnMetricMediansMs": benchmark_metric_medians_ms,
        "executionBackend": "dawn-perf-tests",
        "executionRowCount": row_count,
        "executionSuccessCount": row_count if return_code == 0 else 0,
        "executionErrorCount": row_count if return_code != 0 else 0,
        "executionTotalNs": int(round(timing_ms * 1_000_000.0)),
        "gtestFilterNoMatch": filter_no_match,
        "gtestSkippedCount": skipped_test_count,
        "gtestUnsupported": test_unsupported,
    }
    if running_test_count is not None:
        payload["gtestRunningCount"] = running_test_count
    if benchmark_metric_samples_ms:
        payload["dawnMetricSamplesMs"] = benchmark_metric_samples_ms
        wall_samples = benchmark_metric_samples_ms.get("wall_time", [])
        if wall_samples:
            payload["benchmarkWallMsSamples"] = wall_samples
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_trace(
    path: Path,
    row: dict[str, object],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    selected_filter, filter_resolution = resolve_filter(
        args.workload,
        args.dawn_filter,
        args.dawn_filter_map or "",
    )
    dawn_binary = resolve_binary(args.dawn_binary, args.dawn_state)
    if not dawn_binary:
        raise SystemExit(
            "DAWN benchmark binary not provided. Use --dawn-binary, --dawn-state, or set DAWN_PERF_TEST_BIN."
        )
    if not Path(dawn_binary).exists():
        raise SystemExit(f"Dawn benchmark binary does not exist: {dawn_binary}")
    if filter_resolution == "missing":
        raise SystemExit(
            "No Dawn gtest filter resolved for this workload. "
            "Provide --dawn-filter, add a mapping entry, or set that workload's map value to @autodiscover."
        )
    if filter_resolution == "autodiscover":
        if not args.dawn_filter_map:
            raise SystemExit(
                "Autodiscover is only allowed from an explicit filter map config. "
                "Pass --dawn-filter-map and set the workload/default filter value to @autodiscover."
            )
        selected_filter = autodiscover_filter(dawn_binary, args.dawn_extra_args, args.workload)

    cmd = [dawn_binary, f"--gtest_filter={selected_filter}"]
    cmd.extend(args.dawn_extra_args)
    trace_jsonl = Path(args.trace_jsonl)
    trace_meta = Path(args.trace_meta)
    if args.trace_jsonl:
        cmd.append(f"--trace-file={trace_jsonl}")

    start = time.perf_counter()
    proc = subprocess.run(cmd, text=True, capture_output=True)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    combined_output = f"{proc.stdout}\n{proc.stderr}"
    adapters = parse_dawn_adapters(combined_output)
    running_test_count = parse_running_test_count(proc.stdout)
    skipped_test_count = parse_skipped_test_count(proc.stdout)
    test_unsupported = bool(TEST_UNSUPPORTED_RE.search(proc.stdout))
    filter_no_match = bool(FILTER_NO_MATCH_RE.search(proc.stdout))
    requested_backend, requested_vendor_id = parse_adapter_requirements(args.dawn_extra_args)
    missing_requested_adapter = (
        requested_vendor_id is not None
        and requested_backend is not None
        and not find_matching_adapter(adapters, requested_backend, requested_vendor_id)
    )
    permission_denied = bool(INCOMPATIBLE_DRIVER_RE.search(combined_output))
    no_tests_ran = running_test_count == 0 if running_test_count is not None else False
    skipped_tests = skipped_test_count > 0 or test_unsupported
    effective_return_code = proc.returncode
    if effective_return_code == 0 and missing_requested_adapter:
        effective_return_code = 2
    if effective_return_code == 0 and (filter_no_match or no_tests_ran):
        effective_return_code = 2
    if effective_return_code == 0 and skipped_tests:
        effective_return_code = 2

    benchmark_metric_samples_ms = parse_result_metrics_ms(proc.stdout)
    benchmark_metric_medians_ms: dict[str, float] = {}
    for metric_name, metric_samples in benchmark_metric_samples_ms.items():
        if metric_samples:
            benchmark_metric_medians_ms[metric_name] = statistics.median(metric_samples)

    timing_source = "wall-time"
    timing_class = "process-wall"
    timing_ms = elapsed_ms
    selected_metric = args.timing_metric
    selected_metric_samples = benchmark_metric_samples_ms.get(selected_metric, [])
    if selected_metric_samples:
        timing_source = f"dawn-perf-{selected_metric.replace('_', '-')}"
        timing_class = "operation"
        timing_ms = statistics.median(selected_metric_samples)
    trace_row = build_trace_row(
        workload=args.workload,
        selected_filter=selected_filter,
        command=cmd,
        elapsed_ms=elapsed_ms,
        rc=effective_return_code,
        timing_source=timing_source,
        timing_class=timing_class,
        timing_ms=timing_ms,
    )
    if missing_requested_adapter:
        trace_row["executionStatusMessage"] = (
            f"Requested Dawn adapter not found: backend={requested_backend}, "
            f"vendor-id={requested_vendor_id}"
        )

    if args.trace_jsonl:
        write_trace(trace_jsonl, row=trace_row)
    if args.trace_meta:
        write_meta(
            trace_meta,
            workload=args.workload,
            selected_filter=selected_filter,
            command=cmd,
            elapsed_ms=elapsed_ms,
            timing_source=timing_source,
            timing_class=timing_class,
            timing_ms=timing_ms,
            selected_timing_metric=selected_metric,
            benchmark_metric_samples_ms=benchmark_metric_samples_ms,
            benchmark_metric_medians_ms=benchmark_metric_medians_ms,
            trace_row=trace_row,
            include_trace_row=bool(args.trace_jsonl),
            return_code=effective_return_code,
            running_test_count=running_test_count,
            filter_no_match=filter_no_match,
            skipped_test_count=skipped_test_count,
            test_unsupported=test_unsupported,
            filter_resolution=filter_resolution,
            queue_sync_mode=args.queue_sync_mode,
            upload_buffer_usage=args.upload_buffer_usage,
            upload_submit_every=args.upload_submit_every,
        )

    if effective_return_code != 0:
        print(proc.stdout)
        print(proc.stderr)
        if missing_requested_adapter:
            print(
                "ERROR: Dawn benchmark setup requested an adapter that is not available in this environment."
            )
            print(f"Requested backend: {requested_backend}")
            print(f"Requested vendor-id: {requested_vendor_id}")
            print("Detected adapters:")
            print(format_adapter_summary(adapters))
            if permission_denied:
                print(
                    "Hint: Vulkan backend reported permission denied opening /dev/dri devices."
                )
        elif filter_no_match or no_tests_ran:
            print(
                "ERROR: Dawn gtest filter matched no tests; "
                "benchmark output is not comparable."
            )
        elif skipped_tests:
            print(
                "ERROR: Dawn benchmark test was skipped/unsupported; "
                "benchmark output is not comparable."
            )
            print(f"gtest skipped count: {skipped_test_count}")
            if test_unsupported:
                print("unsupported marker detected: yes")
        return effective_return_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
