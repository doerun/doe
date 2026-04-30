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
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import common
from bench.tools.int4ple_manifest_compile_params import (
    manifest_compile_param_projection,
    runtime_grid,
)
from bench.tools.doppler_rdrr_q4k import dequantize_q4km_rowwise_bytes
from int4ple_hostplan_execution_plan import build_hostplan_execution_plan
from int4ple_embed_roi import build_embed_roi_spec
from int4ple_hostplan_executor_validator import validate_hostplan_executor
from int4ple_summa_layout import (
    a_tiles_from_logical as _summa_a_tiles_from_logical,
    b_tiles_from_weight_matrix as _summa_b_tiles_from_weight_matrix,
    b_tiles_from_q4k_bytes as _summa_b_tiles_from_q4k_bytes,
    required_positive_int as _required_positive_int,
)
from int4ple_runtime_scheduler import (
    count_by,
    load_normalized_execution,
    resolve_artifact_path,
    sha256_json,
    synthesize_runtime_scheduler,
)
from int4ple_checkpoint import (
    CheckpointError,
    CheckpointMissingError,
    compute_identity as _compute_checkpoint_identity,
    compute_launch_identity as _compute_launch_identity,
    init_checkpoint as _init_checkpoint,
    load_checkpoint as _load_checkpoint,
    persist_launch_checkpoint as _persist_launch_checkpoint,
)

SCHEDULE_PREVIEW_COUNT = 4
TARGET_SESSION_PROBE = Path(__file__).with_name("int4ple_target_session_probe.py")
LAUNCH_STEP_ADAPTER = Path(__file__).with_name("int4ple_launch_step_adapter.py")
EMBED_ROI_ADAPTER = Path(__file__).with_name("int4ple_embed_roi_adapter.py")
DEFAULT_LAUNCH_TIMEOUT_SECONDS = 3600
EMBED_ROI_TARGETS = frozenset({"embed", "ple_embed"})
DEFAULT_CS_PYTHON_CANDIDATES = (
    "/home/x/cerebras-sdk-2.10.0/cs_python",
    "/home/x/cerebras-sdk/cs_python",
)
DEFAULT_CSLC_CANDIDATES = (
    "/home/x/cerebras-sdk/cslc",
    "/home/x/cerebras-sdk-2.10.0/cslc",
)


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
    parser.add_argument(
        "--checkpoint-dir",
        default="",
        help="Persist per-launch HostPlan checkpoints under this directory.",
    )
    parser.add_argument(
        "--resume-from-checkpoint",
        default="",
        help="Validate the manifest under this directory and skip launches "
        "already recorded as succeeded. May share a path with --checkpoint-dir.",
    )
    parser.add_argument(
        "--stop-after-launch",
        type=int,
        default=-1,
        help="If >=0, break the launch loop after persisting the checkpoint "
        "for this launch index.",
    )
    parser.add_argument(
        "--launch-timeout-seconds",
        type=int,
        default=DEFAULT_LAUNCH_TIMEOUT_SECONDS,
        help="Per HostPlan launch-step subprocess timeout. Use 0 to disable.",
    )
    parser.add_argument(
        "--ignore-checkpoint",
        action="store_true",
        help="Run from launch 0 even if --resume-from-checkpoint points at a "
        "valid checkpoint. Disables identity validation.",
    )
    return parser.parse_args()


