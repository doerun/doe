#!/usr/bin/env python3
"""INT4PLE af16 HostPlan streaming-runner front door.

This runner owns the operational contract for real af16 prefill/decode
through generated HostPlan/CSL. Gemma 4 31B is the default lane; other lanes
may pass explicit model, manifest, config, and claim fields. It performs the
source-derivable front-door work and delegates the session-scoped runtime
contract to ``gemma4_31b_af16_session_runtime``:

  - resolve the af16 Doppler manifest through its weightsRef primary;
  - validate shard presence and declared sizes without copying weight bytes;
  - expand the execution-v1 smoke config into prefill/decode dispatch plans;
  - bind the af16 HostPlan compile artifacts and per-kernel summary;
  - write the source-graph inventory used by the inference evidence gate;
  - emit a trace with the remaining named blockers.

It does not invent model output. ``status=output_ready`` requires the
session runtime to produce a real token/logit/KV transcript.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_ROOT = REPO_ROOT.parent
RUNNER_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from bench.tools._lane_dtype_profile import (  # noqa: E402
    canonical_dtype_profile,
    csl_dtype_contract_for_profile,
)
from bench.tools._inference_evidence_gate import (  # noqa: E402
    evaluate_inference_evidence_gate,
    session_runtime_evidence_is_complete,
)
from bench.tools.int4ple_runtime_weight_mappings import (  # noqa: E402
    inferred_rmsnorm_weight_key,
    layer_index_from_step_weight_key,
    tensor_name_candidates_for_weight_key,
)
from gemma4_31b_af16_session_runtime import (  # noqa: E402
    DEFAULT_LAUNCH_TIMEOUT_SECONDS,
    build_real_session_runtime,
)

MODEL_ID = "gemma-4-31b-it-text-q4k-ehf16-af16"
LANE_KEY = "q4k-ehf16-af16"
TRACE_ARTIFACT_KIND = "doe_gemma4_31b_af16_hostplan_streaming_trace"
SESSION_ARTIFACT_PREFIX = "gemma4_31b_af16"
DEFAULT_CLAIM_SCOPE = (
    "Gemma 4 31B af16 real-inference runner front door, weight staging "
    "plan, dispatch expansion, per-kernel refresh command, and resumable "
    "HostPlan session contract are materialized."
)
DEFAULT_CLAIM_NOT_WHAT = (
    "Not a generated token transcript until status is output_ready and "
    "blockers is empty."
)
DEFAULT_CLAIM_SUMMARY = (
    "The runnable contract exists; current artifacts remain blocked before "
    "end-to-end CSL output."
)
PLE_EMBED_KEY_PREFIX = "per_layer_inputs.embedTokensPerLayer.layer"
PLE_PROJECTION_KEY_PREFIX = "per_layer_inputs.perLayerModelProjection.layer"
PLE_PROJECTION_NORM_KEY_PREFIX = "per_layer_inputs.perLayerProjectionNorm.layer"
PER_LAYER_INPUT_KEY_PREFIX = "per_layer_inputs."
LINEAR_ATTENTION_POLICY = "skip-with-layout-metadata"
MODEL_LEVEL_PREFILL_STEPS = frozenset({
    "final_norm_prefill",
    "lm_head_prefill",
    "sample_prefill",
})
MODEL_LEVEL_DECODE_STEPS = frozenset({"final_norm", "lm_head"})
LM_HEAD_KERNELS = frozenset({
    "lm_head_gemv",
    "lm_head_gemv",
    "lm_head_prefill",
})
DEFAULT_SOURCE_MANIFEST = (
    WORKSPACE_ROOT
    / "doppler/models/local/gemma-4-31b-it-text-q4k-ehf16-af16/manifest.json"
)
DEFAULT_SMOKE_CONFIG = (
    REPO_ROOT / "runtime/zig/examples/execution-v1/gemma-4-31b-af16-smoke.json"
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
DEFAULT_SOURCE_GRAPH_INVENTORY = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-manifest-fullgraph-compile-steps/"
    "source-graph-inventory.json"
)
MANIFEST_KERNEL_PROBE_RUNNER = (
    REPO_ROOT / "bench/runners/csl-runners/manifest_kernel_probe_runner.py"
)
CS_PYTHON = REPO_ROOT / "runtime/zig/tools/cs_python_singularity.sh"
CHAIN_STEP_ADAPTER = (
    REPO_ROOT / "bench/runners/csl-runners/chain_step_adapter.py"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-doppler-manifest",
        type=Path,
        default=DEFAULT_SOURCE_MANIFEST,
    )
    parser.add_argument("--expected-model-id", default=MODEL_ID)
    parser.add_argument("--lane-key", default=LANE_KEY)
    parser.add_argument("--trace-artifact-kind", default=TRACE_ARTIFACT_KIND)
    parser.add_argument("--session-artifact-prefix", default=SESSION_ARTIFACT_PREFIX)
    parser.add_argument("--claim-scope", default=DEFAULT_CLAIM_SCOPE)
    parser.add_argument("--claim-not-what", default=DEFAULT_CLAIM_NOT_WHAT)
    parser.add_argument("--claim-summary", default=DEFAULT_CLAIM_SUMMARY)
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
        default=1800,
        help=(
            "Per-kernel subprocess timeout passed to the refresh runner. "
            "Wide-output kernels use the HostPlan D2H region contract so "
            "timeouts remain fail-closed diagnostics rather than claim logic."
        ),
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
        "--source-graph-inventory",
        type=Path,
        default=None,
        help=(
            "Source execution-v1 kernel inventory artifact consumed by the "
            "inference evidence gate. Defaults next to --host-plan."
        ),
    )
    parser.add_argument(
        "--stop-after-launch",
        type=int,
        default=-1,
        help="Stop the real session after persisting this launch index.",
    )
    parser.add_argument(
        "--launch-timeout-seconds",
        type=int,
        default=DEFAULT_LAUNCH_TIMEOUT_SECONDS,
        help="Per HostPlan launch-step subprocess timeout. Use 0 to disable.",
    )
    parser.add_argument(
        "--session-lm-head-dispatch-mode",
        choices=["monolithic", "dense_gemv_width_tiled_session"],
        default="monolithic",
        help="Execution mode for real-session lm-head launches.",
    )
    parser.add_argument(
        "--session-lm-head-tile-width",
        type=int,
        default=120,
        help="Hidden-width tile for dense_gemv_width_tiled_session.",
    )
    parser.add_argument(
        "--session-lm-head-tile-jobs",
        type=int,
        default=1,
        help="Parallel tile subprocess count for dense_gemv_width_tiled_session.",
    )
    parser.add_argument(
        "--session-embed-roi-jobs",
        type=int,
        default=1,
        help="Parallel jobs for independent real-session embed/PLE ROI launches.",
    )
    parser.add_argument(
        "--session-embed-roi-hidden-per-pe",
        type=int,
        default=0,
        help=(
            "Override hidden elements per PE for real-session embed ROI "
            "launches; 0 uses the HostPlan compile parameter."
        ),
    )
    parser.add_argument(
        "--session-prefill-q4k-gemv-jobs",
        type=int,
        default=1,
        help="Parallel adapter workers for real-session prefill Q4K GEMV launches.",
    )
    parser.add_argument(
        "--session-prefill-q4k-gemv-output-pe-rows",
        type=int,
        default=1,
        help="Output PE rows per real-session prefill Q4K GEMV launch tile.",
    )
    parser.add_argument(
        "--session-prefill-q4k-gemv-adapter-step-budget",
        type=int,
        default=1,
        help=(
            "Maximum Q4K GEMV tile steps per SDK adapter process. "
            "Use 1 to isolate simulator state between tile launches."
        ),
    )
    parser.add_argument(
        "--session-ple-proj-dispatch-mode",
        choices=["monolithic_summa", "compact_summa_session"],
        default="monolithic_summa",
        help="Execution mode for real-session PLE projection launches.",
    )
    parser.add_argument(
        "--session-attention-prefill-dispatch-mode",
        choices=["hostplan_static", "compact_width_session"],
        default="hostplan_static",
        help="Execution mode for real-session prefill attention launches.",
    )
    parser.add_argument(
        "--session-lm-head-batch-runtime",
        action="store_true",
        help="Run session lm-head tiles through the batched SDK adapter.",
    )
    parser.add_argument(
        "--session-lm-head-batch-runtime-step-budget",
        type=int,
        default=16,
        help="Tile step group size for session lm-head batched runtime.",
    )
    parser.add_argument(
        "--session-lm-head-tile-dispatch-budget",
        type=int,
        default=0,
        help="Stop session lm-head tile dispatch after this many fresh tiles; 0 means unbounded.",
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=None,
        help="Persist per-launch HostPlan checkpoints under this directory.",
    )
    parser.add_argument(
        "--resume-from-checkpoint",
        type=Path,
        default=None,
        help="Resume from a previously persisted HostPlan checkpoint.",
    )
    parser.add_argument(
        "--ignore-checkpoint",
        action="store_true",
        help="Run from launch 0 even when --resume-from-checkpoint is set.",
    )
    parser.add_argument(
        "--allow-checkpoint-runner-drift",
        action="store_true",
        help=(
            "Allow resume when only the checkpoint runnerVersion field drifted. "
            "Manifest/config/compile-target identity and buffer hashes still validate."
        ),
    )
    parser.add_argument(
        "--allow-checkpoint-canonicalization-drift",
        action="store_true",
        help=(
            "Allow resume across the tiled_31b prefill_q4k_gemv "
            "canonicalization boundary. Only hostplanSha256 and compile-target "
            "hashes for the same target set may drift; buffer hashes still validate."
        ),
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
    if len(parts) >= 2 and parts[0] == "layer" and parts[1] == "linear_attn":
        return ".".join(["layer", str(layer_index), *parts[1:]])
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


def is_dense_lm_head_step(step: dict[str, Any] | None) -> bool:
    if not isinstance(step, dict):
        return False
    op = str(step.get("op") or "")
    kernel = str(step.get("kernelKey") or "")
    return op == "matmul" or kernel == "lm_head_prefill"


def is_q4k_lm_head_step(step: dict[str, Any] | None) -> bool:
    if not isinstance(step, dict):
        return False
    op = str(step.get("op") or "")
    kernel = str(step.get("kernelKey") or "")
    return op == "matmul_q4k" or kernel in {"lm_head_gemv", "lm_head_gemv"}


def tensor_candidates_for_key(
    weight_key: str,
    step: dict[str, Any] | None = None,
) -> list[str]:
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
    if weight_key == "lm_head" and is_dense_lm_head_step(step):
        return [
            "model.language_model.embed_tokens.weight",
            "language_model.model.embed_tokens.weight",
            "model.embed_tokens.weight",
            "embed_tokens.weight",
            "model.language_model.lm_head.weight",
            "language_model.lm_head.weight",
            "model.lm_head.weight",
            "lm_head.weight",
        ]
    if weight_key.startswith("layer."):
        parts = weight_key.split(".")
        if len(parts) >= 4 and parts[2] == "linear_attn":
            layer = parts[1]
            suffix = ".".join(parts[3:])
            if suffix == "conv1d":
                suffix = "conv1d.weight"
            if suffix:
                return [
                    f"model.language_model.layers.{layer}.linear_attn.{suffix}",
                    f"model.layers.{layer}.linear_attn.{suffix}",
                ]
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


def is_linear_attention_weight_key(weight_key: str | None) -> bool:
    if not isinstance(weight_key, str):
        return False
    parts = weight_key.split(".")
    return len(parts) >= 3 and parts[0] == "layer" and parts[2] == "linear_attn"


def is_self_attention_weight_key(weight_key: str | None) -> bool:
    if not isinstance(weight_key, str):
        return False
    parts = weight_key.split(".")
    return len(parts) >= 3 and parts[0] == "layer" and parts[2] == "self_attn"


def linear_attention_layers_from_tensors(tensors: dict[str, Any]) -> list[int]:
    layers: set[int] = set()
    prefix = "model.language_model.layers."
    marker = ".linear_attn."
    for tensor_name in tensors:
        if not tensor_name.startswith(prefix) or marker not in tensor_name:
            continue
        rest = tensor_name.removeprefix(prefix)
        layer_text = rest.split(".", 1)[0]
        try:
            layers.add(int(layer_text))
        except ValueError:
            continue
    return sorted(layers)


def self_attention_layers_from_tensors(tensors: dict[str, Any]) -> list[int]:
    layers: set[int] = set()
    prefix = "model.language_model.layers."
    marker = ".self_attn."
    for tensor_name in tensors:
        if not tensor_name.startswith(prefix) or marker not in tensor_name:
            continue
        rest = tensor_name.removeprefix(prefix)
        layer_text = rest.split(".", 1)[0]
        try:
            layers.add(int(layer_text))
        except ValueError:
            continue
    return sorted(layers)


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


def per_layer_input_block_enabled(architecture: dict[str, Any]) -> bool:
    hidden = int(architecture.get("hiddenSizePerLayerInput") or 0)
    return hidden > 0


def is_architecture_disabled_per_layer_input_weight(
    weight_key: str,
    architecture: dict[str, Any],
) -> bool:
    return (
        weight_key.startswith(PER_LAYER_INPUT_KEY_PREFIX)
        and not per_layer_input_block_enabled(architecture)
    )


def is_linear_attention_session_state_key(weight_key: str) -> bool:
    parts = weight_key.split(".")
    return len(parts) == 3 and parts[0] == "layer" and parts[2] == "linear_attn"


def resolve_required_weight(
    *,
    weight_key: str,
    candidates: list[str],
    tensors: dict[str, Any],
    weight_root: Path,
    architecture: dict[str, Any],
    step: dict[str, Any] | None = None,
) -> dict[str, Any]:
    matched_tensor = next((c for c in candidates if c in tensors), None)
    matched_file = next((c for c in candidates if (weight_root / c).is_file()), None)
    if is_architecture_disabled_per_layer_input_weight(weight_key, architecture):
        return {
            "weightKey": weight_key,
            "candidates": candidates,
            "matchedTensor": None,
            "matchedFile": None,
            "resolutionKind": "architecture_disabled_session_input",
            "resolved": True,
        }
    if matched_tensor:
        if weight_key == "lm_head":
            tensor = tensors.get(matched_tensor) or {}
            dtype = str(tensor.get("dtype") or "")
            shape = tensor.get("shape") or []
            valid_dense = (
                is_dense_lm_head_step(step)
                and dtype in {"F16", "BF16", "F32"}
                and isinstance(shape, list)
                and len(shape) >= 2
                and int(shape[0] or 0) > 0
                and int(shape[1] or 0) > 0
            )
            valid_q4k = (
                is_q4k_lm_head_step(step)
                and dtype == "Q4_K_M"
                and (
                    ".lm_head." in matched_tensor
                    or matched_tensor.endswith("lm_head.weight")
                )
            )
            if not (valid_dense or valid_q4k):
                return {
                    "weightKey": weight_key,
                    "candidates": candidates,
                    "matchedTensor": matched_tensor,
                    "matchedFile": None,
                    "resolutionKind": "invalid_lm_head_dtype_selection",
                    "expected": (
                        "Q4_K_M explicit lm_head.weight"
                        if is_q4k_lm_head_step(step)
                        else "F16/BF16/F32 tied dense lm_head tensor"
                    ),
                    "actualDtype": dtype,
                    "actualShape": shape,
                    "resolved": False,
                }
        return {
            "weightKey": weight_key,
            "candidates": candidates,
            "matchedTensor": matched_tensor,
            "matchedFile": None,
            "resolutionKind": (
                "manifest_tied_dense_lm_head"
                if weight_key == "lm_head" and is_dense_lm_head_step(step)
                else "manifest_tensor"
            ),
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
    if is_linear_attention_session_state_key(weight_key):
        return {
            "weightKey": weight_key,
            "candidates": candidates,
            "matchedTensor": None,
            "matchedFile": None,
            "resolutionKind": "linear_attention_session_state",
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
    expected_model_id: str = MODEL_ID,
    lane_key: str = LANE_KEY,
) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    smoke = load_json(smoke_config_path)
    profile = canonical_dtype_profile(manifest.get("quantizationInfo"))
    if manifest.get("modelId") != expected_model_id:
        raise ValueError(
            f"expected modelId {expected_model_id!r}, "
            f"got {manifest.get('modelId')!r}"
        )
    if profile.get("variantTag") != lane_key:
        raise ValueError(
            f"expected lane {lane_key!r}, got {profile.get('variantTag')!r}"
        )
    csl_dtype_contract = csl_dtype_contract_for_profile(
        profile,
        model_id=str(manifest.get("modelId") or ""),
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
    ple_hidden = int(architecture.get("hiddenSizePerLayerInput") or 0)
    linear_attention_layers = linear_attention_layers_from_tensors(tensors)
    linear_attention_layer_set = set(linear_attention_layers)
    self_attention_layers = self_attention_layers_from_tensors(tensors)
    self_attention_layer_set = set(self_attention_layers)
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
            if (
                is_linear_attention_weight_key(key)
                and layer_index not in linear_attention_layer_set
            ):
                continue
            if (
                is_self_attention_weight_key(key)
                and self_attention_layer_set
                and layer_index not in self_attention_layer_set
            ):
                continue
            if key in required:
                continue
            candidates = tensor_candidates_for_key(key, step)
            required[key] = resolve_required_weight(
                weight_key=key,
                candidates=candidates,
                tensors=tensors,
                weight_root=weight_root,
                architecture=architecture,
                step=step,
            )

    unresolved = [
        key for key, record in required.items() if not record["resolved"]
    ]
    architecture_disabled_weight_keys = [
        key
        for key, record in required.items()
        if record.get("resolutionKind") == "architecture_disabled_session_input"
    ]
    return {
        "mode": "weightsRef_resident_session",
        "manifestPath": rel(manifest_path),
        "manifestSha256": sha256_file(manifest_path),
        "modelId": manifest.get("modelId"),
        "laneKey": profile["variantTag"],
        "dtypeProfile": profile,
        "cslDtypeContract": csl_dtype_contract,
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
        "linearAttentionLayers": linear_attention_layers,
        "selfAttentionLayers": self_attention_layers,
        "perLayerInputBlock": {
            "enabled": per_layer_input_block_enabled(architecture),
            "hiddenSizePerLayerInput": ple_hidden,
        },
        "requiredWeightCount": len(required),
        "resolvedWeightCount": sum(
            1 for record in required.values() if record["resolved"]
        ),
        "unresolvedWeightKeys": unresolved,
        "architectureDisabledWeightKeys": architecture_disabled_weight_keys,
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


def is_model_level_prefill_step(step: dict[str, Any]) -> bool:
    name = str(step.get("name") or "")
    kernel = str(step.get("kernelKey") or "")
    return name in MODEL_LEVEL_PREFILL_STEPS or kernel == "sample" or kernel in LM_HEAD_KERNELS


def build_dispatch_plan(
    *,
    smoke_config_path: Path,
    host_plan_path: Path,
    prefill_token_count: int,
    decode_token_count: int,
    model_layer_count: int | None = None,
    linear_attention_layers: list[int] | None = None,
    self_attention_layers: list[int] | None = None,
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

    def layers_for_step(step: dict[str, Any]) -> list[int]:
        raw_key = step.get("weightsKey")
        if is_linear_attention_weight_key(raw_key):
            return list(linear_attention_layers or [])
        if is_self_attention_weight_key(raw_key) and self_attention_layers:
            return list(self_attention_layers)
        return list(range(num_layers))

    def expand_model_step(
        step: dict[str, Any],
        *,
        phase: str,
        token_index: int | None = None,
    ) -> dict[str, Any]:
        return {
            "phase": phase,
            "layer": None,
            "tokenIndex": token_index,
            "name": step.get("name"),
            "kernelKey": step.get("kernelKey"),
            "weightKey": infer_weight_key_for_step(step, 0),
        }

    def expand_layer_step(
        step: dict[str, Any],
        *,
        phase: str,
        layer_index: int,
        token_index: int | None = None,
    ) -> dict[str, Any]:
        record = {
            "phase": phase,
            "layer": layer_index,
            "name": step.get("name"),
            "kernelKey": step.get("kernelKey"),
            "weightKey": infer_weight_key_for_step(step, layer_index),
        }
        if token_index is not None:
            record["tokenIndex"] = token_index
        return record

    def expand_phase_steps(
        template: list[dict[str, Any]],
        *,
        phase: str,
        token_index: int | None = None,
    ) -> list[dict[str, Any]]:
        expanded: list[dict[str, Any]] = []
        layer_steps: list[dict[str, Any]] = []
        suffix_steps: list[dict[str, Any]] = []
        seen_layer_step = False
        for step in template:
            is_model_step = (
                step.get("kernelKey") == "embed"
                or (
                    is_model_level_prefill_step(step)
                    if phase == "prefill"
                    else is_model_level_decode_step(step)
                )
            )
            if is_model_step:
                if seen_layer_step:
                    suffix_steps.append(step)
                else:
                    expanded.append(
                        expand_model_step(
                            step,
                            phase=phase,
                            token_index=(
                                0
                                if step.get("kernelKey") == "sample"
                                and phase == "prefill"
                                else token_index
                            ),
                        )
                    )
                continue
            seen_layer_step = True
            layer_steps.append(step)

        for layer_index in range(num_layers):
            for step in layer_steps:
                if layer_index not in layers_for_step(step):
                    continue
                expanded.append(
                    expand_layer_step(
                        step,
                        phase=phase,
                        layer_index=layer_index,
                        token_index=token_index,
                    )
                )

        for step in suffix_steps:
            expanded.append(
                expand_model_step(
                    step,
                    phase=phase,
                    token_index=(
                        0
                        if step.get("kernelKey") == "sample"
                        and phase == "prefill"
                        else token_index
                    ),
                )
            )
        return expanded

    prefill: list[dict[str, Any]] = []
    prefill.extend(
        expand_phase_steps(
            prefill_template,
            phase="prefill",
        )
    )

    decode_by_token: list[dict[str, Any]] = []
    for token_index in range(1, decode_token_count):
        token_steps = expand_phase_steps(
            [
                step for step in decode_template
                if step.get("kernelKey") != "sample"
            ],
            phase="decode",
            token_index=token_index,
        )
        token_steps.append(
            {
                "phase": "decode",
                "tokenIndex": token_index,
                "layer": None,
                "name": "sample",
                "kernelKey": "sample",
                "weightKey": None,
            }
        )
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


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def source_graph_inventory_path(args: argparse.Namespace) -> Path:
    raw_path = getattr(args, "source_graph_inventory", None)
    if raw_path is not None:
        return raw_path
    host_plan = resolve(args.host_plan)
    if host_plan == resolve(DEFAULT_HOST_PLAN):
        return DEFAULT_SOURCE_GRAPH_INVENTORY
    return host_plan.parent / "source-graph-inventory.json"


def _unique_kernel_keys(steps: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    kernels: list[str] = []
    for step in steps:
        kernel = str(step.get("kernelKey") or "")
        if kernel and kernel not in seen:
            seen.add(kernel)
            kernels.append(kernel)
    return kernels


def _phase_tail(steps: list[dict[str, Any]], phase: str) -> list[str]:
    phase_steps = [
        step for step in steps
        if isinstance(step, dict) and step.get("phase") == phase
    ]
    return [
        str(step.get("kernelKey") or "")
        for step in phase_steps[-3:]
        if step.get("kernelKey")
    ]


def build_source_graph_inventory(
    *,
    smoke_config_path: Path,
    host_plan_path: Path,
    model_layer_count: int,
) -> dict[str, Any]:
    smoke = load_json(smoke_config_path)
    steps = [
        step for step in smoke.get("steps") or []
        if isinstance(step, dict)
    ]
    required_kernels = _unique_kernel_keys(steps)
    payload = {
        "schemaVersion": 1,
        "artifactKind": "execution_v1_source_graph_inventory",
        "source": rel(smoke_config_path),
        "sourceSha256": sha256_file(smoke_config_path),
        "hostPlanPath": rel(host_plan_path),
        "modelLayerCount": model_layer_count,
        "requiredKernels": required_kernels,
        "prefillTail": _phase_tail(steps, "prefill"),
        "decodeTail": _phase_tail(steps, "decode"),
    }
    payload["sourceGraphSha256"] = sha256_json({
        "steps": steps,
        "requiredKernels": required_kernels,
    })
    return payload


def write_source_graph_inventory(
    *,
    path: Path,
    smoke_config_path: Path,
    host_plan_path: Path,
    model_layer_count: int,
) -> dict[str, Any]:
    payload = build_source_graph_inventory(
        smoke_config_path=smoke_config_path,
        host_plan_path=host_plan_path,
        model_layer_count=model_layer_count,
    )
    out = resolve(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "path": rel(out),
        "sha256": sha256_file(out),
        "requiredKernels": payload["requiredKernels"],
        "prefillTail": payload["prefillTail"],
        "decodeTail": payload["decodeTail"],
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

def build_blockers(
    *,
    weight_plan: dict[str, Any],
    per_kernel: dict[str, Any],
    refresh: dict[str, Any],
    real_session: dict[str, Any],
    execute: bool,
    requested_decode_steps: int | None = None,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    session_evidence_ready = session_runtime_evidence_is_complete(
        real_session,
        requested_decode_steps=requested_decode_steps,
    )
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
        and not (session_evidence_ready or (refresh_blocked and stale_dry_run_only))
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
                "The real prefill/decode session runtime contract could not "
                "produce a token/logit/KV transcript on this run."
            ),
            "blockers": real_session.get("blockers", [])[:20],
        })
    elif real_session.get("status") == "checkpoint_stopped":
        blockers.append({
            "class": "execution_stopped_at_checkpoint",
            "detail": (
                "The real session runtime stopped at the requested launch "
                "checkpoint before token/logit/KV transcript completion."
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
    return blockers


def source_graph_kernels_from_inventory(path: Path) -> list[str] | None:
    resolved = resolve(path)
    if not resolved.is_file():
        return None
    payload = load_json(resolved)
    kernels = payload.get("requiredKernels")
    if not isinstance(kernels, list):
        return None
    return [str(kernel) for kernel in kernels if str(kernel)]


def gate_blockers(
    host_plan_path: Path,
    per_kernel_summary_path: Path,
    source_graph_inventory: Path,
    *,
    real_session_runtime: dict[str, Any] | None = None,
    requested_decode_steps: int | None = None,
) -> list[dict[str, Any]]:
    host_plan = load_json(host_plan_path)
    per_kernel = (
        load_json(per_kernel_summary_path)
        if resolve(per_kernel_summary_path).is_file()
        else None
    )
    result = evaluate_inference_evidence_gate(
        host_plan=host_plan,
        per_kernel_summary=per_kernel,
        source_graph_kernels=source_graph_kernels_from_inventory(
            source_graph_inventory
        ),
        real_session_runtime=real_session_runtime,
        requested_decode_steps=requested_decode_steps,
    )
    if result.eligible:
        return []
    return [
        {
            "class": f"inference_evidence_gate.{reason.code}",
            "detail": reason.detail,
        }
        for reason in result.reasons
    ]


def build_trace(args: argparse.Namespace) -> dict[str, Any]:
    expected_model_id = str(
        getattr(args, "expected_model_id", MODEL_ID) or MODEL_ID
    )
    lane_key = str(getattr(args, "lane_key", LANE_KEY) or LANE_KEY)
    trace_artifact_kind = str(
        getattr(args, "trace_artifact_kind", TRACE_ARTIFACT_KIND)
        or TRACE_ARTIFACT_KIND
    )
    weight_plan = build_weight_staging_plan(
        manifest_path=args.source_doppler_manifest,
        smoke_config_path=args.smoke_config,
        expected_model_id=expected_model_id,
        lane_key=lane_key,
    )
    dispatch_plan = build_dispatch_plan(
        smoke_config_path=args.smoke_config,
        host_plan_path=args.host_plan,
        prefill_token_count=args.prefill_token_count,
        decode_token_count=args.decode_token_count,
        model_layer_count=int(weight_plan.get("modelLayerCount") or 0),
        linear_attention_layers=list(
            weight_plan.get("linearAttentionLayers") or []
        ),
        self_attention_layers=list(
            weight_plan.get("selfAttentionLayers") or []
        ),
    )
    source_inventory_path = source_graph_inventory_path(args)
    source_inventory = write_source_graph_inventory(
        path=source_inventory_path,
        smoke_config_path=args.smoke_config,
        host_plan_path=args.host_plan,
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
        requested_decode_steps=int(args.decode_token_count),
    )
    blockers.extend(
        gate_blockers(
            args.host_plan,
            args.per_kernel_summary,
            source_inventory_path,
            real_session_runtime=real_session,
            requested_decode_steps=int(args.decode_token_count),
        )
    )
    return {
        "schemaVersion": 1,
        "artifactKind": trace_artifact_kind,
        "modelId": expected_model_id,
        "laneKey": lane_key,
        "cslDtypeContract": weight_plan["cslDtypeContract"],
        "executionTarget": "system" if args.cmaddr else "simfabric",
        "requestedExecution": {
            "prefillTokenCount": args.prefill_token_count,
            "decodeTokenCount": args.decode_token_count,
            "execute": bool(args.execute),
        },
        "weightStaging": weight_plan,
        "dispatchPlan": dispatch_plan,
        "sourceGraphInventory": source_inventory,
        "perKernelRefresh": refresh,
        "perKernelEvidence": per_kernel,
        "realSessionRuntime": real_session,
        "status": "blocked" if blockers else "output_ready",
        "blockers": blockers,
        "claim": {
            "scope": str(getattr(args, "claim_scope", DEFAULT_CLAIM_SCOPE)),
            "notWhat": str(
                getattr(args, "claim_not_what", DEFAULT_CLAIM_NOT_WHAT)
            ),
            "summary": str(
                getattr(args, "claim_summary", DEFAULT_CLAIM_SUMMARY)
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
