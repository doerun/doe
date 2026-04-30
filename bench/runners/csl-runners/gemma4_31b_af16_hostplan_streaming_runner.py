#!/usr/bin/env python3
"""Gemma 4 31B af16 HostPlan streaming-runner front door.

This runner owns the operational contract for real Gemma 4 31B af16
prefill/decode on the Cerebras simulator. It currently performs the parts
that are source-derivable without a live SDK session:

  - resolve the af16 Doppler manifest through its weightsRef primary;
  - validate shard presence and declared sizes without copying weight bytes;
  - expand the execution-v1 smoke config into prefill/decode dispatch plans;
  - bind the af16 HostPlan compile artifacts and per-kernel summary;
  - emit a trace with the remaining named blockers.

It does not synthesize model output. When the combined session runtime lands,
this file is the place that stages weight payloads into device symbols,
walks the expanded dispatch plan, preserves KV cache state, and writes the
CSL token/logit/KV transcript.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_ROOT = REPO_ROOT.parent
RUNNER_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from bench.tools._lane_dtype_profile import canonical_dtype_profile  # noqa: E402
from bench.tools.int4ple_runtime_weight_mappings import (  # noqa: E402
    inferred_rmsnorm_weight_key,
    layer_index_from_step_weight_key,
    tensor_name_candidates_for_weight_key,
)
from int4ple_hostplan_execution_plan import build_hostplan_execution_plan  # noqa: E402
from int4ple_hostplan_executor_validator import validate_hostplan_executor  # noqa: E402
from int4ple_compile_target_sim_runner import (  # noqa: E402
    execute_hostplan_runtime,
    execute_hostplan_runtime_bootstrap,
)

MODEL_ID = "gemma-4-31b-it-text-q4k-ehf16-af16"
LANE_KEY = "q4k-ehf16-af16"
PLE_EMBED_KEY_PREFIX = "per_layer_inputs.embedTokensPerLayer.layer"
PLE_PROJECTION_KEY_PREFIX = "per_layer_inputs.perLayerModelProjection.layer"
PLE_PROJECTION_NORM_KEY_PREFIX = "per_layer_inputs.perLayerProjectionNorm.layer"
LINEAR_ATTENTION_POLICY = "skip-with-layout-metadata"
MODEL_LEVEL_DECODE_STEPS = frozenset({"final_norm", "lm_head"})
LM_HEAD_KERNELS = frozenset({"lm_head_gemv", "lm_head_gemv_stable"})
DEFAULT_SOURCE_MANIFEST = (
    WORKSPACE_ROOT
    / "doppler/models/local/gemma-4-31b-it-text-q4k-ehf16-af16/manifest.json"
)
DEFAULT_SMOKE_CONFIG = (
    REPO_ROOT / "runtime/zig/examples/execution-v1/gemma-4-31b-smoke.json"
)
DEFAULT_HOST_PLAN = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-manifest-fullgraph-compile-steps/host-plan.json"
)
DEFAULT_SIMULATOR_PLAN = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-manifest-fullgraph-compile-steps/simulator-plan.json"
)
DEFAULT_RUNTIME_CONFIG = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-manifest-fullgraph-compile-steps/runtime-config.json"
)
DEFAULT_COMPILE_ROOT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-manifest-fullgraph-compile-steps/compile"
)
DEFAULT_PER_KERNEL_SUMMARY = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-manifest-simfabric-per-kernel/summary.json"
)
DEFAULT_OUT = (
    REPO_ROOT / "bench/out/r3-1-31b-af16-hostplan-streaming/trace.json"
)
DEFAULT_REFRESH_OUT_DIR = (
    REPO_ROOT / "bench/out/r3-1-31b-af16-manifest-simfabric-per-kernel"
)
DEFAULT_SESSION_OUT_DIR = (
    REPO_ROOT / "bench/out/r3-1-31b-af16-hostplan-session"
)
MANIFEST_KERNEL_PROBE_RUNNER = (
    REPO_ROOT / "bench/runners/csl-runners/manifest_kernel_probe_runner.py"
)
CS_PYTHON = REPO_ROOT / "runtime/zig/tools/cs_python_singularity.sh"
CHAIN_STEP_ADAPTER = (
    REPO_ROOT / "bench/runners/csl-runners/chain_step_adapter.py"
)
DEFAULT_PROMPT_TOKEN_IDS = [2, 3]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-doppler-manifest",
        type=Path,
        default=DEFAULT_SOURCE_MANIFEST,
    )
    parser.add_argument("--smoke-config", type=Path, default=DEFAULT_SMOKE_CONFIG)
    parser.add_argument("--host-plan", type=Path, default=DEFAULT_HOST_PLAN)
    parser.add_argument("--simulator-plan", type=Path, default=DEFAULT_SIMULATOR_PLAN)
    parser.add_argument("--runtime-config", type=Path, default=DEFAULT_RUNTIME_CONFIG)
    parser.add_argument("--compile-root", type=Path, default=DEFAULT_COMPILE_ROOT)
    parser.add_argument(
        "--per-kernel-summary",
        type=Path,
        default=DEFAULT_PER_KERNEL_SUMMARY,
    )
    parser.add_argument("--prefill-token-count", type=int, default=2)
    parser.add_argument("--decode-token-count", type=int, default=2)
    parser.add_argument(
        "--prompt-token-id",
        type=int,
        action="append",
        default=[],
        help="Token id to place in the real-session prompt input. Repeatable.",
    )
    parser.add_argument("--cmaddr", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--refresh-per-kernel", action="store_true")
    parser.add_argument(
        "--refresh-jobs",
        type=int,
        default=1,
        help="Worker count passed to manifest_kernel_probe_runner.py.",
    )
    parser.add_argument(
        "--refresh-resume",
        action="store_true",
        help="Reuse existing non-dry-run per-kernel receipts on refresh.",
    )
    parser.add_argument(
        "--refresh-schedule",
        choices=["host-plan", "heavy-first"],
        default="host-plan",
        help="Per-kernel refresh launch order.",
    )
    parser.add_argument(
        "--refresh-timeout-seconds",
        type=int,
        default=600,
        help="Per-kernel subprocess timeout passed to the refresh runner.",
    )
    parser.add_argument(
        "--refresh-out-dir",
        type=Path,
        default=DEFAULT_REFRESH_OUT_DIR,
    )
    parser.add_argument(
        "--session-out-dir",
        type=Path,
        default=DEFAULT_SESSION_OUT_DIR,
    )
    parser.add_argument(
        "--stop-after-launch",
        type=int,
        default=-1,
        help="Stop the real session after persisting this launch index.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    resolved = resolve(path)
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        pass
    try:
        return "../" + resolved.relative_to(WORKSPACE_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def load_json(path: Path) -> Any:
    return json.loads(resolve(path).read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with resolve(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_weight_root(manifest_path: Path, manifest: dict[str, Any]) -> Path:
    manifest_root = resolve(manifest_path).parent
    weights_ref = manifest.get("weightsRef") or {}
    raw_root = weights_ref.get("artifactRoot")
    if isinstance(raw_root, str) and raw_root:
        return (manifest_root / raw_root).resolve()
    return manifest_root


def expand_layer_weight_key(weight_key: str, layer_index: int) -> str:
    parts = weight_key.split(".")
    if len(parts) >= 2 and parts[0] == "layer" and parts[1] == "0":
        return ".".join(["layer", str(layer_index), *parts[2:]])
    return weight_key


def infer_weight_key_for_step(
    step: dict[str, Any],
    layer_index: int,
) -> str | None:
    raw = step.get("weightsKey")
    if isinstance(raw, str) and raw:
        if raw == "per_layer_inputs.perLayerModelProjection":
            return f"{raw}.layer{layer_index}"
        if raw == "per_layer_inputs.embedTokensPerLayer":
            return f"{raw}.layer{layer_index}"
        if raw == "per_layer_inputs.perLayerProjectionNorm":
            return f"{raw}.layer{layer_index}"
        return expand_layer_weight_key(raw, layer_index)
    if step.get("op") == "rmsnorm" or step.get("kernelKey") == "rmsnorm":
        direct = layer_index_from_step_weight_key(raw)
        return inferred_rmsnorm_weight_key(
            str(step.get("name") or ""),
            direct if direct is not None else layer_index,
        )
    return None


def tensor_candidates_for_key(weight_key: str) -> list[str]:
    if weight_key.startswith(PLE_EMBED_KEY_PREFIX):
        layer = weight_key.removeprefix(PLE_EMBED_KEY_PREFIX)
        return [
            (
                "model.language_model.layers."
                f"{layer}.embed_tokens_per_layer.weight"
            ),
            f"model.layers.{layer}.embed_tokens_per_layer.weight",
            "model.language_model.embed_tokens_per_layer.weight",
            "language_model.embed_tokens_per_layer.weight",
            "model.embed_tokens_per_layer.weight",
            "embed_tokens_per_layer.weight",
            "model.language_model.embed_tokens.weight",
            "model.embed_tokens.weight",
        ]
    if weight_key.startswith(PLE_PROJECTION_NORM_KEY_PREFIX):
        return [
            "model.language_model.per_layer_projection_norm.weight",
            "language_model.per_layer_projection_norm.weight",
            "model.per_layer_projection_norm.weight",
            "per_layer_projection_norm.weight",
        ]
    if weight_key.startswith(PLE_PROJECTION_KEY_PREFIX):
        return [weight_key + ".f32"]
    try:
        return tensor_name_candidates_for_weight_key(weight_key)
    except ValueError:
        return [weight_key + ".f32"]


def layer_index_from_weight_key(weight_key: str) -> int | None:
    parts = weight_key.split(".")
    if len(parts) < 2 or parts[0] != "layer":
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def tensor_exists(tensors: dict[str, Any], name: str) -> bool:
    return name in tensors


def is_linear_attention_absent_v_projection(
    weight_key: str,
    tensors: dict[str, Any],
) -> bool:
    if not weight_key.endswith(".self_attn.v_proj"):
        return False
    layer_index = layer_index_from_weight_key(weight_key)
    if layer_index is None:
        return False
    prefix = f"model.language_model.layers.{layer_index}.self_attn"
    has_v = tensor_exists(tensors, f"{prefix}.v_proj.weight")
    return (
        not has_v
        and tensor_exists(tensors, f"{prefix}.q_proj.weight")
        and tensor_exists(tensors, f"{prefix}.k_proj.weight")
        and tensor_exists(tensors, f"{prefix}.o_proj.weight")
    )


def is_architecture_disabled_ple_projection_norm(
    weight_key: str,
    architecture: dict[str, Any],
) -> bool:
    if not weight_key.startswith(PLE_PROJECTION_NORM_KEY_PREFIX):
        return False
    hidden = int(architecture.get("hiddenSizePerLayerInput") or 0)
    return hidden <= 0


def resolve_required_weight(
    *,
    weight_key: str,
    candidates: list[str],
    tensors: dict[str, Any],
    weight_root: Path,
    architecture: dict[str, Any],
) -> dict[str, Any]:
    matched_tensor = next((c for c in candidates if c in tensors), None)
    matched_file = next((c for c in candidates if (weight_root / c).is_file()), None)
    if matched_tensor:
        return {
            "weightKey": weight_key,
            "candidates": candidates,
            "matchedTensor": matched_tensor,
            "matchedFile": None,
            "resolutionKind": "manifest_tensor",
            "resolved": True,
        }
    if matched_file:
        return {
            "weightKey": weight_key,
            "candidates": candidates,
            "matchedTensor": None,
            "matchedFile": matched_file,
            "resolutionKind": "sidecar_file",
            "resolved": True,
        }
    if is_linear_attention_absent_v_projection(weight_key, tensors):
        return {
            "weightKey": weight_key,
            "candidates": candidates,
            "matchedTensor": None,
            "matchedFile": None,
            "resolutionKind": "linear_attention_absent_v_projection",
            "linearAttentionPolicy": LINEAR_ATTENTION_POLICY,
            "resolved": True,
        }
    if is_architecture_disabled_ple_projection_norm(weight_key, architecture):
        return {
            "weightKey": weight_key,
            "candidates": candidates,
            "matchedTensor": None,
            "matchedFile": None,
            "resolutionKind": "architecture_disabled_session_input",
            "resolved": True,
        }
    return {
        "weightKey": weight_key,
        "candidates": candidates,
        "matchedTensor": None,
        "matchedFile": None,
        "resolutionKind": "unresolved",
        "resolved": False,
    }


def build_weight_staging_plan(
    *,
    manifest_path: Path,
    smoke_config_path: Path,
) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    smoke = load_json(smoke_config_path)
    profile = canonical_dtype_profile(manifest.get("quantizationInfo"))
    if manifest.get("modelId") != MODEL_ID:
        raise ValueError(
            f"expected modelId {MODEL_ID!r}, got {manifest.get('modelId')!r}"
        )
    if profile.get("variantTag") != LANE_KEY:
        raise ValueError(
            f"expected lane {LANE_KEY!r}, got {profile.get('variantTag')!r}"
        )

    weight_root = resolve_weight_root(manifest_path, manifest)
    shards = manifest.get("shards") or []
    missing_shards: list[str] = []
    size_mismatches: list[dict[str, Any]] = []
    present_shards = 0
    for shard in shards:
        if not isinstance(shard, dict):
            continue
        filename = str(shard.get("filename") or "")
        if not filename:
            continue
        path = weight_root / filename
        expected_size = int(shard.get("size") or 0)
        if not path.is_file():
            missing_shards.append(filename)
            continue
        present_shards += 1
        actual_size = path.stat().st_size
        if expected_size and actual_size != expected_size:
            size_mismatches.append({
                "filename": filename,
                "expectedSize": expected_size,
                "actualSize": actual_size,
            })

    tensors = manifest.get("tensors") or {}
    architecture = manifest.get("architecture") or {}
    steps = [
        step
        for step in smoke.get("steps") or []
        if isinstance(step, dict)
    ]
    num_layers = int(
        architecture.get("numLayers")
        or (smoke.get("modelConfig") or {}).get("numLayers")
        or 0
    )
    required: dict[str, dict[str, Any]] = {}
    for layer_index in range(num_layers):
        for step in steps:
            key = infer_weight_key_for_step(step, layer_index)
            if not key:
                continue
            if key in required:
                continue
            candidates = tensor_candidates_for_key(key)
            required[key] = resolve_required_weight(
                weight_key=key,
                candidates=candidates,
                tensors=tensors,
                weight_root=weight_root,
                architecture=architecture,
            )

    unresolved = [
        key for key, record in required.items() if not record["resolved"]
    ]
    return {
        "mode": "weightsRef_resident_session",
        "manifestPath": rel(manifest_path),
        "manifestSha256": sha256_file(manifest_path),
        "modelId": manifest.get("modelId"),
        "laneKey": profile["variantTag"],
        "dtypeProfile": profile,
        "weightPackId": (manifest.get("artifactIdentity") or {}).get(
            "weightPackId"
        ),
        "shardSetHash": (manifest.get("artifactIdentity") or {}).get(
            "shardSetHash"
        ),
        "weightRoot": rel(weight_root),
        "weightRootPresent": weight_root.is_dir(),
        "shardCount": len(shards),
        "presentShardCount": present_shards,
        "missingShards": missing_shards,
        "sizeMismatches": size_mismatches,
        "tensorCount": len(tensors),
        "modelLayerCount": num_layers,
        "requiredWeightCount": len(required),
        "resolvedWeightCount": sum(
            1 for record in required.values() if record["resolved"]
        ),
        "unresolvedWeightKeys": unresolved,
        "requiredWeights": list(required.values()),
    }


def phase_steps(smoke: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    return [
        step for step in smoke.get("steps") or []
        if isinstance(step, dict) and step.get("phase") == phase
    ]


def is_model_level_decode_step(step: dict[str, Any]) -> bool:
    name = str(step.get("name") or "")
    kernel = str(step.get("kernelKey") or "")
    return name in MODEL_LEVEL_DECODE_STEPS or kernel in LM_HEAD_KERNELS


def build_dispatch_plan(
    *,
    smoke_config_path: Path,
    host_plan_path: Path,
    prefill_token_count: int,
    decode_token_count: int,
    model_layer_count: int | None = None,
) -> dict[str, Any]:
    smoke = load_json(smoke_config_path)
    host_plan = load_json(host_plan_path)
    num_layers = int(
        model_layer_count
        if model_layer_count is not None
        else (smoke.get("modelConfig") or {}).get("numLayers") or 0
    )
    prefill_template = phase_steps(smoke, "prefill")
    decode_template = phase_steps(smoke, "decode")
    prefill: list[dict[str, Any]] = []
    for step in prefill_template:
        if step.get("kernelKey") == "embed":
            prefill.append({
                "phase": "prefill",
                "layer": None,
                "name": step.get("name"),
                "kernelKey": step.get("kernelKey"),
                "weightKey": step.get("weightsKey"),
            })
            continue
        for layer_index in range(num_layers):
            prefill.append({
                "phase": "prefill",
                "layer": layer_index,
                "name": step.get("name"),
                "kernelKey": step.get("kernelKey"),
                "weightKey": infer_weight_key_for_step(step, layer_index),
            })

    decode_by_token: list[dict[str, Any]] = []
    for token_index in range(decode_token_count):
        token_steps: list[dict[str, Any]] = []
        for step in decode_template:
            if step.get("kernelKey") == "sample":
                continue
            if is_model_level_decode_step(step):
                token_steps.append({
                    "phase": "decode",
                    "tokenIndex": token_index,
                    "layer": None,
                    "name": step.get("name"),
                    "kernelKey": step.get("kernelKey"),
                    "weightKey": infer_weight_key_for_step(step, 0),
                })
                continue
            for layer_index in range(num_layers):
                token_steps.append({
                    "phase": "decode",
                    "tokenIndex": token_index,
                    "layer": layer_index,
                    "name": step.get("name"),
                    "kernelKey": step.get("kernelKey"),
                    "weightKey": infer_weight_key_for_step(step, layer_index),
                })
        token_steps.append({
            "phase": "decode",
            "tokenIndex": token_index,
            "layer": None,
            "name": "sample",
            "kernelKey": "sample",
            "weightKey": None,
        })
        decode_by_token.append({
            "tokenIndex": token_index,
            "steps": token_steps,
        })

    compact_host_plan = host_plan.get("hostPlan") or {}
    return {
        "kind": "expanded_execution_v1_hostplan_stream",
        "smokeConfigPath": rel(smoke_config_path),
        "smokeConfigSha256": sha256_file(smoke_config_path),
        "hostPlanPath": rel(host_plan_path),
        "hostPlanHash": sha256_file(host_plan_path),
        "prefillTokenCount": prefill_token_count,
        "decodeTokenCount": decode_token_count,
        "modelLayerCount": num_layers,
        "prefillStepCount": len(prefill),
        "decodeStepCount": sum(len(item["steps"]) for item in decode_by_token),
        "prefillSteps": prefill,
        "decodeByToken": decode_by_token,
        "prefillPreview": prefill[:8],
        "decodePreview": decode_by_token[:1],
        "compactHostPlanPhaseKernelCounts": {
            key: len(value)
            for key, value in (compact_host_plan.get("phases") or {}).items()
            if isinstance(value, list)
        },
    }


def build_per_kernel_refresh_command(
    *,
    host_plan: Path,
    compile_root: Path,
    out_dir: Path,
    cmaddr: str,
    jobs: int,
    resume: bool,
    schedule: str,
    timeout_seconds: int,
) -> list[str]:
    return [
        sys.executable,
        rel(MANIFEST_KERNEL_PROBE_RUNNER),
        "--host-plan", rel(host_plan),
        "--compile-root", rel(compile_root / "compiled"),
        "--source-root", rel(compile_root),
        "--out-dir", rel(out_dir),
        "--cs-python", rel(CS_PYTHON),
        "--adapter", rel(CHAIN_STEP_ADAPTER),
        "--jobs", str(jobs),
        "--schedule", schedule,
        "--timeout-seconds", str(timeout_seconds),
        *([] if not resume else ["--resume"]),
        *([] if not cmaddr else ["--cmaddr", cmaddr]),
    ]


def sdk_preflight() -> dict[str, Any]:
    if not CS_PYTHON.is_file():
        return {
            "status": "blocked",
            "class": "cs_python_unavailable",
            "detail": f"cs_python wrapper absent at {rel(CS_PYTHON)}",
        }
    proc = subprocess.run(
        [
            str(CS_PYTHON),
            "-c",
            "import cerebras.sdk.runtime.sdkruntimepybind as r; print('ok')",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "status": "ready" if proc.returncode == 0 else "blocked",
        "class": "" if proc.returncode == 0 else "sdk_python_import_failed",
        "returncode": proc.returncode,
        "stdoutTail": proc.stdout.splitlines()[-20:],
        "stderrTail": proc.stderr.splitlines()[-20:],
    }


def maybe_refresh_per_kernel(args: argparse.Namespace) -> dict[str, Any]:
    command = build_per_kernel_refresh_command(
        host_plan=args.host_plan,
        compile_root=args.compile_root,
        out_dir=args.refresh_out_dir,
        cmaddr=args.cmaddr,
        jobs=args.refresh_jobs,
        resume=args.refresh_resume,
        schedule=args.refresh_schedule,
        timeout_seconds=args.refresh_timeout_seconds,
    )
    if not args.refresh_per_kernel:
        return {
            "requested": False,
            "command": command,
            "status": "not_requested",
        }
    preflight = sdk_preflight()
    if preflight["status"] != "ready":
        return {
            "requested": True,
            "command": command,
            "status": "blocked",
            "blocker": preflight,
        }
    proc = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "requested": True,
        "command": command,
        "status": "completed" if proc.returncode == 0 else "blocked",
        "returncode": proc.returncode,
        "stdoutTail": proc.stdout.splitlines()[-20:],
        "stderrTail": proc.stderr.splitlines()[-20:],
    }


def per_kernel_summary_block(summary_path: Path) -> dict[str, Any]:
    if not resolve(summary_path).is_file():
        return {
            "path": rel(summary_path),
            "present": False,
            "totals": {},
            "blockedKernels": [],
            "blockerCounts": {},
            "staleDryRunOnly": False,
        }
    summary = load_json(summary_path)
    kernels = summary.get("kernels") or []
    blocked = [
        k
        for k in kernels
        if isinstance(k, dict) and k.get("verdict") != "bound"
    ]
    blocker_counts: dict[str, int] = {}
    for kernel in blocked:
        blocker = str(kernel.get("blocker") or "unknown")
        blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
    return {
        "path": rel(summary_path),
        "present": True,
        "sha256": sha256_file(summary_path),
        "totals": summary.get("totals") or {},
        "blockedKernels": [k.get("kernel") for k in blocked],
        "blockerCounts": blocker_counts,
        "staleDryRunOnly": bool(blocked) and set(blocker_counts) == {"dry_run"},
    }


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def runtime_dtype(manifest_dtype: str) -> str:
    if manifest_dtype == "BF16":
        return "bf16"
    if manifest_dtype == "F16":
        return "f16"
    if manifest_dtype == "Q4_K_M":
        return "u8_q4k"
    if manifest_dtype == "Q8_0":
        return "u8_q8"
    if manifest_dtype == "F32":
        return "f32"
    raise ValueError(f"unsupported runtime weight dtype: {manifest_dtype}")


def runtime_quant(manifest_dtype: str) -> dict[str, Any]:
    if manifest_dtype == "BF16":
        return {
            "format": "BF16",
            "storageDtype": "bfloat16",
            "sourceDtype": "bfloat16",
        }
    if manifest_dtype == "F16":
        return {
            "format": "F16",
            "storageDtype": "float16",
            "sourceDtype": "float16",
        }
    if manifest_dtype == "F32":
        return {
            "format": "F32",
            "storageDtype": "float32",
            "sourceDtype": "float32",
        }
    if manifest_dtype == "Q4_K_M":
        return {
            "format": "Q4_K_M",
            "storageDtype": "uint8",
            "sourceDtype": "float16",
            "blockSizeElements": 256,
            "blockSizeBytes": 144,
            "encoding": "rdrr_int4ple",
        }
    if manifest_dtype == "Q8_0":
        return {
            "format": "Q8_0",
            "storageDtype": "uint8",
            "sourceDtype": "float16",
            "blockSizeElements": 32,
            "blockSizeBytes": 34,
            "encoding": "rdrr_int4ple",
        }
    raise ValueError(f"unsupported runtime weight quant metadata: {manifest_dtype}")


def shard_identities_by_index(manifest: dict[str, Any]) -> dict[int, dict[str, Any]]:
    identities: dict[int, dict[str, Any]] = {}
    for shard in manifest.get("shards") or []:
        if not isinstance(shard, dict):
            continue
        index = int(shard.get("index", len(identities)))
        identities[index] = shard
    return identities


def tensor_spans_for_runtime(
    *,
    tensor: dict[str, Any],
    shard_identities: dict[int, dict[str, Any]],
    weight_root: Path,
) -> list[dict[str, Any]]:
    raw_spans = tensor.get("spans")
    if not isinstance(raw_spans, list):
        raw_spans = [
            {
                "shardIndex": int(tensor["shard"]),
                "offset": int(tensor["offset"]),
                "size": int(tensor["size"]),
            }
        ]
    spans: list[dict[str, Any]] = []
    for raw_span in raw_spans:
        shard_index = int(raw_span["shardIndex"])
        identity = shard_identities.get(shard_index, {})
        filename = str(identity.get("filename", f"shard_{shard_index:05d}.bin"))
        spans.append(
            {
                "shardIndex": shard_index,
                "shardPath": str((weight_root / filename).resolve()),
                "shardSha256": str(
                    identity.get("sha256")
                    or identity.get("hash")
                    or identity.get("blake3")
                    or "missing"
                ),
                "offset": int(raw_span["offset"]),
                "size": int(raw_span["size"]),
            }
        )
    return spans


def runtime_mapping_from_tensor(
    *,
    weight_key: str,
    tensor_name: str,
    tensor: dict[str, Any],
    spans: list[dict[str, Any]],
    pe_count: int,
) -> dict[str, Any]:
    manifest_dtype = str(tensor["dtype"])
    shape = [int(value) for value in tensor.get("shape", [])]
    return {
        "shard": spans[0]["shardPath"],
        "path": spans[0]["shardPath"],
        "sha256": spans[0]["shardSha256"],
        "peBuffer": weight_key,
        "peRange": [0, max(0, pe_count - 1)],
        "dtype": runtime_dtype(manifest_dtype),
        "tensor": weight_key,
        "offsetBytes": int(spans[0]["offset"]),
        "shape": shape,
        "quant": runtime_quant(manifest_dtype),
        "weightKey": weight_key,
        "tensorName": tensor_name,
        "role": str(tensor.get("role", "unknown")),
        "layout": str(tensor.get("layout", "unknown")),
        "byteSize": int(tensor["size"]),
        "byteOffset": int(spans[0]["offset"]),
        "spans": spans,
    }


def runtime_mapping_from_sidecar(
    *,
    weight_key: str,
    path: Path,
    pe_count: int,
) -> dict[str, Any]:
    size = path.stat().st_size
    return {
        "shard": str(path.resolve()),
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "peBuffer": weight_key,
        "peRange": [0, max(0, pe_count - 1)],
        "dtype": "f32",
        "tensor": weight_key,
        "offsetBytes": 0,
        "shape": [size // 4],
        "quant": runtime_quant("F32"),
        "weightKey": weight_key,
        "tensorName": weight_key,
        "role": "sidecar_weight",
        "layout": "flat_sidecar",
        "byteSize": size,
        "byteOffset": 0,
        "spans": [
            {
                "shardIndex": -1,
                "shardPath": str(path.resolve()),
                "shardSha256": sha256_file(path),
                "offset": 0,
                "size": size,
            }
        ],
    }


def build_runtime_weight_mappings(
    *,
    manifest_path: Path,
    weight_plan: dict[str, Any],
    runtime_config: dict[str, Any],
) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    tensors = manifest.get("tensors") or {}
    weight_root = resolve_weight_root(manifest_path, manifest)
    grid = (runtime_config.get("memoryPlan") or {}).get("grid") or {}
    pe_count = int(grid.get("width") or 1) * int(grid.get("height") or 1)
    shard_identities = shard_identities_by_index(manifest)
    mappings: list[dict[str, Any]] = []
    missing: list[str] = []
    sidecar_keys: list[str] = []

    for record in weight_plan.get("requiredWeights") or []:
        if not isinstance(record, dict):
            continue
        key = str(record.get("weightKey") or "")
        if not key:
            continue
        matched_tensor = record.get("matchedTensor")
        matched_file = record.get("matchedFile")
        if isinstance(matched_tensor, str) and isinstance(tensors.get(matched_tensor), dict):
            tensor = tensors[matched_tensor]
            spans = tensor_spans_for_runtime(
                tensor=tensor,
                shard_identities=shard_identities,
                weight_root=weight_root,
            )
            mappings.append(
                runtime_mapping_from_tensor(
                    weight_key=key,
                    tensor_name=matched_tensor,
                    tensor=tensor,
                    spans=spans,
                    pe_count=pe_count,
                )
            )
            continue
        if isinstance(matched_file, str) and matched_file:
            path = weight_root / matched_file
            if path.is_file():
                mappings.append(
                    runtime_mapping_from_sidecar(
                        weight_key=key,
                        path=path,
                        pe_count=pe_count,
                    )
                )
                sidecar_keys.append(key)
                continue
        if record.get("resolutionKind") in {
            "linear_attention_absent_v_projection",
            "architecture_disabled_session_input",
        }:
            continue
        missing.append(key)

    return {
        "mappings": mappings,
        "identity": {
            "modelId": manifest.get("modelId"),
            "manifestPath": rel(manifest_path),
            "manifestSha256": sha256_file(manifest_path),
            "weightSetId": (manifest.get("artifactIdentity") or {}).get(
                "weightPackId"
            ),
            "weightSetSha256": (manifest.get("artifactIdentity") or {}).get(
                "shardSetHash"
            ),
            "declaredShardCount": len(manifest.get("shards") or []),
            "requiredWeightCount": int(weight_plan.get("requiredWeightCount") or 0),
            "mappedWeightCount": len(mappings),
            "missingWeightCount": len(missing),
            "missingWeightKeys": missing,
            "sidecarWeightKeys": sidecar_keys,
            "requiredWeightKeysSha256": sha256_json(
                [
                    str(item.get("weightKey"))
                    for item in weight_plan.get("requiredWeights") or []
                    if isinstance(item, dict) and item.get("weightKey")
                ]
            ),
            "mappedWeightKeysSha256": sha256_json(
                [mapping["weightKey"] for mapping in mappings]
            ),
        },
    }


def normalize_smoke_execution(
    *,
    smoke_config_path: Path,
    out_dir: Path,
    model_layer_count: int,
) -> dict[str, Any]:
    smoke = load_json(smoke_config_path)
    payload = {
        "schemaVersion": 1,
        "artifactKind": "gemma4_31b_af16_normalized_execution_v1",
        "source": {
            "path": rel(smoke_config_path),
            "sha256": sha256_file(smoke_config_path),
        },
        "modelConfig": {
            **(smoke.get("modelConfig") or {}),
            "numLayers": model_layer_count,
        },
        "steps": smoke.get("steps") or [],
    }
    payload["sourceGraphSha256"] = sha256_json(payload["steps"])
    path = out_dir / "normalized-execution-v1.json"
    write_json(path, payload)
    return {
        "present": True,
        "path": str(path),
        "sha256": sha256_file(path),
        "modelConfig": payload["modelConfig"],
        "steps": payload["steps"],
    }


def token_prompt_ids(args: argparse.Namespace) -> list[int]:
    supplied = [int(value) for value in args.prompt_token_id]
    source = supplied if supplied else DEFAULT_PROMPT_TOKEN_IDS
    count = max(1, int(args.prefill_token_count))
    if len(source) >= count:
        return source[:count]
    return [*source, *([source[-1]] * (count - len(source)))]


def build_reference_request(
    *,
    args: argparse.Namespace,
    session_dir: Path,
) -> dict[str, Any]:
    token_ids = token_prompt_ids(args)
    prompt_path = session_dir / "inputs" / "prompt.u32"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    np.asarray(token_ids, dtype=np.uint32).tofile(prompt_path)
    transcript_path = session_dir / "reference-request.json"
    transcript_payload = {
        "schemaVersion": 1,
        "artifactKind": "gemma4_31b_af16_runtime_request",
        "promptTokenIds": token_ids,
        "requestedDecodeSteps": int(args.decode_token_count),
        "actualDecodeSteps": int(args.decode_token_count),
        "kvCache": {
            "mode": "runtime_generated",
            "layerDigestCount": int(args.decode_token_count),
        },
    }
    write_json(transcript_path, transcript_payload)
    return {
        "modelId": MODEL_ID,
        "manifestPath": rel(args.source_doppler_manifest),
        "manifestSha256": sha256_file(args.source_doppler_manifest),
        "inputSetComponents": {"tokenCount": len(token_ids)},
        "tokenizedPrompt": {
            "path": str(prompt_path),
            "sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
            "tokenCount": len(token_ids),
        },
        "decodeTranscript": {
            "status": "output_ready",
            "requestedDecodeSteps": int(args.decode_token_count),
            "actualDecodeSteps": int(args.decode_token_count),
            "stopReason": "operator_decode_budget",
            "generatedTokenIds": {"tokenCount": int(args.decode_token_count)},
            "logitsDigests": [
                {"stepIndex": index, "sha256": "runtime_capture_pending"}
                for index in range(int(args.decode_token_count))
            ],
            "transcript": {"path": str(transcript_path)},
        },
    }


def binding(
    *,
    symbol: str,
    buffer: str,
    role: str,
    access: str,
    source: str,
    **fields: Any,
) -> dict[str, Any]:
    result = {
        "symbol": symbol,
        "buffer": buffer,
        "role": role,
        "access": access,
        "source": source,
    }
    for key, value in fields.items():
        if value is not None:
            result[key] = value
    return result


def symbol_table_entry(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "buffer": item["buffer"],
        "role": item["role"],
        "access": item["access"],
    }


def append_symbol_table_entry(
    symbols: dict[str, dict[str, Any]],
    item: dict[str, Any],
) -> None:
    symbol = item["symbol"]
    entry = symbol_table_entry(item)
    existing = symbols.get(symbol)
    if existing is None:
        symbols[symbol] = entry
        return
    bindings = existing.get("bindings")
    if isinstance(bindings, list):
        bindings.append(entry)
    else:
        bindings = [symbol_table_entry(existing), entry]
    buffers = {str(record.get("buffer") or "") for record in bindings}
    roles = {str(record.get("role") or "") for record in bindings}
    accesses = {str(record.get("access") or "") for record in bindings}
    symbols[symbol] = {
        "buffer": next(iter(buffers)) if len(buffers) == 1 else "multiple",
        "role": next(iter(roles)) if len(roles) == 1 else "inout",
        "access": next(iter(accesses)) if len(accesses) == 1 else "readwrite",
        "bindings": bindings,
    }


def routed_tensor_role(buffer: str) -> str:
    if buffer.startswith("state:kv_cache"):
        return "kv_cache"
    return "activation"


def output_buffer(step: dict[str, Any], launch_index: int) -> str:
    layer = step.get("layer")
    token = step.get("tokenIndex")
    layer_part = "global" if layer is None else f"layer{layer}"
    token_part = "" if token is None else f":token{token}"
    return f"activation:{step['phase']}{token_part}:{launch_index:04d}:{layer_part}:{step['name']}"


def build_real_session_scheduler(
    *,
    dispatch_plan: dict[str, Any],
    runtime_config: dict[str, Any],
) -> dict[str, Any]:
    launches: list[dict[str, Any]] = []
    blockers: list[str] = []
    sample_feedback_edges: list[dict[str, Any]] = []
    kv_operations: list[dict[str, Any]] = []
    transcript_emitters: list[dict[str, Any]] = []
    lifetimes: dict[str, dict[str, Any]] = {}
    current = "input:prompt_token_ids"
    layer_state: dict[int, dict[str, str]] = {}
    last_generated_token = "input:prompt_token_ids"
    last_logits = ""
    last_logits_launch_index: int | None = None

    def touch_input(buffer: str, role: str, launch_index: int) -> None:
        item = lifetimes.setdefault(
            buffer,
            {
                "buffer": buffer,
                "role": role,
                "producerLaunchIndex": None,
                "firstConsumerLaunchIndex": None,
                "lastConsumerLaunchIndex": None,
                "consumerCount": 0,
            },
        )
        if item["firstConsumerLaunchIndex"] is None:
            item["firstConsumerLaunchIndex"] = launch_index
        item["lastConsumerLaunchIndex"] = launch_index
        item["consumerCount"] += 1

    def touch_output(buffer: str, role: str, launch_index: int) -> None:
        item = lifetimes.setdefault(
            buffer,
            {
                "buffer": buffer,
                "role": role,
                "producerLaunchIndex": None,
                "firstConsumerLaunchIndex": None,
                "lastConsumerLaunchIndex": None,
                "consumerCount": 0,
            },
        )
        if item["producerLaunchIndex"] is None:
            item["producerLaunchIndex"] = launch_index

    def make_launch(step: dict[str, Any]) -> None:
        nonlocal current, last_generated_token, last_logits, last_logits_launch_index
        launch_index = len(launches)
        kernel = str(step.get("kernelKey") or "")
        name = str(step.get("name") or kernel)
        weight_key = step.get("weightKey")
        is_lm_head = (
            name == "lm_head"
            or kernel in LM_HEAD_KERNELS
            or weight_key == "lm_head"
        )
        layer = step.get("layer")
        layer_idx = layer if isinstance(layer, int) else None
        state = layer_state.setdefault(layer_idx if layer_idx is not None else -1, {})
        inputs: list[dict[str, Any]] = []
        outputs: list[dict[str, Any]] = []

        def add_input(
            symbol: str,
            buffer_name: str,
            role: str,
            source: str,
            **fields: Any,
        ) -> None:
            inputs.append(
                binding(
                    symbol=symbol,
                    buffer=buffer_name,
                    role=role,
                    access="read",
                    source=source,
                    **fields,
                )
            )
            touch_input(buffer_name, role, launch_index)

        def add_output(
            symbol: str,
            buffer_name: str,
            role: str,
            source: str,
            **fields: Any,
        ) -> None:
            outputs.append(
                binding(
                    symbol=symbol,
                    buffer=buffer_name,
                    role=role,
                    access="write",
                    source=source,
                    **fields,
                )
            )
            touch_output(buffer_name, role, launch_index)

        out = output_buffer(step, launch_index)
        if kernel in {"embed", "ple_embed"}:
            token_source = (
                "input:prompt_token_ids"
                if step["phase"] == "prefill"
                else last_generated_token
            )
            add_input("indices", token_source, "tokenized_prompt", "runtime_prompt")
            add_input("table", f"weight:{step.get('weightKey')}", "weight", "weights")
            add_output("output", out, "activation", f"{kernel}.output")
            current = out
        elif kernel in {"tiled", "ple_proj"}:
            add_input("a", current, "activation", "activation_router")
            add_input("b", f"weight:{step.get('weightKey')}", "weight", "weights")
            add_output("c", out, "activation", f"{kernel}.output")
            current = out
        elif kernel in {"gemv", *LM_HEAD_KERNELS}:
            add_input("activation", current, "activation", "activation_router")
            add_input("weight", f"weight:{weight_key}", "weight", "weights")
            add_output(
                "output",
                out,
                "logits" if is_lm_head else "activation",
                f"{kernel}.output",
            )
            if name in {"q_proj", "k_proj", "v_proj"}:
                state[name[0]] = out
            if is_lm_head:
                decode_index = int(step.get("tokenIndex") or 0)
                last_logits = out
                last_logits_launch_index = launch_index
                transcript_emitters.append(
                    {
                        "kind": "logits_digest",
                        "stepIndex": decode_index,
                        "launchIndex": launch_index,
                        "symbol": "output",
                        "buffer": out,
                        "expectedSha256": None,
                    }
                )
            else:
                current = out
        elif kernel in {"rmsnorm", "ple_rmsnorm"}:
            add_input("input", current, "activation", "activation_router")
            add_input("weight", f"weight:{step.get('weightKey')}", "weight", "weights")
            add_output("output", out, "activation", f"{kernel}.output")
            if name == "input_norm":
                state["residual_base"] = current
            elif name == "post_attn_norm":
                state["ffn_residual_base"] = current
            current = out
        elif kernel == "rope":
            source_key = "q" if name == "rope_q" else "k"
            source = state.get(source_key, current)
            add_input("input", source, "activation", "activation_router")
            add_input("cos_table", "state:rope_cos_table", "position_encoding", "runtime_state")
            add_input("sin_table", "state:rope_sin_table", "position_encoding", "runtime_state")
            add_output("input", out, "activation", "rope.output")
            state[source_key] = out
            current = out
        elif kernel in {"attn_small", "attn_decode", "attn_decode_sliding"}:
            query = state.get("q", current)
            key = state.get("k", "state:kv_cache:key")
            val = state.get("v", "state:kv_cache:value")
            add_input("query", query, "activation", "activation_router")
            add_input("key", key, routed_tensor_role(key), "kv_or_activation_router")
            add_input("val", val, routed_tensor_role(val), "kv_or_activation_router")
            if kernel in {"attn_decode", "attn_decode_sliding"}:
                add_input("position", "state:decode_position", "position", "runtime_state")
                add_input("sliding_window", "state:sliding_window", "position", "runtime_state")
            add_output("output", out, "activation", f"{kernel}.output")
            kv_operations.append(
                {
                    "launchIndex": launch_index,
                    "phase": step["phase"],
                    "decodeStepIndex": step.get("tokenIndex"),
                    "layerIndex": layer_idx,
                    "attentionKernel": kernel,
                    "write": {
                        "keyBuffer": state.get("k", key),
                        "valueBuffer": state.get("v", val),
                        "cacheBuffer": "state:kv_cache",
                        "positionSource": "decode_position",
                    },
                    "read": {
                        "keyBuffer": key,
                        "valueBuffer": val,
                        "cacheBuffer": "state:kv_cache",
                        "slidingWindowSource": (
                            "sliding_window"
                            if kernel == "attn_decode"
                            else "prefill_full_context"
                        ),
                    },
                }
            )
            current = out
        elif kernel in {"kv_write", "kv_write_shared"}:
            add_input(
                "key_proj",
                state.get("k", current),
                "activation",
                "activation_router",
            )
            add_input(
                "val_proj",
                state.get("v", current),
                "activation",
                "activation_router",
            )
            add_input("position", "state:decode_position", "position", "runtime_state")
            add_output(
                "key_cache",
                f"activation:kv:{launch_index:04d}:key",
                "activation",
                f"{kernel}.key_cache",
            )
            add_output(
                "val_cache",
                f"activation:kv:{launch_index:04d}:val",
                "activation",
                f"{kernel}.val_cache",
            )
        elif kernel == "residual":
            residual = (
                state.get("residual_base")
                if name == "attn_residual"
                else state.get("ffn_residual_base")
            )
            if not residual:
                residual = "activation:missing:residual"
                blockers.append(f"launch[{launch_index}].residual_base_missing:{name}")
            add_input("input", current, "activation", "activation_router")
            add_input("residual", residual, "activation", "activation_router")
            add_output("output", out, "activation", "residual.output")
            current = out
        elif kernel == "ple_residual":
            add_input("u", "state:decode_position", "position", "runtime_state")
            add_input("input", current, "activation", "activation_router")
            add_output("output", out, "activation", "ple_residual.output")
            current = out
        elif kernel == "gelu":
            add_input("input", current, "activation", "activation_router")
            add_output("output", out, "activation", "gelu.output")
            current = out
        elif kernel == "sample":
            if not last_logits:
                blockers.append(f"launch[{launch_index}].sample_logits_producer_missing")
                last_logits = "logits:missing"
            token_buffer = f"tokens:decode:{launch_index:04d}"
            add_input("logits", last_logits, "logits", "transcript_capture")
            add_output("tokens", token_buffer, "generated_tokens", "sample.output")
            transcript_emitters.append(
                {
                    "kind": "generated_token",
                    "stepIndex": int(step.get("tokenIndex") or 0),
                    "launchIndex": launch_index,
                    "symbol": "tokens",
                    "buffer": token_buffer,
                    "logitsBuffer": last_logits,
                    "logitsLaunchIndex": last_logits_launch_index,
                }
            )
            decode_index = int(step.get("tokenIndex") or 0)
            if decode_index + 1 < int(dispatch_plan["decodeTokenCount"]):
                sample_feedback_edges.append(
                    {
                        "fromLaunchIndex": launch_index,
                        "tokenBuffer": token_buffer,
                        "toDecodeStepIndex": decode_index + 1,
                    }
                )
            last_generated_token = token_buffer
        else:
            add_input("input", current, "activation", "activation_router")
            add_output("output", out, "activation", f"{kernel}.output")
            current = out

        symbols: dict[str, dict[str, Any]] = {}
        for item in [*inputs, *outputs]:
            append_symbol_table_entry(symbols, item)
        launches.append(
            {
                "launchIndex": launch_index,
                "phase": step["phase"],
                "phaseLaunchIndex": launch_index,
                "kernelName": kernel,
                "kernelPattern": kernel,
                "repeat": 1,
                "operationName": name,
                "layerIndex": layer_idx,
                "decodeStepIndex": step.get("tokenIndex"),
                "weightKey": step.get("weightKey"),
                "inputs": inputs,
                "outputs": outputs,
                "symbols": symbols,
                "symbolDataflowPresent": True,
                "inputSymbolCount": len(inputs),
                "outputSymbolCount": len(outputs),
                "symbolTablePresent": True,
            }
        )

    for step in dispatch_plan.get("prefillSteps") or []:
        make_launch(step)
    for token in dispatch_plan.get("decodeByToken") or []:
        for step in token.get("steps") or []:
            make_launch(step)

    model_layers = int(runtime_config.get("modelConfig", {}).get("numLayers") or 0)
    covered_layers = sorted(
        {
            op.get("layerIndex")
            for op in kv_operations
            if isinstance(op.get("layerIndex"), int)
        }
    )
    expected_decode_steps = int(dispatch_plan["decodeTokenCount"])
    logits_emitters = [
        item for item in transcript_emitters if item["kind"] == "logits_digest"
    ]
    token_emitters = [
        item for item in transcript_emitters if item["kind"] == "generated_token"
    ]
    if len(logits_emitters) != expected_decode_steps:
        blockers.append(
            f"transcript_logits_emitter_count:{len(logits_emitters)}!={expected_decode_steps}"
        )
    if len(token_emitters) != expected_decode_steps:
        blockers.append(
            f"transcript_token_emitter_count:{len(token_emitters)}!={expected_decode_steps}"
        )
    transcript_status = (
        "bound"
        if expected_decode_steps > 0
        and len(logits_emitters) == expected_decode_steps
        and len(token_emitters) == expected_decode_steps
        else "blocked_missing_decode_emitters"
    )
    status = "bound" if not blockers else "blocked"
    return {
        "status": status,
        "blockers": blockers,
        "runtimeExpansion": {
            "decodeIterationCount": int(dispatch_plan["decodeTokenCount"]),
            "runtimeLaunchCount": len(launches),
        },
        "activationRouting": {
            "status": "bound",
            "bufferCount": len(lifetimes),
            "routedBufferCount": len(lifetimes),
            "lifetimes": sorted(lifetimes.values(), key=lambda item: item["buffer"]),
        },
        "kvCacheSchedule": {
            "status": "bound" if kv_operations else "blocked_missing_kv_operations",
            "cacheWriteCount": len(kv_operations),
            "cacheReadCount": len(kv_operations),
            "layerCoverage": {
                "layerCount": model_layers,
                "coveredLayerCount": len(covered_layers),
                "coveredLayers": covered_layers,
            },
            "operations": kv_operations,
        },
        "sampleFeedback": {
            "status": (
                "bound"
                if len(sample_feedback_edges)
                == max(0, int(dispatch_plan["decodeTokenCount"]) - 1)
                else "blocked"
            ),
            "edges": sample_feedback_edges,
        },
        "transcriptCaptureSchedule": {
            "status": transcript_status,
            "expectedActualDecodeSteps": expected_decode_steps,
            "logitsEmitterCount": len(logits_emitters),
            "tokenEmitterCount": len(token_emitters),
            "emitters": transcript_emitters,
        },
        "launches": launches,
    }


def host_io_layout_from_buffer_plan(
    buffer_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    layout: list[dict[str, Any]] = []
    for buffer in buffer_plan.get("buffers") or []:
        if not isinstance(buffer, dict):
            continue
        storage = str(buffer.get("storageClass") or "")
        if storage not in {
            "shared_input",
            "captured_output",
            "persistent_state",
            "external_weight",
        }:
            continue
        layout.append(
            {
                "buffer": buffer.get("buffer"),
                "bufferRole": buffer.get("role"),
                "storageClass": storage,
                "dtype": buffer.get("dtype"),
                "plannedElementCount": buffer.get("plannedElementCount"),
                "plannedByteLength": buffer.get("plannedByteLength"),
            }
        )
    return layout


def build_real_session_runtime(
    args: argparse.Namespace,
    dispatch_plan: dict[str, Any],
    weight_plan: dict[str, Any],
) -> dict[str, Any]:
    session_dir = resolve(args.session_out_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    plan = load_json(args.simulator_plan)
    runtime_config = load_json(args.runtime_config)
    runtime_config["mode"] = "sdk-runtime-command"
    runtime_config["modelConfig"] = {
        **(runtime_config.get("modelConfig") or {}),
        "numLayers": int(weight_plan.get("modelLayerCount") or 0),
    }
    mappings = build_runtime_weight_mappings(
        manifest_path=args.source_doppler_manifest,
        weight_plan=weight_plan,
        runtime_config=runtime_config,
    )
    runtime_config["weightMappings"] = mappings["mappings"]
    runtime_config["weightIdentity"] = mappings["identity"]
    normalized = normalize_smoke_execution(
        smoke_config_path=args.smoke_config,
        out_dir=session_dir,
        model_layer_count=int(weight_plan.get("modelLayerCount") or 0),
    )
    reference = build_reference_request(args=args, session_dir=session_dir)
    scheduler = build_real_session_scheduler(
        dispatch_plan=dispatch_plan,
        runtime_config=runtime_config,
    )
    scheduler_record = {
        "path": str(args.host_plan),
        "present": True,
        "runtimeScheduler": scheduler,
        "launchesCarrySymbolDataflow": bool(scheduler.get("launches")),
    }
    manifest_preflight = {
        "status": "passed",
        "blockers": [],
        "source": "gemma4_31b_af16_session_runtime_contract",
    }
    validator = validate_hostplan_executor(
        plan=plan,
        compile_root=resolve(args.compile_root),
        runtime_config=runtime_config,
        scheduler={"hostPlan": scheduler_record},
        manifest_preflight=manifest_preflight,
    )
    execution_plan = build_hostplan_execution_plan(
        plan=plan,
        compile_root=resolve(args.compile_root),
        runtime_config=runtime_config,
        scheduler={"hostPlan": scheduler_record},
        executor_validator=validator,
    )
    runtime_config["hostIoLayout"] = host_io_layout_from_buffer_plan(
        execution_plan.get("bufferPlan") or {}
    )
    runtime_config_path = session_dir / "runtime-config.json"
    execution_plan_path = session_dir / "hostplan-execution-plan.json"
    scheduler_path = session_dir / "runtime-scheduler.json"
    write_json(runtime_config_path, runtime_config)
    write_json(scheduler_path, scheduler)
    write_json(execution_plan_path, execution_plan)
    result: dict[str, Any] = {
        "requested": bool(args.execute),
        "status": "planned",
        "sessionDir": rel(session_dir),
        "runtimeConfigPath": rel(runtime_config_path),
        "runtimeConfigSha256": sha256_file(runtime_config_path),
        "normalizedExecution": {
            "path": rel(Path(normalized["path"])),
            "sha256": normalized["sha256"],
        },
        "runtimeSchedulerPath": rel(scheduler_path),
        "executionPlanPath": rel(execution_plan_path),
        "weightMappingStatus": mappings["identity"],
        "hostIoLayoutCount": len(runtime_config["hostIoLayout"]),
        "schedulerStatus": scheduler.get("status"),
        "schedulerBlockers": scheduler.get("blockers") or [],
        "executorValidatorStatus": validator.get("status"),
        "executorValidatorBlockers": validator.get("blockers") or [],
        "executionPlanStatus": execution_plan.get("status"),
        "executionPlanBlockers": execution_plan.get("blockers") or [],
        "sampleFeedback": scheduler.get("sampleFeedback") or {},
    }
    blockers = [
        *[f"scheduler:{item}" for item in scheduler.get("blockers") or []],
        *[f"executor_validator:{item}" for item in validator.get("blockers") or []],
        *[f"execution_plan:{item}" for item in execution_plan.get("blockers") or []],
    ]
    if mappings["identity"]["missingWeightCount"]:
        blockers.append("runtime_weight_mappings_incomplete")
    if blockers:
        result["status"] = "blocked"
        result["blockers"] = blockers
        return result
    if not args.execute:
        result["status"] = "ready_not_executed"
        result["blockers"] = ["execution_not_requested"]
        return result

    progress_path = session_dir / "progress.jsonl"
    bootstrap = execute_hostplan_runtime_bootstrap(
        execution_plan=execution_plan,
        progress_path=progress_path,
        cmaddr=args.cmaddr.strip() or None,
    )
    result["bootstrap"] = bootstrap
    if bootstrap.get("status") != "ready_for_tensor_movement":
        result["status"] = "blocked"
        result["blockers"] = [
            f"bootstrap:{item}" for item in bootstrap.get("blockers") or ["unknown"]
        ]
        return result
    runtime = execute_hostplan_runtime(
        bootstrap=bootstrap,
        export=reference,
        progress_path=progress_path,
        cmaddr=args.cmaddr.strip() or None,
        trace_path=session_dir / "trace.json",
        stop_after_launch=args.stop_after_launch,
    )
    result["runtime"] = runtime
    result["status"] = (
        "output_ready" if runtime.get("status") == "succeeded" else "blocked"
    )
    if result["status"] != "output_ready":
        result["blockers"] = [
            f"runtime:{item}" for item in runtime.get("blockers") or ["unknown"]
        ]
    return result


def build_blockers(
    *,
    weight_plan: dict[str, Any],
    per_kernel: dict[str, Any],
    refresh: dict[str, Any],
    real_session: dict[str, Any],
    execute: bool,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if (
        not weight_plan["weightRootPresent"]
        or weight_plan["missingShards"]
        or weight_plan["sizeMismatches"]
    ):
        blockers.append({
            "class": "weight_pack_not_stageable",
            "detail": (
                "The af16 weightsRef primary is not fully present by declared "
                "shard files and sizes."
            ),
        })
    if weight_plan["unresolvedWeightKeys"]:
        blockers.append({
            "class": "weight_symbol_mapping_incomplete",
            "detail": (
                "Some execution-v1 weightsKey entries do not resolve to a "
                "manifest tensor or sidecar f32 slice."
            ),
            "unresolvedWeightKeys": weight_plan["unresolvedWeightKeys"][:20],
        })
    refresh_requested = bool(refresh.get("requested"))
    refresh_blocked = refresh_requested and refresh.get("status") == "blocked"
    stale_dry_run_only = bool(per_kernel.get("staleDryRunOnly"))
    if (
        per_kernel.get("blockedKernels")
        and not (refresh_blocked and stale_dry_run_only)
    ):
        blockers.append({
            "class": "manifest_kernel_dispatch_not_bound",
            "detail": (
                "The current manifest-shape per-kernel summary still contains "
                "non-bound kernel verdicts."
            ),
            "blockedKernelCount": len(per_kernel["blockedKernels"]),
        })
    if refresh.get("requested") and refresh.get("status") == "blocked":
        refresh_blocker = refresh.get("blocker") or {}
        blockers.append({
            "class": refresh_blocker.get("class")
            or "per_kernel_refresh_blocked",
            "detail": (
                "The af16 per-kernel refresh command could not run to bound "
                "receipts on this host."
            ),
        })
    if real_session.get("status") == "blocked":
        blockers.append({
            "class": "real_session_runtime_blocked",
            "detail": (
                "The real prefill/decode session runtime contract is "
                "materialized but not executable to token output yet."
            ),
            "blockers": real_session.get("blockers", [])[:20],
        })
    if not execute:
        blockers.append({
            "class": "execution_not_requested",
            "detail": (
                "The runner emitted the session plan and staging checks "
                "without launching SDK dispatch."
            ),
        })
    elif real_session.get("status") in {"planned", "ready_not_executed"}:
        blockers.append({
            "class": "combined_session_runtime_absent",
            "detail": (
                "The checked-in af16 artifacts are per-kernel cslc outputs. "
                "A real end-to-end simfabric run needs one session runtime "
                "that binds cross-kernel tensors and KV cache state."
            ),
        })
    return blockers


def build_trace(args: argparse.Namespace) -> dict[str, Any]:
    weight_plan = build_weight_staging_plan(
        manifest_path=args.source_doppler_manifest,
        smoke_config_path=args.smoke_config,
    )
    dispatch_plan = build_dispatch_plan(
        smoke_config_path=args.smoke_config,
        host_plan_path=args.host_plan,
        prefill_token_count=args.prefill_token_count,
        decode_token_count=args.decode_token_count,
        model_layer_count=int(weight_plan.get("modelLayerCount") or 0),
    )
    refresh = maybe_refresh_per_kernel(args)
    per_kernel = per_kernel_summary_block(args.per_kernel_summary)
    real_session = build_real_session_runtime(args, dispatch_plan, weight_plan)
    blockers = build_blockers(
        weight_plan=weight_plan,
        per_kernel=per_kernel,
        refresh=refresh,
        real_session=real_session,
        execute=args.execute,
    )
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_gemma4_31b_af16_hostplan_streaming_trace",
        "modelId": MODEL_ID,
        "laneKey": LANE_KEY,
        "executionTarget": "system" if args.cmaddr else "simfabric",
        "requestedExecution": {
            "prefillTokenCount": args.prefill_token_count,
            "decodeTokenCount": args.decode_token_count,
            "execute": bool(args.execute),
        },
        "weightStaging": weight_plan,
        "dispatchPlan": dispatch_plan,
        "perKernelRefresh": refresh,
        "perKernelEvidence": per_kernel,
        "realSessionRuntime": real_session,
        "status": "blocked" if blockers else "output_ready",
        "blockers": blockers,
        "claim": {
            "scope": (
                "Gemma 4 31B af16 real-inference runner front door, weight "
                "staging plan, dispatch expansion, per-kernel refresh command, "
                "and serial HostPlan session contract are materialized."
            ),
            "notWhat": (
                "Not a generated token transcript until status is output_ready "
                "and blockers is empty."
            ),
            "summary": (
                "The runnable contract exists; current artifacts remain "
                "blocked before end-to-end CSL output."
            ),
        },
    }


def main() -> int:
    args = parse_args()
    trace = build_trace(args)
    out = resolve(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {rel(out)} status={trace['status']} "
        f"blockers={len(trace['blockers'])}"
    )
    return 0 if trace["status"] == "output_ready" else 1


if __name__ == "__main__":
    sys.exit(main())