def _runner_version() -> str:
    """Best-effort runner identity tag.

    Uses the runner file's sha256 so any logic edit invalidates the
    checkpoint. Falls back to a literal constant if the file is unreadable.
    """
    try:
        return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]
    except OSError:
        return "unknown"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def tail_lines(value: str | bytes | None, count: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    stripped = value.strip()
    return stripped.splitlines()[-count:] if stripped else []


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


def cs_python_executable() -> str:
    for env_key in ("DOE_CSL_RUNTIME_EXECUTABLE", "DOE_CSL_CS_PYTHON"):
        candidate = os.environ.get(env_key, "").strip()
        if candidate and Path(candidate).is_file():
            return candidate
    sdk_root = os.environ.get("DOE_CSL_SDK_ROOT", "").strip()
    if sdk_root:
        candidate = Path(sdk_root) / "cs_python"
        if candidate.is_file():
            return str(candidate)
    for candidate in DEFAULT_CS_PYTHON_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    discovered = shutil.which("cs_python")
    if discovered:
        return discovered
    return "cs_python"


def cslc_executable() -> str:
    candidate = os.environ.get("DOE_CSLC_EXECUTABLE", "").strip()
    if candidate and Path(candidate).is_file():
        return candidate
    sdk_root = os.environ.get("DOE_CSL_SDK_ROOT", "").strip()
    if sdk_root:
        candidate_path = Path(sdk_root) / "cslc"
        if candidate_path.is_file():
            return str(candidate_path)
    for candidate_path in DEFAULT_CSLC_CANDIDATES:
        if Path(candidate_path).is_file():
            return candidate_path
    discovered = shutil.which("cslc")
    if discovered:
        return discovered
    return "cslc"


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
        "lm_head_gemv",
        "lm_head_gemv_stable",
        "lm_head_prefill_stable",
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

    global_head_dim = int(model.get("globalHeadDim") or 0)
    for target_name in ("attn_head256", "attn_head512"):
        params = target_params.get(target_name) or {}
        if not params:
            if target_name == "attn_head512" and global_head_dim <= 0:
                continue
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

    lm_head = (
        target_params.get("lm_head_gemv")
        or target_params.get("lm_head_gemv_stable")
        or target_params.get("lm_head_prefill_stable")
        or {}
    )
    if lm_head:
        if "out_dim_per_pe" in lm_head:
            logits_coverage = int(lm_head.get("height") or 0) * int(
                lm_head.get("out_dim_per_pe") or 0
            )
        elif "out_dim" in lm_head:
            logits_coverage = int(lm_head.get("width") or 0) * int(
                lm_head.get("out_dim") or 0
            )
        else:
            logits_coverage = int(lm_head.get("P") or 0) * int(
                lm_head.get("Nt") or 0
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
    executor_validator = validate_hostplan_executor(
        plan=plan,
        compile_root=compile_root,
        runtime_config=runtime_config,
        scheduler={"hostPlan": host_plan},
        manifest_preflight=executor_preflight,
    )
    execution_plan = build_hostplan_execution_plan(
        plan=plan,
        compile_root=compile_root,
        runtime_config=runtime_config,
        scheduler={"hostPlan": host_plan},
        executor_validator=executor_validator,
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
        "hostPlanExecutorValidatorPassed": executor_validator.get("status") == "passed",
        "hostPlanExecutionPlanReady": execution_plan.get("status") == "planned",
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
    if metadata_ready and not readiness["hostPlanExecutorValidatorPassed"]:
        blockers.append("hostplan_executor_validator_not_passed")
    elif metadata_ready and not readiness["hostPlanExecutionPlanReady"]:
        blockers.append("hostplan_execution_plan_not_ready")
    elif metadata_ready:
        blockers.append("full_model_prefill_decode_runtime_executor_missing")
    status = (
        "blocked_missing_full_model_runtime_execution"
        if metadata_ready
        and readiness["hostPlanExecutorValidatorPassed"]
        and readiness["hostPlanExecutionPlanReady"]
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
            "executorValidator": executor_validator,
            "executionPlan": execution_plan,
        },
        "nextRuntimeStep": (
            "stage runtime weight/input buffers onto the concrete HostPlan "
            "execution plan, execute the launch chain, and emit the bounded "
            "logit/token/KV transcript"
        ),
    }


def _probe_target_session_command(
    *,
    target_session: dict[str, Any],
    receipt_path: Path,
    cmaddr: str | None,
) -> list[str]:
    command = [
        cs_python_executable(),
        str(TARGET_SESSION_PROBE),
        "--compile-dir",
        str(target_session.get("compileDir") or ""),
        "--launch-fn",
        str(target_session.get("launchFunction") or "compute"),
        "--receipt-out",
        str(receipt_path),
    ]
    required_symbols = sorted(
        {
            str(symbol)
            for symbol in (
                (target_session.get("requiredInputSymbols") or [])
                + (target_session.get("requiredOutputSymbols") or [])
            )
            if isinstance(symbol, str) and symbol
        }
    )
    for symbol in required_symbols:
        command.extend(["--symbol", symbol])
    if cmaddr is not None:
        command.extend(["--cmaddr", cmaddr])
    return command


def probe_target_session(
    *,
    target_session: dict[str, Any],
    progress_path: Path,
    cmaddr: str | None,
) -> dict[str, Any]:
    target_name = str(target_session.get("targetName") or "unknown")
    if not TARGET_SESSION_PROBE.is_file():
        return {
            "schemaVersion": 1,
            "artifactKind": "int4ple_target_session_probe",
            "status": "blocked",
            "targetName": target_name,
            "compileDir": str(target_session.get("compileDir") or ""),
            "launchFunction": str(target_session.get("launchFunction") or "compute"),
            "resolvedSymbols": {},
            "blockers": [f"target_session_probe_missing:{TARGET_SESSION_PROBE}"],
        }

    with tempfile.TemporaryDirectory(prefix="int4ple-session-probe-") as tmpdir:
        receipt_path = Path(tmpdir) / f"{target_name}-probe.json"
        required_symbol_count = len(
            {
                str(symbol)
                for symbol in (
                    (target_session.get("requiredInputSymbols") or [])
                    + (target_session.get("requiredOutputSymbols") or [])
                )
                if isinstance(symbol, str) and symbol
            }
        )
        command = _probe_target_session_command(
            target_session=target_session,
            receipt_path=receipt_path,
            cmaddr=cmaddr,
        )
        append_progress(
            progress_path,
            "hostplan_target_session_probe_start",
            target=target_name,
            symbolCount=required_symbol_count,
            compileDir=str(target_session.get("compileDir") or ""),
        )
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        if receipt_path.is_file():
            receipt = load_json(receipt_path)
        else:
            receipt = {
                "schemaVersion": 1,
                "artifactKind": "int4ple_target_session_probe",
                "status": "blocked",
                "targetName": target_name,
                "compileDir": str(target_session.get("compileDir") or ""),
                "launchFunction": str(target_session.get("launchFunction") or "compute"),
                "resolvedSymbols": {},
                "blockers": ["target_session_probe_receipt_missing"],
            }
        blockers = list(receipt.get("blockers") or [])
        if completed.returncode != 0 and "target_session_probe_return_code" not in blockers:
            blockers.append(f"target_session_probe_return_code:{completed.returncode}")
        receipt["blockers"] = blockers
        if blockers:
            receipt["status"] = "blocked"
        if completed.stdout.strip():
            receipt["stdout"] = completed.stdout.strip().splitlines()[-1]
        if completed.stderr.strip():
            receipt["stderr"] = completed.stderr.strip().splitlines()[-1]
        append_progress(
            progress_path,
            "hostplan_target_session_probe_complete",
            target=target_name,
            status=receipt.get("status"),
            blockers=receipt.get("blockers"),
        )
        return receipt


def execute_hostplan_runtime_bootstrap(
    *,
    execution_plan: dict[str, Any],
    progress_path: Path,
    cmaddr: str | None,
    probe_session: Any | None = None,
) -> dict[str, Any]:
    probe_fn = probe_target_session if probe_session is None else probe_session
    blockers: list[str] = []
    target_sessions = execution_plan.get("targetSessions") or []
    launches = execution_plan.get("launches") or []
    if not isinstance(target_sessions, list) or not target_sessions:
        blockers.append("execution_plan_target_sessions_missing")
        target_sessions = []
    if not isinstance(launches, list) or not launches:
        blockers.append("execution_plan_launches_missing")
        launches = []

    append_progress(
        progress_path,
        "hostplan_executor_bootstrap_start",
        targetSessionCount=len(target_sessions),
        launchCount=len(launches),
    )

    resolved_by_target: dict[str, dict[str, Any]] = {}
    target_receipts: list[dict[str, Any]] = []
    for target_session in target_sessions:
        if not isinstance(target_session, dict):
            blockers.append("target_session_not_object")
            continue
        receipt = probe_fn(
            target_session=target_session,
            progress_path=progress_path,
            cmaddr=cmaddr,
        )
        target_name = str(target_session.get("targetName") or "unknown")
        target_receipts.append(receipt)
        if receipt.get("status") != "resolved":
            blockers.append(f"target_session_not_resolved:{target_name}")
            for blocker in receipt.get("blockers") or []:
                blockers.append(f"target[{target_name}]:{blocker}")
            continue
        resolved_symbols = receipt.get("resolvedSymbols") or {}
        if not isinstance(resolved_symbols, dict) or not resolved_symbols:
            blockers.append(f"target[{target_name}].resolved_symbols_missing")
            continue
        resolved_by_target[target_name] = resolved_symbols

    launch_receipts: list[dict[str, Any]] = []
    resolved_launch_count = 0
    for launch in launches:
        if not isinstance(launch, dict):
            blockers.append("launch_not_object")
            continue
        target_name = str(launch.get("targetName") or "")
        launch_index = int(launch.get("launchIndex") or len(launch_receipts))
        launch_blockers: list[str] = []
        target_symbols = resolved_by_target.get(target_name) or {}
        resolved_inputs: list[dict[str, Any]] = []
        resolved_outputs: list[dict[str, Any]] = []

        for side, source_items, resolved_items in (
            ("input", launch.get("inputBindings") or [], resolved_inputs),
            ("output", launch.get("outputBindings") or [], resolved_outputs),
        ):
            for item in source_items:
                if not isinstance(item, dict):
                    launch_blockers.append(f"launch[{launch_index}].{side}_binding_not_object")
                    continue
                symbol = str(item.get("symbol") or "")
                symbol_id = target_symbols.get(symbol)
                if symbol_id is None:
                    launch_blockers.append(
                        f"launch[{launch_index}].{side}_symbol_id_missing:{target_name}.{symbol}"
                    )
                resolved_items.append({**item, "symbolId": symbol_id})

        launch_status = "resolved" if not launch_blockers else "blocked"
        if launch_status == "resolved":
            resolved_launch_count += 1
        blockers.extend(launch_blockers)
        launch_receipts.append(
            {
                "launchIndex": launch_index,
                "targetName": target_name,
                "compileDir": launch.get("compileDir"),
                "compileParams": launch.get("compileParams") or {},
                "launchFunction": launch.get("launchFunction"),
                "targetGeometry": launch.get("targetGeometry") or {},
                "phase": launch.get("phase"),
                "decodeStepIndex": launch.get("decodeStepIndex"),
                "status": launch_status,
                "resolvedInputs": resolved_inputs,
                "resolvedOutputs": resolved_outputs,
                "runtimeActions": launch.get("runtimeActions") or [],
                "blockers": launch_blockers,
            }
        )

    status = "ready_for_tensor_movement" if not blockers else "blocked"
    receipt = {
        "schemaVersion": 1,
        "artifactKind": "int4ple_hostplan_executor_runtime_bootstrap",
        "status": status,
        "blockers": blockers,
        "cmaddrProvided": cmaddr is not None,
        "targetSessionCount": len(target_sessions),
        "targetSessionsLoadedCount": len(resolved_by_target),
        "launchCount": len(launches),
        "resolvedLaunchCount": resolved_launch_count,
        "targetSessions": target_receipts,
        "launches": launch_receipts,
        "bufferPlan": execution_plan.get("bufferPlan") or {},
        "nextAction": (
            "stage runtime weights and prompt/state buffers, execute each launch, "
            "and capture the bounded logit/token/KV transcript"
        ),
    }
    append_progress(
        progress_path,
        "hostplan_executor_bootstrap_complete",
        status=status,
        blockers=blockers,
        resolvedLaunchCount=resolved_launch_count,
    )
    return receipt


def _tokenized_prompt_path(export: dict[str, Any]) -> Path:
    tokenized = export.get("tokenizedPrompt") or {}
    raw_path = tokenized.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("tokenized prompt path missing")
    return resolve_artifact_path(Path(__file__), raw_path)


def _load_tokenized_prompt(export: dict[str, Any], expected_per_pe: int, pe_count: int) -> np.ndarray:
    prompt_path = _tokenized_prompt_path(export)
    tokens = np.fromfile(prompt_path, dtype=np.uint32)
    padded = np.zeros(expected_per_pe, dtype=np.uint32)
    count = min(tokens.size, expected_per_pe)
    if count > 0:
        padded[:count] = tokens[:count]
    return np.tile(padded, pe_count)


def _read_weight_prefix_bytes(weight_mapping: dict[str, Any], byte_count: int) -> bytes:
    remaining = byte_count
    chunks = bytearray()
    spans = weight_mapping.get("spans") or []
    if isinstance(spans, list) and spans:
        for span in spans:
            if remaining <= 0:
                break
            if not isinstance(span, dict):
                continue
            shard_path = Path(str(span.get("shardPath") or ""))
            offset = int(span.get("offset") or 0)
            size = min(int(span.get("size") or 0), remaining)
            if not shard_path.is_file():
                raise FileNotFoundError(f"weight shard missing: {shard_path}")
            with shard_path.open("rb") as handle:
                handle.seek(offset)
                payload = handle.read(size)
            chunks.extend(payload)
            remaining -= len(payload)
    else:
        shard_path = Path(str(weight_mapping.get("path") or weight_mapping.get("shard") or ""))
        offset = int(weight_mapping.get("byteOffset") or weight_mapping.get("offsetBytes") or 0)
        if not shard_path.is_file():
            raise FileNotFoundError(f"weight shard missing: {shard_path}")
        with shard_path.open("rb") as handle:
            handle.seek(offset)
            chunks.extend(handle.read(byte_count))
        remaining = byte_count - len(chunks)
    if remaining > 0:
        raise ValueError(
            f"weight bytes unavailable:{weight_mapping.get('weightKey') or weight_mapping.get('tensor')} "
            f"{byte_count - remaining}<{byte_count}"
        )
    return bytes(chunks[:byte_count])


def _materialize_weight_matrix_q4k_bytes(
    mapping: dict[str, Any],
    transform: dict[str, Any],
) -> np.ndarray:
    """Read raw Q4_K_M bytes for the [N, K] weight matrix without dequantizing.

    Mirror of ``_materialize_weight_matrix_f32`` for the Q4K passthrough
    path: on-PE dequant materializes the f32 working tile from these
    bytes inside the SUMMA broadcast step.
    """
    nested = transform.get("sourceTransform") or {}
    if not isinstance(nested, dict):
        nested = {}
    nested_kind = str(nested.get("kind") or "")
    if nested_kind != "q4km_rowwise_passthrough":
        raise ValueError(
            "unsupported_summa_q4k_source_transform:"
            f"{mapping.get('weightKey') or mapping.get('tensor')}:{nested_kind or 'none'}"
        )
    byte_count = int(mapping.get("byteSize") or 0)
    if byte_count <= 0:
        raise ValueError(
            "summa_q4k_byte_size_missing:"
            f"{mapping.get('weightKey') or mapping.get('tensor')}"
        )
    raw = _read_weight_prefix_bytes(mapping, byte_count)
    return np.frombuffer(raw, dtype=np.uint8).copy()


def _materialize_weight_matrix_f32(
    mapping: dict[str, Any],
    transform: dict[str, Any],
) -> np.ndarray:
    nested = transform.get("sourceTransform") or {}
    if not isinstance(nested, dict):
        nested = {}
    nested_kind = str(nested.get("kind") or "")
    source_rows = _required_positive_int(transform, "sourceRows")
    source_cols = _required_positive_int(transform, "sourceCols")
    element_count = source_rows * source_cols
    if nested_kind == "q4km_rowwise_to_f32":
        byte_count = int(mapping.get("byteSize") or 0)
        raw = _read_weight_prefix_bytes(mapping, byte_count)
        values = dequantize_q4km_rowwise_bytes(raw, [source_rows, source_cols])
        return np.asarray(values, dtype=np.float32)
    if nested_kind in {"f16_to_f32", "litert_axis_dequant"}:
        raw = _read_weight_prefix_bytes(mapping, element_count * 2)
        return np.frombuffer(raw, dtype=np.float16).astype(np.float32, copy=True)
    if nested_kind == "bf16_to_f32":
        raw = _read_weight_prefix_bytes(mapping, element_count * 2)
        bf16_words = np.frombuffer(raw, dtype=np.uint16).astype(np.uint32, copy=False)
        return (bf16_words << 16).view(np.float32).copy()
    if nested_kind in {"", "none"} and str(mapping.get("dtype") or "") == "f32":
        raw = _read_weight_prefix_bytes(mapping, element_count * 4)
        return np.frombuffer(raw, dtype=np.float32).copy()
    raise ValueError(
        "unsupported_summa_weight_source_transform:"
        f"{mapping.get('weightKey') or mapping.get('tensor')}:{nested_kind or 'none'}"
    )


def _dense_gemv_weight_shards(
    mapping: dict[str, Any],
    transform: dict[str, Any],
) -> np.ndarray:
    source_rows = _required_positive_int(transform, "sourceRows")
    source_cols = _required_positive_int(transform, "sourceCols")
    logical_cols = _required_positive_int(transform, "logicalCols")
    width = _required_positive_int(transform, "width")
    height = _required_positive_int(transform, "height")
    out_dim = _required_positive_int(transform, "outDim")
    out_dim_per_pe = _required_positive_int(transform, "outDimPerPe")
    in_dim_per_pe = _required_positive_int(transform, "inDimPerPe")
    if str(mapping.get("dtype") or "") != "f16":
        raise ValueError(
            "dense_gemv_weight_requires_f16:"
            f"{mapping.get('weightKey') or mapping.get('tensor')}"
        )
    raw = _read_weight_prefix_bytes(mapping, source_rows * source_cols * 2)
    matrix = np.frombuffer(raw, dtype=np.float16).reshape(source_rows, source_cols)
    values = np.zeros(
        (height, width, out_dim_per_pe, in_dim_per_pe),
        dtype=np.float16,
    )
    for pe_y in range(height):
        row_start = pe_y * out_dim_per_pe
        row_end = min(row_start + out_dim_per_pe, out_dim, source_rows)
        if row_end <= row_start:
            continue
        for pe_x in range(width):
            col_start = pe_x * in_dim_per_pe
            col_end = min(col_start + in_dim_per_pe, logical_cols, source_cols)
            if col_end <= col_start:
                continue
            values[
                pe_y,
                pe_x,
                : row_end - row_start,
                : col_end - col_start,
            ] = matrix[row_start:row_end, col_start:col_end]
    return values.reshape(-1)


def _dense_gemv_activation_shards(
    host: np.ndarray,
    transform: dict[str, Any],
) -> np.ndarray:
    width = _required_positive_int(transform, "width")
    height = _required_positive_int(transform, "height")
    in_dim_per_pe = _required_positive_int(transform, "inDimPerPe")
    source_elements = _required_positive_int(transform, "sourceElements")
    logical = np.asarray(host[:source_elements], dtype=np.float16)
    values = np.zeros((height, width, in_dim_per_pe), dtype=np.float16)
    for pe_x in range(width):
        col_start = pe_x * in_dim_per_pe
        col_end = min(col_start + in_dim_per_pe, logical.size)
        if col_end <= col_start:
            continue
        values[:, pe_x, : col_end - col_start] = logical[col_start:col_end]
    return values.reshape(-1)


def _broadcast_factor_or_one(
    *,
    mapping: dict[str, Any],
    materialization: dict[str, Any],
    source_byte_width: int,
    total_elements: int,
) -> int:
    """Detect broadcast weights (e.g. layernorm scale vectors) where the source
    tensor holds one PE's worth of bytes and is meant to be replicated across
    every PE in the target grid. Returns the replication factor when the shape
    fits exactly; returns 1 (no broadcast) otherwise.

    A match requires: source byteSize == elementsPerPe * source_byte_width,
    AND elementsPerPe * peCount == total_elements. This avoids false positives
    on truncated or malformed weight mappings.
    """
    elements_per_pe = int(materialization.get("elementsPerPe") or 0)
    geometry = materialization.get("targetGeometry") or {}
    pe_count = int(geometry.get("peCount") or 0)
    if elements_per_pe <= 0 or pe_count <= 1:
        return 1
    try:
        source_bytes = int(mapping.get("byteSize") or 0)
    except (TypeError, ValueError):
        return 1
    if source_bytes != elements_per_pe * source_byte_width:
        return 1
    if elements_per_pe * pe_count != total_elements:
        return 1
    return pe_count


def _materialize_weight_input(
    materialization: dict[str, Any],
) -> np.ndarray:
    mapping = materialization.get("weightMapping")
    if not isinstance(mapping, dict):
        raise ValueError("weight mapping missing")
    dtype = str(materialization.get("dtype") or "")
    total_elements = int(materialization.get("plannedElementCount") or 0)
    source_transform = materialization.get("sourceTransform") or {}
    transform_kind = (
        str(source_transform.get("kind") or "")
        if isinstance(source_transform, dict)
        else ""
    )
    if dtype == "f32" and transform_kind == "weight_matrix_to_summa_tiles":
        matrix = _materialize_weight_matrix_f32(mapping, source_transform)
        values = _summa_b_tiles_from_weight_matrix(matrix, source_transform)
        if values.size != total_elements:
            raise ValueError(
                f"weight_summa_tile_size_mismatch:{values.size}!={total_elements}"
            )
        return values
    if dtype == "q4k_block256" and transform_kind == "weight_matrix_to_summa_q4k_tiles":
        # Q4K passthrough: ship 144-byte blocks per 256-weight chunk to
        # the fabric without host-side dequant. The PE program runs
        # `dequant_b_tile()` as a per-broadcast-step prologue (see
        # runtime/zig/src/doe_wgsl/emit_csl_matmul_q4k.zig).
        # plannedElementCount is in BYTES for this dtype, not weights.
        raw_bytes = _materialize_weight_matrix_q4k_bytes(mapping, source_transform)
        values = _summa_b_tiles_from_q4k_bytes(raw_bytes, source_transform)
        if values.size != total_elements:
            raise ValueError(
                f"weight_summa_q4k_tile_byte_mismatch:{values.size}!={total_elements}"
            )
        return values
    if dtype == "f16" and transform_kind == "tied_f16_embedding_to_dense_gemv_shards":
        values = _dense_gemv_weight_shards(mapping, source_transform)
        if values.size != total_elements:
            raise ValueError(
                f"weight_dense_gemv_shard_size_mismatch:{values.size}!={total_elements}"
            )
        return values
    if dtype == "f32" and transform_kind in {"f16_to_f32", "litert_axis_dequant"}:
        broadcast = _broadcast_factor_or_one(
            mapping=mapping,
            materialization=materialization,
            source_byte_width=2,
            total_elements=total_elements,
        )
        per_pe_elements = total_elements // broadcast
        raw = _read_weight_prefix_bytes(mapping, per_pe_elements * 2)
        per_pe = np.frombuffer(raw, dtype=np.float16).astype(np.float32, copy=True)
        values = np.tile(per_pe, broadcast) if broadcast > 1 else per_pe
        if values.size != total_elements:
            raise ValueError(f"weight_f16_to_f32_size_mismatch:{values.size}!={total_elements}")
        return values
    if dtype == "f32" and transform_kind == "bf16_to_f32":
        broadcast = _broadcast_factor_or_one(
            mapping=mapping,
            materialization=materialization,
            source_byte_width=2,
            total_elements=total_elements,
        )
        per_pe_elements = total_elements // broadcast
        raw = _read_weight_prefix_bytes(mapping, per_pe_elements * 2)
        bf16_words = np.frombuffer(raw, dtype=np.uint16).astype(np.uint32, copy=False)
        per_pe = (bf16_words << 16).view(np.float32).copy()
        values = np.tile(per_pe, broadcast) if broadcast > 1 else per_pe
        if values.size != total_elements:
            raise ValueError(f"weight_bf16_to_f32_size_mismatch:{values.size}!={total_elements}")
        return values
    if dtype == "u32" and transform_kind == "u8_bytes_to_u32_words":
        raw = _read_weight_prefix_bytes(mapping, total_elements * 4)
        values = np.frombuffer(raw, dtype=np.uint32).copy()
        if values.size != total_elements:
            raise ValueError(f"weight_u8_to_u32_size_mismatch:{values.size}!={total_elements}")
        return values
    raise ValueError(
        "unsupported_weight_materialization:"
        f"{mapping.get('weightKey') or mapping.get('tensor')}:{dtype}:{transform_kind or 'none'}"
    )


def _materialize_constant_input(
    *,
    materialization: dict[str, Any],
    export: dict[str, Any],
) -> np.ndarray:
    dtype = str(materialization.get("dtype") or "")
    elements_per_pe = int(materialization.get("elementsPerPe") or 0)
    geometry = materialization.get("targetGeometry") or {}
    pe_count = int(geometry.get("peCount") or 1)
    role = str(materialization.get("role") or "")
    buffer = str(materialization.get("buffer") or "")
    if role == "tokenized_prompt":
        return _load_tokenized_prompt(export, elements_per_pe, pe_count)
    if role == "position_encoding":
        count = elements_per_pe
        pairs = np.arange(count, dtype=np.float32)
        values = np.cos(pairs) if buffer.endswith("cos_table") else np.sin(pairs)
        return np.tile(values.astype(np.float32), pe_count)
    if role == "position":
        value = 0
        if buffer.endswith("sliding_window"):
            value = 512
        return np.full(pe_count * max(1, elements_per_pe), value, dtype=np.uint32)
    if role == "uniform":
        return np.zeros(pe_count * max(1, elements_per_pe), dtype=np.uint32)
    if role == "kv_cache":
        return np.zeros(pe_count * max(1, elements_per_pe), dtype=np.float32)
    raise ValueError(f"unsupported_constant_input:{role}:{buffer}:{dtype}")


def _transform_existing_input(
    host: np.ndarray,
    materialization: dict[str, Any],
) -> tuple[np.ndarray, dict[str, int]]:
    source_transform = materialization.get("sourceTransform") or {}
    if not isinstance(source_transform, dict):
        return host, {}
    transform_kind = str(source_transform.get("kind") or "")
    if transform_kind == "logical_matrix_to_summa_tiles":
        values, rows = _summa_a_tiles_from_logical(host, source_transform)
        return values, {
            "rows": rows,
            "cols": _required_positive_int(source_transform, "sourceCols"),
        }
    if transform_kind == "logical_vector_to_dense_gemv_activation_shards":
        return _dense_gemv_activation_shards(host, source_transform), {}
    return host, {}


def _launch_spec_path(runtime_dir: Path, launch_index: int) -> Path:
    return runtime_dir / "launch-specs" / f"launch-{launch_index:04d}.json"


def _launch_receipt_path(runtime_dir: Path, launch_index: int) -> Path:
    return runtime_dir / "launch-receipts" / f"launch-{launch_index:04d}.json"


def _buffer_path(runtime_dir: Path, buffer_name: str) -> Path:
    safe = hashlib.sha256(buffer_name.encode("utf-8")).hexdigest()
    return runtime_dir / "buffers" / f"{safe}.npy"


def _staged_input_path(
    runtime_dir: Path,
    launch_index: int,
    symbol: str,
    buffer_name: str,
) -> Path:
    safe = hashlib.sha256(f"{launch_index}:{symbol}:{buffer_name}".encode("utf-8")).hexdigest()
    return runtime_dir / "staged-inputs" / f"{safe}.npy"


def _stage_launch_arrays(
    *,
    runtime_dir: Path,
    launch: dict[str, Any],
    buffer_files: dict[str, Path],
    export: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    staged_inputs: list[dict[str, Any]] = []
    staged_outputs: list[dict[str, Any]] = []
    matrix_shapes: dict[str, dict[str, int]] = {}
    for side, source_items, staged in (
        ("input", launch.get("resolvedInputs") or [], staged_inputs),
        ("output", launch.get("resolvedOutputs") or [], staged_outputs),
    ):
        for item in source_items:
            if not isinstance(item, dict):
                raise ValueError(f"launch[{launch.get('launchIndex')}].{side}_binding_not_object")
            materialization = item.get("materialization") or {}
            if not isinstance(materialization, dict):
                raise ValueError(
                    f"launch[{launch.get('launchIndex')}].{side}_materialization_missing"
                )
            buffer_name = str(item.get("buffer") or "")
            role = str(item.get("role") or "")
            symbol = str(item.get("symbol") or "")
            path = _buffer_path(runtime_dir, buffer_name)
            if side == "input":
                existing = buffer_files.get(buffer_name)
                total_elements = int(materialization.get("plannedElementCount") or 0)
                source_transform = materialization.get("sourceTransform") or {}
                transform_kind = (
                    str(source_transform.get("kind") or "")
                    if isinstance(source_transform, dict)
                    else ""
                )
                cache_buffer_file = role != "weight" and transform_kind not in {
                    "logical_matrix_to_summa_tiles",
                    "weight_matrix_to_summa_tiles",
                    "logical_vector_to_dense_gemv_activation_shards",
                    "tied_f16_embedding_to_dense_gemv_shards",
                }
                if not cache_buffer_file:
                    path = _staged_input_path(
                        runtime_dir,
                        int(launch.get("launchIndex") or 0),
                        symbol,
                        buffer_name,
                    )
                if existing is not None:
                    host = np.load(existing, allow_pickle=False).ravel()
                    host, matrix_shape = _transform_existing_input(
                        host,
                        materialization,
                    )
                    if matrix_shape:
                        matrix_role = str(source_transform.get("matrixRole") or symbol)
                        matrix_shapes[matrix_role] = matrix_shape
                    if int(host.size) != total_elements:
                        raise ValueError(
                            f"launch[{launch.get('launchIndex')}].input_buffer_size_mismatch:"
                            f"{buffer_name}:{host.size}!={total_elements}"
                        )
                elif role == "weight":
                    host = _materialize_weight_input(materialization)
                else:
                    host = _materialize_constant_input(
                        materialization=materialization,
                        export=export,
                    )
                    if int(host.size) != total_elements:
                        raise ValueError(
                            f"launch[{launch.get('launchIndex')}].constant_input_size_mismatch:"
                            f"{buffer_name}:{host.size}!={total_elements}"
                        )
                path.parent.mkdir(parents=True, exist_ok=True)
                np.save(path, host)
                if cache_buffer_file:
                    buffer_files[buffer_name] = path
            staged_item = {
                "symbol": symbol,
                "buffer": buffer_name,
                "path": str(path),
                "dtype": str(materialization.get("dtype") or ""),
                "elementsPerPe": int(materialization.get("elementsPerPe") or 0),
            }
            if side == "input" and isinstance(materialization.get("sourceTransform"), dict):
                staged_item["sourceTransform"] = materialization["sourceTransform"]
            if side == "output" and isinstance(materialization.get("outputTransform"), dict):
                output_transform = dict(materialization["outputTransform"])
                rows_from_input = str(output_transform.get("rowsFromInput") or "")
                if rows_from_input and not output_transform.get("rows"):
                    input_shape = matrix_shapes.get(rows_from_input)
                    if input_shape is None:
                        raise ValueError(
                            f"launch[{launch.get('launchIndex')}].output_rows_unresolved:"
                            f"{symbol}:{rows_from_input}"
                        )
                    output_transform["rows"] = input_shape["rows"]
                staged_item["outputTransform"] = output_transform
            staged.append(staged_item)
    return staged_inputs, staged_outputs


def _is_embed_roi_launch(launch: dict[str, Any]) -> bool:
    if str(launch.get("targetName") or "") not in EMBED_ROI_TARGETS:
        return False
    params = launch.get("compileParams") or {}
    return all(
        int(params.get(key) or 0) > 0
        for key in ("rows_per_pe", "hidden_size", "hidden_per_pe", "tokens_per_chunk")
    )


def _compile_embed_roi_target(
    *,
    launch: dict[str, Any],
    roi_spec: dict[str, Any],
    roi_dir: Path,
) -> Path:
    source_compile_dir = Path(str(launch.get("compileDir") or ""))
    compile_root = source_compile_dir.parent.parent
    target_name = str(launch.get("targetName") or "embed")
    layout_path = compile_root / target_name / "layout.csl"
    output_dir = roi_dir / "compiled"
    params = roi_spec.get("compileParams") or {}
    compact_width = int(params.get("compactWidth") or 1)
    hidden_size = int(params.get("hiddenSize") or 0)
    hidden_per_pe = int(params.get("hiddenPerPe") or 0)
    rows_per_pe = int(params.get("rowsPerPe") or 0)
    tokens_per_chunk = int(params.get("tokensPerChunk") or 0)
    if min(compact_width, hidden_size, hidden_per_pe, rows_per_pe, tokens_per_chunk) <= 0:
        raise ValueError("embed_roi_compile_params_incomplete")
    command = [
        cslc_executable(),
        str(layout_path),
        "--arch=wse3",
        f"--fabric-dims={compact_width + 7},3",
        "--fabric-offsets=4,1",
        "--channels=1",
        "--params="
        + ",".join(
            [
                f"width:{compact_width}",
                "height:1",
                f"hidden_per_pe:{hidden_per_pe}",
                f"hidden_size:{hidden_size}",
                f"num_tokens:{tokens_per_chunk}",
                f"rows_per_pe:{rows_per_pe}",
                f"tokens_per_chunk:{tokens_per_chunk}",
            ]
        ),
        "-o",
        str(output_dir),
        "--memcpy",
    ]
    scratch_cwd = roi_dir / "scratch"
    scratch_cwd.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        cwd=str(scratch_cwd),
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown"
        raise ValueError(f"embed_roi_compile_failed:{detail[-400:]}")
    return output_dir


def _execute_embed_roi_launch(
    *,
    runtime_dir: Path,
    launch: dict[str, Any],
    buffer_files: dict[str, Path],
    export: dict[str, Any],
    progress_path: Path,
    cmaddr: str | None,
) -> dict[str, Any]:
    launch_index = int(launch.get("launchIndex") or 0)
    output_binding = next(
        (
            item
            for item in launch.get("resolvedOutputs") or []
            if isinstance(item, dict) and item.get("symbol") == "output"
        ),
        None,
    )
    if not isinstance(output_binding, dict):
        raise ValueError("embed_roi_output_binding_missing")
    output_buffer = str(output_binding.get("buffer") or "")
    if not output_buffer:
        raise ValueError("embed_roi_output_buffer_missing")
    roi_dir = runtime_dir / "embed-roi" / f"launch-{launch_index:04d}"
    output_path = _buffer_path(runtime_dir, output_buffer)
    prompt_path = _tokenized_prompt_path(export)
    roi_spec, roi_digest = build_embed_roi_spec(
        roi_dir=roi_dir,
        launch=launch,
        prompt_path=prompt_path,
        output_buffer_path=output_path,
    )
    roi_compile_dir = _compile_embed_roi_target(
        launch=launch,
        roi_spec=roi_spec,
        roi_dir=roi_dir,
    )
    roi_spec["compileDir"] = str(roi_compile_dir)
    roi_spec["cmaddr"] = cmaddr or ""
    roi_digest = sha256_bytes(
        json.dumps(roi_spec, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    spec_path = roi_dir / "launch-spec.json"
    receipt_path = _launch_receipt_path(runtime_dir, launch_index)
    write_json(spec_path, roi_spec)
    append_progress(
        progress_path,
        "embed_roi_spec_ready",
        launchIndex=launch_index,
        tokenCount=(roi_spec.get("prompt") or {}).get("tokenCount"),
        sublaunchCount=len(roi_spec.get("sublaunches") or []),
        specSha256=roi_digest,
    )
    command = [
        cs_python_executable(),
        str(EMBED_ROI_ADAPTER),
        "--spec",
        str(spec_path),
        "--receipt-out",
        str(receipt_path),
        "--progress-out",
        str(progress_path),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if not receipt_path.is_file():
        raise ValueError("embed_roi_launch_receipt_missing")
    receipt = load_json(receipt_path)
    receipt["stdoutTail"] = (
        completed.stdout.strip().splitlines()[-3:] if completed.stdout.strip() else []
    )
    receipt["stderrTail"] = (
        completed.stderr.strip().splitlines()[-3:] if completed.stderr.strip() else []
    )
    receipt["roiSpecPath"] = str(spec_path)
    receipt["roiSpecSha256"] = roi_digest
    if completed.returncode != 0 or receipt.get("status") != "succeeded":
        raise ValueError("; ".join(receipt.get("blockers") or ["embed_roi_launch_failed"]))
    buffer_files[output_buffer] = output_path
    return receipt


def execute_hostplan_runtime(
    *,
    bootstrap: dict[str, Any],
    export: dict[str, Any],
    progress_path: Path,
    cmaddr: str | None,
    trace_path: Path,
    checkpoint_dir: Path | None = None,
    resume_state: Any = None,
    stop_after_launch: int = -1,
    launch_timeout_seconds: int | None = DEFAULT_LAUNCH_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    runtime_dir = trace_path.parent / "hostplan-runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    launches = bootstrap.get("launches") or []
    blockers: list[str] = []
    buffer_files: dict[str, Path] = {}
    executed_launches: list[dict[str, Any]] = []
    executed_count = 0
    start_index = 0
    if resume_state is not None:
        buffer_files.update(resume_state.buffer_files)
        start_index = int(resume_state.start_index)
        append_progress(
            progress_path,
            "hostplan_resume_loaded",
            startIndex=start_index,
            bufferCount=len(buffer_files),
        )
    stopped_at_checkpoint = False
    for launch in launches:
        if not isinstance(launch, dict):
            blockers.append("launch_not_object")
            break
        launch_index = int(launch.get("launchIndex") or executed_count)
        if launch_index < start_index:
            append_progress(
                progress_path,
                "hostplan_launch_skipped_resume",
                launchIndex=launch_index,
                target=launch.get("targetName"),
            )
            executed_count += 1
            continue
        launch_started_at = time.time()
        append_progress(
            progress_path,
            "hostplan_launch_start",
            launchIndex=launch_index,
            target=launch.get("targetName"),
        )
        try:
            if _is_embed_roi_launch(launch):
                buffer_keys_before = set(buffer_files.keys())
                launch_receipt = _execute_embed_roi_launch(
                    runtime_dir=runtime_dir,
                    launch=launch,
                    buffer_files=buffer_files,
                    export=export,
                    progress_path=progress_path,
                    cmaddr=cmaddr,
                )
                executed_launches.append(launch_receipt)
                executed_count += 1
                append_progress(
                    progress_path,
                    "hostplan_launch_complete",
                    launchIndex=launch_index,
                    target=launch.get("targetName"),
                    status="succeeded",
                )
                if checkpoint_dir is not None:
                    new_keys = sorted(set(buffer_files.keys()) - buffer_keys_before)
                    embed_outputs = [
                        {
                            "buffer": key,
                            "path": str(buffer_files[key]),
                            "dtype": "unknown",
                            "shape": [],
                        }
                        for key in new_keys
                    ]
                    _persist_launch_checkpoint(
                        checkpoint_dir=checkpoint_dir,
                        launch_index=launch_index,
                        launch=launch,
                        launch_receipt=launch_receipt,
                        staged_outputs=embed_outputs,
                        launch_identity=_compute_launch_identity(launch, {}),
                        started_at_unix=launch_started_at,
                    )
                if stop_after_launch >= 0 and launch_index >= stop_after_launch:
                    stopped_at_checkpoint = True
                    break
                continue
            staged_inputs, staged_outputs = _stage_launch_arrays(
                runtime_dir=runtime_dir,
                launch=launch,
                buffer_files=buffer_files,
                export=export,
            )
            receipt_path = _launch_receipt_path(runtime_dir, launch_index)
            spec_path = _launch_spec_path(runtime_dir, launch_index)
            launch_spec = {
                "compileDir": launch.get("compileDir"),
                "launchFunction": launch.get("launchFunction"),
                "launchIndex": launch_index,
                "cmaddr": cmaddr or "",
                "targetGeometry": launch.get("targetGeometry") or {},
                "inputs": staged_inputs,
                "outputs": staged_outputs,
            }
            write_json(spec_path, launch_spec)
            command = [
                cs_python_executable(),
                str(LAUNCH_STEP_ADAPTER),
                "--spec",
                str(spec_path),
                "--receipt-out",
                str(receipt_path),
                "--progress-out",
                str(progress_path),
            ]
            timeout = (
                launch_timeout_seconds
                if launch_timeout_seconds is not None and launch_timeout_seconds > 0
                else None
            )
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                timeout_receipt = {
                    "schemaVersion": 1,
                    "artifactKind": "int4ple_launch_step_receipt",
                    "status": "blocked",
                    "blockers": ["launch_step_timeout"],
                    "launchIndex": launch_index,
                    "targetName": launch.get("targetName"),
                    "timeoutSeconds": timeout,
                    "stdoutTail": tail_lines(exc.stdout, 1),
                    "stderrTail": tail_lines(exc.stderr, 1),
                }
                write_json(receipt_path, timeout_receipt)
                executed_launches.append(timeout_receipt)
                append_progress(
                    progress_path,
                    "hostplan_launch_timeout",
                    launchIndex=launch_index,
                    target=launch.get("targetName"),
                    timeoutSeconds=timeout,
                )
                raise ValueError("launch_step_timeout") from exc
            if not receipt_path.is_file():
                raise ValueError("launch_receipt_missing")
            launch_receipt = load_json(receipt_path)
            launch_receipt["stdoutTail"] = tail_lines(completed.stdout, 1)
            launch_receipt["stderrTail"] = tail_lines(completed.stderr, 1)
            executed_launches.append(launch_receipt)
            if completed.returncode != 0 or launch_receipt.get("status") != "succeeded":
                raise ValueError(
                    "; ".join(launch_receipt.get("blockers") or ["launch_failed"])
                )
            for output in staged_outputs:
                buffer_files[str(output["buffer"])] = Path(str(output["path"]))
            executed_count += 1
            append_progress(
                progress_path,
                "hostplan_launch_complete",
                launchIndex=launch_index,
                target=launch.get("targetName"),
                status="succeeded",
            )
            if checkpoint_dir is not None:
                _persist_launch_checkpoint(
                    checkpoint_dir=checkpoint_dir,
                    launch_index=launch_index,
                    launch=launch,
                    launch_receipt=launch_receipt,
                    staged_outputs=staged_outputs,
                    launch_identity=_compute_launch_identity(launch, {}),
                    started_at_unix=launch_started_at,
                )
            if stop_after_launch >= 0 and launch_index >= stop_after_launch:
                stopped_at_checkpoint = True
                break
        except Exception as exc:
            blockers.append(f"launch[{launch_index}]_blocked:{exc}")
            append_progress(
                progress_path,
                "hostplan_launch_blocked",
                launchIndex=launch_index,
                target=launch.get("targetName"),
                error=str(exc),
            )
            break
    if blockers:
        status = "blocked"
    elif stopped_at_checkpoint:
        status = "stopped_at_checkpoint"
    else:
        status = "succeeded"
    return {
        "schemaVersion": 1,
        "artifactKind": "int4ple_hostplan_executor_runtime",
        "status": status,
        "blockers": blockers,
        "executedLaunchCount": executed_count,
        "launchCount": len(launches),
        "bufferDir": str(runtime_dir / "buffers"),
        "launches": executed_launches,
        "targetSessions": bootstrap.get("targetSessions") or [],
        "stoppedAtCheckpoint": stopped_at_checkpoint,
        "launchTimeoutSeconds": launch_timeout_seconds,
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
    hostplan_executor_runtime: dict[str, Any] | None,
    kernel_results: list[dict[str, Any]],
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    elapsed_ms = (time.monotonic() - started) * 1000.0
    runtime_artifact_kind = (
        str(hostplan_executor_runtime.get("artifactKind"))
        if isinstance(hostplan_executor_runtime, dict)
        else ""
    )
    bootstrap_ready = (
        isinstance(hostplan_executor_runtime, dict)
        and hostplan_executor_runtime.get("status") == "ready_for_tensor_movement"
    )
    runtime_executed = runtime_artifact_kind == "int4ple_hostplan_executor_runtime"
    if runtime_executed:
        model_blocker = (
            "The HostPlan executor launched real CSL targets, but stopped "
            "before a full-model transcript because the bound launch graph "
            "still hit an unsupported materialization or tensor-handoff blocker."
        )
    elif bootstrap_ready:
        model_blocker = (
            "The HostPlan executor bootstrap loaded each compiled target, "
            "resolved the required runtime symbols, and materialized the "
            "concrete activation/KV/logit/token buffer plan, but weight "
            "staging, tensor movement, launch execution, and transcript "
            "capture are still pending."
        )
    elif scheduler.get("status") == "blocked_missing_full_model_runtime_execution":
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
    production_targets = [
        str(item.get("targetName") or item.get("target"))
        for item in kernel_results
        if item.get("status") in {"resolved", "succeeded"}
    ]
    kernel_stage = (
        "int4ple_hostplan_executor_runtime"
        if runtime_executed
        else
        "int4ple_hostplan_executor_bootstrap"
        if hostplan_executor_runtime is not None
        else "int4ple_compile_target_runtime_diagnostic"
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
            "kernelStage": kernel_stage,
            "kernelIsStub": False,
            "elapsedMs": elapsed_ms,
        },
        "executedRun": {
            "fullModelDepthExecuted": False,
            "boundedTranscriptProduced": False,
            "productionCompileTargetsExecuted": production_targets,
            "runtimeConfigMode": runtime_config.get("mode"),
            "diagnosticOnly": hostplan_executor_runtime is None,
            "executorBootstrapOnly": (
                hostplan_executor_runtime is not None and not runtime_executed
            ),
            "schedulerStatus": scheduler.get("status"),
            "hostPlanExecutorRuntimeStatus": (
                hostplan_executor_runtime.get("status")
                if isinstance(hostplan_executor_runtime, dict)
                else "not_run"
            ),
        },
        "modelExecution": {
            "fullModelDepthExecuted": False,
            "blocker": model_blocker,
        },
        "hostPlanScheduler": scheduler,
        "kernelResults": kernel_results,
    }
    if hostplan_executor_runtime is not None:
        trace["hostPlanExecutorRuntime"] = hostplan_executor_runtime
    if error is not None:
        trace["simulatorRun"]["error"] = error
    return trace


def main() -> int:
    args = parse_args()
    trace_path = Path(args.trace_out)
    progress_path = Path(args.progress_out)
    started = time.monotonic()
    append_progress(progress_path, "runner_start")
    hostplan_executor_runtime: dict[str, Any] | None = None

    checkpoint_dir = Path(args.checkpoint_dir) if args.checkpoint_dir.strip() else None
    resume_dir = (
        Path(args.resume_from_checkpoint)
        if args.resume_from_checkpoint.strip() and not args.ignore_checkpoint
        else None
    )

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
        identity = _compute_checkpoint_identity(
            plan=plan,
            plan_path=Path(args.plan),
            runtime_config=runtime_config,
            runtime_config_path=Path(args.runtime_config),
            export=export,
            reference_export_path=Path(args.reference_export),
            runner_version=_runner_version(),
        )
        resume_state = None
        if resume_dir is not None:
            try:
                resume_state = _load_checkpoint(
                    checkpoint_dir=resume_dir,
                    identity=identity,
                )
                append_progress(
                    progress_path,
                    "checkpoint_resume_validated",
                    startIndex=resume_state.start_index,
                    bufferCount=len(resume_state.buffer_files),
                )
            except CheckpointMissingError:
                # Fresh resume directory: treat as empty checkpoint.
                resume_state = None
            except CheckpointError as exc:
                append_progress(
                    progress_path,
                    "checkpoint_resume_rejected",
                    code=getattr(exc, "code", "checkpoint_error"),
                    error=str(exc),
                )
                raise
        if checkpoint_dir is not None:
            _init_checkpoint(checkpoint_dir, identity)
        append_progress(
            progress_path,
            "scheduler_readiness",
            status=scheduler["status"],
            blockers=scheduler["blockers"],
        )
        execution_plan = ((scheduler.get("hostPlanExecutor") or {}).get("executionPlan") or {})
        has_launch_plan = bool(execution_plan.get("targetSessions")) and bool(
            execution_plan.get("launches")
        )
        if has_launch_plan:
            hostplan_executor_runtime = execute_hostplan_runtime_bootstrap(
                execution_plan=execution_plan,
                progress_path=progress_path,
                cmaddr=cmaddr,
            )
            if hostplan_executor_runtime.get("status") != "ready_for_tensor_movement":
                raise ValueError(
                    "hostplan executor bootstrap blocked: "
                    + ", ".join(hostplan_executor_runtime.get("blockers") or ["unknown"])
                )
            hostplan_executor_runtime = execute_hostplan_runtime(
                bootstrap=hostplan_executor_runtime,
                export=export,
                progress_path=progress_path,
                cmaddr=cmaddr,
                trace_path=trace_path,
                checkpoint_dir=checkpoint_dir,
                resume_state=resume_state,
                stop_after_launch=args.stop_after_launch,
                launch_timeout_seconds=args.launch_timeout_seconds,
            )
            runtime_status = hostplan_executor_runtime.get("status")
            if runtime_status not in ("succeeded", "stopped_at_checkpoint"):
                raise ValueError(
                    "hostplan executor runtime blocked: "
                    + ", ".join(hostplan_executor_runtime.get("blockers") or ["unknown"])
                )
            kernel_results = hostplan_executor_runtime.get("launches") or []
        else:
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
            kernel_results = [result]
        trace = diagnostic_trace(
            export=export,
            runtime_config=runtime_config,
            scheduler=scheduler,
            cmaddr=cmaddr,
            started=started,
            hostplan_executor_runtime=hostplan_executor_runtime,
            kernel_results=kernel_results,
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
                hostplan_executor_runtime=hostplan_executor_runtime,
                kernel_results=(
                    hostplan_executor_runtime.get("launches")
                    or hostplan_executor_runtime.get("targetSessions")
                    or []
                    if isinstance(hostplan_executor_runtime, dict)
                    else []
                ),
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
