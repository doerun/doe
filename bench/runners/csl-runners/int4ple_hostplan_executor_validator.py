#!/usr/bin/env python3
"""Fail-closed HostPlan executor validation for INT4 PLE schedules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

NO_PRODUCER_INPUT_ROLES = frozenset(
    {
        "tokenized_prompt",
        "weight",
        "kv_cache",
        "position_encoding",
        "position",
        "linear_attention_state",
        "uniform",
    }
)
PRODUCED_INPUT_ROLES = frozenset({"activation", "logits", "generated_tokens"})
OUTPUT_ROLES = frozenset({
    "activation",
    "logits",
    "generated_tokens",
    "kv_cache",
    "linear_attention_state",
})


def _target_names(plan: dict[str, Any]) -> set[str]:
    targets = (plan.get("inputs") or {}).get("compileTargets") or []
    return {
        str(target.get("name"))
        for target in targets
        if isinstance(target, dict) and target.get("name")
    }


def _compiled_out_path(compile_root: Path, target_name: str) -> Path:
    return compile_root / "compiled" / target_name / "out.json"


def _state_roots(runtime_config: dict[str, Any]) -> set[str]:
    roots: set[str] = set()
    for item in runtime_config.get("stateBuffers") or []:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            roots.add(item["name"])
    return roots


def _state_root(buffer: str) -> str:
    if not buffer.startswith("state:"):
        return ""
    return buffer.removeprefix("state:").split(":", 1)[0]


def _state_declared(buffer: str, states: set[str]) -> bool:
    root = _state_root(buffer)
    if not root:
        return False
    return root in states or buffer in {
        "state:rope_cos_table",
        "state:rope_sin_table",
    }


def _runtime_scheduler(scheduler: dict[str, Any]) -> dict[str, Any]:
    host_plan = scheduler.get("hostPlan") or {}
    if isinstance(host_plan, dict):
        runtime_scheduler = host_plan.get("runtimeScheduler")
        if isinstance(runtime_scheduler, dict):
            return runtime_scheduler
    runtime_scheduler = scheduler.get("runtimeScheduler")
    if isinstance(runtime_scheduler, dict):
        return runtime_scheduler
    if isinstance(scheduler.get("launches"), list):
        return scheduler
    return {}


def _append_missing_fields(
    *,
    blockers: list[str],
    launch_index: int,
    side: str,
    item_index: int,
    item: dict[str, Any],
    fields: tuple[str, ...],
) -> None:
    for field in fields:
        if item.get(field) in (None, ""):
            blockers.append(
                f"launch[{launch_index}].{side}[{item_index}].{field}_missing"
            )


def _symbol_table_candidates(resolved: dict[str, Any]) -> list[dict[str, Any]]:
    bindings = resolved.get("bindings")
    if isinstance(bindings, list):
        return [item for item in bindings if isinstance(item, dict)]
    return [resolved]


def _candidate_matches_item(
    candidate: dict[str, Any],
    item: dict[str, Any],
) -> bool:
    return all(candidate.get(field) == item.get(field) for field in (
        "buffer",
        "role",
        "access",
    ))


def _validate_binding_items(
    *,
    blockers: list[str],
    launch_index: int,
    side: str,
    items: Any,
    expected_access: str,
    symbol_table: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        blockers.append(f"launch[{launch_index}].{side}_not_list")
        return []
    parsed: list[dict[str, Any]] = []
    for item_index, item in enumerate(items):
        if not isinstance(item, dict):
            blockers.append(f"launch[{launch_index}].{side}[{item_index}]_not_object")
            continue
        _append_missing_fields(
            blockers=blockers,
            launch_index=launch_index,
            side=side,
            item_index=item_index,
            item=item,
            fields=("symbol", "buffer", "role", "access"),
        )
        if item.get("access") != expected_access:
            blockers.append(
                f"launch[{launch_index}].{side}[{item_index}].access="
                f"{item.get('access')!r}, expected {expected_access!r}"
            )
        symbol = str(item.get("symbol") or "")
        if symbol:
            resolved = symbol_table.get(symbol)
            if not isinstance(resolved, dict):
                blockers.append(
                    f"launch[{launch_index}].{side}[{item_index}].symbol_unresolved:"
                    f"{symbol}"
                )
            else:
                candidates = _symbol_table_candidates(resolved)
                if any(_candidate_matches_item(candidate, item) for candidate in candidates):
                    parsed.append(item)
                    continue
                first = candidates[0] if candidates else resolved
                for field in ("buffer", "role", "access"):
                    if first.get(field) != item.get(field):
                        blockers.append(
                            f"launch[{launch_index}].{side}[{item_index}]."
                            f"{field}_mismatch:{symbol}"
                        )
        parsed.append(item)
    return parsed


def _validate_transcript_emitters(
    *,
    blockers: list[str],
    transcript: dict[str, Any],
    produced_buffers: set[str],
    launch_indices: set[int],
) -> dict[str, Any]:
    emitters = transcript.get("emitters") or []
    if transcript.get("status") != "bound":
        blockers.append(f"transcript_capture_not_bound:{transcript.get('status')}")
    if not isinstance(emitters, list):
        blockers.append("transcript_capture_emitters_not_list")
        emitters = []
    logits_emitters = [item for item in emitters if item.get("kind") == "logits_digest"]
    token_emitters = [item for item in emitters if item.get("kind") == "generated_token"]
    expected_steps = int(transcript.get("expectedActualDecodeSteps") or 0)
    if expected_steps <= 0:
        blockers.append("transcript_expected_decode_steps_missing")
    if len(logits_emitters) != expected_steps:
        blockers.append(
            f"transcript_logits_emitter_count:{len(logits_emitters)}!={expected_steps}"
        )
    if len(token_emitters) != expected_steps:
        blockers.append(
            f"transcript_token_emitter_count:{len(token_emitters)}!={expected_steps}"
        )
    for index, emitter in enumerate(emitters):
        launch_index = emitter.get("launchIndex")
        if not isinstance(launch_index, int) or launch_index not in launch_indices:
            blockers.append(f"transcript.emitter[{index}].launchIndex_unresolved")
        buffer = str(emitter.get("buffer") or "")
        if not buffer:
            blockers.append(f"transcript.emitter[{index}].buffer_missing")
        elif buffer not in produced_buffers:
            blockers.append(f"transcript.emitter[{index}].buffer_unproduced:{buffer}")
        logits_buffer = emitter.get("logitsBuffer")
        if emitter.get("kind") == "generated_token":
            if not isinstance(logits_buffer, str) or not logits_buffer:
                blockers.append(f"transcript.emitter[{index}].logitsBuffer_missing")
            elif logits_buffer not in produced_buffers:
                blockers.append(
                    f"transcript.emitter[{index}].logitsBuffer_unproduced:{logits_buffer}"
                )
    return {
        "expectedDecodeSteps": expected_steps,
        "logitsEmitterCount": len(logits_emitters),
        "tokenEmitterCount": len(token_emitters),
    }


def _validate_kv_schedule(
    *,
    blockers: list[str],
    kv_schedule: dict[str, Any],
    launch_indices: set[int],
) -> dict[str, Any]:
    operations = kv_schedule.get("operations") or []
    if kv_schedule.get("status") != "bound":
        blockers.append(f"kv_cache_schedule_not_bound:{kv_schedule.get('status')}")
    if not isinstance(operations, list):
        blockers.append("kv_cache_operations_not_list")
        operations = []
    cache_write_count = int(kv_schedule.get("cacheWriteCount") or 0)
    cache_read_count = int(kv_schedule.get("cacheReadCount") or 0)
    if cache_write_count <= 0:
        blockers.append("kv_cache_write_count_zero")
    if cache_read_count <= 0:
        blockers.append("kv_cache_read_count_zero")
    coverage = kv_schedule.get("layerCoverage") or {}
    layer_count = int(coverage.get("layerCount") or 0)
    covered_layer_count = int(coverage.get("coveredLayerCount") or 0)
    if layer_count > 0 and covered_layer_count != layer_count:
        blockers.append(f"kv_cache_layer_coverage:{covered_layer_count}!={layer_count}")
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            blockers.append(f"kv_cache.operations[{index}]_not_object")
            continue
        launch_index = operation.get("launchIndex")
        if not isinstance(launch_index, int) or launch_index not in launch_indices:
            blockers.append(f"kv_cache.operations[{index}].launchIndex_unresolved")
        if not isinstance(operation.get("read"), dict):
            blockers.append(f"kv_cache.operations[{index}].read_missing")
        if not isinstance(operation.get("write"), dict):
            blockers.append(f"kv_cache.operations[{index}].write_missing")
        for side, required_fields in (
            ("read", ("keyBuffer", "valueBuffer", "cacheBuffer", "slidingWindowSource")),
            ("write", ("keyBuffer", "valueBuffer", "cacheBuffer", "positionSource")),
        ):
            entry = operation.get(side)
            if not isinstance(entry, dict):
                continue
            for field in required_fields:
                value = entry.get(field)
                if not isinstance(value, str) or not value:
                    blockers.append(
                        f"kv_cache.operations[{index}].{side}.{field}_missing"
                    )
    return {
        "cacheWriteCount": cache_write_count,
        "cacheReadCount": cache_read_count,
        "layerCoverage": coverage,
    }


def validate_hostplan_executor(
    *,
    plan: dict[str, Any],
    compile_root: Path,
    runtime_config: dict[str, Any],
    scheduler: dict[str, Any],
    manifest_preflight: dict[str, Any],
) -> dict[str, Any]:
    runtime_scheduler = _runtime_scheduler(scheduler)
    launches = runtime_scheduler.get("launches") or []
    blockers: list[str] = []
    checks: list[dict[str, Any]] = []
    target_names = _target_names(plan)
    states = _state_roots(runtime_config)
    produced_buffers: set[str] = {"input:prompt_token_ids"}
    launch_indices: set[int] = set()
    launched_targets: set[str] = set()
    compiled_targets: set[str] = set()
    compiled_target_status: dict[str, str] = {}

    if runtime_scheduler.get("status") != "bound":
        blockers.append(f"runtime_scheduler_not_bound:{runtime_scheduler.get('status')}")
    if manifest_preflight.get("status") != "passed":
        blockers.append(
            f"manifest_shape_preflight_not_passed:{manifest_preflight.get('status')}"
        )
    if not isinstance(launches, list) or not launches:
        blockers.append("runtime_scheduler_launches_missing")
        launches = []

    for launch_index, record in enumerate(launches):
        if not isinstance(record, dict):
            blockers.append(f"launch[{launch_index}]_not_object")
            continue
        runtime_launch_index = record.get("launchIndex")
        if not isinstance(runtime_launch_index, int):
            blockers.append(f"launch[{launch_index}].launchIndex_missing")
            runtime_launch_index = launch_index
        if runtime_launch_index in launch_indices:
            blockers.append(
                f"launch[{launch_index}].launchIndex_duplicate:{runtime_launch_index}"
            )
        else:
            launch_indices.add(runtime_launch_index)
        target_name = str(record.get("kernelName") or "")
        launched_targets.add(target_name)
        if not target_name:
            blockers.append(f"launch[{runtime_launch_index}].kernelName_missing")
        elif target_name not in target_names:
            blockers.append(
                f"launch[{runtime_launch_index}].kernelName_unresolved:{target_name}"
            )
        if target_name and target_name not in compiled_target_status:
            compiled_path = _compiled_out_path(compile_root, target_name)
            if not compiled_path.is_file():
                compiled_target_status[target_name] = "missing"
            else:
                try:
                    json.loads(compiled_path.read_text(encoding="utf-8"))
                    compiled_target_status[target_name] = "ready"
                except (OSError, json.JSONDecodeError):
                    compiled_target_status[target_name] = "unreadable"
        compiled_status = compiled_target_status.get(target_name)
        if target_name and compiled_status == "missing":
            blockers.append(
                f"launch[{runtime_launch_index}].compiled_target_missing:{target_name}"
            )
        elif target_name and compiled_status == "unreadable":
            blockers.append(
                f"launch[{runtime_launch_index}].compiled_target_unreadable:"
                f"{target_name}"
            )
        elif target_name and compiled_status == "ready":
            compiled_targets.add(target_name)
        if record.get("symbolDataflowPresent") is not True:
            blockers.append(
                f"launch[{runtime_launch_index}].symbol_dataflow_missing"
            )
        if not isinstance(record.get("symbols"), dict) or not record.get("symbols"):
            blockers.append(f"launch[{runtime_launch_index}].symbols_missing")
        symbol_table = record.get("symbols") if isinstance(record.get("symbols"), dict) else {}

        inputs = _validate_binding_items(
            blockers=blockers,
            launch_index=runtime_launch_index,
            side="inputs",
            items=record.get("inputs"),
            expected_access="read",
            symbol_table=symbol_table,
        )
        outputs = _validate_binding_items(
            blockers=blockers,
            launch_index=runtime_launch_index,
            side="outputs",
            items=record.get("outputs"),
            expected_access="write",
            symbol_table=symbol_table,
        )
        if not inputs:
            blockers.append(f"launch[{runtime_launch_index}].inputs_empty")
        if not outputs:
            blockers.append(f"launch[{runtime_launch_index}].outputs_empty")

        for item in inputs:
            role = str(item.get("role") or "")
            buffer = str(item.get("buffer") or "")
            if role in PRODUCED_INPUT_ROLES:
                if buffer not in produced_buffers:
                    blockers.append(
                        f"launch[{runtime_launch_index}].input_unproduced:{buffer}"
                    )
            elif role in NO_PRODUCER_INPUT_ROLES:
                if buffer.startswith("state:") and not _state_declared(buffer, states):
                    blockers.append(
                        f"launch[{runtime_launch_index}].state_input_undeclared:"
                        f"{buffer}"
                    )
                if item.get("status") == "missing":
                    blockers.append(
                        f"launch[{runtime_launch_index}].state_input_missing:"
                        f"{buffer}"
                    )
            elif role:
                blockers.append(
                    f"launch[{runtime_launch_index}].input_role_unsupported:{role}"
                )

        for item in outputs:
            role = str(item.get("role") or "")
            buffer = str(item.get("buffer") or "")
            if role not in OUTPUT_ROLES:
                blockers.append(
                    f"launch[{runtime_launch_index}].output_role_unsupported:{role}"
                )
                continue
            if not buffer:
                continue
            produced_buffers.add(buffer)

    activation = runtime_scheduler.get("activationRouting") or {}
    if activation.get("status") != "bound":
        blockers.append(f"activation_routing_not_bound:{activation.get('status')}")
    transcript_summary = _validate_transcript_emitters(
        blockers=blockers,
        transcript=runtime_scheduler.get("transcriptCaptureSchedule") or {},
        produced_buffers=produced_buffers,
        launch_indices=launch_indices,
    )
    kv_summary = _validate_kv_schedule(
        blockers=blockers,
        kv_schedule=runtime_scheduler.get("kvCacheSchedule") or {},
        launch_indices=launch_indices,
    )

    checks.append(
        {
            "id": "launched_targets_compiled",
            "actual": len(compiled_targets),
            "minimum": len(launched_targets),
            "passed": len(compiled_targets) == len(launched_targets),
        }
    )
    checks.append(
        {
            "id": "runtime_launches_validated",
            "actual": len(launch_indices),
            "minimum": len(launches),
            "passed": len(launch_indices) == len(launches),
        }
    )
    return {
        "schemaVersion": 1,
        "artifactKind": "int4ple_hostplan_executor_validation",
        "status": "passed" if not blockers else "blocked",
        "blockers": blockers,
        "checks": checks,
        "launchCount": len(launches),
        "validatedLaunchCount": len(launch_indices),
        "launchedTargetNames": sorted(launched_targets),
        "compiledTargetNames": sorted(compiled_targets),
        "producedBufferCount": len(produced_buffers),
        "manifestShapePreflightStatus": manifest_preflight.get("status"),
        "activationRoutingStatus": activation.get("status", "missing"),
        "kvCacheSchedule": kv_summary,
        "transcriptCaptureSchedule": transcript_summary,
    }
