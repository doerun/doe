#!/usr/bin/env cs_python
"""Diagnostic runtime runner for generated INT4 PLE CSL compile targets.

This is not the final bounded transcript runner. It drives one generated
production-derived residual target through SdkRuntime so timeout/debug evidence
moves past compile-only mode. The trace intentionally keeps full-model
transcript depth false until the HostPlan scheduler emits token/logit/KV
artifacts.
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
from int4ple_runtime_scheduler import (
    count_by,
    load_normalized_execution,
    resolve_artifact_path,
    sha256_json,
    synthesize_runtime_scheduler,
)

SCHEDULE_PREVIEW_COUNT = 4
COMPILE_DISTINCT_PE_WARNING_THRESHOLD = 10_000
Q4K_BLOCK_SIZE = 256
TARGET_MATMUL_TILE = 16
ATTENTION_PREFILL_BLOCK_SIZE = 32
DEFAULT_GEMV_INPUT_PER_PE = 512


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--runtime-config", required=True)
    parser.add_argument("--compile-root", required=True)
    parser.add_argument("--reference-export", required=True)
    parser.add_argument("--trace-out", required=True)
    parser.add_argument("--progress-out", required=True)
    parser.add_argument("--diagnostic-compile-dir", default="")
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


def compile_target_coverage(
    plan: dict[str, Any],
    compile_root: Path,
) -> dict[str, Any]:
    targets: list[dict[str, Any]] = []
    source_ready = 0
    compiled_ready = 0
    for target in (plan.get("inputs") or {}).get("compileTargets") or []:
        if not isinstance(target, dict):
            continue
        name = str(target.get("name", ""))
        layout = str(target.get("layout", f"{name}/layout.csl"))
        pe_program = str(target.get("peProgram", f"{name}/pe_program.csl"))
        layout_path = compile_root / layout
        pe_program_path = compile_root / pe_program
        compiled_path = compile_root / "compiled" / name / "out.json"
        target_source_ready = layout_path.is_file() and pe_program_path.is_file()
        target_compiled_ready = compiled_path.is_file()
        source_ready += 1 if target_source_ready else 0
        compiled_ready += 1 if target_compiled_ready else 0
        targets.append(
            {
                "name": name,
                "sourceReady": target_source_ready,
                "compiledReady": target_compiled_ready,
                "layoutPath": str(layout_path),
                "peProgramPath": str(pe_program_path),
                "compiledOutPath": str(compiled_path),
            }
        )
    return {
        "totalTargetCount": len(targets),
        "sourceReadyTargetCount": source_ready,
        "compiledReadyTargetCount": compiled_ready,
        "allSourcesReady": bool(targets) and source_ready == len(targets),
        "allCompiledTargetsReady": bool(targets) and compiled_ready == len(targets),
        "targets": targets,
    }


def compiled_target_params(compile_root: Path, target_name: str) -> dict[str, int]:
    compiled_path = compile_root / "compiled" / target_name / "out.json"
    if not compiled_path.is_file():
        return {}
    try:
        compiled = load_json(compiled_path)
    except (OSError, json.JSONDecodeError):
        return {}
    params = compiled.get("params") or {}
    if not isinstance(params, dict):
        return {}
    parsed: dict[str, int] = {}
    for key, value in params.items():
        try:
            parsed[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return parsed


def require_minimum(
    *,
    blockers: list[str],
    checks: list[dict[str, Any]],
    check_id: str,
    actual: int,
    minimum: int,
) -> None:
    passed = actual >= minimum
    checks.append(
        {
            "id": check_id,
            "actual": actual,
            "minimum": minimum,
            "passed": passed,
        }
    )
    if not passed:
        blockers.append(f"{check_id}:{actual}<{minimum}")


def ceil_div(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return (numerator + denominator - 1) // denominator


def runtime_grid(runtime_config: dict[str, Any]) -> dict[str, int]:
    memory_plan = runtime_config.get("memoryPlan") or {}
    grid = memory_plan.get("grid") if isinstance(memory_plan, dict) else {}
    if not isinstance(grid, dict):
        grid = {}
    return {
        "width": int(grid.get("width") or 0),
        "height": int(grid.get("height") or 0),
    }


def manifest_compile_param_projection(
    *,
    runtime_config: dict[str, Any],
    reference: dict[str, Any],
) -> dict[str, Any]:
    model = runtime_config.get("modelConfig") or {}
    if not isinstance(model, dict) or not model:
        return {"status": "not_evaluated", "reason": "model_config_missing"}
    grid = runtime_grid(runtime_config)
    grid_width = grid["width"]
    grid_height = grid["height"]
    if grid_width <= 0 or grid_height <= 0:
        return {"status": "not_evaluated", "reason": "runtime_grid_missing"}

    vocab_size = int(model.get("vocabSize") or model.get("pleVocabSize") or 0)
    hidden_dim = int(model.get("hiddenDim") or 0)
    head_dim = int(model.get("headDim") or 0)
    global_head_dim = int(model.get("globalHeadDim") or head_dim)
    max_seq_len = int(model.get("maxSeqLen") or reference.get("promptTokenCount") or 0)
    prompt_tokens = int(reference.get("promptTokenCount") or max_seq_len or 0)
    pe_count = grid_width * grid_height
    matmul_p = min(
        grid_width,
        grid_height,
        int(COMPILE_DISTINCT_PE_WARNING_THRESHOLD**0.5),
        max(1, ceil_div(hidden_dim, TARGET_MATMUL_TILE)),
    )
    matmul_tile = ceil_div(hidden_dim, matmul_p)
    gemv_input_per_pe = max(
        DEFAULT_GEMV_INPUT_PER_PE,
        ceil_div(hidden_dim, max(1, grid_width)),
    )
    gemv_blocks = ceil_div(gemv_input_per_pe, Q4K_BLOCK_SIZE)
    lm_head_out_dim = ceil_div(vocab_size, max(1, grid_width))
    sample_chunk = ceil_div(vocab_size, max(1, grid_width))
    attention_tokens = max(1, prompt_tokens)

    params = {
        "embed": {
            "height": grid_height,
            "hidden_size": hidden_dim,
            "num_tokens": max_seq_len,
            "rows_per_pe": ceil_div(vocab_size, max(1, pe_count)),
        },
        "tiled": {
            "P": matmul_p,
            "Mt": matmul_tile,
            "Kt": matmul_tile,
            "Nt": matmul_tile,
        },
        "attn_head256": {
            "block_size": min(ATTENTION_PREFILL_BLOCK_SIZE, attention_tokens),
            "head_dim": head_dim,
            "kv_len": attention_tokens,
            "q_len": attention_tokens,
        },
        "attn_head512": {
            "block_size": min(ATTENTION_PREFILL_BLOCK_SIZE, attention_tokens),
            "head_dim": global_head_dim,
            "kv_len": attention_tokens,
            "q_len": attention_tokens,
        },
        "lm_head_gemv_stable": {
            "out_dim": lm_head_out_dim,
            "in_dim_per_pe": gemv_input_per_pe,
            "num_blocks_per_row": gemv_blocks,
        },
        "sample": {
            "chunk_size": sample_chunk,
        },
    }
    compile_scale = {
        "embedDistinctPeProgramCount": pe_count,
        "tiledDistinctPeProgramCount": matmul_p * matmul_p,
        "warningThreshold": COMPILE_DISTINCT_PE_WARNING_THRESHOLD,
    }
    warnings = [
        f"{key}:{value}>{COMPILE_DISTINCT_PE_WARNING_THRESHOLD}"
        for key, value in compile_scale.items()
        if key.endswith("Count") and value > COMPILE_DISTINCT_PE_WARNING_THRESHOLD
    ]
    return {
        "status": "projected",
        "source": "runtime_config_model_and_grid",
        "grid": grid,
        "params": params,
        "coverage": {
            "embedRows": pe_count * int(params["embed"]["rows_per_pe"]),
            "tiledM": matmul_p * matmul_tile,
            "tiledN": matmul_p * matmul_tile,
            "lmHeadLogits": grid_width * lm_head_out_dim,
            "sampleLogits": grid_width * sample_chunk,
        },
        "compileScale": compile_scale,
        "warnings": warnings,
    }


def host_plan_executor_preflight(
    *,
    compile_root: Path,
    runtime_config: dict[str, Any],
    reference: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed before a full-model executor can promote smoke targets."""

    model = runtime_config.get("modelConfig") or {}
    if not isinstance(model, dict) or not model:
        return {
            "status": "not_evaluated",
            "blockers": ["model_config_missing"],
            "checks": [],
            "targetParams": {},
        }

    target_names = (
        "embed",
        "tiled",
        "lm_head_gemv_stable",
        "attn_head256",
        "attn_head512",
        "sample",
    )
    target_params = {
        name: compiled_target_params(compile_root, name)
        for name in target_names
    }
    if not any(target_params.values()):
        return {
            "status": "not_evaluated",
            "blockers": ["compiled_target_params_unavailable"],
            "checks": [],
            "targetParams": target_params,
        }

    blockers: list[str] = []
    checks: list[dict[str, Any]] = []
    vocab_size = int(model.get("vocabSize") or model.get("pleVocabSize") or 0)
    hidden_dim = int(model.get("hiddenDim") or 0)
    prompt_tokens = int(reference.get("promptTokenCount") or 0)

    embed = target_params.get("embed") or {}
    if embed:
        embed_rows = (
            int(embed.get("width") or 0)
            * int(embed.get("height") or 0)
            * int(embed.get("rows_per_pe") or 0)
        )
        require_minimum(
            blockers=blockers,
            checks=checks,
            check_id="embed_vocab_row_coverage",
            actual=embed_rows,
            minimum=vocab_size,
        )
        require_minimum(
            blockers=blockers,
            checks=checks,
            check_id="embed_prompt_token_capacity",
            actual=int(embed.get("num_tokens") or 0),
            minimum=prompt_tokens,
        )
    else:
        blockers.append("embed_target_params_missing")

    tiled = target_params.get("tiled") or {}
    if tiled:
        tile_m = int(tiled.get("Mt") or 0) * int(tiled.get("P") or 0)
        tile_n = int(tiled.get("Nt") or 0) * int(tiled.get("P") or 0)
        require_minimum(
            blockers=blockers,
            checks=checks,
            check_id="tiled_m_dimension_coverage",
            actual=tile_m,
            minimum=hidden_dim,
        )
        require_minimum(
            blockers=blockers,
            checks=checks,
            check_id="tiled_n_dimension_coverage",
            actual=tile_n,
            minimum=hidden_dim,
        )
    else:
        blockers.append("tiled_target_params_missing")

    for target_name in ("attn_head256", "attn_head512"):
        params = target_params.get(target_name) or {}
        if not params:
            blockers.append(f"{target_name}_target_params_missing")
            continue
        require_minimum(
            blockers=blockers,
            checks=checks,
            check_id=f"{target_name}_prefill_q_len_coverage",
            actual=int(params.get("q_len") or 0),
            minimum=prompt_tokens,
        )
        require_minimum(
            blockers=blockers,
            checks=checks,
            check_id=f"{target_name}_prefill_kv_len_coverage",
            actual=int(params.get("kv_len") or 0),
            minimum=prompt_tokens,
        )

    lm_head = target_params.get("lm_head_gemv_stable") or {}
    if lm_head:
        logits_coverage = int(lm_head.get("width") or 0) * int(
            lm_head.get("out_dim") or 0
        )
        require_minimum(
            blockers=blockers,
            checks=checks,
            check_id="lm_head_vocab_logit_coverage",
            actual=logits_coverage,
            minimum=vocab_size,
        )
    else:
        blockers.append("lm_head_target_params_missing")

    sample = target_params.get("sample") or {}
    if sample:
        sample_coverage = int(sample.get("width") or 0) * int(
            sample.get("chunk_size") or 0
        )
        require_minimum(
            blockers=blockers,
            checks=checks,
            check_id="sample_vocab_logit_coverage",
            actual=sample_coverage,
            minimum=vocab_size,
        )
    else:
        blockers.append("sample_target_params_missing")

    return {
        "status": "passed" if not blockers else "failed",
        "blockers": blockers,
        "checks": checks,
        "targetParams": target_params,
        "manifestCompileParamProjection": manifest_compile_param_projection(
            runtime_config=runtime_config,
            reference=reference,
        ),
    }


