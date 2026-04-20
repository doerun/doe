#!/usr/bin/env python3
"""Materialize Gemma-4 E2B smoke slices from Doppler RDRR Q4_K_M shards."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools.doppler_rdrr_q4k import (
    Q4_K_M_BLOCK_BYTES,
    Q4_K_M_BLOCK_ELEMENTS,
    f32_values_to_bytes,
    read_tensor_prefix_as_f32,
)

DEFAULT_FIXTURE = "config/gemma-4-e2b-doppler-rdrr-int4ple-fixture.json"
DEFAULT_OUT_DIR = "bench/out/gemma-4-e2b-rdrr-int4ple-weights"
DEFAULT_OUT_JSON = (
    "bench/out/doppler-rdrr/"
    "gemma-4-e2b-int4ple-q4k-extraction.json"
)
DEFAULT_REFERENCE_WEIGHTS_DIR = "bench/out/gemma-4-e2b-real-weights"
LANG_PREFIX = "model.language_model.layers"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument(
        "--artifact-root",
        default="",
        help="Override artifactRoot from the RDRR fixture.",
    )
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--out-json", default=DEFAULT_OUT_JSON)
    parser.add_argument(
        "--compare-weights-dir",
        default=DEFAULT_REFERENCE_WEIGHTS_DIR,
        help=(
            "Optional BF16-derived smoke-contract weightsDir used only for "
            "lossy weight-drift diagnostics. Absence does not block extraction."
        ),
    )
    parser.add_argument("--size", type=int, default=1024)
    return parser.parse_args()


def resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {rel(path)}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_files(num_layers: int) -> list[str]:
    names: list[str] = []
    for layer in range(num_layers):
        names.append(
            "per_layer_inputs.perLayerModelProjection."
            f"layer{layer}.f32"
        )
        names.append(f"layer.{layer}.smoke_layer_block_wts.f32")
    return names


def weight_set_sha256(out_dir: Path, names: list[str]) -> str:
    digest = hashlib.sha256()
    for name in names:
        with (out_dir / name).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    return digest.hexdigest()


def f32_bytes_to_values(raw: bytes) -> list[float]:
    if len(raw) % 4 != 0:
        raise ValueError("f32 byte length is not divisible by 4")
    return [row[0] for row in struct.iter_unpack("<f", raw)]


def percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, math.ceil(q * len(sorted_values)) - 1))
    return float(sorted_values[index])


def compare_file_pair(left: Path, right: Path) -> dict[str, Any]:
    left_values = f32_bytes_to_values(left.read_bytes())
    right_values = f32_bytes_to_values(right.read_bytes())
    if len(left_values) != len(right_values):
        return {
            "status": "shape_mismatch",
            "leftCount": len(left_values),
            "rightCount": len(right_values),
        }
    diffs = sorted(abs(a - b) for a, b in zip(left_values, right_values))
    return {
        "status": "compared",
        "valueCount": len(diffs),
        "maxAbsDiff": float(diffs[-1]) if diffs else 0.0,
        "meanAbsDiff": float(sum(diffs) / len(diffs)) if diffs else 0.0,
        "p95AbsDiff": percentile(diffs, 0.95),
    }


def compare_reference_weights(
    out_dir: Path,
    reference_dir: Path,
    names: list[str],
) -> dict[str, Any]:
    if not reference_dir.is_dir():
        return {
            "status": "reference_absent",
            "referenceWeightsDir": rel(reference_dir),
        }
    compared: list[dict[str, Any]] = []
    missing: list[str] = []
    max_abs = 0.0
    mean_sum = 0.0
    compared_count = 0
    for name in names:
        left = out_dir / name
        right = reference_dir / name
        if not right.is_file():
            missing.append(name)
            continue
        record = compare_file_pair(left, right)
        record["file"] = name
        compared.append(record)
        if record["status"] == "compared":
            compared_count += 1
            max_abs = max(max_abs, float(record["maxAbsDiff"]))
            mean_sum += float(record["meanAbsDiff"])
    return {
        "status": "compared" if not missing else "missing_reference_files",
        "referenceWeightsDir": rel(reference_dir),
        "comparedFiles": compared_count,
        "missingReferenceFiles": missing[:20],
        "maxAbsDiffAcrossFiles": max_abs,
        "meanAbsDiffAcrossFiles": (
            mean_sum / compared_count if compared_count else 0.0
        ),
        "filesPreview": compared[:12],
        "interpretation": (
            "Diagnostic only: Q4_K_M is lossy, so this comparison is not a "
            "strict equality gate. Cross-runtime output parity uses the "
            "RDRR-derived slices on both lanes."
        ),
    }


def take(
    artifact_root: Path,
    manifest: dict[str, Any],
    tensor_name: str,
    count: int,
    source_records: list[dict[str, Any]],
) -> list[float]:
    tensor = (manifest.get("tensors") or {}).get(tensor_name)
    if tensor is None:
        raise KeyError(f"tensor not found: {tensor_name}")
    values = read_tensor_prefix_as_f32(
        artifact_root, manifest, tensor_name, count
    )
    source_records.append({
        "tensor": tensor_name,
        "dtype": tensor.get("dtype"),
        "shape": tensor.get("shape"),
        "layout": tensor.get("layout"),
        "count": count,
    })
    return values


def materialize_smoke_contract(
    artifact_root: Path,
    manifest: dict[str, Any],
    out_dir: Path,
    num_layers: int,
    size: int,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    qs = size // 4
    num_heads = 8
    smoke_head_dim = 8
    smoke_kv_len = 4
    per_head_values = smoke_head_dim * smoke_kv_len
    mlp_len = qs // 2
    files_written = 0
    source_records: list[dict[str, Any]] = []

    for layer in range(num_layers):
        prefix = f"{LANG_PREFIX}.{layer}"
        projection = take(
            artifact_root,
            manifest,
            f"{prefix}.per_layer_projection.weight",
            size,
            source_records,
        )
        projection_name = (
            "per_layer_inputs.perLayerModelProjection."
            f"layer{layer}.f32"
        )
        (out_dir / projection_name).write_bytes(f32_values_to_bytes(projection))
        files_written += 1

        gamma2 = take(
            artifact_root,
            manifest,
            f"{prefix}.post_attention_layernorm.weight",
            qs,
            source_records,
        )
        k_values = take(
            artifact_root,
            manifest,
            f"{prefix}.self_attn.k_proj.weight",
            num_heads * per_head_values,
            source_records,
        )
        v_values = take(
            artifact_root,
            manifest,
            f"{prefix}.self_attn.v_proj.weight",
            num_heads * per_head_values,
            source_records,
        )
        per_head_kv: list[float] = []
        for head in range(num_heads):
            lo = head * per_head_values
            hi = lo + per_head_values
            per_head_kv.extend(k_values[lo:hi])
            per_head_kv.extend(v_values[lo:hi])
        gate = take(
            artifact_root,
            manifest,
            f"{prefix}.mlp.gate_proj.weight",
            mlp_len,
            source_records,
        )
        up = take(
            artifact_root,
            manifest,
            f"{prefix}.mlp.up_proj.weight",
            mlp_len,
            source_records,
        )
        weights = gamma2 + per_head_kv + gate + up
        if len(weights) != size:
            raise ValueError(
                f"layer {layer}: composed weights count {len(weights)} "
                f"!= expected {size}"
            )
        (out_dir / f"layer.{layer}.smoke_layer_block_wts.f32").write_bytes(
            f32_values_to_bytes(weights)
        )
        files_written += 1

    return {
        "mode": "gemma4_e2b_doppler_rdrr_q4k_smoke_contract",
        "filesWritten": files_written,
        "sourceTensorCount": len(source_records),
        "sourceTensorsPreview": source_records[:24],
        "smokeContract": {
            "size": size,
            "qs": qs,
            "numHeads": num_heads,
            "headDim": smoke_head_dim,
            "kvLenPerHead": smoke_kv_len,
            "perHeadValues": per_head_values,
            "mlpSliceValues": mlp_len,
        },
    }


def absent_payload(
    fixture_path: Path,
    fixture: dict[str, Any],
    artifact_root: Path,
    out_dir: str,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_doppler_rdrr_q4k_extraction",
        "status": "blocked",
        "verdict": "blocked_artifact_absent",
        "fixturePath": rel(fixture_path),
        "modelId": fixture.get("modelId"),
        "artifactRoot": str(artifact_root),
        "outDir": out_dir,
        "errors": [f"artifact root not found: {artifact_root}"],
        "claimScope": {
            "claimable": "none",
            "notClaimable": [
                "Q4_K_M smoke-contract parity",
                "Doppler production inference output parity",
                "Full Gemma-4 E2B execution from the RDRR artifact",
                "Cerebras hardware execution",
            ],
        },
    }


def main() -> int:
    args = parse_args()
    fixture_path = resolve(args.fixture)
    fixture = read_json(fixture_path)
    artifact_root = resolve(args.artifact_root or fixture["artifactRoot"])
    out_dir = resolve(args.out_dir)
    out_json = resolve(args.out_json)

    if not artifact_root.is_dir():
        write_json(
            out_json,
            absent_payload(fixture_path, fixture, artifact_root, args.out_dir),
        )
        print(f"blocked_artifact_absent: {artifact_root}")
        return 0

    manifest_rel = (fixture.get("manifest") or {}).get("path", "manifest.json")
    manifest_path = artifact_root / manifest_rel
    manifest = read_json(manifest_path)
    errors: list[str] = []
    manifest_sha = sha256_file(manifest_path)
    expected_manifest_sha = (fixture.get("manifest") or {}).get("sha256")
    if manifest_sha != expected_manifest_sha:
        errors.append("manifest sha256 drift")
    expected = fixture.get("expected") or {}
    if int(expected.get("q4kBlockSizeElements", 0)) != Q4_K_M_BLOCK_ELEMENTS:
        errors.append("fixture q4kBlockSizeElements drift")
    if int(expected.get("q4kBlockSizeBytes", 0)) != Q4_K_M_BLOCK_BYTES:
        errors.append("fixture q4kBlockSizeBytes drift")
    if manifest.get("quantization") != "Q4_K_M":
        errors.append("manifest quantization is not Q4_K_M")

    architecture = manifest.get("architecture") or {}
    num_layers = int(architecture.get("numLayers", 35))
    names = expected_files(num_layers)
    materialization: dict[str, Any] = {}
    if not errors:
        try:
            materialization = materialize_smoke_contract(
                artifact_root,
                manifest,
                out_dir,
                num_layers,
                int(args.size),
            )
        except (OSError, KeyError, ValueError) as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

    status = "failed" if errors else "succeeded"
    weight_sha = None
    comparison = {"status": "not_attempted"}
    if status == "succeeded":
        weight_sha = weight_set_sha256(out_dir, names)
        comparison = compare_reference_weights(
            out_dir,
            resolve(args.compare_weights_dir),
            names,
        )

    payload = {
        "schemaVersion": 1,
        "artifactKind": "doe_doppler_rdrr_q4k_extraction",
        "status": status,
        "verdict": (
            "rdrr_q4k_smoke_contract_extracted"
            if status == "succeeded"
            else "rdrr_q4k_smoke_contract_failed"
        ),
        "fixturePath": rel(fixture_path),
        "artifactRoot": str(artifact_root),
        "modelId": manifest.get("modelId"),
        "manifest": {
            "path": str(manifest_path),
            "sha256": manifest_sha,
            "expectedSha256": expected_manifest_sha,
            "matched": manifest_sha == expected_manifest_sha,
        },
        "outDir": args.out_dir,
        "numLayers": num_layers,
        "sizePerSliceF32": int(args.size),
        "filesExpected": len(names),
        "filesWritten": materialization.get("filesWritten", 0),
        "weightSetSha256": weight_sha,
        "q4kDequantStatus": {
            "q4k": "implemented_for_smoke_contract",
            "int4Ple": "metadata_validated_no_runtime_dequant",
            "parity": "not_evaluated_by_extractor",
        },
        "materialization": materialization,
        "comparisonToReferenceWeights": comparison,
        "claimScope": {
            "claimable": (
                "Q4_K_M dequantized Doppler RDRR slices are materialized "
                "for Doe's existing Gemma-4 E2B L1 smoke-contract parity "
                "runner."
            ),
            "notClaimable": [
                "Doppler production inference output parity",
                "Full Gemma-4 E2B execution from the RDRR artifact",
                "Manifest-shape execution",
                "Cerebras hardware execution",
            ],
        },
        "errors": errors,
    }
    write_json(out_json, payload)
    if errors:
        print(f"FAIL: RDRR Q4_K_M extraction failed ({len(errors)} issues)")
        for error in errors[:10]:
            print(f"  {error}")
        return 1
    print(
        f"extracted {len(names)} RDRR Q4_K_M smoke-contract files to "
        f"{rel(out_dir)} weightSetSha256={str(weight_sha)[:16]}..."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
