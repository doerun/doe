#!/usr/bin/env python3
"""Materialize Gemma-4 31B layer-block weight slices (smoke shape).

Closes "Real-weight Doppler smoke-shape projection extraction" from
docs/cerebras-north-star.md (Remaining no-hardware evidence gaps).

The 31B real-weight pin lives at bench/out/r3-1-31b-real-weights/, but
the parity audit flips to weights_audit_failed when the smoke-shape
.f32 projection files are absent (per-layer projection +
smoke_layer_block_wts). This extractor materializes those files from
the canonical HuggingFace Gemma-4 31B safetensors snapshot, using the
same smoke contract as the E2B layer-block extractor (size=1024,
num_heads=8, smoke_head_dim=8, smoke_kv_len=4, qs=size/4) — both
models share the smoke layer-block kernel even though the manifest-
shape model architectures differ.

Source discovery order:
  1. --source-dir flag, when passed.
  2. DOE_GEMMA4_31B_SAFETENSORS_DIR env var.
  3. Default candidates under
     /home/x/deco/doppler/models/source/huggingface_cache/google--gemma-4-31B-it
     (where doppler downloads pinned HF snapshots) and
     ../doppler/models/local/... origin metadata.

If no source can be resolved the extractor records a typed
blocked_source_absent verdict and returns 0 — the audit verdict stays
weights_audit_failed but the blocker is now machine-readable.

Output:
  --out-dir (default bench/out/gemma-4-31b-real-weights/) gets two
  files per layer:
    - per_layer_inputs.perLayerModelProjection.layer{N}.f32
    - layer.{N}.smoke_layer_block_wts.f32
  Each file is `size * 4` bytes (4096 at smoke size 1024).

Verdict JSON (`--out-json` or stdout) records:
  - sourceDir, numLayers, sizePerSliceF32
  - status (succeeded/failed/blocked) + typed verdict
  - filesWritten, materialization mode + smokeContract
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools import extract_gemma4_e2b_weight_slices as e2b_extractor

DEFAULT_FIXTURE = "config/gemma-4-31b-real-weight-fixture.json"
DEFAULT_OUT_DIR = "bench/out/gemma-4-31b-real-weights"
_ENV_SOURCE_DIR = os.environ.get("DOE_GEMMA4_31B_SAFETENSORS_DIR")
DEFAULT_SOURCE_DIR_CANDIDATES = [
    *([_ENV_SOURCE_DIR] if _ENV_SOURCE_DIR else []),
    "/home/x/deco/doppler/models/source/huggingface_cache/google--gemma-4-31B-it",
    "/home/x/model-downloads/gemma-4-31b-it",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fixture", default=DEFAULT_FIXTURE)
    p.add_argument(
        "--source-dir",
        default="",
        help=(
            "Directory containing 31B safetensors files. When omitted, the "
            "extractor tries DOE_GEMMA4_31B_SAFETENSORS_DIR, then the "
            "doppler huggingface_cache, then /home/x/model-downloads/."
        ),
    )
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    p.add_argument("--out-json", default="")
    return p.parse_args()


def discover_31b_source_dir() -> tuple[Path | None, str | None]:
    for candidate in DEFAULT_SOURCE_DIR_CANDIDATES:
        path = Path(candidate)
        if path.is_dir() and any(path.glob("*.safetensors")):
            return path, str(path)
    return None, None


def main() -> int:
    args = parse_args()
    fixture_path = e2b_extractor.resolve(args.fixture)
    fixture = e2b_extractor.read_json(fixture_path)
    num_layers = int((fixture.get("modelShape") or {}).get("numLayers", 61))
    size = int((fixture.get("input") or {}).get("size", 1024))
    out_dir = e2b_extractor.resolve(args.out_dir)

    discovered_from = None
    if args.source_dir:
        source_dir = e2b_extractor.resolve(args.source_dir)
    else:
        source_dir, discovered_from = discover_31b_source_dir()

    base: dict[str, Any] = {
        "schemaVersion": 1,
        "artifactKind": "doe_gemma4_31b_weight_slice_extraction",
        "fixturePath": args.fixture,
        "sourceDir": str(source_dir) if source_dir is not None else None,
        "sourceDiscovery": discovered_from,
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
            "blockerNote": (
                "No 31B safetensors directory found. Set "
                "DOE_GEMMA4_31B_SAFETENSORS_DIR to point at a snapshot of "
                "HuggingFace google/gemma-4-31B-it at revision "
                "439edf5652646a0d1bd8b46bfdc1d3645761a445, or pass "
                "--source-dir explicitly."
            ),
        }
        _emit_verdict(args, verdict)
        print(
            "blocked_source_absent: pass --source-dir or set "
            "DOE_GEMMA4_31B_SAFETENSORS_DIR"
        )
        return 0

    names = e2b_extractor.expected_files(num_layers)
    copied, missing = e2b_extractor.copy_contract_files(source_dir, out_dir, names)
    if copied:
        verdict = {
            **base,
            "status": "succeeded",
            "verdict": "contract_f32_files_copied",
            "filesWritten": len(names),
        }
        _emit_verdict(args, verdict)
        print(f"copied {len(names)} contract .f32 files to {e2b_extractor.rel(out_dir)}")
        return 0

    if e2b_extractor.has_safetensors(source_dir):
        failures, materialization = (
            e2b_extractor.materialize_gemma4_e2b_smoke_contract(
                source_dir, out_dir, num_layers, size
            )
        )
        materialization = {
            **materialization,
            "mode": "gemma4_31b_bf16_safetensors_smoke_contract",
        }
        verdict = {
            **base,
            "status": "failed" if failures else "succeeded",
            "verdict": "gemma4_31b_smoke_contract_failed"
            if failures
            else "gemma4_31b_smoke_contract_extracted",
            "failures": failures[:20],
            "filesWritten": 0 if failures else len(names),
            "materialization": materialization,
        }
        _emit_verdict(args, verdict)
        if failures:
            print(
                f"FAIL: Gemma-4 31B smoke-contract extraction failed "
                f"({len(failures)} issues)"
            )
            for failure in failures[:10]:
                print(f"  {failure}")
            return 1
        print(
            f"extracted {len(names)} Gemma-4 31B smoke-contract .f32 "
            f"slices to {e2b_extractor.rel(out_dir)}"
        )
        return 0

    verdict = {
        **base,
        "status": "blocked",
        "verdict": "blocked_no_safetensors_in_source",
        "blocker": "no_safetensors_in_source_dir",
        "missingContractFilesPreview": missing[:12],
    }
    _emit_verdict(args, verdict)
    print("blocked_no_safetensors_in_source: source dir lacks .safetensors files")
    return 0


def _emit_verdict(args: argparse.Namespace, verdict: dict[str, Any]) -> None:
    text = json.dumps(verdict, indent=2) + "\n"
    if args.out_json:
        out_path = e2b_extractor.resolve(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    raise SystemExit(main())
