#!/usr/bin/env python3
"""Materialize Gemma-4 E2B layer-block weight slices.

This is the repo-side extractor entrypoint for the real-weight lane. It
does not guess checkpoint tensor names. A caller must provide either:

1. a source directory that already contains the fixture-contract `.f32`
   files, or
2. a safetensors directory plus a mapping JSON that names the projection
   and layer-weight tensor for each layer.

Absent source or absent mapping is a blocked verdict, not success. The
downstream promotion remains `blocked_weights_absent` until this tool
materializes `bench/out/gemma-4-e2b-real-weights/` and
`validate_weights_dir.py` accepts it.
"""

from __future__ import annotations

import argparse
import json
import shutil
import struct
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = "config/gemma-4-e2b-real-weight-fixture.json"
DEFAULT_OUT_DIR = "bench/out/gemma-4-e2b-real-weights"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fixture", default=DEFAULT_FIXTURE)
    p.add_argument(
        "--source-dir",
        default="",
        help="Directory containing contract .f32 files or safetensors files.",
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


def extract_f32_tensor(
    tensor_index: dict[str, tuple[Path, dict[str, Any]]],
    tensor_name: str,
    count: int,
    dst: Path,
) -> str | None:
    hit = tensor_index.get(tensor_name)
    if hit is None:
        return f"tensor not found: {tensor_name}"
    path, meta = hit
    dtype = meta.get("dtype")
    offsets = meta.get("data_offsets")
    if dtype != "F32":
        return f"{tensor_name}: dtype {dtype!r} unsupported; expected F32"
    if not (
        isinstance(offsets, list)
        and len(offsets) == 2
        and all(isinstance(v, int) for v in offsets)
    ):
        return f"{tensor_name}: invalid data_offsets"
    expected_bytes = count * 4
    start, end = offsets
    if end - start < expected_bytes:
        return (
            f"{tensor_name}: tensor byte span {end - start} < "
            f"expected {expected_bytes}"
        )
    with path.open("rb") as fh:
        header_len = struct.unpack("<Q", fh.read(8))[0]
        data_start = 8 + header_len
        fh.seek(data_start + start)
        data = fh.read(expected_bytes)
    dst.write_bytes(data)
    return None


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
    source_dir = resolve(args.source_dir) if args.source_dir else None
    mapping_path = resolve(args.mapping_json) if args.mapping_json else None

    base: dict[str, Any] = {
        "schemaVersion": 1,
        "artifactKind": "doe_gemma4_e2b_weight_slice_extraction",
        "fixturePath": args.fixture,
        "sourceDir": args.source_dir or None,
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
