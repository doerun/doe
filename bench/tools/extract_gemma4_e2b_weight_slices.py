#!/usr/bin/env python3
"""Materialize Gemma-4 E2B layer-block weight slices.

This is the repo-side extractor entrypoint for the real-weight lane. It
does not guess checkpoint tensor names. A caller may provide either:

1. a source directory that already contains the fixture-contract `.f32`
   files, or
2. a safetensors directory plus a mapping JSON that names the projection
   and layer-weight tensor for each layer, or
3. the raw Gemma-4 E2B SafeTensors snapshot discoverable from Doppler's
   local E2B origin metadata.

Absent source is a blocked verdict, not success. The downstream promotion
remains `blocked_weights_absent` until this tool materializes
`bench/out/gemma-4-e2b-real-weights/` and `validate_weights_dir.py`
accepts it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = "config/gemma-4-e2b-real-weight-fixture.json"
DEFAULT_OUT_DIR = "bench/out/gemma-4-e2b-real-weights"
DEFAULT_DOPPLER_ORIGIN_PATHS = [
    "../doppler/models/local/gemma-4-e2b-it-q4k-ehf16-af32-int4ple/origin.json",
    "../doppler/models/local/gemma-4-e2b-it-q4k-ehf16-af32/origin.json",
]
_ENV_SOURCE_DIR = os.environ.get("DOE_GEMMA4_E2B_SAFETENSORS_DIR")
DEFAULT_SOURCE_DIR_CANDIDATES = [
    *([_ENV_SOURCE_DIR] if _ENV_SOURCE_DIR else []),
    "/home/x/model-downloads/gemma4-e2b-it",
]
LANG_PREFIX = "model.language_model.layers"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fixture", default=DEFAULT_FIXTURE)
    p.add_argument(
        "--source-dir",
        default="",
        help=(
            "Directory containing contract .f32 files or safetensors files. "
            "When omitted, the extractor tries Doppler's local Gemma-4 E2B "
            "origin metadata."
        ),
    )
    p.add_argument(
        "--mapping-json",
        default="",
        help="Optional safetensors tensor mapping JSON.",
    )
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    p.add_argument("--out-json", default="")
    return p.parse_args()


def resolve(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def has_safetensors(path: Path) -> bool:
    return path.is_dir() and any(path.glob("*.safetensors"))


def discover_doppler_source_dir() -> tuple[Path | None, str | None]:
    """Find the raw SafeTensors snapshot referenced by Doppler's local E2B
    conversion metadata.

    The int4-PLE Doppler artifact records the source location in a human
    note rather than a structured field, so the parser only accepts an
    absolute path after "Converted from " and still verifies that the
    directory contains .safetensors files before trusting it.
    """
    for raw in DEFAULT_DOPPLER_ORIGIN_PATHS:
        origin_path = resolve(raw)
        if not origin_path.is_file():
            continue
        try:
            origin = read_json(origin_path)
        except (OSError, json.JSONDecodeError):
            continue
        for key in ("sourcePath", "sourceDir", "localSourcePath"):
            value = origin.get(key)
            if isinstance(value, str) and value:
                candidate = Path(value)
                if has_safetensors(candidate):
                    return candidate, rel(origin_path)
        notes = origin.get("notes")
        if isinstance(notes, str):
            m = re.search(r"Converted from\s+(\S+)", notes)
            if m:
                candidate = Path(m.group(1))
                if has_safetensors(candidate):
                    return candidate, rel(origin_path)
    for raw in DEFAULT_SOURCE_DIR_CANDIDATES:
        candidate = Path(raw)
        if has_safetensors(candidate):
            return candidate, "default_candidate"
    return None, None


def expected_files(num_layers: int) -> list[str]:
    out: list[str] = []
    for layer in range(num_layers):
        out.append(
            "per_layer_inputs.perLayerModelProjection."
            f"layer{layer}.f32"
        )
        out.append(f"layer.{layer}.smoke_layer_block_wts.f32")
    return out


def write_verdict(args: argparse.Namespace, verdict: dict[str, Any]) -> None:
    if not args.out_json:
        return
    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(verdict, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {rel(out_path)}")


def copy_contract_files(
    source_dir: Path,
    out_dir: Path,
    names: list[str],
) -> tuple[bool, list[str]]:
    missing = [name for name in names if not (source_dir / name).is_file()]
    if missing:
        return False, missing
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copyfile(source_dir / name, out_dir / name)
    return True, []


def load_safetensors_index(source_dir: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    index: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted(source_dir.glob("*.safetensors")):
        with path.open("rb") as fh:
            raw_len = fh.read(8)
            if len(raw_len) != 8:
                continue
            (header_len,) = struct.unpack("<Q", raw_len)
            header = json.loads(fh.read(header_len).decode("utf-8"))
        for name, meta in header.items():
            if name == "__metadata__":
                continue
            index[name] = (path, meta)
    return index


def _decode_bf16_to_f32_bytes(raw: bytes) -> bytes:
    if len(raw) % 2 != 0:
        raise ValueError("BF16 byte span is not even")
    out = bytearray((len(raw) // 2) * 4)
    o = 0
    for i in range(0, len(raw), 2):
        word = raw[i] | (raw[i + 1] << 8)
        out[o:o + 4] = struct.pack("<I", word << 16)
        o += 4
    return bytes(out)


def _decode_f16_to_f32_bytes(raw: bytes) -> bytes:
    if len(raw) % 2 != 0:
        raise ValueError("F16 byte span is not even")
    out = bytearray((len(raw) // 2) * 4)
    o = 0
    for i in range(0, len(raw), 2):
        value = struct.unpack("<e", raw[i:i + 2])[0]
        out[o:o + 4] = struct.pack("<f", float(value))
        o += 4
    return bytes(out)


def read_tensor_as_f32_bytes(
    tensor_index: dict[str, tuple[Path, dict[str, Any]]],
    tensor_name: str,
    count: int,
    start_element: int = 0,
) -> tuple[bytes | None, str | None, dict[str, Any] | None]:
    hit = tensor_index.get(tensor_name)
    if hit is None:
        return None, f"tensor not found: {tensor_name}", None
    path, meta = hit
    dtype = meta.get("dtype")
    offsets = meta.get("data_offsets")
    if not (
        isinstance(offsets, list)
        and len(offsets) == 2
        and all(isinstance(v, int) for v in offsets)
    ):
        return None, f"{tensor_name}: invalid data_offsets", None
    bytes_per_element = {"F32": 4, "BF16": 2, "F16": 2}.get(dtype)
    if bytes_per_element is None:
        return (
            None,
            f"{tensor_name}: dtype {dtype!r} unsupported; expected F32/BF16/F16",
            None,
        )
    start, end = offsets
    byte_start = start + start_element * bytes_per_element
    byte_len = count * bytes_per_element
    if byte_start < start or byte_start + byte_len > end:
        return (
            None,
            f"{tensor_name}: requested element span {start_element}:{start_element + count} "
            f"exceeds tensor byte span {end - start}",
            None,
        )
    with path.open("rb") as fh:
        header_len = struct.unpack("<Q", fh.read(8))[0]
        data_start = 8 + header_len
        fh.seek(data_start + byte_start)
        raw = fh.read(byte_len)
    if len(raw) != byte_len:
        return None, f"{tensor_name}: short read", None
    if dtype == "F32":
        data = raw
    elif dtype == "BF16":
        data = _decode_bf16_to_f32_bytes(raw)
    else:
        data = _decode_f16_to_f32_bytes(raw)
    source = {
        "tensor": tensor_name,
        "dtype": dtype,
        "shape": meta.get("shape"),
        "sourcePath": rel(path),
        "startElement": start_element,
        "count": count,
    }
    return data, None, source


def extract_f32_tensor(
    tensor_index: dict[str, tuple[Path, dict[str, Any]]],
    tensor_name: str,
    count: int,
    dst: Path,
) -> str | None:
    data, err, _source = read_tensor_as_f32_bytes(tensor_index, tensor_name, count)
    if err:
        return err
    assert data is not None
    dst.write_bytes(data)
    return None


def _take(
    failures: list[str],
    sources: list[dict[str, Any]],
    tensor_index: dict[str, tuple[Path, dict[str, Any]]],
    tensor_name: str,
    count: int,
    start_element: int = 0,
) -> bytes:
    data, err, source = read_tensor_as_f32_bytes(
        tensor_index, tensor_name, count, start_element
    )
    if err:
        failures.append(err)
        return b"\x00" * (count * 4)
    assert data is not None
    assert source is not None
    sources.append(source)
    return data


def materialize_gemma4_e2b_smoke_contract(
    source_dir: Path,
    out_dir: Path,
    num_layers: int,
    size: int,
) -> tuple[list[str], dict[str, Any]]:
    """Emit Doe's current smoke-contract files from canonical Gemma-4 E2B
    language-model tensors.

    Contract file layout is intentionally the runner's smoke layout, not the
    manifest-shape model layout:
      projection: first `size` f32 values from per_layer_projection.weight
      weights: [post_attn_norm[:qs],
                per-head K/V smoke window,
                gate_proj[:qs/2],
                up_proj[:qs/2]]
    """
    tensor_index = load_safetensors_index(source_dir)
    if not tensor_index:
        return ["no .safetensors tensors found in source-dir"], {}
    out_dir.mkdir(parents=True, exist_ok=True)
    qs = size // 4
    num_heads = 8
    smoke_head_dim = 8
    smoke_kv_len = 4
    per_head_values = smoke_head_dim * smoke_kv_len
    mlp_len = qs // 2
    failures: list[str] = []
    source_records: list[dict[str, Any]] = []
    files_written = 0

    for layer in range(num_layers):
        prefix = f"{LANG_PREFIX}.{layer}"
        projection_name = f"{prefix}.per_layer_projection.weight"
        projection = _take(
            failures, source_records, tensor_index, projection_name, size
        )
        (out_dir / (
            "per_layer_inputs.perLayerModelProjection."
            f"layer{layer}.f32"
        )).write_bytes(projection)
        files_written += 1

        gamma2 = _take(
            failures,
            source_records,
            tensor_index,
            f"{prefix}.post_attention_layernorm.weight",
            qs,
        )
        k = _take(
            failures,
            source_records,
            tensor_index,
            f"{prefix}.self_attn.k_proj.weight",
            num_heads * per_head_values,
        )
        v = _take(
            failures,
            source_records,
            tensor_index,
            f"{prefix}.self_attn.v_proj.weight",
            num_heads * per_head_values,
        )
        per_head_kv = bytearray()
        chunk = per_head_values * 4
        for head in range(num_heads):
            lo = head * chunk
            hi = lo + chunk
            per_head_kv.extend(k[lo:hi])
            per_head_kv.extend(v[lo:hi])
        gate = _take(
            failures,
            source_records,
            tensor_index,
            f"{prefix}.mlp.gate_proj.weight",
            mlp_len,
        )
        up = _take(
            failures,
            source_records,
            tensor_index,
            f"{prefix}.mlp.up_proj.weight",
            mlp_len,
        )
        weights = gamma2 + bytes(per_head_kv) + gate + up
        if len(weights) != size * 4:
            failures.append(
                f"layer {layer}: composed weights size {len(weights)} != {size * 4}"
            )
        (out_dir / f"layer.{layer}.smoke_layer_block_wts.f32").write_bytes(
            weights
        )
        files_written += 1

    materialization = {
        "mode": "gemma4_e2b_bf16_safetensors_smoke_contract",
        "sourceTensorCount": len(source_records),
        "sourceTensorsPreview": source_records[:24],
        "filesWritten": files_written,
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
    return failures, materialization


def materialize_from_safetensors(
    source_dir: Path,
    mapping_path: Path,
    out_dir: Path,
    num_layers: int,
    size: int,
) -> list[str]:
    mapping = read_json(mapping_path)
    layers = mapping.get("layers")
    if not isinstance(layers, list):
        return ["mapping-json must contain layers[]"]
    by_layer = {int(row.get("layer")): row for row in layers if "layer" in row}
    tensor_index = load_safetensors_index(source_dir)
    if not tensor_index:
        return ["no .safetensors tensors found in source-dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for layer in range(num_layers):
        row = by_layer.get(layer)
        if not isinstance(row, dict):
            failures.append(f"mapping missing layer {layer}")
            continue
        for key, dst_name in [
            (
                "projectionTensor",
                "per_layer_inputs.perLayerModelProjection."
                f"layer{layer}.f32",
            ),
            ("weightsTensor", f"layer.{layer}.smoke_layer_block_wts.f32"),
        ]:
            tensor_name = row.get(key)
            if not isinstance(tensor_name, str) or not tensor_name:
                failures.append(f"layer {layer} missing {key}")
                continue
            err = extract_f32_tensor(
                tensor_index, tensor_name, size, out_dir / dst_name
            )
            if err:
                failures.append(err)
    return failures


def main() -> int:
    args = parse_args()
    fixture_path = resolve(args.fixture)
    fixture = read_json(fixture_path)
    num_layers = int((fixture.get("modelShape") or {}).get("numLayers", 35))
    size = int((fixture.get("input") or {}).get("size", 1024))
    out_dir = resolve(args.out_dir)
    discovered_from = None
    if args.source_dir:
        source_dir = resolve(args.source_dir)
    else:
        source_dir, discovered_from = discover_doppler_source_dir()
    mapping_path = resolve(args.mapping_json) if args.mapping_json else None

    base: dict[str, Any] = {
        "schemaVersion": 1,
        "artifactKind": "doe_gemma4_e2b_weight_slice_extraction",
        "fixturePath": args.fixture,
        "sourceDir": str(source_dir) if source_dir is not None else None,
        "sourceDiscovery": discovered_from,
        "mappingJson": args.mapping_json or None,
        "outDir": args.out_dir,
        "numLayers": num_layers,
        "sizePerSliceF32": size,
    }

    if source_dir is None or not source_dir.is_dir():
        verdict = {
            **base,
            "status": "blocked",
            "verdict": "blocked_source_absent",
            "blocker": "source_dir_absent",
        }
        write_verdict(args, verdict)
        print("blocked_source_absent: pass --source-dir with checkpoint slices")
        return 0

    names = expected_files(num_layers)
    copied, missing = copy_contract_files(source_dir, out_dir, names)
    if copied:
        verdict = {
            **base,
            "status": "succeeded",
            "verdict": "contract_f32_files_copied",
            "filesWritten": len(names),
        }
        write_verdict(args, verdict)
        print(f"copied {len(names)} contract .f32 files to {rel(out_dir)}")
        return 0

    if mapping_path is None or not mapping_path.is_file():
        if has_safetensors(source_dir):
            failures, materialization = materialize_gemma4_e2b_smoke_contract(
                source_dir, out_dir, num_layers, size
            )
            verdict = {
                **base,
                "status": "failed" if failures else "succeeded",
                "verdict": "gemma4_e2b_smoke_contract_failed"
                if failures else "gemma4_e2b_smoke_contract_extracted",
                "failures": failures[:20],
                "filesWritten": 0 if failures else len(names),
                "materialization": materialization,
            }
            write_verdict(args, verdict)
            if failures:
                print(
                    f"FAIL: Gemma-4 E2B smoke-contract extraction failed "
                    f"({len(failures)} issues)"
                )
                for failure in failures[:10]:
                    print(f"  {failure}")
                return 1
            print(
                f"extracted {len(names)} Gemma-4 E2B smoke-contract .f32 "
                f"slices to {rel(out_dir)}"
            )
            return 0
        verdict = {
            **base,
            "status": "blocked",
            "verdict": "blocked_mapping_absent",
            "blocker": "mapping_json_absent",
            "missingContractFilesPreview": missing[:12],
        }
        write_verdict(args, verdict)
        print("blocked_mapping_absent: source did not contain contract files")
        return 0

    failures = materialize_from_safetensors(
        source_dir, mapping_path, out_dir, num_layers, size
    )
    verdict = {
        **base,
        "status": "failed" if failures else "succeeded",
        "verdict": "safetensors_extraction_failed"
        if failures else "safetensors_extracted",
        "failures": failures[:20],
        "filesWritten": 0 if failures else len(names),
    }
    write_verdict(args, verdict)
    if failures:
        print(f"FAIL: safetensors extraction failed ({len(failures)} issues)")
        for failure in failures[:10]:
            print(f"  {failure}")
        return 1
    print(f"extracted {len(names)} .f32 slices to {rel(out_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
