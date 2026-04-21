#!/usr/bin/env cs_python
"""Run one Gemma 4 E2B manifest-shape attention-core CSL shape."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

from cerebras.sdk.runtime.sdkruntimepybind import (  # pylint: disable=no-name-in-module
    Color,
    Edge,
    Route,
    RoutingPosition,
    SdkLayout,
    SdkRuntime,
    SdkTarget,
    SimfabConfig,
    get_platform,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KERNEL = (
    "bench/runners/csl-runners/gemma4_e2b_manifest_attention_core.csl"
)
QUERY_HEADS = 8
KV_HEADS = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attention-kind", choices=["local", "global"], required=True)
    parser.add_argument("--head-dim", type=int, required=True)
    parser.add_argument("--kernel-source", default=DEFAULT_KERNEL)
    parser.add_argument(
        "--compile-out",
        default="bench/out/manifest-shape/attention-core/compile",
    )
    parser.add_argument(
        "--out-json",
        default=(
            "bench/out/manifest-shape/attention-core/"
            "gemma-4-e2b-attention-core-shape.json"
        ),
    )
    parser.add_argument("--cmaddr", default="")
    return parser.parse_args()


def resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_core(q_values: np.ndarray, k_values: np.ndarray, v_values: np.ndarray) -> np.ndarray:
    dot = np.float32(0.0)
    for index in range(q_values.shape[0]):
        product = np.float32(q_values[index] * k_values[index])
        dot = np.float32(dot + product)
    expected = v_values.astype(np.float32, copy=True)
    expected[0] = dot
    return expected


def wait_task(runtime: SdkRuntime, task: object) -> float:
    start = time.time()
    runtime.task_wait(task)
    return (time.time() - start) * 1000.0


def build_payload(args: argparse.Namespace) -> tuple[dict, bool]:
    kernel_source = resolve(args.kernel_source)
    if not kernel_source.is_file():
        raise FileNotFoundError(f"kernel source not found: {rel(kernel_source)}")

    compile_out = resolve(args.compile_out)
    compile_out.mkdir(parents=True, exist_ok=True)

    compile_start = time.time()
    platform = get_platform(
        args.cmaddr.strip(),
        SimfabConfig(dump_core=False),
        SdkTarget.WSE3,
    )
    layout = SdkLayout(platform)

    region_name = "gemma4_e2b_manifest_attention_core"
    region = layout.create_code_region(str(kernel_source), region_name, 1, 1)

    rx_q = Color("rx_q")
    rx_k = Color("rx_k")
    rx_v = Color("rx_v")
    tx_out = Color("tx_out")
    recv = RoutingPosition().set_output([Route.RAMP])
    send = RoutingPosition().set_input([Route.RAMP])

    region.set_param_all("head_dim", args.head_dim)
    region.set_param_all(rx_q)
    region.set_param_all(rx_k)
    region.set_param_all(rx_v)
    region.set_param_all(tx_out)

    q_port = region.create_input_port(rx_q, Edge.LEFT, [recv], args.head_dim)
    k_port = region.create_input_port(rx_k, Edge.TOP, [recv], args.head_dim)
    v_port = region.create_input_port(rx_v, Edge.BOTTOM, [recv], args.head_dim)
    out_port = region.create_output_port(tx_out, Edge.RIGHT, [send], args.head_dim)
    region.place(4, 2)

    io_buffer_size = max(1024, args.head_dim)
    q_stream = layout.create_input_stream(q_port, io_buffer_size=io_buffer_size)
    k_stream = layout.create_input_stream(k_port, io_buffer_size=io_buffer_size)
    v_stream = layout.create_input_stream(v_port, io_buffer_size=io_buffer_size)
    out_stream = layout.create_output_stream(out_port, io_buffer_size=io_buffer_size)

    compile_prefix = compile_out / (
        f"{region_name}-{args.attention_kind}-hd{args.head_dim}"
    )
    compile_artifacts = layout.compile(out_prefix=str(compile_prefix))
    compile_elapsed_ms = (time.time() - compile_start) * 1000.0

    runtime = SdkRuntime(compile_artifacts, platform, memcpy_required=False)
    run_start = time.time()
    stream_wait_ms = {
        "q": 0.0,
        "k": 0.0,
        "v": 0.0,
        "out": 0.0,
    }
    per_head_records: list[dict] = []
    max_abs_err = 0.0
    all_passed = True
    runtime_stop = {"reached": False, "elapsedMs": None, "error": None}
    failure: dict | None = None
    run_status = "not_started"

    try:
        runtime.load()
        runtime.run()

        kv_rng = np.random.default_rng(seed=54000 + args.head_dim)
        shared_k = kv_rng.standard_normal(args.head_dim, dtype=np.float32)
        shared_v = kv_rng.standard_normal(args.head_dim, dtype=np.float32)
        shared_k_sha = hashlib.sha256(shared_k.tobytes()).hexdigest()
        shared_v_sha = hashlib.sha256(shared_v.tobytes()).hexdigest()

        for q_head in range(QUERY_HEADS):
            q_rng = np.random.default_rng(
                seed=55000 + args.head_dim * 16 + q_head
            )
            q_values = q_rng.standard_normal(args.head_dim, dtype=np.float32)
            expected = expected_core(q_values, shared_k, shared_v)
            received = np.empty(args.head_dim, dtype=np.float32)

            layer_start = time.time()
            task_q = runtime.send(q_stream, q_values, nonblock=True)
            task_k = runtime.send(k_stream, shared_k, nonblock=True)
            task_v = runtime.send(v_stream, shared_v, nonblock=True)
            task_out = runtime.receive(
                out_stream,
                received,
                args.head_dim,
                nonblock=True,
            )
            stream_wait_ms["q"] += wait_task(runtime, task_q)
            stream_wait_ms["k"] += wait_task(runtime, task_k)
            stream_wait_ms["v"] += wait_task(runtime, task_v)
            stream_wait_ms["out"] += wait_task(runtime, task_out)

            err = float(np.max(np.abs(received - expected)))
            passed = bool(np.array_equal(received, expected))
            max_abs_err = max(max_abs_err, err)
            all_passed = all_passed and passed
            per_head_records.append({
                "queryHead": q_head,
                "keyValueHead": 0,
                "kvSourceSha256": {
                    "k": shared_k_sha,
                    "v": shared_v_sha,
                },
                "elapsedMs": (time.time() - layer_start) * 1000.0,
                "maxAbsErr": err,
                "passed": passed,
                "outputSha256": hashlib.sha256(received.tobytes()).hexdigest(),
            })

        stop_start = time.time()
        runtime.stop()
        runtime_stop = {
            "reached": True,
            "elapsedMs": (time.time() - stop_start) * 1000.0,
            "error": None,
        }
        run_status = "succeeded" if all_passed else "mismatch"
    except Exception as exc:  # pylint: disable=broad-except
        run_status = f"failed:{type(exc).__name__}:{str(exc)[:160]}"
        failure = {
            "errorType": type(exc).__name__,
            "message": str(exc)[:500],
            "completedQueryHeads": len(per_head_records),
        }
        try:
            stop_start = time.time()
            runtime.stop()
            runtime_stop = {
                "reached": True,
                "elapsedMs": (time.time() - stop_start) * 1000.0,
                "error": None,
            }
        except Exception as stop_exc:  # pylint: disable=broad-except
            runtime_stop = {
                "reached": False,
                "elapsedMs": None,
                "error": f"{type(stop_exc).__name__}: {str(stop_exc)[:160]}",
            }

    run_elapsed_ms = (time.time() - run_start) * 1000.0
    passed = run_status == "succeeded" and all_passed
    payload = {
        "schemaVersion": 1,
        "artifactKind": "doe_gemma4_e2b_manifest_shape_attention_core_shape_run",
        "status": run_status,
        "attentionKind": args.attention_kind,
        "modelId": "gemma-4-e2b-it",
        "target": "wse3",
        "shape": {
            "headDim": args.head_dim,
            "numAttentionHeads": QUERY_HEADS,
            "numKeyValueHeads": KV_HEADS,
            "groupedKvQueryHeadsPerKvHead": QUERY_HEADS // KV_HEADS,
        },
        "inputs": {
            "kernelSource": {
                "path": rel(kernel_source),
                "sha256": sha256_file(kernel_source),
            },
        },
        "executedCompile": {
            "status": "succeeded",
            "elapsedMs": compile_elapsed_ms,
            "compilePrefix": rel(compile_prefix),
            "sdkVersionFloor": "2.10.0",
            "compileOptions": {
                "target": "wse3",
                "f16Type": None,
                "libs": [],
                "cslcPrefix": None,
                "savePortMap": False,
            },
        },
        "executedRun": {
            "status": run_status,
            "elapsedMs": run_elapsed_ms,
            "runtimeStop": runtime_stop,
            "failure": failure,
            "sendReceiveCounts": {
                "sends": 3 * QUERY_HEADS,
                "receives": QUERY_HEADS,
            },
            "observedBytesTransferredTotal": args.head_dim * 4 * 4 * QUERY_HEADS,
            "streamWaitMs": stream_wait_ms,
            "numericalParity": {
                "passed": passed,
                "maxAbsErr": max_abs_err,
                "atol": 0.0,
                "comparison": "bit_exact_np_array_equal",
            },
            "perQueryHead": per_head_records,
        },
        "connectionGraph": {
            "region": region_name,
            "grid": {"width": 1, "height": 1, "peCount": 1, "place": [4, 2]},
            "inputPorts": [
                {"color": "rx_q", "edge": "LEFT", "size": args.head_dim},
                {"color": "rx_k", "edge": "TOP", "size": args.head_dim},
                {"color": "rx_v", "edge": "BOTTOM", "size": args.head_dim},
            ],
            "outputPorts": [
                {"color": "tx_out", "edge": "RIGHT", "size": args.head_dim},
            ],
            "crossRegionConnections": [],
        },
        "hostIoLayout": [
            {
                "streamId": "q_head_stream",
                "role": "input",
                "elementsPerPe": args.head_dim,
                "dtype": "float32",
                "ioBufferSize": io_buffer_size,
            },
            {
                "streamId": "k_grouped_kv_stream",
                "role": "input",
                "elementsPerPe": args.head_dim,
                "dtype": "float32",
                "ioBufferSize": io_buffer_size,
            },
            {
                "streamId": "v_grouped_kv_stream",
                "role": "input",
                "elementsPerPe": args.head_dim,
                "dtype": "float32",
                "ioBufferSize": io_buffer_size,
            },
            {
                "streamId": "attention_core_out_stream",
                "role": "output",
                "elementsPerPe": args.head_dim,
                "dtype": "float32",
                "ioBufferSize": io_buffer_size,
            },
        ],
        "claimScope": {
            "claimable": False,
            "summary": (
                "Attention-core diagnostic only: full-head Q.K plus grouped "
                "K/V stream reuse over all query heads. This is not full "
                "attention, decoder, logits, hardware, or performance evidence."
            ),
        },
    }
    return payload, passed


def main() -> int:
    args = parse_args()
    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload, passed = build_payload(args)
    except Exception as exc:  # pylint: disable=broad-except
        payload = {
            "schemaVersion": 1,
            "artifactKind": "doe_gemma4_e2b_manifest_shape_attention_core_shape_run",
            "status": f"failed:{type(exc).__name__}:{str(exc)[:160]}",
            "attentionKind": args.attention_kind,
            "modelId": "gemma-4-e2b-it",
            "target": "wse3",
            "shape": {"headDim": args.head_dim},
            "errors": [f"{type(exc).__name__}: {exc}"],
        }
        passed = False
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {rel(out_path)}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
