#!/usr/bin/env python3
"""Record the first Doppler WebGPU-capture to CSL lowering receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CAPTURE_GRAPH = (
    "bench/out/doppler-capture/"
    "gemma-4-e2b-doe-webgpu-capture-graph.json"
)
DEFAULT_ATTENTION_RECEIPT = (
    "bench/out/manifest-shape/"
    "gemma-4-e2b-manifest-shape-attention-core.json"
)
DEFAULT_CSL_KERNEL = (
    "bench/runners/csl-runners/gemma4_e2b_manifest_attention_core.csl"
)
DEFAULT_PYTHON_RUNNER = (
    "bench/runners/csl-runners/gemma4_e2b_manifest_attention_core.py"
)
DEFAULT_OUT = (
    "bench/out/doppler-capture/"
    "gemma-4-e2b-capture-to-csl-attention-core-lowering.json"
)
CAPTURE_ARTIFACT_KIND = "doe_webgpu_capture_graph"
ATTENTION_ARTIFACT_KIND = "doe_gemma4_e2b_manifest_shape_attention_core"
LOWERING_ARTIFACT_KIND = (
    "doe_doppler_webgpu_capture_to_csl_attention_core_lowering"
)
EXPECTED_MODEL_ID = "gemma-4-e2b-it-q4k-ehf16-af32"
EXPECTED_SHADER_TOKENS = (
    "local_head_dim",
    "global_head_dim",
    "num_kv_heads",
    "arrayLength(&weights)",
)
EXPECTED_ARCHITECTURE = {
    "headDim": 256,
    "globalHeadDim": 512,
    "hiddenSize": 1536,
    "numAttentionHeads": 8,
    "numKeyValueHeads": 1,
    "numLayers": 35,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-graph", default=DEFAULT_CAPTURE_GRAPH)
    parser.add_argument("--attention-core-receipt", default=DEFAULT_ATTENTION_RECEIPT)
    parser.add_argument("--csl-kernel", default=DEFAULT_CSL_KERNEL)
    parser.add_argument("--python-runner", default=DEFAULT_PYTHON_RUNNER)
    parser.add_argument("--out-json", default=DEFAULT_OUT)
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


def file_link(path: Path) -> dict[str, Any]:
    link: dict[str, Any] = {"path": rel(path), "exists": path.is_file()}
    if path.is_file():
        link["sha256"] = sha256_file(path)
    return link


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object at {rel(path)}")
    return payload


def first_shader_code(graph: dict[str, Any]) -> str:
    for module in graph.get("shaderModules") or []:
        if isinstance(module, dict) and isinstance(module.get("code"), str):
            return module["code"]
    return ""


def parse_workgroup_size(wgsl: str) -> list[int]:
    match = re.search(r"@workgroup_size\(([^)]*)\)", wgsl)
    if match is None:
        return []
    sizes: list[int] = []
    for part in match.group(1).split(","):
        text = part.strip()
        if not text:
            continue
        try:
            sizes.append(int(text))
        except ValueError:
            return []
    return sizes


def collect_dispatches(graph: dict[str, Any]) -> list[dict[str, Any]]:
    dispatches: list[dict[str, Any]] = []
    for command_buffer in graph.get("commandBuffers") or []:
        if not isinstance(command_buffer, dict):
            continue
        for command in command_buffer.get("commands") or []:
            if not isinstance(command, dict):
                continue
            nested = command.get("commands") or []
            for nested_command in nested:
                if (
                    isinstance(nested_command, dict)
                    and nested_command.get("kind") == "dispatchWorkgroups"
                ):
                    dispatches.append({
                        "commandBuffer": command_buffer.get("id"),
                        "pipeline": nested_command.get("pipeline"),
                        "bindGroups": nested_command.get("bindGroups") or [],
                        "workgroups": [
                            int(nested_command.get("x", 0)),
                            int(nested_command.get("y", 1)),
                            int(nested_command.get("z", 1)),
                        ],
                    })
    return dispatches


def collect_bindings(graph: dict[str, Any]) -> list[dict[str, Any]]:
    layout_entries: dict[int, dict[str, Any]] = {}
    for layout in graph.get("bindGroupLayouts") or []:
        if not isinstance(layout, dict):
            continue
        for entry in layout.get("entries") or []:
            if isinstance(entry, dict) and isinstance(entry.get("binding"), int):
                layout_entries[int(entry["binding"])] = entry

    buffers_by_id = {
        buffer.get("id"): buffer
        for buffer in graph.get("buffers") or []
        if isinstance(buffer, dict)
    }
    bindings: list[dict[str, Any]] = []
    for bind_group in graph.get("bindGroups") or []:
        if not isinstance(bind_group, dict):
            continue
        for entry in bind_group.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            binding = entry.get("binding")
            buffer_ref = (
                ((entry.get("resource") or {}).get("buffer") or {})
                if isinstance(entry.get("resource"), dict)
                else {}
            )
            buffer = buffers_by_id.get(buffer_ref.get("id")) or {}
            layout_entry = layout_entries.get(binding) or {}
            buffer_type = (layout_entry.get("buffer") or {}).get("type")
            bindings.append({
                "binding": binding,
                "bufferId": buffer.get("id"),
                "bufferLabel": buffer.get("label"),
                "bufferSize": buffer.get("size"),
                "bufferType": buffer_type or "unknown",
                "visibility": layout_entry.get("visibility"),
            })
    return sorted(bindings, key=lambda item: int(item.get("binding") or 0))


def buffer_roles(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    roles: list[dict[str, Any]] = []
    for binding in bindings:
        label = str(binding.get("bufferLabel") or "")
        if "hidden-state" in label:
            role = "hidden_state_input"
        elif "grouped-kv" in label:
            role = "grouped_kv_projection_input"
        elif "capture-output" in label:
            role = "attention_core_output"
        elif "params" in label:
            role = "manifest_shape_params"
        else:
            role = "unclassified"
        roles.append({**binding, "role": role})
    return roles


def attention_shape_summary(attention: dict[str, Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for run in attention.get("shapeRuns") or []:
        if not isinstance(run, dict):
            continue
        executed = run.get("executedRun") or {}
        parity = executed.get("numericalParity") or {}
        summaries.append({
            "attentionKind": run.get("attentionKind"),
            "headDim": (run.get("shape") or {}).get("headDim"),
            "status": run.get("status"),
            "runtimeStopReached": bool(
                (executed.get("runtimeStop") or {}).get("reached")
            ),
            "numericalParity": {
                "passed": bool(parity.get("passed")),
                "maxAbsErr": float(parity.get("maxAbsErr", 0.0)),
                "comparison": parity.get("comparison"),
            },
            "sendReceiveCounts": executed.get("sendReceiveCounts") or {},
        })
    return summaries


def build_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    capture_path = resolve(args.capture_graph)
    attention_path = resolve(args.attention_core_receipt)
    csl_path = resolve(args.csl_kernel)
    runner_path = resolve(args.python_runner)

    blockers: list[str] = []
    errors: list[str] = []
    graph: dict[str, Any] = {}
    attention: dict[str, Any] = {}

    if capture_path.is_file():
        try:
            graph = load_json(capture_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            blockers.append("capture_graph_unreadable")
            errors.append(f"capture_graph: {type(exc).__name__}: {exc}")
    else:
        blockers.append("capture_graph_missing")

    if attention_path.is_file():
        try:
            attention = load_json(attention_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            blockers.append("attention_core_receipt_unreadable")
            errors.append(f"attention_core_receipt: {type(exc).__name__}: {exc}")
    else:
        blockers.append("attention_core_receipt_missing")

    for path, blocker in (
        (csl_path, "csl_kernel_missing"),
        (runner_path, "python_sdklayout_runner_missing"),
    ):
        if not path.is_file():
            blockers.append(blocker)

    metadata = graph.get("metadata") or {}
    model = metadata.get("model") or {}
    architecture = model.get("architecture") or {}
    if graph:
        if graph.get("artifactKind") != CAPTURE_ARTIFACT_KIND:
            blockers.append("capture_graph_kind_mismatch")
        if not graph.get("graphSha256"):
            blockers.append("capture_graph_sha_missing")
        if model.get("modelId") != EXPECTED_MODEL_ID:
            blockers.append("capture_model_id_mismatch")
        for key, expected in EXPECTED_ARCHITECTURE.items():
            if architecture.get(key) != expected:
                blockers.append(f"capture_architecture_{key}_mismatch")
        if graph.get("unsupported") not in ([], None):
            blockers.append("capture_graph_contains_unsupported_calls")
        for field, blocker in (
            ("shaderModules", "capture_graph_no_shader_modules"),
            ("computePipelines", "capture_graph_no_compute_pipelines"),
            ("commandBuffers", "capture_graph_no_command_buffers"),
            ("submissions", "capture_graph_no_submissions"),
            ("readbacks", "capture_graph_no_readbacks"),
        ):
            if len(graph.get(field) or []) < 1:
                blockers.append(blocker)

    wgsl = first_shader_code(graph)
    missing_tokens = [
        token for token in EXPECTED_SHADER_TOKENS if token not in wgsl
    ]
    if graph and missing_tokens:
        blockers.append("capture_wgsl_missing_manifest_shape_tokens")
        errors.append(f"missing WGSL tokens: {', '.join(missing_tokens)}")

    if attention:
        if attention.get("artifactKind") != ATTENTION_ARTIFACT_KIND:
            blockers.append("attention_core_kind_mismatch")
        if attention.get("status") != "succeeded":
            blockers.append("attention_core_not_succeeded")
        if attention.get("verdict") != "manifest_shape_attention_core_passed":
            blockers.append("attention_core_verdict_not_passed")
        coverage = attention.get("coverage") or {}
        for field in (
            "localHeadDimExecuted",
            "globalHeadDimExecuted",
            "groupedKvExecuted",
            "attentionCoreCslRuntimeExecuted",
        ):
            if coverage.get(field) is not True:
                blockers.append(f"attention_core_coverage_{field}_not_true")
        if coverage.get("embedUnembedExecuted") is not False:
            blockers.append("attention_core_embed_unembed_scope_mismatch")
        if coverage.get("logitsParityExecuted") is not False:
            blockers.append("attention_core_logits_scope_mismatch")

    dispatches = collect_dispatches(graph)
    bindings = collect_bindings(graph)
    shader_modules = [
        {
            "id": module.get("id"),
            "label": module.get("label"),
            "wgslSha256": module.get("wgslSha256"),
        }
        for module in graph.get("shaderModules") or []
        if isinstance(module, dict)
    ]
    shape_runs = attention_shape_summary(attention)
    parity_passed = bool(shape_runs) and all(
        (run.get("numericalParity") or {}).get("passed") is True
        and run.get("runtimeStopReached") is True
        for run in shape_runs
    )
    if attention and not parity_passed:
        blockers.append("attention_core_parity_not_passed")

    status = (
        "attention_core_capture_slice_lowered_and_simulated"
        if not blockers
        else "blocked"
    )
    payload = {
        "schemaVersion": 1,
        "artifactKind": LOWERING_ARTIFACT_KIND,
        "status": status,
        "claimable": False,
        "source": {
            "captureGraph": {
                **file_link(capture_path),
                "graphSha256": graph.get("graphSha256"),
            },
            "captureScope": metadata.get("captureScope"),
            "sourceRepo": (metadata.get("bootstrap") or {}).get("sourceRepo"),
            "sourcePath": (metadata.get("bootstrap") or {}).get("sourcePath"),
            "model": {
                "modelId": model.get("modelId"),
                "manifestPath": model.get("manifestPath"),
                "manifestSha256": model.get("manifestSha256"),
                "architecture": architecture,
            },
            "shaderModules": shader_modules,
        },
        "capturedHostPlanView": {
            "kind": "webgpu_capture_host_plan_view",
            "graphSha256": graph.get("graphSha256"),
            "workload": "gemma4_e2b_manifest_shape_grouped_kv_capture_smoke",
            "dispatches": dispatches,
            "bindings": bindings,
            "bufferRoles": buffer_roles(bindings),
            "workgroupSize": parse_workgroup_size(wgsl),
            "workgroupDispatchCount": len(dispatches),
            "readbackCheckpoints": len(graph.get("readbacks") or []),
        },
        "loweredArtifacts": {
            "sdkVersionFloor": "2.10.0",
            "pythonSdkLayoutRunner": file_link(runner_path),
            "cslKernel": file_link(csl_path),
            "attentionCoreReceipt": file_link(attention_path),
            "targetRuntime": "sdk_layout_streaming",
            "targetBackend": "csl",
        },
        "simulatorEvidence": {
            "status": (
                "succeeded" if status.endswith("_lowered_and_simulated")
                else "blocked"
            ),
            "attentionCoreReceiptStatus": attention.get("status"),
            "semanticParity": {
                "passed": parity_passed,
                "scope": "attention_core_cpu_oracle_bit_exact",
                "againstDopplerProductionInference": False,
                "shapeRuns": shape_runs,
            },
            "hardwareExecuted": False,
        },
        "claimScope": {
            "claimable": False,
            "summary": (
                "Consumes the recorded Doppler WebGPU capture graph and "
                "binds it to the first Gemma-4 E2B manifest-shape "
                "attention-core SdkLayout/CSL slice. The slice has "
                "simulator parity against the CPU oracle, but this is not "
                "full Doppler inference capture or full model lowering."
            ),
            "notClaimable": [
                "full Doppler production inference capture",
                "mechanical WGSL-to-CSL compiler coverage",
                "full captured WebGPU graph HostPlan lowering",
                "embed/unembed, decoder stack, or logits parity",
                "Cerebras hardware execution",
                "throughput or latency performance",
            ],
        },
        "blockers": blockers,
        "remainingClaimBlockers": [
            "ordinary_doppler_inference_graph_capture",
            "full_captured_webgpu_graph_to_hostplan_lowering",
            "automated_wgsl_to_csl_kernel_lowering",
            "embed_unembed_decoder_logits_parity",
            "cerebras_hardware_receipt",
        ],
        "errors": errors,
    }
    return payload, 0 if status.endswith("_lowered_and_simulated") else 1


def main() -> int:
    args = parse_args()
    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload, rc = build_payload(args)
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {rel(out_path)}")
    print(f"status={payload['status']}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
