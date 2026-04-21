#!/usr/bin/env python3
"""Probe Gemma-4 E2B manifest-shape contract against local SafeTensors.

This is a diagnostic contract artifact, not a model execution path. It reads
only the SafeTensors header and Hugging Face config, then compares the upstream
Gemma-4 E2B tensor contract against Doe's execution-v1 manifest fields. The
goal is to keep the manifest-shape tensor contract explicit and schema-backed.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXECUTION_MANIFEST = (
    "runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json"
)
DEFAULT_SOURCE_DIR = "/home/x/model-downloads/gemma4-e2b-it"
DEFAULT_OUT = "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-probe.json"
LANG_PREFIX = "model.language_model"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execution-manifest",
        default=DEFAULT_EXECUTION_MANIFEST,
        help="Doe execution-v1 manifest to compare against upstream tensors.",
    )
    parser.add_argument(
        "--source-dir",
        default=DEFAULT_SOURCE_DIR,
        help="Local raw Gemma-4 E2B SafeTensors snapshot directory.",
    )
    parser.add_argument(
        "--layer",
        type=int,
        default=0,
        help="Layer index whose tensor shapes are probed.",
    )
    parser.add_argument(
        "--out-json",
        default=DEFAULT_OUT,
        help="Output JSON path for the manifest-shape probe artifact.",
    )
    return parser.parse_args()


def resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {rel(path)}")


def safetensors_index(source_dir: Path) -> tuple[dict[str, dict[str, Any]], str | None]:
    paths = sorted(source_dir.glob("*.safetensors"))
    if not paths:
        return {}, None
    index: dict[str, dict[str, Any]] = {}
    for path in paths:
        with path.open("rb") as handle:
            raw_len = handle.read(8)
            if len(raw_len) != 8:
                raise ValueError(f"{path} is too short to be SafeTensors")
            (header_len,) = struct.unpack("<Q", raw_len)
            header = json.loads(handle.read(header_len).decode("utf-8"))
        for name, meta in header.items():
            if name == "__metadata__":
                continue
            record = dict(meta)
            record["file"] = rel(path)
            index[name] = record
    return index, rel(paths[0])


def text_config(raw: dict[str, Any]) -> dict[str, Any]:
    value = raw.get("text_config")
    if isinstance(value, dict):
        return value
    return raw


def int_field(data: dict[str, Any], key: str) -> int | None:
    value = data.get(key)
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def expected_tensor_shapes(config: dict[str, Any], layer: int) -> dict[str, list[int]]:
    hidden = int(config["hidden_size"])
    local_head = int(config["head_dim"])
    num_heads = int(config["num_attention_heads"])
    kv_heads = int(config["num_key_value_heads"])
    intermediate = int(config["intermediate_size"])
    ple_width = int(config["hidden_size_per_layer_input"])
    q_out = num_heads * local_head
    kv_out = kv_heads * local_head
    base = f"{LANG_PREFIX}.layers.{layer}"
    return {
        f"{base}.input_layernorm.weight": [hidden],
        f"{base}.self_attn.q_norm.weight": [local_head],
        f"{base}.self_attn.k_norm.weight": [local_head],
        f"{base}.self_attn.q_proj.weight": [q_out, hidden],
        f"{base}.self_attn.k_proj.weight": [kv_out, hidden],
        f"{base}.self_attn.v_proj.weight": [kv_out, hidden],
        f"{base}.self_attn.o_proj.weight": [hidden, q_out],
        f"{base}.post_attention_layernorm.weight": [hidden],
        f"{base}.post_feedforward_layernorm.weight": [hidden],
        f"{base}.post_per_layer_input_norm.weight": [hidden],
        f"{base}.mlp.gate_proj.weight": [intermediate, hidden],
        f"{base}.mlp.up_proj.weight": [intermediate, hidden],
        f"{base}.mlp.down_proj.weight": [hidden, intermediate],
        f"{base}.per_layer_projection.weight": [hidden, ple_width],
        f"{LANG_PREFIX}.per_layer_projection_norm.weight": [ple_width],
        f"{LANG_PREFIX}.embed_tokens.weight": [
            int(config["vocab_size"]),
            hidden,
        ],
        f"{LANG_PREFIX}.embed_tokens_per_layer.weight": [
            int(config["vocab_size_per_layer_input"]),
            int(config["num_hidden_layers"]) * ple_width,
        ],
    }


def tensor_audit(
    index: dict[str, dict[str, Any]],
    expected: dict[str, list[int]],
) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for name, shape in expected.items():
        meta = index.get(name)
        actual_shape = meta.get("shape") if meta else None
        passed = actual_shape == shape
        if not passed:
            errors.append(f"{name}: shape {actual_shape!r} != {shape!r}")
        records.append({
            "name": name,
            "present": meta is not None,
            "dtype": meta.get("dtype") if meta else None,
            "shape": actual_shape,
            "expectedShape": shape,
            "passed": passed,
            "file": meta.get("file") if meta else None,
        })
    return records, errors


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    expected: Any,
    actual: Any,
    level: str = "blocking",
) -> None:
    checks.append({
        "name": name,
        "expected": expected,
        "actual": actual,
        "passed": actual == expected,
        "level": level,
    })


def full_attention_layers(config: dict[str, Any]) -> list[int]:
    layer_types = config.get("layer_types")
    if not isinstance(layer_types, list):
        return []
    return [
        idx for idx, value in enumerate(layer_types)
        if value == "full_attention"
    ]


def layer_pattern_matches(manifest: dict[str, Any], full_layers: list[int]) -> bool:
    pattern = manifest.get("layerPattern") or {}
    if pattern.get("type") != "every_n":
        return False
    try:
        period = int(pattern["period"])
        offset = int(pattern["offset"])
        layer_count = int((manifest.get("modelConfig") or {})["numLayers"])
    except (KeyError, TypeError, ValueError):
        return False
    expected = list(range(offset, layer_count, period))
    return expected == full_layers


def manifest_derived_shapes(
    manifest_model: dict[str, Any],
    hidden: int,
    observed: dict[str, list[int]],
) -> list[dict[str, Any]]:
    num_heads = int_field(manifest_model, "numHeads")
    head_dim = int_field(manifest_model, "headDim")
    kv_heads = int_field(manifest_model, "numKeyValueHeads")
    out: list[dict[str, Any]] = []
    if num_heads is not None and head_dim is not None:
        q_out = num_heads * head_dim
        for name, expected in [
            ("q_proj", [q_out, hidden]),
            ("o_proj", [hidden, q_out]),
            ("per_layer_projection", [hidden, head_dim]),
        ]:
            out.append({
                "name": name,
                "expectedFromDoeManifest": expected,
                "actualSafeTensorsShape": observed.get(name),
                "passed": observed.get(name) == expected,
                "level": "blocking",
            })
    if kv_heads is not None and head_dim is not None:
        kv_out = kv_heads * head_dim
        for name in ("k_proj", "v_proj"):
            expected = [kv_out, hidden]
            out.append({
                "name": name,
                "expectedFromDoeManifest": expected,
                "actualSafeTensorsShape": observed.get(name),
                "passed": observed.get(name) == expected,
                "level": "blocking",
            })
    return out


def base_payload(args: argparse.Namespace, manifest_path: Path, source_dir: Path) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_gemma4_e2b_manifest_shape_probe",
        "modelId": None,
        "status": "blocked",
        "verdict": "manifest_shape_probe_blocked_source_absent",
        "executionManifestPath": rel(manifest_path),
        "sourceDir": str(source_dir),
        "upstreamConfigPath": str(source_dir / "config.json"),
        "safetensorsPath": None,
        "layer": args.layer,
        "upstreamConfig": {},
        "doeManifestConfig": {},
        "expectedTensorShapes": {},
        "tensorAudit": [],
        "manifestChecks": [],
        "manifestDerivedTensorChecks": [],
        "blockers": [],
        "advisories": [],
        "claimScope": {
            "claimable": (
                "Local diagnostic only: upstream tensor-shape contract "
                "readability and Doe manifest-shape contract classification."
            ),
            "notClaimable": [
                "Manifest-shape execution",
                "Full end-to-end Gemma-4 inference",
                "Cerebras hardware execution",
                "Performance or efficiency claims",
            ],
        },
        "errors": [],
    }


def check_summary(check: dict[str, Any]) -> str:
    if "expectedFromDoeManifest" in check:
        return (
            f"{check['name']}: expectedFromDoeManifest "
            f"{check.get('expectedFromDoeManifest')!r}, "
            f"actualSafeTensorsShape {check.get('actualSafeTensorsShape')!r}"
        )
    return (
        f"{check['name']}: expected {check.get('expected')!r}, "
        f"actual {check.get('actual')!r}"
    )


def main() -> int:
    args = parse_args()
    manifest_path = resolve(args.execution_manifest)
    source_dir = Path(args.source_dir).resolve()
    out_path = resolve(args.out_json)
    payload = base_payload(args, manifest_path, source_dir)

    if not manifest_path.is_file():
        payload.update({
            "status": "failed",
            "verdict": "manifest_shape_probe_failed_manifest_absent",
            "errors": [f"execution manifest not found: {manifest_path}"],
        })
        write_json(out_path, payload)
        return 1
    if not source_dir.is_dir() or not (source_dir / "config.json").is_file():
        payload["blockers"] = [
            "raw Gemma-4 E2B source directory or config.json is absent"
        ]
        write_json(out_path, payload)
        return 0

    try:
        manifest = load_json(manifest_path)
        upstream = text_config(load_json(source_dir / "config.json"))
        index, safetensors_path = safetensors_index(source_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        payload.update({
            "status": "failed",
            "verdict": "manifest_shape_probe_failed_source_unreadable",
            "errors": [f"{type(exc).__name__}: {exc}"],
        })
        write_json(out_path, payload)
        return 1

    if not index:
        payload["blockers"] = ["no .safetensors file found in source directory"]
        write_json(out_path, payload)
        return 0

    manifest_model = manifest.get("modelConfig") or {}
    expected_shapes = expected_tensor_shapes(upstream, args.layer)
    tensors, tensor_errors = tensor_audit(index, expected_shapes)
    def observed_shape(name: str) -> list[int] | None:
        meta = index.get(name)
        shape = meta.get("shape") if meta else None
        return shape if isinstance(shape, list) else None

    observed_short = {
        "q_proj": observed_shape(
            f"{LANG_PREFIX}.layers.{args.layer}.self_attn.q_proj.weight"
        ),
        "k_proj": observed_shape(
            f"{LANG_PREFIX}.layers.{args.layer}.self_attn.k_proj.weight"
        ),
        "v_proj": observed_shape(
            f"{LANG_PREFIX}.layers.{args.layer}.self_attn.v_proj.weight"
        ),
        "o_proj": observed_shape(
            f"{LANG_PREFIX}.layers.{args.layer}.self_attn.o_proj.weight"
        ),
        "per_layer_projection": observed_shape(
            f"{LANG_PREFIX}.layers.{args.layer}.per_layer_projection.weight"
        ),
    }

    manifest_checks: list[dict[str, Any]] = []
    add_check(manifest_checks, "modelConfig.hiddenDim", upstream["hidden_size"],
              manifest_model.get("hiddenDim"))
    add_check(manifest_checks, "modelConfig.numHeads",
              upstream["num_attention_heads"], manifest_model.get("numHeads"))
    add_check(manifest_checks, "modelConfig.headDim",
              upstream["head_dim"], manifest_model.get("headDim"))
    add_check(manifest_checks, "modelConfig.globalHeadDim",
              upstream["global_head_dim"], manifest_model.get("globalHeadDim"))
    add_check(manifest_checks, "modelConfig.numKeyValueHeads",
              upstream["num_key_value_heads"],
              manifest_model.get("numKeyValueHeads"))
    add_check(manifest_checks, "modelConfig.numLayers",
              upstream["num_hidden_layers"], manifest_model.get("numLayers"))
    add_check(manifest_checks, "modelConfig.vocabSize",
              upstream["vocab_size"], manifest_model.get("vocabSize"))
    add_check(manifest_checks, "modelConfig.pleWidth",
              upstream["hidden_size_per_layer_input"],
              manifest_model.get("pleWidth"))
    add_check(manifest_checks, "modelConfig.pleVocabSize",
              upstream["vocab_size_per_layer_input"],
              manifest_model.get("pleVocabSize"))
    add_check(manifest_checks, "slidingWindowSize",
              upstream["sliding_window"], manifest.get("slidingWindowSize"))
    add_check(
        manifest_checks,
        "layerPattern.fullAttentionLayers",
        True,
        layer_pattern_matches(manifest, full_attention_layers(upstream)),
    )
    add_check(
        manifest_checks,
        "numKvSharedLayers",
        upstream.get("num_kv_shared_layers"),
        manifest.get("numKvSharedLayers"),
        level="advisory",
    )

    derived_shape_checks = manifest_derived_shapes(
        manifest_model,
        int(upstream["hidden_size"]),
        observed_short,
    )

    blocking_checks = [
        check for check in manifest_checks
        if check["level"] == "blocking" and not check["passed"]
    ]
    blocking_checks.extend([
        check for check in derived_shape_checks
        if check["level"] == "blocking" and not check["passed"]
    ])
    advisories = [
        f"{check['name']}: expected {check['expected']!r}, "
        f"actual {check['actual']!r}"
        for check in manifest_checks
        if check["level"] == "advisory" and not check["passed"]
    ]

    if tensor_errors:
        status = "failed"
        verdict = "manifest_shape_probe_failed_tensor_shape_mismatch"
        rc = 1
    elif blocking_checks:
        status = "blocked"
        verdict = "manifest_shape_probe_blocked_contract_mismatch"
        rc = 0
    else:
        status = "succeeded"
        verdict = "manifest_shape_probe_passed"
        rc = 0

    payload.update({
        "modelId": manifest.get("modelId"),
        "status": status,
        "verdict": verdict,
        "safetensorsPath": safetensors_path,
        "upstreamConfig": {
            "hiddenSize": upstream.get("hidden_size"),
            "headDim": upstream.get("head_dim"),
            "globalHeadDim": upstream.get("global_head_dim"),
            "numAttentionHeads": upstream.get("num_attention_heads"),
            "numKeyValueHeads": upstream.get("num_key_value_heads"),
            "numHiddenLayers": upstream.get("num_hidden_layers"),
            "intermediateSize": upstream.get("intermediate_size"),
            "hiddenSizePerLayerInput": upstream.get(
                "hidden_size_per_layer_input"
            ),
            "vocabSize": upstream.get("vocab_size"),
            "vocabSizePerLayerInput": upstream.get(
                "vocab_size_per_layer_input"
            ),
            "slidingWindow": upstream.get("sliding_window"),
            "maxPositionEmbeddings": upstream.get("max_position_embeddings"),
            "numKvSharedLayers": upstream.get("num_kv_shared_layers"),
            "fullAttentionLayerIndices": full_attention_layers(upstream),
        },
        "doeManifestConfig": {
            "modelConfig": manifest_model,
            "slidingWindowSize": manifest.get("slidingWindowSize"),
            "layerPattern": manifest.get("layerPattern"),
            "numKvSharedLayers": manifest.get("numKvSharedLayers"),
        },
        "expectedTensorShapes": expected_shapes,
        "tensorAudit": tensors,
        "manifestChecks": manifest_checks,
        "manifestDerivedTensorChecks": derived_shape_checks,
        "blockers": [check_summary(check) for check in blocking_checks],
        "advisories": advisories,
        "errors": tensor_errors,
    })
    write_json(out_path, payload)
    return rc


if __name__ == "__main__":
    sys.exit(main())
