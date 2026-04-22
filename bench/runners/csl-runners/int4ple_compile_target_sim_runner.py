#!/usr/bin/env cs_python
"""Diagnostic runtime runner for generated INT4 PLE CSL compile targets.

This is not the final bounded transcript runner. It drives one generated
production compile target through SdkRuntime so timeout/debug evidence moves
past compile-only mode. The trace intentionally keeps full-model transcript
depth false until the HostPlan scheduler emits token/logit/KV artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

import common


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--runtime-config", required=True)
    parser.add_argument("--compile-root", required=True)
    parser.add_argument("--reference-export", required=True)
    parser.add_argument("--trace-out", required=True)
    parser.add_argument("--progress-out", required=True)
    parser.add_argument("--cmaddr", default="")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_progress(path: Path, phase: str, **fields: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestampUnix": time.time(),
        "phase": phase,
        **fields,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def target_by_name(plan: dict[str, Any], name: str) -> dict[str, Any]:
    for target in (plan.get("inputs") or {}).get("compileTargets") or []:
        if isinstance(target, dict) and target.get("name") == name:
            return target
    raise ValueError(f"simulator plan is missing compile target {name!r}")


def int_param(target: dict[str, Any], key: str, default: int) -> int:
    params = target.get("compileParams") or {}
    if isinstance(params, dict) and key in params:
        return int(params[key])
    return default


def source_program(export: dict[str, Any]) -> dict[str, Any]:
    graph = export.get("executionGraph") or {}
    return {
        "authoringSurface": "doppler_execution_v1",
        "manifestPath": export["manifestPath"],
        "manifestSha256": export["manifestSha256"],
        "graphPath": graph.get("path", "pending"),
        "graphSha256": export["executionGraphSha256"],
        "weightSetId": export["weightSetId"],
        "weightSha256": export["weightSetSha256"],
        "inputSetSha256": export["inputSetSha256"],
        "executionDepth": "not_executed",
    }


def write_array(path: Path, array: np.ndarray) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = array.tobytes(order="C")
    path.write_bytes(data)
    return {
        "path": str(path),
        "sha256": sha256_bytes(data),
        "byteLength": len(data),
    }


def run_residual_target(
    *,
    compile_root: Path,
    target: dict[str, Any],
    trace_path: Path,
    progress_path: Path,
    cmaddr: str | None,
) -> dict[str, Any]:
    # Import inside the runner so progress evidence can show SDK import/start
    # failures instead of failing before the governed entrypoint begins.
    # pylint: disable=import-error,import-outside-toplevel
    from cerebras.sdk.runtime.sdkruntimepybind import (
        MemcpyDataType,
        MemcpyOrder,
        SdkRuntime,
    )

    chunk_size = int_param(target, "chunk_size", 1024)
    input_host = (np.arange(chunk_size, dtype=np.float32) * 0.25) + 1.0
    expected = input_host.copy()
    actual = np.zeros(chunk_size, dtype=np.float32)
    compile_dir = compile_root / "compiled" / "residual"

    append_progress(
        progress_path,
        "runtime_create",
        target="residual",
        compileDir=str(compile_dir),
        cmaddrProvided=cmaddr is not None,
    )
    runner = SdkRuntime(str(compile_dir), cmaddr=cmaddr)
    input_sym = runner.get_id("input")
    output_sym = runner.get_id("output")

    try:
        append_progress(progress_path, "runtime_load", target="residual")
        runner.load()
        append_progress(progress_path, "runtime_run", target="residual")
        runner.run()
        append_progress(progress_path, "memcpy_h2d", target="residual", elements=chunk_size)
        runner.memcpy_h2d(
            input_sym,
            input_host,
            0,
            0,
            1,
            1,
            chunk_size,
            streaming=False,
            order=MemcpyOrder.ROW_MAJOR,
            data_type=MemcpyDataType.MEMCPY_32BIT,
            nonblock=False,
        )
        append_progress(progress_path, "launch_compute", target="residual")
        runner.launch("compute", nonblock=False)
        append_progress(progress_path, "memcpy_d2h", target="residual", elements=chunk_size)
        runner.memcpy_d2h(
            actual,
            output_sym,
            0,
            0,
            1,
            1,
            chunk_size,
            streaming=False,
            order=MemcpyOrder.ROW_MAJOR,
            data_type=MemcpyDataType.MEMCPY_32BIT,
            nonblock=False,
        )
    finally:
        append_progress(progress_path, "runtime_stop", target="residual")
        runner.stop()

    max_abs_err = common.max_abs_error(actual, expected)
    if not np.allclose(actual, expected, atol=1e-6, rtol=0.0):
        raise ValueError(f"residual target mismatch: max_abs_err={max_abs_err}")

    output_link = write_array(
        trace_path.parent / "int4ple-residual-diagnostic-output.f32",
        actual,
    )
    append_progress(
        progress_path,
        "runtime_target_succeeded",
        target="residual",
        maxAbsErr=max_abs_err,
    )
    return {
        "target": "residual",
        "status": "succeeded",
        "compileDir": str(compile_dir),
        "roi": {"x": 0, "y": 0, "width": 1, "height": 1},
        "chunkSize": chunk_size,
        "maxAbsErr": max_abs_err,
        "inputSynthetic": True,
        "output": {
            **output_link,
            "dtype": "float32",
            "shape": [chunk_size],
        },
    }


def diagnostic_trace(
    *,
    export: dict[str, Any],
    runtime_config: dict[str, Any],
    cmaddr: str | None,
    started: float,
    kernel_results: list[dict[str, Any]],
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    elapsed_ms = (time.monotonic() - started) * 1000.0
    trace: dict[str, Any] = {
        "schemaVersion": 1,
        "artifactKind": "csl_simulator_trace",
        "target": "wse3",
        "contract": "explicit_simulator_trace",
        "sourceProgram": source_program(export),
        "simulatorRun": {
            "status": status,
            "executionTarget": common.execution_target(cmaddr),
            "compileStatus": "succeeded",
            "kernelStage": "int4ple_compile_target_runtime_diagnostic",
            "kernelIsStub": False,
            "elapsedMs": elapsed_ms,
        },
        "executedRun": {
            "fullModelDepthExecuted": False,
            "boundedTranscriptProduced": False,
            "productionCompileTargetsExecuted": [
                item["target"] for item in kernel_results if item.get("status") == "succeeded"
            ],
            "runtimeConfigMode": runtime_config.get("mode"),
            "diagnosticOnly": True,
        },
        "modelExecution": {
            "fullModelDepthExecuted": False,
            "blocker": (
                "Only a production compile-target runtime diagnostic ran. "
                "The full HostPlan prefill/decode scheduler has not emitted "
                "token/logit/KV transcript artifacts."
            ),
        },
        "kernelResults": kernel_results,
    }
    if error is not None:
        trace["simulatorRun"]["error"] = error
    return trace


def main() -> int:
    args = parse_args()
    trace_path = Path(args.trace_out)
    progress_path = Path(args.progress_out)
    started = time.monotonic()
    append_progress(progress_path, "runner_start")

    try:
        plan = load_json(Path(args.plan))
        runtime_config = load_json(Path(args.runtime_config))
        export = load_json(Path(args.reference_export))
        cmaddr = common.endpoint(args.cmaddr)
        residual_target = target_by_name(plan, "residual")
        result = run_residual_target(
            compile_root=Path(args.compile_root),
            target=residual_target,
            trace_path=trace_path,
            progress_path=progress_path,
            cmaddr=cmaddr,
        )
        trace = diagnostic_trace(
            export=export,
            runtime_config=runtime_config,
            cmaddr=cmaddr,
            started=started,
            kernel_results=[result],
            status="succeeded",
        )
        write_json(trace_path, trace)
        append_progress(progress_path, "runner_succeeded", tracePath=str(trace_path))
        print(f"PASS: diagnostic INT4 PLE compile-target run wrote {trace_path}")
        return 0
    except Exception as exc:  # pragma: no cover - runner evidence path
        append_progress(progress_path, "runner_failed", error=str(exc))
        try:
            runtime_config = load_json(Path(args.runtime_config))
            export = load_json(Path(args.reference_export))
            cmaddr = common.endpoint(args.cmaddr)
            trace = diagnostic_trace(
                export=export,
                runtime_config=runtime_config,
                cmaddr=cmaddr,
                started=started,
                kernel_results=[],
                status="failed",
                error=str(exc),
            )
            write_json(trace_path, trace)
        except Exception:
            pass
        print(f"FAIL: diagnostic INT4 PLE compile-target run: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
