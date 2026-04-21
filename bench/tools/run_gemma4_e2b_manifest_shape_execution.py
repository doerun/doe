#!/usr/bin/env python3
"""Run a Gemma-4 E2B text-only manifest-shape execution probe.

This is a CPU/Numpy oracle for the upstream BF16 SafeTensors checkpoint. It
executes the text stack at the manifest tensor dimensions so Doe can distinguish
"the raw model shape is executable" from "the Doe CSL runtime executes it".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DIR = os.environ.get(
    "DOE_GEMMA4_E2B_SAFETENSORS_DIR",
    "/home/x/model-downloads/gemma4-e2b-it",
)
DEFAULT_OUT = (
    "bench/out/manifest-shape/"
    "gemma-4-e2b-manifest-shape-execution.json"
)
DEFAULT_OUT_HIDDEN = (
    "bench/out/manifest-shape/"
    "gemma-4-e2b-manifest-shape-final-hidden.f32"
)
LANG_PREFIX = "model.language_model"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--token-id", type=int, default=2)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--logit-chunk-size", type=int, default=4096)
    parser.add_argument("--out-json", default=DEFAULT_OUT)
    parser.add_argument("--out-hidden", default=DEFAULT_OUT_HIDDEN)
    parser.add_argument(
        "--hash-full-safetensors",
        action="store_true",
        help="Also stream-hash the full SafeTensors file; expensive on first run.",
    )
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
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def text_config(raw: dict[str, Any]) -> dict[str, Any]:
    value = raw.get("text_config")
    return value if isinstance(value, dict) else raw


class SafeTensorStore:
    def __init__(self, source_dir: Path):
        paths = sorted(source_dir.glob("*.safetensors"))
        if len(paths) != 1:
            raise ValueError(
                f"expected exactly one .safetensors file in {source_dir}, "
                f"found {len(paths)}"
            )
        self.path = paths[0]
        with self.path.open("rb") as handle:
            raw_len = handle.read(8)
            if len(raw_len) != 8:
                raise ValueError(f"{self.path} is too short to be SafeTensors")
            (self.header_len,) = struct.unpack("<Q", raw_len)
            self.header_bytes = handle.read(self.header_len)
        self.header = json.loads(self.header_bytes.decode("utf-8"))
        self.data_start = 8 + self.header_len
        self.tensors_read: set[str] = set()

    def meta(self, name: str) -> dict[str, Any]:
        meta = self.header.get(name)
        if not isinstance(meta, dict):
            raise KeyError(f"tensor not found: {name}")
        return meta

    def _decode(
        self,
        name: str,
        raw: bytes,
        dtype: str,
        out_shape: tuple[int, ...],
    ) -> np.ndarray:
        self.tensors_read.add(name)
        if dtype == "BF16":
            words = np.frombuffer(raw, dtype="<u2")
            data = (words.astype(np.uint32) << 16).view(np.float32)
        elif dtype == "F16":
            data = np.frombuffer(raw, dtype="<f2").astype(np.float32)
        else:
            data = np.frombuffer(raw, dtype="<f4")
        return data.reshape(out_shape).copy()

    def read(self, name: str, row: int | None = None) -> np.ndarray:
        meta = self.meta(name)
        shape = meta.get("shape")
        offsets = meta.get("data_offsets")
        dtype = meta.get("dtype")
        if not (
            isinstance(shape, list)
            and isinstance(offsets, list)
            and len(offsets) == 2
            and all(isinstance(v, int) for v in offsets)
        ):
            raise ValueError(f"{name}: invalid SafeTensors metadata")
        bytes_per_element = {"BF16": 2, "F16": 2, "F32": 4}.get(dtype)
        if bytes_per_element is None:
            raise ValueError(f"{name}: unsupported dtype {dtype!r}")
        start, end = offsets
        if row is None:
            byte_start = start
            count = int(np.prod(shape, dtype=np.int64))
            out_shape = tuple(int(v) for v in shape)
        else:
            if row < 0 or row >= int(shape[0]):
                raise ValueError(f"{name}: row {row} outside shape {shape}")
            row_count = int(np.prod(shape[1:], dtype=np.int64))
            byte_start = start + row * row_count * bytes_per_element
            count = row_count
            out_shape = tuple(int(v) for v in shape[1:])
        byte_len = count * bytes_per_element
        if byte_start < start or byte_start + byte_len > end:
            raise ValueError(f"{name}: requested byte span outside tensor")
        with self.path.open("rb") as handle:
            handle.seek(self.data_start + byte_start)
            raw = handle.read(byte_len)
        if len(raw) != byte_len:
            raise ValueError(f"{name}: short read")
        return self._decode(name, raw, str(dtype), out_shape)

    def read_rows(self, name: str, start_row: int, row_count: int) -> np.ndarray:
        meta = self.meta(name)
        shape = meta.get("shape")
        offsets = meta.get("data_offsets")
        dtype = meta.get("dtype")
        if not (
            isinstance(shape, list)
            and len(shape) >= 2
            and isinstance(offsets, list)
            and len(offsets) == 2
            and all(isinstance(v, int) for v in offsets)
        ):
            raise ValueError(f"{name}: invalid row-readable metadata")
        bytes_per_element = {"BF16": 2, "F16": 2, "F32": 4}.get(dtype)
        if bytes_per_element is None:
            raise ValueError(f"{name}: unsupported dtype {dtype!r}")
        if start_row < 0 or row_count < 1 or start_row + row_count > int(shape[0]):
            raise ValueError(
                f"{name}: row span {start_row}:{start_row + row_count} "
                f"outside shape {shape}"
            )
        row_elements = int(np.prod(shape[1:], dtype=np.int64))
        start, _end = offsets
        byte_start = start + start_row * row_elements * bytes_per_element
        byte_len = row_count * row_elements * bytes_per_element
        out_shape = (row_count, *tuple(int(v) for v in shape[1:]))
        with self.path.open("rb") as handle:
            handle.seek(self.data_start + byte_start)
            raw = handle.read(byte_len)
        if len(raw) != byte_len:
            raise ValueError(f"{name}: short read")
        return self._decode(name, raw, str(dtype), out_shape)


def rms_norm(
    hidden: np.ndarray,
    weight: np.ndarray | None,
    eps: float,
) -> np.ndarray:
    x = hidden.astype(np.float32, copy=False)
    mean_sq = np.mean(x * x, dtype=np.float32)
    y = x * np.float32((mean_sq + np.float32(eps)) ** np.float32(-0.5))
    if weight is not None:
        y = y * weight.astype(np.float32, copy=False)
    return y.astype(np.float32, copy=False)


def gelu_pytorch_tanh(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float32, copy=False)
    cubic = x * x * x
    scale = np.float32(math.sqrt(2.0 / math.pi))
    inner = scale * (x + np.float32(0.044715) * cubic)
    return (np.float32(0.5) * x * (np.float32(1.0) + np.tanh(inner))).astype(
        np.float32,
        copy=False,
    )


def layer_type(config: dict[str, Any], layer: int) -> str:
    types = config.get("layer_types")
    if not isinstance(types, list) or layer >= len(types):
        return "sliding_attention"
    return str(types[layer])


def layer_head_dim(config: dict[str, Any], layer: int) -> int:
    if layer_type(config, layer) == "full_attention":
        value = config.get("global_head_dim") or config["head_dim"]
        return int(value)
    return int(config["head_dim"])


def last_non_shared_by_type(config: dict[str, Any]) -> dict[str, int]:
    first_shared = int(config["num_hidden_layers"]) - int(
        config.get("num_kv_shared_layers", 0)
    )
    out: dict[str, int] = {}
    for idx in range(max(first_shared, 0)):
        out[layer_type(config, idx)] = idx
    return out


def execute_attention(
    store: SafeTensorStore,
    config: dict[str, Any],
    hidden: np.ndarray,
    layer: int,
    shared_kv: dict[int, tuple[np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, dict[str, Any]]:
    prefix = f"{LANG_PREFIX}.layers.{layer}"
    num_heads = int(config["num_attention_heads"])
    kv_heads = int(config.get("num_key_value_heads", 1))
    head_dim = layer_head_dim(config, layer)
    hidden_size = int(config["hidden_size"])
    first_shared = int(config["num_hidden_layers"]) - int(
        config.get("num_kv_shared_layers", 0)
    )
    is_shared = layer >= first_shared > 0
    kv_source_layer: int | None = None

    q = store.read(f"{prefix}.self_attn.q_proj.weight") @ hidden
    q = q.reshape(num_heads, head_dim)
    q_norm_w = store.read(f"{prefix}.self_attn.q_norm.weight")
    q = np.stack([rms_norm(row, q_norm_w, float(config["rms_norm_eps"])) for row in q])

    if is_shared:
        kv_source_layer = last_non_shared_by_type(config)[layer_type(config, layer)]
        key, value = shared_kv[kv_source_layer]
    else:
        key = (store.read(f"{prefix}.self_attn.k_proj.weight") @ hidden).reshape(
            kv_heads,
            head_dim,
        )
        value = (
            store.read(f"{prefix}.self_attn.v_proj.weight") @ hidden
        ).reshape(kv_heads, head_dim)
        k_norm_w = store.read(f"{prefix}.self_attn.k_norm.weight")
        key = np.stack([
            rms_norm(row, k_norm_w, float(config["rms_norm_eps"]))
            for row in key
        ])
        value = np.stack([
            rms_norm(row, None, float(config["rms_norm_eps"]))
            for row in value
        ])
        if layer in set(last_non_shared_by_type(config).values()):
            shared_kv[layer] = (key.copy(), value.copy())

    groups = num_heads // int(value.shape[0])
    attn = np.repeat(value, groups, axis=0).reshape(num_heads * head_dim)
    out = store.read(f"{prefix}.self_attn.o_proj.weight") @ attn
    if out.shape != (hidden_size,):
        raise ValueError(f"layer {layer}: o_proj output shape {out.shape}")
    return out.astype(np.float32, copy=False), {
        "qShape": [int(v) for v in q.shape],
        "kvShape": [int(v) for v in value.shape],
        "headDim": head_dim,
        "qDim": num_heads * head_dim,
        "kvDim": int(value.shape[0]) * head_dim,
        "usesSharedKv": is_shared,
        "kvSourceLayer": kv_source_layer,
        "qFinite": bool(np.isfinite(q).all()),
        "kvFinite": bool(np.isfinite(value).all()),
    }


def execute_layer(
    store: SafeTensorStore,
    config: dict[str, Any],
    hidden: np.ndarray,
    per_layer_input: np.ndarray,
    layer: int,
    shared_kv: dict[int, tuple[np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, dict[str, Any]]:
    start = time.time()
    prefix = f"{LANG_PREFIX}.layers.{layer}"
    eps = float(config["rms_norm_eps"])

    residual = hidden
    normed = rms_norm(
        hidden,
        store.read(f"{prefix}.input_layernorm.weight"),
        eps,
    )
    attn_out, attn_record = execute_attention(store, config, normed, layer, shared_kv)
    attn_out = rms_norm(
        attn_out,
        store.read(f"{prefix}.post_attention_layernorm.weight"),
        eps,
    )
    hidden = (residual + attn_out).astype(np.float32, copy=False)

    residual = hidden
    normed = rms_norm(
        hidden,
        store.read(f"{prefix}.pre_feedforward_layernorm.weight"),
        eps,
    )
    gate = store.read(f"{prefix}.mlp.gate_proj.weight") @ normed
    mlp_intermediate = int(gate.shape[0])
    up = store.read(f"{prefix}.mlp.up_proj.weight") @ normed
    mlp = gelu_pytorch_tanh(gate) * up
    mlp = store.read(f"{prefix}.mlp.down_proj.weight") @ mlp
    mlp = rms_norm(
        mlp,
        store.read(f"{prefix}.post_feedforward_layernorm.weight"),
        eps,
    )
    hidden = (residual + mlp).astype(np.float32, copy=False)

    residual = hidden
    gate = store.read(f"{prefix}.per_layer_input_gate.weight") @ hidden
    ple = gelu_pytorch_tanh(gate) * per_layer_input
    ple = store.read(f"{prefix}.per_layer_projection.weight") @ ple
    ple = rms_norm(
        ple,
        store.read(f"{prefix}.post_per_layer_input_norm.weight"),
        eps,
    )
    layer_scalar = store.read(f"{prefix}.layer_scalar")[0]
    hidden = ((residual + ple) * layer_scalar).astype(np.float32, copy=False)

    elapsed_ms = (time.time() - start) * 1000.0
    max_abs = float(np.max(np.abs(hidden)))
    finite = bool(np.isfinite(hidden).all())
    return hidden, {
        "layer": layer,
        "layerType": layer_type(config, layer),
        "attention": attn_record,
        "mlpIntermediate": mlp_intermediate,
        "hiddenShape": [int(v) for v in hidden.shape],
        "hiddenFinite": finite,
        "hiddenMaxAbs": max_abs,
        "elapsedMs": elapsed_ms,
    }


def compute_per_layer_inputs(
    store: SafeTensorStore,
    config: dict[str, Any],
    token_id: int,
    input_embed: np.ndarray,
) -> np.ndarray:
    num_layers = int(config["num_hidden_layers"])
    ple_width = int(config["hidden_size_per_layer_input"])
    token_ple = store.read(f"{LANG_PREFIX}.embed_tokens_per_layer.weight", row=token_id)
    token_ple = token_ple.reshape(num_layers, ple_width)
    token_ple = token_ple * np.float32(math.sqrt(ple_width))
    model_projection = store.read(
        f"{LANG_PREFIX}.per_layer_model_projection.weight"
    )
    projected = model_projection @ input_embed
    projected = projected * np.float32(float(config["hidden_size"]) ** -0.5)
    projected = projected.reshape(num_layers, ple_width)
    norm_w = store.read(f"{LANG_PREFIX}.per_layer_projection_norm.weight")
    projected = np.stack([
        rms_norm(projected[layer], norm_w, float(config["rms_norm_eps"]))
        for layer in range(num_layers)
    ])
    return ((projected + token_ple) * np.float32(2.0 ** -0.5)).astype(
        np.float32,
        copy=False,
    )


def topk_logits(
    store: SafeTensorStore,
    config: dict[str, Any],
    hidden: np.ndarray,
    *,
    top_k: int,
    chunk_size: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    vocab = int(config["vocab_size"])
    top_indices = np.empty(0, dtype=np.int64)
    top_values = np.empty(0, dtype=np.float32)
    chunks = 0
    softcap = config.get("final_logit_softcapping")
    for lo in range(0, vocab, chunk_size):
        hi = min(vocab, lo + chunk_size)
        block = store.read_rows(f"{LANG_PREFIX}.embed_tokens.weight", lo, hi - lo)
        logits = block @ hidden
        if softcap is not None:
            cap = np.float32(float(softcap))
            logits = np.tanh(logits / cap) * cap
        candidate_values = np.concatenate([top_values, logits.astype(np.float32)])
        candidate_indices = np.concatenate([
            top_indices,
            np.arange(lo, hi, dtype=np.int64),
        ])
        take = min(top_k, candidate_values.shape[0])
        part = np.argpartition(candidate_values, -take)[-take:]
        order = part[np.argsort(candidate_values[part])[::-1]]
        top_values = candidate_values[order].astype(np.float32, copy=False)
        top_indices = candidate_indices[order].astype(np.int64, copy=False)
        chunks += 1
    records = [
        {"tokenId": int(idx), "logit": float(val)}
        for idx, val in zip(top_indices, top_values, strict=True)
    ]
    summary = {
        "vocabSize": vocab,
        "topK": top_k,
        "chunkSize": chunk_size,
        "chunks": chunks,
        "finalLogitSoftcapping": softcap,
        "finite": bool(np.isfinite(top_values).all()),
    }
    return records, summary


def blocked_payload(
    args: argparse.Namespace,
    source_dir: Path,
    reason: str,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_gemma4_e2b_manifest_shape_execution",
        "status": "blocked",
        "verdict": "manifest_shape_execution_blocked_source_absent",
        "modelId": "gemma-4-e2b-it",
        "runtimeLane": "cpu_numpy_oracle",
        "source": {
            "sourceDir": str(source_dir),
            "configPath": str(source_dir / "config.json"),
            "safetensorsPath": None,
        },
        "input": {
            "tokenId": args.token_id,
            "sequenceLength": 1,
        },
        "executionSummary": {},
        "layerRecords": [],
        "output": {},
        "promotionCriteriaMet": {
            "manifestShapeExecuted": False,
            "fullLayerDepthExecuted": False,
            "lmHeadTopKComputed": False,
            "doeRuntimeExecuted": False,
            "cslRuntimeExecuted": False,
            "hardwareExecuted": False,
        },
        "claimScope": claim_scope(),
        "blockers": [reason],
        "errors": [],
    }


def claim_scope() -> dict[str, Any]:
    return {
        "claimable": (
            "CPU/Numpy oracle only: the raw BF16 Gemma-4 E2B text "
            "checkpoint executes at upstream manifest tensor dimensions "
            "for one token through embed, PLE, 35 decoder layers, final "
            "norm, and tied lm-head top-k with finite outputs."
        ),
        "notClaimable": [
            "Doe CSL runtime manifest-shape execution",
            "Doe full-model runtime receipt",
            "Cerebras hardware execution",
            "Doppler RDRR full-model execution",
            "Tokenizer/chat-template generation parity",
            "Performance or efficiency claims",
        ],
    }


def main() -> int:
    args = parse_args()
    source_dir = Path(args.source_dir).resolve()
    out_path = resolve(args.out_json)
    out_hidden = resolve(args.out_hidden)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_hidden.parent.mkdir(parents=True, exist_ok=True)

    if not source_dir.is_dir() or not (source_dir / "config.json").is_file():
        payload = blocked_payload(
            args,
            source_dir,
            "raw Gemma-4 E2B source directory or config.json is absent",
        )
        out_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {rel(out_path)}")
        return 0

    try:
        config_path = source_dir / "config.json"
        config = text_config(load_json(config_path))
        store = SafeTensorStore(source_dir)
        if not (0 <= args.token_id < int(config["vocab_size"])):
            raise ValueError(
                f"token id {args.token_id} outside vocab size {config['vocab_size']}"
            )

        start = time.time()
        hidden = store.read(f"{LANG_PREFIX}.embed_tokens.weight", row=args.token_id)
        hidden = hidden * np.float32(math.sqrt(float(config["hidden_size"])))
        per_layer_inputs = compute_per_layer_inputs(
            store,
            config,
            args.token_id,
            hidden,
        )
        shared_kv: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        layer_records: list[dict[str, Any]] = []
        for layer in range(int(config["num_hidden_layers"])):
            hidden, record = execute_layer(
                store,
                config,
                hidden,
                per_layer_inputs[layer],
                layer,
                shared_kv,
            )
            layer_records.append(record)
            if not record["hiddenFinite"]:
                raise FloatingPointError(f"layer {layer} produced non-finite output")

        hidden = rms_norm(hidden, store.read(f"{LANG_PREFIX}.norm.weight"),
                          float(config["rms_norm_eps"]))
        top_logits, logits_summary = topk_logits(
            store,
            config,
            hidden,
            top_k=args.top_k,
            chunk_size=args.logit_chunk_size,
        )
        if not logits_summary["finite"]:
            raise FloatingPointError("lm-head top-k produced non-finite logits")
        out_hidden.write_bytes(hidden.astype("<f4", copy=False).tobytes())
        elapsed_ms = (time.time() - start) * 1000.0

        full_sha = sha256_file(store.path) if args.hash_full_safetensors else None
        local_layers = [
            idx for idx in range(int(config["num_hidden_layers"]))
            if layer_type(config, idx) == "sliding_attention"
        ]
        global_layers = [
            idx for idx in range(int(config["num_hidden_layers"]))
            if layer_type(config, idx) == "full_attention"
        ]
        payload = {
            "schemaVersion": 1,
            "artifactKind": "doe_gemma4_e2b_manifest_shape_execution",
            "status": "succeeded",
            "verdict": "manifest_shape_cpu_full_text_forward_passed",
            "modelId": "gemma-4-e2b-it",
            "runtimeLane": "cpu_numpy_oracle",
            "source": {
                "sourceDir": str(source_dir),
                "configPath": str(config_path),
                "configSha256": sha256_file(config_path),
                "safetensorsPath": str(store.path),
                "safetensorsSizeBytes": store.path.stat().st_size,
                "safetensorsHeaderSha256": sha256_bytes(store.header_bytes),
                "safetensorsFullSha256": full_sha,
                "safetensorsFullSha256Computed": args.hash_full_safetensors,
                "tensorsInHeader": len([
                    key for key in store.header
                    if key != "__metadata__"
                ]),
                "tensorsRead": len(store.tensors_read),
            },
            "input": {
                "tokenId": args.token_id,
                "sequenceLength": 1,
                "textModalityOnly": True,
            },
            "executionSummary": {
                "hiddenSize": int(config["hidden_size"]),
                "numLayers": int(config["num_hidden_layers"]),
                "layersExecuted": len(layer_records),
                "localHeadDim": int(config["head_dim"]),
                "globalHeadDim": int(config["global_head_dim"]),
                "numAttentionHeads": int(config["num_attention_heads"]),
                "numKeyValueHeads": int(config["num_key_value_heads"]),
                "numKvSharedLayers": int(config["num_kv_shared_layers"]),
                "localAttentionLayerIndices": local_layers,
                "globalAttentionLayerIndices": global_layers,
                "pleWidth": int(config["hidden_size_per_layer_input"]),
                "pleVocabSize": int(config["vocab_size_per_layer_input"]),
                "elapsedMs": elapsed_ms,
                "allLayerOutputsFinite": all(
                    bool(row["hiddenFinite"]) for row in layer_records
                ),
            },
            "layerRecords": layer_records,
            "output": {
                "finalHiddenPath": rel(out_hidden),
                "finalHiddenSha256": sha256_file(out_hidden),
                "finalHiddenShape": [int(v) for v in hidden.shape],
                "finalHiddenFinite": bool(np.isfinite(hidden).all()),
                "finalHiddenMaxAbs": float(np.max(np.abs(hidden))),
                "lmHeadTopK": top_logits,
                "lmHeadSummary": logits_summary,
            },
            "promotionCriteriaMet": {
                "manifestShapeExecuted": True,
                "fullLayerDepthExecuted": len(layer_records) == int(
                    config["num_hidden_layers"]
                ),
                "lmHeadTopKComputed": True,
                "doeRuntimeExecuted": False,
                "cslRuntimeExecuted": False,
                "hardwareExecuted": False,
            },
            "claimScope": claim_scope(),
            "blockers": [
                "doe_csl_manifest_shape_runtime_not_executed",
                "hardware_endpoint_unavailable",
            ],
            "errors": [],
        }
        out_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {rel(out_path)}")
        return 0
    except (OSError, ValueError, KeyError, FloatingPointError) as exc:
        payload = blocked_payload(args, source_dir, str(exc))
        payload.update({
            "status": "failed",
            "verdict": "manifest_shape_execution_failed",
            "errors": [f"{type(exc).__name__}: {exc}"],
        })
        out_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {rel(out_path)}")
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
