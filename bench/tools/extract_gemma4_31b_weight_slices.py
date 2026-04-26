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


PROJECTION_SUBSTITUTE_CHOICES = (
    "fail",
    "pre_feedforward_layernorm.weight",
    "post_feedforward_layernorm.weight",
    "input_layernorm.weight",
)
LINEAR_ATTENTION_POLICY_CHOICES = (
    "fail",
    "skip-with-layout-metadata",
    "dup-k-into-v",
)


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
    p.add_argument(
        "--projection-substitute-tensor",
        choices=PROJECTION_SUBSTITUTE_CHOICES,
        default=None,
        help=(
            "Per-layer-scalar tensor that substitutes for E2B's "
            "per_layer_projection.weight at smoke shape. Gemma 4 31B has no "
            "per_layer_projection learned tensor; smoke shape needs a "
            "per-layer slice from a tensor that exists in the 31B "
            "checkpoint. CLI flag overrides the fixture's "
            "weightsDir.smokeContract.projectionSubstituteTensor; either "
            "must be set explicitly. Default 'fail' surfaces the decision "
            "rather than silently substituting."
        ),
    )
    p.add_argument(
        "--linear-attention-policy",
        choices=LINEAR_ATTENTION_POLICY_CHOICES,
        default=None,
        help=(
            "Policy for layers that lack self_attn.v_proj.weight (linear / "
            "sliding-window attention). 'skip-with-layout-metadata' omits "
            "the v_proj concat for those layers and records "
            "kv_layout='linear' in the materialization metadata so the "
            "audit accepts the layer as complete-by-policy. 'dup-k-into-v' "
            "duplicates k_proj into the v_proj slot (structurally "
            "dishonest; use only when the audit explicitly asks for it). "
            "'fail' (default) refuses to substitute and surfaces the "
            "missing tensors."
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


def materialize_gemma4_31b_smoke_contract(
    source_dir: Path,
    out_dir: Path,
    num_layers: int,
    size: int,
    projection_substitute_tensor: str,
    linear_attention_policy: str,
) -> tuple[list[str], dict[str, Any]]:
    """Emit Doe's smoke-contract files from Gemma 4 31B safetensors.

    Differs from materialize_gemma4_e2b_smoke_contract in two ways:
      1) per_layer_projection.weight does not exist in 31B — the
         projection slice is read from `projection_substitute_tensor`
         instead (one of pre_feedforward_layernorm / post_feedforward_-
         layernorm / input_layernorm).
      2) self_attn.v_proj.weight is absent on linear-attention layers.
         When `linear_attention_policy='skip-with-layout-metadata'` the
         v_proj concat is dropped for those layers and kv_layout='linear'
         is recorded in the materialization metadata; the layer is
         considered complete-by-policy so the smoke audit can still
         emit a complete-model verdict.
    """
    tensor_index = e2b_extractor.load_safetensors_index(source_dir)
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
    per_layer_kv_layout: list[dict[str, Any]] = []

    for layer in range(num_layers):
        prefix = f"{e2b_extractor.LANG_PREFIX}.{layer}"
        projection_name = f"{prefix}.{projection_substitute_tensor}"
        projection = e2b_extractor._take(
            failures, source_records, tensor_index, projection_name, size
        )
        (out_dir / (
            "per_layer_inputs.perLayerModelProjection."
            f"layer{layer}.f32"
        )).write_bytes(projection)
        files_written += 1

        gamma2 = e2b_extractor._take(
            failures,
            source_records,
            tensor_index,
            f"{prefix}.post_attention_layernorm.weight",
            qs,
        )
        k = e2b_extractor._take(
            failures,
            source_records,
            tensor_index,
            f"{prefix}.self_attn.k_proj.weight",
            num_heads * per_head_values,
        )
        v_name = f"{prefix}.self_attn.v_proj.weight"
        v_present = v_name in tensor_index
        kv_layout = "full" if v_present else "linear"
        if v_present:
            v = e2b_extractor._take(
                failures,
                source_records,
                tensor_index,
                v_name,
                num_heads * per_head_values,
            )
        elif linear_attention_policy == "skip-with-layout-metadata":
            v = b"\x00" * (num_heads * per_head_values * 4)
        elif linear_attention_policy == "dup-k-into-v":
            v = bytes(k)
        else:
            failures.append(
                f"layer {layer}: tensor not found: {v_name} "
                f"(linear-attention layer; pass "
                f"--linear-attention-policy=skip-with-layout-metadata "
                f"to substitute)"
            )
            v = b"\x00" * (num_heads * per_head_values * 4)

        per_head_kv = bytearray()
        chunk = per_head_values * 4
        for head in range(num_heads):
            lo = head * chunk
            hi = lo + chunk
            per_head_kv.extend(k[lo:hi])
            per_head_kv.extend(v[lo:hi])
        gate = e2b_extractor._take(
            failures,
            source_records,
            tensor_index,
            f"{prefix}.mlp.gate_proj.weight",
            mlp_len,
        )
        up = e2b_extractor._take(
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
        per_layer_kv_layout.append({"layer": layer, "kv_layout": kv_layout})

    materialization = {
        "mode": "gemma4_31b_bf16_safetensors_smoke_contract_v2",
        "projectionSubstituteTensor": projection_substitute_tensor,
        "linearAttentionPolicy": linear_attention_policy,
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
        "perLayerKvLayout": per_layer_kv_layout,
        "linearLayerCount": sum(
            1 for r in per_layer_kv_layout if r["kv_layout"] == "linear"
        ),
        "fullLayerCount": sum(
            1 for r in per_layer_kv_layout if r["kv_layout"] == "full"
        ),
    }
    return failures, materialization


def main() -> int:
    args = parse_args()
    fixture_path = e2b_extractor.resolve(args.fixture)
    fixture = e2b_extractor.read_json(fixture_path)
    num_layers = int((fixture.get("modelShape") or {}).get("numLayers", 61))
    size = int((fixture.get("input") or {}).get("size", 1024))
    out_dir = e2b_extractor.resolve(args.out_dir)

    smoke_contract_pin = (
        ((fixture.get("weightsDir") or {}).get("smokeContract") or {})
    )
    projection_substitute = (
        args.projection_substitute_tensor
        or smoke_contract_pin.get("projectionSubstituteTensor")
        or "fail"
    )
    linear_policy = (
        args.linear_attention_policy
        or smoke_contract_pin.get("linearAttentionPolicy")
        or "fail"
    )

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
        "projectionSubstituteTensor": projection_substitute,
        "linearAttentionPolicy": linear_policy,
    }

    if projection_substitute == "fail":
        verdict = {
            **base,
            "status": "blocked",
            "verdict": "blocked_projection_substitute_unset",
            "blocker": "projection_substitute_tensor_undecided",
            "blockerNote": (
                "31B has no per_layer_projection.weight. Pass "
                "--projection-substitute-tensor "
                "pre_feedforward_layernorm.weight (or another listed "
                "candidate), or pin "
                "weightsDir.smokeContract.projectionSubstituteTensor in "
                "the fixture. See "
                "bench/out/r3-1-31b-real-weight-smoke-extraction-preflight/"
                "receipt.json for the option set."
            ),
        }
        _emit_verdict(args, verdict)
        print(
            "blocked_projection_substitute_unset: pass "
            "--projection-substitute-tensor or pin "
            "weightsDir.smokeContract.projectionSubstituteTensor"
        )
        return 0
    if linear_policy == "fail":
        verdict = {
            **base,
            "status": "blocked",
            "verdict": "blocked_linear_attention_policy_unset",
            "blocker": "linear_attention_policy_undecided",
            "blockerNote": (
                "Subset of 31B layers lack self_attn.v_proj.weight "
                "(linear / sliding-window attention). Pass "
                "--linear-attention-policy skip-with-layout-metadata "
                "(or pin "
                "weightsDir.smokeContract.linearAttentionPolicy in the "
                "fixture)."
            ),
        }
        _emit_verdict(args, verdict)
        print(
            "blocked_linear_attention_policy_unset: pass "
            "--linear-attention-policy or pin "
            "weightsDir.smokeContract.linearAttentionPolicy"
        )
        return 0

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
        failures, materialization = materialize_gemma4_31b_smoke_contract(
            source_dir,
            out_dir,
            num_layers,
            size,
            projection_substitute_tensor=projection_substitute,
            linear_attention_policy=linear_policy,
        )
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
        linear_n = materialization.get("linearLayerCount", 0)
        full_n = materialization.get("fullLayerCount", 0)
        print(
            f"extracted {len(names)} Gemma-4 31B smoke-contract .f32 "
            f"slices to {e2b_extractor.rel(out_dir)} "
            f"(projection_substitute={projection_substitute}, "
            f"linear_attention_policy={linear_policy}, "
            f"layers full={full_n} linear={linear_n})"
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