def host_plan_phase_summary(
    host_plan_path: Path,
    *,
    runtime_config: dict[str, Any] | None = None,
    normalized_execution: dict[str, Any] | None = None,
    reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not host_plan_path.is_file():
        return {
            "path": str(host_plan_path),
            "present": False,
            "phaseLaunchCounts": {},
            "phaseInvocationCounts": {},
            "kernelLaunchCounts": {},
            "kernelInvocationCounts": {},
            "launchesCarrySymbolDataflow": False,
            "launchSchedule": {
                "schemaVersion": 1,
                "artifactKind": "int4ple_hostplan_launch_schedule",
                "status": "missing_host_plan",
                "launchDescriptorCount": 0,
                "scheduledInvocationCount": 0,
                "launches": [],
                "scheduleSha256": sha256_json([]),
            },
        }
    host_plan = load_json(host_plan_path)
    phases = (host_plan.get("hostPlan") or {}).get("phases") or {}
    phase_counts: dict[str, int] = {}
    phase_invocation_counts: dict[str, int] = {}
    launches: list[dict[str, Any]] = []
    if isinstance(phases, dict):
        phase_names = [
            name for name in ("prefill", "decode") if name in phases
        ] + sorted(
            str(name) for name in phases.keys() if name not in ("prefill", "decode")
        )
        for phase_name in phase_names:
            raw_steps = phases[phase_name]
            steps = raw_steps if isinstance(raw_steps, list) else []
            phase_counts[str(phase_name)] = len(steps)
            phase_invocation_counts[str(phase_name)] = sum(
                max(1, int(step.get("repeat") or 1))
                for step in steps
                if isinstance(step, dict)
            )
            launches.extend(
                {
                    **step,
                    "_phase": str(phase_name),
                    "_phaseIndex": index,
                }
                for index, step in enumerate(steps)
                if isinstance(step, dict)
            )
    kernels = (host_plan.get("hostPlan") or {}).get("kernels") or []
    kernel_patterns = {
        str(item.get("name")): str(item.get("pattern", "unknown"))
        for item in kernels
        if isinstance(item, dict) and item.get("name")
    }
    declared_kernel_counts = {
        str(item.get("name")): int(item.get("count") or 0)
        for item in kernels
        if isinstance(item, dict) and item.get("name")
    }
    schedule_records: list[dict[str, Any]] = []
    kernel_invocation_counts: dict[str, int] = {}
    for launch_index, step in enumerate(launches):
        kernel_name = str(step.get("kernelName") or step.get("name") or "unknown")
        repeat = max(1, int(step.get("repeat") or 1))
        inputs = step.get("inputs")
        outputs = step.get("outputs")
        symbols = step.get("symbols")
        symbol_dataflow_present = (
            isinstance(inputs, list)
            or isinstance(outputs, list)
            or isinstance(symbols, dict)
        )
        kernel_invocation_counts[kernel_name] = (
            kernel_invocation_counts.get(kernel_name, 0) + repeat
        )
        schedule_records.append(
            {
                "launchIndex": launch_index,
                "phase": step["_phase"],
                "phaseLaunchIndex": int(step["_phaseIndex"]),
                "kernelName": kernel_name,
                "kernelPattern": kernel_patterns.get(kernel_name, "unknown"),
                "repeat": repeat,
                "symbolDataflowPresent": symbol_dataflow_present,
                "inputSymbolCount": len(inputs) if isinstance(inputs, list) else 0,
                "outputSymbolCount": len(outputs) if isinstance(outputs, list) else 0,
                "symbolTablePresent": isinstance(symbols, dict),
            }
        )
    runtime_scheduler = synthesize_runtime_scheduler(
        launches=[
            {
                **step,
                "launchIndex": index,
                "phase": step["_phase"],
                "phaseLaunchIndex": int(step["_phaseIndex"]),
                "kernelName": str(step.get("kernelName") or step.get("name") or "unknown"),
                "kernelPattern": kernel_patterns.get(
                    str(step.get("kernelName") or step.get("name") or "unknown"),
                    "unknown",
                ),
                "repeat": max(1, int(step.get("repeat") or 1)),
            }
            for index, step in enumerate(launches)
        ],
        runtime_config=runtime_config,
        normalized_execution=normalized_execution,
        reference=reference,
    )
    if runtime_scheduler.get("status") == "bound":
        schedule_records = runtime_scheduler.get("launches") or schedule_records
    launches_with_dataflow = sum(
        1 for record in schedule_records if record["symbolDataflowPresent"]
    )
    all_launches_carry_dataflow = bool(schedule_records) and (
        launches_with_dataflow == len(schedule_records)
    )
    scheduled_invocation_count = sum(record["repeat"] for record in schedule_records)
    schedule_status = (
        "symbol_dataflow_bound"
        if all_launches_carry_dataflow
        else "blocked_missing_symbol_dataflow"
    )
    schedule = {
        "schemaVersion": 1,
        "artifactKind": "int4ple_hostplan_launch_schedule",
        "status": schedule_status,
        "launchDescriptorCount": len(schedule_records),
        "scheduledInvocationCount": scheduled_invocation_count,
        "phaseDescriptorCounts": phase_counts,
        "phaseInvocationCounts": phase_invocation_counts,
        "kernelDescriptorCounts": count_by(schedule_records, "kernelName"),
        "kernelInvocationCounts": dict(sorted(kernel_invocation_counts.items())),
        "launchesWithSymbolDataflowCount": launches_with_dataflow,
        "allLaunchesCarrySymbolDataflow": all_launches_carry_dataflow,
        "launches": schedule_records,
    }
    schedule["scheduleSha256"] = sha256_json(schedule_records)
    return {
        "path": str(host_plan_path),
        "present": True,
        "phaseLaunchCounts": phase_counts,
        "phaseInvocationCounts": phase_invocation_counts,
        "kernelLaunchCounts": dict(sorted(declared_kernel_counts.items())),
        "kernelInvocationCounts": dict(sorted(kernel_invocation_counts.items())),
        "launchesCarrySymbolDataflow": all_launches_carry_dataflow,
        "firstLaunches": schedule_records[:SCHEDULE_PREVIEW_COUNT],
        "lastLaunches": schedule_records[-SCHEDULE_PREVIEW_COUNT:],
        "launchSchedule": schedule,
        "runtimeScheduler": runtime_scheduler,
    }


def runtime_input_summary(runtime_config: dict[str, Any]) -> dict[str, Any]:
    weight_mappings = runtime_config.get("weightMappings") or []
    state_buffers = runtime_config.get("stateBuffers") or []
    host_io_layout = runtime_config.get("hostIoLayout") or []
    if not isinstance(weight_mappings, list):
        weight_mappings = []
    if not isinstance(state_buffers, list):
        state_buffers = []
    if not isinstance(host_io_layout, list):
        host_io_layout = []
    synthetic_host_entries = [
        entry
        for entry in host_io_layout
        if isinstance(entry, dict)
        and isinstance(entry.get("sourceIdentity"), dict)
        and entry["sourceIdentity"].get("synthetic") is True
    ]
    weight_identity = runtime_config.get("weightIdentity") or {}
    return {
        "weightMappingCount": len(weight_mappings),
        "requiredWeightCount": int(weight_identity.get("requiredWeightCount") or 0),
        "missingWeightCount": int(weight_identity.get("missingWeightCount") or 0),
        "stateBufferKinds": sorted(
            str(item.get("kind"))
            for item in state_buffers
            if isinstance(item, dict) and item.get("kind")
        ),
        "hostIoRoleCounts": count_by(
            [entry for entry in host_io_layout if isinstance(entry, dict)],
            "bufferRole",
        ),
        "syntheticHostEntryCount": len(synthetic_host_entries),
    }


def reference_transcript_summary(
    export: dict[str, Any],
    reference_export_path: Path,
) -> dict[str, Any]:
    transcript = export.get("decodeTranscript") or {}
    generated = transcript.get("generatedTokenIds") or {}
    logits = transcript.get("logitsDigests") or []
    transcript_payload: dict[str, Any] = {}
    transcript_link = transcript.get("transcript") or {}
    linked_path = transcript_link.get("path")
    if isinstance(linked_path, str) and linked_path:
        candidate = resolve_artifact_path(reference_export_path, linked_path)
        if candidate.is_file():
            transcript_payload = load_json(candidate)
    kv_cache = transcript_payload.get("kvCache") or {}
    return {
        "status": transcript.get("status", "pending"),
        "requestedDecodeSteps": int(transcript.get("requestedDecodeSteps") or 0),
        "actualDecodeSteps": int(transcript.get("actualDecodeSteps") or 0),
        "stopReason": transcript.get("stopReason", "pending"),
        "generatedTokenCount": int(generated.get("tokenCount") or 0),
        "logitsDigestCount": len(logits) if isinstance(logits, list) else 0,
        "promptTokenCount": int((export.get("inputSetComponents") or {}).get("tokenCount") or 0),
        "kvCacheMode": kv_cache.get("mode", "not_captured"),
        "kvLayerDigestCount": int(kv_cache.get("layerDigestCount") or 0),
    }


def scheduler_readiness(
    *,
    plan_path: Path,
    plan: dict[str, Any],
    runtime_config: dict[str, Any],
    export: dict[str, Any],
    reference_export_path: Path,
    compile_root: Path,
) -> dict[str, Any]:
    compile_targets = compile_target_coverage(plan, compile_root)
    runtime_inputs = runtime_input_summary(runtime_config)
    reference = reference_transcript_summary(export, reference_export_path)
    normalized_execution = load_normalized_execution(plan_path)
    host_plan = host_plan_phase_summary(
        plan_path.parent / "host-plan.json",
        runtime_config=runtime_config,
        normalized_execution=normalized_execution,
        reference=reference,
    )
    runtime_scheduler = host_plan.get("runtimeScheduler") or {}
    activation = runtime_scheduler.get("activationRouting") or {}
    kv_schedule = runtime_scheduler.get("kvCacheSchedule") or {}
    transcript = runtime_scheduler.get("transcriptCaptureSchedule") or {}
    executor_preflight = host_plan_executor_preflight(
        compile_root=compile_root,
        runtime_config=runtime_config,
        reference=reference,
    )
    expected_runtime = plan.get("runtime") or {}
    readiness = {
        "phaseLaunchesMaterialized": bool(host_plan.get("phaseLaunchCounts")),
        "compileTargetsReady": compile_targets["allSourcesReady"]
        and compile_targets["allCompiledTargetsReady"],
        "weightMappingsReady": runtime_inputs["weightMappingCount"] > 0
        and runtime_inputs["missingWeightCount"] == 0,
        "stateBuffersDeclared": "kv_cache" in runtime_inputs["stateBufferKinds"],
        "referenceTranscriptReady": reference["status"] == "output_ready"
        and reference["actualDecodeSteps"] > 0
        and reference["generatedTokenCount"] == reference["actualDecodeSteps"]
        and reference["logitsDigestCount"] == reference["actualDecodeSteps"],
        "kvReferenceReady": reference["kvLayerDigestCount"] > 0,
        "launchesCarrySymbolDataflow": bool(host_plan["launchesCarrySymbolDataflow"]),
        "activationRoutingBound": activation.get("status") == "bound",
        "kvReadWriteScheduleBound": kv_schedule.get("status") == "bound",
        "transcriptEmittersBound": transcript.get("status") == "bound",
        "manifestShapePreflightPassed": executor_preflight.get("status") == "passed",
        "fullModelRuntimeExecutorBound": False,
    }
    blockers: list[str] = []
    if not readiness["compileTargetsReady"]:
        blockers.append("compiled_csl_targets_not_ready")
    if not readiness["weightMappingsReady"]:
        blockers.append("runtime_weight_mappings_incomplete")
    if not readiness["referenceTranscriptReady"]:
        blockers.append("doppler_reference_transcript_incomplete")
    if not readiness["kvReferenceReady"]:
        blockers.append("doppler_kv_reference_digest_missing")
    if not readiness["launchesCarrySymbolDataflow"]:
        blockers.append("hostplan_launches_lack_symbol_dataflow_bindings")
    if not readiness["activationRoutingBound"]:
        blockers.append("activation_tensor_lifetime_schedule_missing")
    if not readiness["kvReadWriteScheduleBound"]:
        blockers.append("kv_cache_write_read_schedule_missing")
    if not readiness["transcriptEmittersBound"]:
        blockers.append("logits_and_sample_output_capture_schedule_missing")
    metadata_ready = not blockers
    if metadata_ready and executor_preflight.get("status") == "failed":
        blockers.append("manifest_shape_preflight_failed")
    if metadata_ready:
        blockers.append("full_model_prefill_decode_runtime_executor_missing")
    status = (
        "blocked_missing_full_model_runtime_execution"
        if metadata_ready
        else "blocked_missing_runtime_scheduler"
    )
    return {
        "status": status,
        "readiness": readiness,
        "blockers": blockers,
        "expectedRuntime": {
            "prefillLaunchCount": int(expected_runtime.get("prefillLaunchCount") or 0),
            "decodeLaunchCount": int(expected_runtime.get("decodeLaunchCount") or 0),
            "maxDecodeTokens": expected_runtime.get("maxDecodeTokens"),
            "weightMappingCount": expected_runtime.get("weightMappingCount"),
            "stateBufferCount": expected_runtime.get("stateBufferCount"),
        },
        "hostPlan": host_plan,
        "compileTargetCoverage": compile_targets,
        "runtimeInputs": runtime_inputs,
        "referenceTranscript": reference,
        "hostPlanExecutor": {
            "status": "blocked",
            "fullModelRuntimeExecutorBound": False,
            "manifestShapePreflight": executor_preflight,
        },
        "nextRuntimeStep": (
            "replace the residual-only diagnostic run with a multi-target "
            "HostPlan interpreter that loads the bound symbols, moves "
            "activation/KV tensors between launches, captures logits/tokens, "
            "and emits the CSL transcript"
        ),
    }


def run_residual_target(
    *,
    compile_root: Path,
    diagnostic_compile_dir: Path | None,
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
    compile_dir = diagnostic_compile_dir or (compile_root / "compiled" / "residual")
    compile_dir_source = "compact_diagnostic" if diagnostic_compile_dir else "production"
    if not (compile_dir / "out.json").is_file():
        raise FileNotFoundError(f"missing compiled residual target: {compile_dir}")

    append_progress(
        progress_path,
        "runtime_create",
        target="residual",
        compileDir=str(compile_dir),
        compileDirSource=compile_dir_source,
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
        compileDirSource=compile_dir_source,
    )
    return {
        "target": "residual",
        "status": "succeeded",
        "compileDir": str(compile_dir),
        "compileDirSource": compile_dir_source,
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
    scheduler: dict[str, Any],
    cmaddr: str | None,
    started: float,
    kernel_results: list[dict[str, Any]],
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    elapsed_ms = (time.monotonic() - started) * 1000.0
    if scheduler.get("status") == "blocked_missing_full_model_runtime_execution":
        model_blocker = (
            "The HostPlan runtime scheduler has symbol-level dataflow, "
            "activation lifetime routing, KV read/write scheduling, and "
            "logit/token capture points bound, but this runner still only "
            "executes the residual diagnostic target. The full prefill/decode "
            "target interpreter has not executed the bound schedule."
        )
    else:
        model_blocker = (
            "HostPlan phase launches, weights, and the Doppler reference "
            "transcript are visible, but the runtime scheduler is not yet "
            "fully bound for symbol-level dataflow, activation routing, "
            "KV read/write scheduling, and logit/token capture."
        )
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
            "schedulerStatus": scheduler.get("status"),
        },
        "modelExecution": {
            "fullModelDepthExecuted": False,
            "blocker": model_blocker,
        },
        "hostPlanScheduler": scheduler,
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
        scheduler = scheduler_readiness(
            plan_path=Path(args.plan),
            plan=plan,
            runtime_config=runtime_config,
            export=export,
            reference_export_path=Path(args.reference_export),
            compile_root=Path(args.compile_root),
        )
        append_progress(
            progress_path,
            "scheduler_readiness",
            status=scheduler["status"],
            blockers=scheduler["blockers"],
        )
        residual_target = target_by_name(plan, "residual")
        diagnostic_compile_dir = (
            Path(args.diagnostic_compile_dir)
            if args.diagnostic_compile_dir.strip()
            else None
        )
        result = run_residual_target(
            compile_root=Path(args.compile_root),
            diagnostic_compile_dir=diagnostic_compile_dir,
            target=residual_target,
            trace_path=trace_path,
            progress_path=progress_path,
            cmaddr=cmaddr,
        )
        trace = diagnostic_trace(
            export=export,
            runtime_config=runtime_config,
            scheduler=scheduler,
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
                scheduler=scheduler_readiness(
                    plan_path=Path(args.plan),
                    plan=load_json(Path(args.plan)),
                    runtime_config=runtime_config,
                    export=export,
                    reference_export_path=Path(args.reference_export),
                    compile_root=Path(args.compile_root),
                ),
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
