#!/usr/bin/env python3
"""Probe a Doppler RDRR artifact without claiming dequant parity.

The probe validates the manifest, declared shard files, target tensor
locations, Q4_K_M packed byte sizes, and Gemma-4 int4 per-layer embedding
metadata. It intentionally stops before Q4_K_M dequantization or model-output
parity; those require a separate promotion path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = "config/gemma-4-e2b-doppler-rdrr-int4ple-fixture.json"
DEFAULT_OUT = "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-probe.json"

Q4_K_M_BLOCK_ELEMENTS = 256
Q4_K_M_BLOCK_BYTES = 144


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture",
        default=DEFAULT_FIXTURE,
        help="Path to the Doppler RDRR fixture contract.",
    )
    parser.add_argument(
        "--artifact-root",
        default="",
        help="Override the artifact root declared by the fixture.",
    )
    parser.add_argument(
        "--out-json",
        default=DEFAULT_OUT,
        help="Output JSON path for the probe verdict.",
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


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_span(path: Path, offset: int, size: int) -> str:
    digest = hashlib.sha256()
    remaining = size
    with path.open("rb") as handle:
        handle.seek(offset)
        while remaining:
            chunk = handle.read(min(1 << 20, remaining))
            if not chunk:
                raise ValueError(
                    f"short read while hashing {path} at {offset}+{size}"
                )
            remaining -= len(chunk)
            digest.update(chunk)
    return digest.hexdigest()


def product(values: list[int]) -> int:
    result = 1
    for value in values:
        result *= int(value)
    return result


def q4k_expected_bytes(shape: list[int], layout: str | None) -> int:
    if layout == "row" and len(shape) >= 2:
        rows = int(shape[0])
        cols = product([int(v) for v in shape[1:]])
        return rows * math.ceil(cols / Q4_K_M_BLOCK_ELEMENTS) * Q4_K_M_BLOCK_BYTES
    return math.ceil(product(shape) / Q4_K_M_BLOCK_ELEMENTS) * Q4_K_M_BLOCK_BYTES


def expected_storage_bytes(tensor: dict[str, Any]) -> int | None:
    shape = [int(v) for v in tensor.get("shape", [])]
    dtype = tensor.get("dtype")
    source = tensor.get("sourceTransform") or {}
    if source.get("sourceDtype") == "INT4":
        return math.ceil(product(shape) / 2)
    if dtype == "Q4_K_M":
        return q4k_expected_bytes(shape, tensor.get("layout"))
    if dtype == "F16":
        return product(shape) * 2
    if dtype == "F32":
        return product(shape) * 4
    return None


def shard_filename(index: int, shards_by_index: dict[int, dict[str, Any]]) -> str:
    shard = shards_by_index.get(index)
    if not shard:
        raise ValueError(f"manifest has no shard entry for index {index}")
    return str(shard.get("filename") or f"shard_{index:05d}.bin")


def validate_span(
    root: Path,
    shards_by_index: dict[int, dict[str, Any]],
    raw_span: dict[str, Any],
) -> dict[str, Any]:
    index = int(raw_span.get("shardIndex", raw_span.get("shard", -1)))
    offset = int(raw_span["offset"])
    size = int(raw_span["size"])
    filename = shard_filename(index, shards_by_index)
    path = root / filename
    file_size = path.stat().st_size if path.is_file() else None
    in_bounds = file_size is not None and offset >= 0 and offset + size <= file_size
    return {
        "shard": index,
        "filename": filename,
        "offset": offset,
        "size": size,
        "fileSize": file_size,
        "inBounds": in_bounds,
    }


def tensor_spans(
    tensor: dict[str, Any],
    root: Path,
    shards_by_index: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    spans = tensor.get("spans")
    if isinstance(spans, list):
        return [validate_span(root, shards_by_index, span) for span in spans]
    if tensor.get("shard") is None:
        return []
    return [
        validate_span(
            root,
            shards_by_index,
            {
                "shardIndex": int(tensor["shard"]),
                "offset": int(tensor["offset"]),
                "size": int(tensor["size"]),
            },
        )
    ]


def maybe_hash_tensor(
    root: Path,
    spans: list[dict[str, Any]],
    max_bytes: int,
) -> dict[str, Any]:
    total = sum(int(span["size"]) for span in spans)
    if not spans:
        return {"status": "not_applicable", "totalBytes": 0}
    if total > max_bytes:
        return {
            "status": "skipped_size_limit",
            "totalBytes": total,
            "maxBytes": max_bytes,
        }
    digest = hashlib.sha256()
    for span in spans:
        path = root / str(span["filename"])
        offset = int(span["offset"])
        size = int(span["size"])
        remaining = size
        with path.open("rb") as handle:
            handle.seek(offset)
            while remaining:
                chunk = handle.read(min(1 << 20, remaining))
                if not chunk:
                    raise ValueError(
                        f"short read while hashing tensor span {span}"
                    )
                remaining -= len(chunk)
                digest.update(chunk)
    return {
        "status": "hashed",
        "totalBytes": total,
        "sha256": digest.hexdigest(),
    }


def inspect_tensor(
    root: Path,
    manifest: dict[str, Any],
    shards_by_index: dict[int, dict[str, Any]],
    spec: dict[str, Any],
    max_hash_bytes: int,
) -> dict[str, Any]:
    name = str(spec["name"])
    tensor = (manifest.get("tensors") or {}).get(name)
    if tensor is None:
        return {
            "name": name,
            "required": bool(spec.get("required", True)),
            "present": False,
            "passed": not bool(spec.get("required", True)),
            "errors": ["target tensor missing"],
        }

    errors: list[str] = []
    dtype = tensor.get("dtype")
    role = tensor.get("role")
    layout = tensor.get("layout")
    shape = tensor.get("shape") or []
    if "dtype" in spec and dtype != spec["dtype"]:
        errors.append(f"dtype {dtype!r} != expected {spec['dtype']!r}")
    if "shape" in spec and shape != spec["shape"]:
        errors.append(f"shape {shape!r} != expected {spec['shape']!r}")
    if "expectedRole" in spec and role != spec["expectedRole"]:
        errors.append(f"role {role!r} != expected {spec['expectedRole']!r}")
    if "expectedLayout" in spec and layout != spec["expectedLayout"]:
        errors.append(
            f"layout {layout!r} != expected {spec['expectedLayout']!r}"
        )

    source_transform = tensor.get("sourceTransform") or {}
    if (
        "expectedSourceTransformKind" in spec
        and source_transform.get("kind") != spec["expectedSourceTransformKind"]
    ):
        errors.append(
            f"sourceTransform.kind {source_transform.get('kind')!r} "
            f"!= expected {spec['expectedSourceTransformKind']!r}"
        )
    if (
        "expectedSourceDtype" in spec
        and source_transform.get("sourceDtype") != spec["expectedSourceDtype"]
    ):
        errors.append(
            f"sourceTransform.sourceDtype "
            f"{source_transform.get('sourceDtype')!r} "
            f"!= expected {spec['expectedSourceDtype']!r}"
        )

    expected_size = expected_storage_bytes(tensor)
    declared_size = int(tensor.get("size", 0))
    size_matches_formula = expected_size is None or declared_size == expected_size
    if not size_matches_formula:
        errors.append(
            f"size {declared_size} != expected storage bytes {expected_size}"
        )

    spans = tensor_spans(tensor, root, shards_by_index)
    span_total = sum(int(span["size"]) for span in spans)
    spans_in_bounds = all(bool(span["inBounds"]) for span in spans)
    if spans and span_total != declared_size:
        errors.append(f"span total {span_total} != declared size {declared_size}")
    if spans and not spans_in_bounds:
        errors.append("one or more tensor spans are outside shard bounds")

    scale_source = (source_transform.get("scaleSource") or {})
    scale_audit: dict[str, Any] = {"status": "not_applicable"}
    if scale_source:
        scale_span = validate_span(root, shards_by_index, scale_source)
        if scale_span["inBounds"]:
            scale_path = root / str(scale_span["filename"])
            scale_audit = {
                "status": "hashed",
                "span": scale_span,
                "sha256": sha256_span(
                    scale_path,
                    int(scale_span["offset"]),
                    int(scale_span["size"]),
                ),
            }
        else:
            errors.append("sourceTransform.scaleSource is outside shard bounds")
            scale_audit = {"status": "out_of_bounds", "span": scale_span}

    span_hash = maybe_hash_tensor(root, spans, max_hash_bytes)
    if dtype == "Q4_K_M":
        format_status = "q4k_packed_shape_validated"
    elif source_transform.get("sourceDtype") == "INT4":
        format_status = "int4_ple_envelope_validated"
    else:
        format_status = "direct_storage_validated"

    return {
        "name": name,
        "required": bool(spec.get("required", True)),
        "present": True,
        "passed": not errors,
        "errors": errors,
        "dtype": dtype,
        "role": role,
        "layout": layout,
        "shape": shape,
        "declaredSize": declared_size,
        "expectedStorageBytes": expected_size,
        "sizeMatchesFormula": size_matches_formula,
        "spanCount": len(spans),
        "spanBytes": span_total,
        "spansInBounds": spans_in_bounds,
        "spanHash": span_hash,
        "formatStatus": format_status,
        "sourceTransform": source_transform or None,
        "scaleSourceAudit": scale_audit,
    }


def build_absent_payload(
    fixture_path: Path,
    fixture: dict[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_doppler_rdrr_artifact_probe",
        "status": "blocked_artifact_absent",
        "verdict": "blocked_artifact_absent",
        "fixturePath": rel(fixture_path),
        "modelId": fixture.get("modelId"),
        "artifactRoot": str(artifact_root),
        "claimScope": fixture.get("claimScope", {}),
        "dequantStatus": {
            "q4k": "not_attempted",
            "int4Ple": "not_attempted",
        },
        "errors": [f"artifact root not found: {artifact_root}"],
    }


def main() -> int:
    args = parse_args()
    fixture_path = resolve(args.fixture)
    fixture = load_json(fixture_path)
    artifact_root = resolve(args.artifact_root or fixture["artifactRoot"])
    out_path = resolve(args.out_json)

    if not artifact_root.is_dir():
        write_json(out_path, build_absent_payload(fixture_path, fixture, artifact_root))
        print(f"blocked_artifact_absent: {artifact_root}")
        return 0

    manifest_rel = (fixture.get("manifest") or {}).get("path", "manifest.json")
    origin_rel = (fixture.get("origin") or {}).get("path", "origin.json")
    manifest_path = artifact_root / manifest_rel
    origin_path = artifact_root / origin_rel
    manifest = load_json(manifest_path)
    origin = load_json(origin_path) if origin_path.is_file() else {}

    expected = fixture.get("expected") or {}
    declared_shards = manifest.get("shards") or []
    shards_by_index = {
        int(shard["index"]): shard
        for shard in declared_shards
    }
    declared_names = {str(shard["filename"]) for shard in declared_shards}
    local_names = sorted(path.name for path in artifact_root.glob("shard_*.bin"))
    extra_local = [name for name in local_names if name not in declared_names]
    missing = [name for name in sorted(declared_names) if name not in local_names]

    size_mismatches = []
    for shard in declared_shards:
        filename = str(shard["filename"])
        path = artifact_root / filename
        if not path.is_file():
            continue
        actual_size = path.stat().st_size
        expected_size = int(shard["size"])
        if actual_size != expected_size:
            size_mismatches.append({
                "filename": filename,
                "expected": expected_size,
                "actual": actual_size,
            })

    target_indices = [int(v) for v in expected.get("targetShardIndices", [])]
    selected_hashes = []
    selected_hash_errors = []
    for index in target_indices:
        shard = shards_by_index.get(index)
        if shard is None:
            selected_hash_errors.append(f"missing declared shard index {index}")
            continue
        filename = str(shard["filename"])
        path = artifact_root / filename
        if not path.is_file():
            selected_hash_errors.append(f"missing selected shard file {filename}")
            continue
        actual_hash = sha256_file(path)
        expected_hash = str(shard.get("hash", ""))
        selected_hashes.append({
            "index": index,
            "filename": filename,
            "sha256": actual_hash,
            "expectedSha256": expected_hash,
            "matched": actual_hash == expected_hash,
        })
        if actual_hash != expected_hash:
            selected_hash_errors.append(f"hash mismatch for {filename}")

    max_tensor_hash_bytes = int(
        (fixture.get("probe") or {}).get("maxTensorSpanHashBytes", 16_000_000)
    )
    tensor_results = [
        inspect_tensor(
            artifact_root,
            manifest,
            shards_by_index,
            spec,
            max_tensor_hash_bytes,
        )
        for spec in fixture.get("targetTensors", [])
    ]
    required_results = [r for r in tensor_results if r["required"]]
    required_passed = all(bool(r["passed"]) for r in required_results)

    expected_extra = sorted(expected.get("extraLocalShards", []))
    manifest_sha = sha256_file(manifest_path)
    origin_sha = sha256_file(origin_path) if origin_path.is_file() else None
    errors = []
    if fixture.get("modelId") != manifest.get("modelId"):
        errors.append("fixture modelId does not match manifest modelId")
    if manifest_sha != (fixture.get("manifest") or {}).get("sha256"):
        errors.append("manifest sha256 drift")
    if origin_sha != (fixture.get("origin") or {}).get("sha256"):
        errors.append("origin sha256 drift")
    if expected.get("declaredShardCount") != len(declared_shards):
        errors.append("declared shard count drift")
    if expected.get("localShardCount") != len(local_names):
        errors.append("local shard count drift")
    if expected_extra != extra_local:
        errors.append("extra local shard list drift")
    if expected.get("totalSize") != manifest.get("totalSize"):
        errors.append("manifest totalSize drift")
    if expected.get("quantization") != manifest.get("quantization"):
        errors.append("manifest quantization drift")
    qinfo = manifest.get("quantizationInfo") or {}
    if expected.get("perLayerEmbeddings") != qinfo.get("perLayerEmbeddings"):
        errors.append("perLayerEmbeddings quantization drift")
    if missing:
        errors.append("one or more declared shards are missing")
    if size_mismatches:
        errors.append("one or more declared shard sizes drifted")
    if selected_hash_errors:
        errors.extend(selected_hash_errors)
    if not required_passed:
        errors.append("one or more required target tensors failed audit")

    status = "succeeded" if not errors else "failed"
    payload = {
        "schemaVersion": 1,
        "artifactKind": "doe_doppler_rdrr_artifact_probe",
        "status": status,
        "verdict": (
            "rdrr_structural_probe_passed"
            if status == "succeeded"
            else "rdrr_structural_probe_failed"
        ),
        "fixturePath": rel(fixture_path),
        "artifactRoot": str(artifact_root),
        "modelId": manifest.get("modelId"),
        "manifest": {
            "path": str(manifest_path),
            "sha256": manifest_sha,
            "expectedSha256": (fixture.get("manifest") or {}).get("sha256"),
            "matched": manifest_sha == (fixture.get("manifest") or {}).get("sha256"),
        },
        "origin": {
            "path": str(origin_path),
            "sha256": origin_sha,
            "expectedSha256": (fixture.get("origin") or {}).get("sha256"),
            "matched": origin_sha == (fixture.get("origin") or {}).get("sha256"),
            "sourceModel": origin.get("sourceModel"),
            "variant": origin.get("variant"),
        },
        "artifactSummary": {
            "quantization": manifest.get("quantization"),
            "quantizationInfo": manifest.get("quantizationInfo"),
            "totalSize": manifest.get("totalSize"),
            "tensorCount": len(manifest.get("tensors") or {}),
            "declaredShardCount": len(declared_shards),
            "localShardCount": len(local_names),
            "extraLocalShardCount": len(extra_local),
            "extraLocalShards": extra_local,
        },
        "shardAudit": {
            "declaredShardSizeAudit": {
                "status": "passed" if not missing and not size_mismatches else "failed",
                "missing": missing,
                "sizeMismatches": size_mismatches,
            },
            "selectedShardHashAudit": {
                "status": "passed" if not selected_hash_errors else "failed",
                "hashMode": (fixture.get("probe") or {}).get("hashMode"),
                "selectedShards": selected_hashes,
            },
            "fullShardHashAudit": {
                "status": "not_attempted",
                "reason": "fixture hashMode validates selected target shards only",
            },
        },
        "tensorAudit": {
            "status": "passed" if required_passed else "failed",
            "requiredCount": len(required_results),
            "passedRequiredCount": sum(1 for r in required_results if r["passed"]),
            "targetTensors": tensor_results,
        },
        "dequantStatus": {
            "q4k": "blocked_not_implemented",
            "int4Ple": "metadata_validated_no_runtime_dequant",
            "parity": "not_claimed",
        },
        "claimScope": fixture.get("claimScope", {}),
        "errors": errors,
    }
    write_json(out_path, payload)
    print(f"wrote {rel(out_path)} status={status}")
    return 0 if status == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
