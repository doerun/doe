#!/usr/bin/env cs_python
"""SdkLayout streaming-executor skeleton — iteration 1.

Consumes a doe_stream_graph + doe_stream_execution_plan and drives the
Cerebras SDK's SdkLayout API to materialize a compiled layout, then the
SdkRuntime to execute it. Emits a doe_streaming_executor_trace artifact
mirroring the dry-run trace schema, so diff_dry_run_traces.py can compare
predicted vs observed without methodology arguments.

Iteration 1 scope (this turn):
  - Single code region (the transformer_layer_shape region that both
    E2B and 31B emit today).
  - Wire one compute-ready code region from a CSL source file loaded at
    the region's PE-range dimensions.
  - Compile via SdkLayout.compile(out_prefix).
  - Launch compute via SdkRuntime at the compiled grid, memcpy in a
    seed input, launch, memcpy out, and record wall clock timings.
  - Emit a trace artifact with `{executedCompile, executedRun,
    observedBytesTransferredPerPe, observedWallClockMs}`.

Not done this turn (deferred):
  - Multi-region layouts (SdkLayout.connect, hstack, vstack).
  - Async DSD prefetch with explicit ring buffers.
  - Compile-artifact cache lookup via SdkCompileArtifacts.add_port_mapping.
  - KV spill / on_demand residency behavior.

Those live in subsequent iterations. The schema for the trace artifact
is forward-compatible — adding observed fields later is a pure extension.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from cerebras.sdk.runtime.sdkruntimepybind import (  # pylint: disable=no-name-in-module
    SdkLayout,
    SdkRuntime,
    SdkTarget,
    MemcpyDataType,
    MemcpyOrder,
    WSE3,
    get_platform,
    get_simulator,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--stream-graph", required=True)
    p.add_argument("--execution-plan", required=True)
    p.add_argument(
        "--kernel-source",
        required=True,
        help="Path to the CSL source (layout.csl or pe_program.csl) that this executor compiles.",
    )
    p.add_argument(
        "--region-name",
        default="transformer_layer_shape",
        help="Which codeRegion.regionId to instantiate.",
    )
    p.add_argument(
        "--compile-out",
        default="bench/out/streaming-executor/iter1",
    )
    p.add_argument(
        "--trace-out",
        default="bench/out/streaming-executor/iter1-trace.json",
    )
    p.add_argument("--cmaddr", default="")
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    if p.is_absolute():
        return p
    return Path(__file__).resolve().parents[3] / p


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def find_region(graph: dict, region_id: str) -> dict[str, Any]:
    for region in graph.get("codeRegions", []):
        if region.get("regionId") == region_id:
            return region
    raise KeyError(f"codeRegion {region_id!r} not found in stream-graph")


def dim_from_pe_range(region: dict) -> tuple[int, int]:
    """Derive (width, height) from peRange. Assumes a square grid for now;
    the stream-graph schema only has a 1-D peRange today, so we factor it
    into the squarest rectangle that fits. Multi-region 2D layouts land in
    a later iteration when the graph schema gains explicit width/height.
    """
    pe_range = region.get("peRange", {})
    pe_count = int(pe_range.get("end", 0)) - int(pe_range.get("start", 0))
    if pe_count <= 0:
        raise ValueError(f"codeRegion {region.get('regionId')!r}: empty peRange")
    # For the first executable iteration, use a 4x1 grid regardless of the
    # declared peRange. The stream-graph's peRange spans the whole model
    # (17k or 58k PEs) but the runnable compile size today is governed by
    # the cslc memcpy-module constraints; we scope the iter-1 executor to
    # a small verifiable grid.
    return 4, 1


def main() -> int:
    args = parse_args()
    graph_path = resolve(args.stream_graph)
    plan_path = resolve(args.execution_plan)
    kernel_source_path = resolve(args.kernel_source)
    graph = load_json(graph_path)
    plan = load_json(plan_path)

    region = find_region(graph, args.region_name)
    width, height = dim_from_pe_range(region)

    source_text = kernel_source_path.read_text(encoding="utf-8")

    compile_out = resolve(args.compile_out)
    compile_out.mkdir(parents=True, exist_ok=True)

    # --- SdkLayout compile phase ---------------------------------------
    compile_start = time.time()
    platform = get_simulator() if not args.cmaddr.strip() else get_platform(args.cmaddr.strip())
    target = SdkTarget(WSE3)
    layout = SdkLayout(target, platform)
    code_region = layout.create_code_region(
        source_text, args.region_name, width, height
    )
    compile_prefix = str(compile_out / args.region_name)
    compiled = layout.compile(compile_prefix, False)
    compile_elapsed_ms = (time.time() - compile_start) * 1000.0

    # --- SdkRuntime execute phase --------------------------------------
    # Treat the compiled output as the kernel. Provide a deterministic
    # seed and verify the kernel runs end-to-end. Iteration 1: single
    # compute call; no streaming, no prefetch.
    run_start = time.time()
    runner = SdkRuntime(compile_prefix, cmaddr=args.cmaddr.strip() or None)
    runner.load()
    runner.run()
    # Best-effort: this iteration assumes the code region exports 'input'
    # and 'output' f32 symbols and a 'compute' entry, matching the
    # elementwise-double fixture shape. A future iteration will read the
    # symbols from the compile artifact's exported_symbols list.
    chunk_size = 1024
    total = width * chunk_size
    input_host = (np.arange(total, dtype=np.float32) + 0.5)
    expected = input_host * 2.0
    output_host = np.zeros(total, dtype=np.float32)
    try:
        input_id = runner.get_id("input")
        output_id = runner.get_id("output")
        runner.memcpy_h2d(input_id, input_host, 0, 0, width, height, chunk_size,
            streaming=False, order=MemcpyOrder.ROW_MAJOR,
            data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
        runner.launch("compute", nonblock=False)
        runner.memcpy_d2h(output_host, output_id, 0, 0, width, height, chunk_size,
            streaming=False, order=MemcpyOrder.ROW_MAJOR,
            data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
        max_abs_err = float(np.max(np.abs(output_host - expected)))
        run_status = "succeeded"
    except Exception as exc:  # pylint: disable=broad-except
        max_abs_err = float("nan")
        run_status = f"failed:{type(exc).__name__}:{exc}"
    runner.stop()
    run_elapsed_ms = (time.time() - run_start) * 1000.0

    observed_bytes = total * 4 * 2  # input h2d + output d2h, f32 = 4 bytes

    trace = {
        "schemaVersion": 1,
        "artifactKind": "doe_streaming_executor_trace",
        "target": "wse3",
        "modelId": graph.get("modelId", ""),
        "executorIteration": 1,
        "sourcePlan": {
            "streamGraphPath": str(graph_path.relative_to(resolve("."))),
            "executionPlanPath": str(plan_path.relative_to(resolve("."))),
            "kernelSourcePath": str(kernel_source_path.relative_to(resolve("."))),
        },
        "region": {
            "regionId": args.region_name,
            "width": width,
            "height": height,
            "peCount": width * height,
        },
        "executedCompile": {
            "compilePrefix": str(Path(compile_prefix).relative_to(resolve("."))),
            "elapsedMs": compile_elapsed_ms,
            "status": "succeeded",
        },
        "executedRun": {
            "status": run_status,
            "elapsedMs": run_elapsed_ms,
            "observedBytesTransferredPerPe": observed_bytes // max(width * height, 1),
            "observedBytesTransferredTotal": observed_bytes,
            "numericalParity": {
                "maxAbsErr": max_abs_err,
                "atol": 1e-6,
                "passed": max_abs_err == 0.0 if run_status == "succeeded" else False,
            },
        },
        "notes": (
            "Iteration 1 — single-region SdkLayout compile + SdkRuntime execute. "
            "Does not yet exercise streams, prefetch, compile-artifact cache, or "
            "KV spill. Future iterations extend this skeleton."
        ),
    }

    trace_path = resolve(args.trace_out)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    print(f"executor iter-1: compile {compile_elapsed_ms:.1f} ms, "
          f"run {run_elapsed_ms:.1f} ms, run_status={run_status!r}, "
          f"max_abs_err={max_abs_err} → {trace_path}")
    return 0 if run_status == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
