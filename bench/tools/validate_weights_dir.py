#!/usr/bin/env python3
"""Validate a candidate --weights-dir against the runner contract.

The E2B / 31B layer-block runner (bench/runners/csl-runners/
e2b_layer_block_smoke.py and gemma_4_31b_layer_block_smoke.py) reads
per-layer tensor slices from --weights-dir via load_layer_data(). For
each layer l_idx in [0, num_layers), the runner expects two files:

  per_layer_inputs.perLayerModelProjection.layer{l_idx}.f32
  layer.{l_idx}.smoke_layer_block_wts.f32

Each file must contain exactly --size f32 values (--size * 4 bytes)
in native little-endian order. When all expected files exist and are
readable at the right size, the runner's dataSource.kind promotes
from 'synthetic_seeded_rng' to 'manifest_weights_only', flipping
two promotion criteria on the parity receipt:

  promotionCriteria.syntheticInputsAbsent  false -> true
  promotionCriteria.syntheticWeightsAbsent false -> true

This tool audits a candidate weights-dir without running the kernel:

  - enumerates expected filenames from manifest.modelConfig.numLayers
  - checks presence, size, readability as f32
  - emits a per-file sha256 so the downstream receipt can bind a
    weightSetSha256 (covering all slices as a single digest)
  - writes a JSON audit artifact the parity-receipt builder can
    consume to populate promotionCriteria.weightHashMatched

Usage:

  python3 bench/tools/validate_weights_dir.py \\
    --weights-dir <path> \\
    --manifest runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json \\
    --size 1024 \\
    --out bench/out/weights-audit/gemma-4-e2b-weights-audit.json

Exit 0 iff every expected file is present, correctly sized, and
readable. The JSON output at --out records per-file status + sha256
so an extractor author can compare their output against a recorded
baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--weights-dir",
        required=True,
        help="Directory containing per-layer .f32 slice files.",
    )
    p.add_argument(
        "--manifest",
        default="runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json",
    )
    p.add_argument(
        "--size",
        type=int,
        default=1024,
        help="Per-stream f32 count. Must match the runner's --size.",
    )
    p.add_argument(
        "--out",
        default="",
        help="Optional JSON audit artifact path. When unset, skips "
             "the audit-file write and prints verdict only.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    manifest = json.loads(
        Path(args.manifest).read_text(encoding="utf-8")
    )
    num_layers = int(manifest["modelConfig"]["numLayers"])
    model_id = manifest.get("modelId", "")
    expected_bytes = args.size * 4  # f32 = 4 bytes

    weights_dir = Path(args.weights_dir)
    if not weights_dir.is_dir():
        print(
            f"FAIL: weights-dir is not a directory: {weights_dir}"
        )
        return 2

    per_layer_entries: list[dict] = []
    per_file_sha = hashlib.sha256()  # aggregate over all slices
    failures: list[str] = []

    for l_idx in range(num_layers):
        proj_name = (
            "per_layer_inputs.perLayerModelProjection."
            f"layer{l_idx}.f32"
        )
        wts_name = f"layer.{l_idx}.smoke_layer_block_wts.f32"
        entry: dict = {"layer": l_idx}
        for role, name in (("projection", proj_name), ("weights", wts_name)):
            fpath = weights_dir / name
            rec: dict = {
                "role": role,
                "file": name,
                "exists": fpath.is_file(),
            }
            if not rec["exists"]:
                failures.append(f"layer {l_idx} {role} missing: {name}")
            else:
                sz = fpath.stat().st_size
                rec["sizeBytes"] = sz
                rec["expectedBytes"] = expected_bytes
                if sz != expected_bytes:
                    failures.append(
                        f"layer {l_idx} {role} wrong size: {sz} "
                        f"!= expected {expected_bytes}"
                    )
                else:
                    sha = sha256_file(fpath)
                    rec["sha256"] = sha
                    # Fold file bytes into aggregate set-sha.
                    with fpath.open("rb") as fh:
                        for ch in iter(lambda: fh.read(1 << 20), b""):
                            per_file_sha.update(ch)
            entry[role] = rec
        per_layer_entries.append(entry)

    weight_set_sha256 = per_file_sha.hexdigest()
    audit = {
        "schemaVersion": 1,
        "artifactKind": "doe_weights_dir_audit",
        "modelId": model_id,
        "manifestPath": args.manifest,
        "numLayersExpected": num_layers,
        "sizePerFileF32": args.size,
        "expectedBytesPerFile": expected_bytes,
        "weightsDir": args.weights_dir,
        "perLayer": per_layer_entries,
        "weightSetSha256": weight_set_sha256,
        "passedAudit": not failures,
        "failures": failures,
    }

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = REPO_ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(audit, indent=2) + "\n", encoding="utf-8"
        )
        try:
            rel = str(out_path.relative_to(REPO_ROOT))
        except ValueError:
            rel = str(out_path)
        print(f"wrote {rel}")

    if failures:
        print(
            f"FAIL: weights-dir audit {len(failures)} violation(s) "
            f"(expected {2 * num_layers} files at {expected_bytes} "
            f"bytes each; {args.weights_dir})"
        )
        for f in failures[:10]:
            print(f"  {f}")
        if len(failures) > 10:
            print(f"  ... and {len(failures) - 10} more")
        return 1

    print(
        f"PASS: weights-dir audit ({2 * num_layers} files, "
        f"weightSetSha256={weight_set_sha256[:16]}..., "
        f"model={model_id})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
