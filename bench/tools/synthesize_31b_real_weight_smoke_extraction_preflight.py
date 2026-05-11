#!/usr/bin/env python3
"""Synthesize the 31B real-weight smoke-shape extraction preflight.

Mitigates "Real-weight Doppler reference" smoke-shape projection
extraction from docs/cerebras-model-ledgers.md (Remaining no-hardware
evidence gaps).

The 31B real-weight pin (`bench/out/r3-1-31b-real-weights/pin.json`)
flips `weightsDirPresent` to true, but the parity audit at
`bench/out/gemma-4-31b-real-weight-parity-L1.json` reports
`weights_audit_failed` because the smoke-shape `.f32` files
(per_layer_inputs.perLayerModelProjection.layer{N}.f32 +
layer.{N}.smoke_layer_block_wts.f32) are not materialized.

`bench/tools/extract_gemma4_31b_weight_slices.py` (added 2026-04-25)
runs the E2B smoke contract against 31B safetensors but produces a
typed `gemma4_31b_smoke_contract_failed` verdict because:

  1. 31B safetensors lack `per_layer_projection.weight` per layer
     (E2B has it as a learned per-layer projection; 31B does not —
     the Gemma 4 31B architecture has no equivalent learned tensor).
  2. A subset of layers (sliding-window attention layers) lack
     `self_attn.v_proj.weight` (linear-attention layers in Gemma 4
     31B do not produce a v_proj tensor).

This synthesizer reads the failed-verdict file and emits a structured
preflight that:
  - records the architectural mismatch precisely,
  - names which substitute decisions a Doe operator must make to
    proceed (which 31B tensor stands in for the per-layer projection
    at smoke shape; how to handle linear-attention layers),
  - leaves the substitution choice unmade — this is a model-
    architectural decision, not an automatable one.

The preflight artifact is reviewer-facing: it tells whoever owns 31B
weight extraction what they need to decide before the smoke contract
can produce clean files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VERDICT = (
    REPO_ROOT
    / "bench/out/gemma-4-31b-smoke-extraction-test/verdict.json"
)
DEFAULT_OUT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-real-weight-smoke-extraction-preflight/receipt.json"
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--source-verdict",
        type=Path,
        default=DEFAULT_VERDICT,
        help=(
            "Path to the gemma4_31b_smoke_contract_failed verdict written "
            "by extract_gemma4_31b_weight_slices.py. When absent, the "
            "preflight records the architectural mismatch from notes "
            "alone."
        ),
    )
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return p.parse_args()


def main() -> int:
    args = parse_args()

    source_failures: list[str] = []
    if args.source_verdict.is_file():
        try:
            verdict = json.loads(
                args.source_verdict.read_text(encoding="utf-8")
            )
            for f in verdict.get("failures") or []:
                if isinstance(f, str):
                    source_failures.append(f)
        except (OSError, json.JSONDecodeError):
            pass

    receipt = {
        "schemaVersion": 1,
        "artifactKind": "doe_31b_real_weight_smoke_extraction_preflight",
        "purpose": (
            "Records the architectural mismatch between the E2B smoke "
            "contract and Gemma 4 31B safetensors. The smoke contract "
            "expects per_layer_projection.weight + self_attn.v_proj.weight "
            "per layer; 31B has neither for all layers. The preflight "
            "names the decisions a Doe operator must make to proceed."
        ),
        "extractorState": {
            "tool": "bench/tools/extract_gemma4_31b_weight_slices.py",
            "verdict": "gemma4_31b_smoke_contract_failed",
            "verdictPath": str(
                args.source_verdict.relative_to(REPO_ROOT)
                if args.source_verdict.is_absolute()
                and str(args.source_verdict).startswith(str(REPO_ROOT))
                else args.source_verdict
            ),
            "failureSamples": source_failures[:20],
        },
        "architecturalMismatch": {
            "missingTensorClass1": {
                "name": "per_layer_projection.weight",
                "presentInE2B": True,
                "presentIn31B": False,
                "reason": (
                    "Gemma 4 E2B's per-layer projection is a learned "
                    "tensor (used by the E2B-specific per-layer scalar "
                    "enrichment path). Gemma 4 31B does not have this "
                    "learned tensor — the 31B architecture omits the "
                    "per-layer projection entirely."
                ),
            },
            "missingTensorClass2": {
                "name": "self_attn.v_proj.weight",
                "presentIn31BForAllLayers": False,
                "missingFromLayers": "subset (sliding-window / linear-attention layers)",
                "reason": (
                    "A subset of Gemma 4 31B layers use linear attention "
                    "or a sliding-window variant that does not produce a "
                    "v_proj tensor. The exact layer list is captured in "
                    "the failure list of the source verdict."
                ),
            },
        },
        "operatorDecisionsRequired": [
            {
                "decision": "per_layer_projection_substitute",
                "options": [
                    "pre_feedforward_layernorm.weight (per-layer scalar)",
                    "post_feedforward_layernorm.weight (per-layer scalar)",
                    "input_layernorm.weight (per-layer scalar)",
                    "explicit zero pad (substitute=null, write 4096 zero bytes)",
                    "delete the projection file from the smoke contract entirely (audit code change)",
                ],
                "decisionFraming": (
                    "The smoke contract uses the projection file as a "
                    "1024-float per-layer slice. Any per-layer scalar "
                    "tensor of suitable size can substitute since smoke "
                    "shape is structural (not numerical) — but the choice "
                    "must be explicit and deterministic."
                ),
            },
            {
                "decision": "linear_attention_layer_handling",
                "options": [
                    "skip the v_proj concat for linear-attention layers; record per-layer kv_layout in the smoke metadata",
                    "duplicate k_proj into the v_proj slot (zero numerical meaning, structural fill)",
                    "explicitly fail the smoke audit for linear-attention layers (audit accepts a partial layer set)",
                ],
                "decisionFraming": (
                    "The Gemma 4 31B HostPlan separates kv_write (full "
                    "attention) from kv_write_shared (linear attention). "
                    "Smoke shape currently assumes uniform layers; the "
                    "extractor needs the same heterogeneity awareness."
                ),
            },
        ],
        "blocker": {
            "class": "model_architectural_mapping_decision_unmade",
            "detail": (
                "Both decisions above are model-architectural choices. "
                "Doe cannot make them unilaterally because they affect "
                "what the smoke audit's parity verdict means — a "
                "per-layer-scalar substitute is structurally OK at smoke "
                "scale, but only if reviewers know which substitute was "
                "used. Once the choice is made, the extractor accepts "
                "--projection-substitute-tensor and "
                "--linear-attention-policy CLI flags."
            ),
            "namedRunnerExtensions": [
                "bench/tools/extract_gemma4_31b_weight_slices.py: add "
                "--projection-substitute-tensor flag (default 'fail') "
                "and --linear-attention-policy flag (default 'fail') so "
                "the operator's choice is explicit at extraction time.",
                "config/gemma-4-31b-real-weight-fixture.json: add "
                "weightsDir.smokeContract.{projectionSubstituteTensor, "
                "linearAttentionPolicy} so the audit verdict cites the "
                "explicit choice.",
                "bench/tools/validate_weights_dir.py: read the new "
                "smokeContract fields and accept layered audits where "
                "linear-attention layers are explicitly partial.",
            ],
        },
        "claim": {
            "scope": (
                "Architectural mismatch between E2B smoke contract and "
                "31B safetensors is precisely named. Two operator "
                "decisions are surfaced with concrete option lists."
            ),
            "notWhat": (
                "Not an extraction. Not a parity verdict flip. Not a "
                "decision — both architectural choices remain unmade by "
                "design; this preflight is reviewer-facing context for "
                "the operator who owns 31B weight extraction."
            ),
            "summary": (
                "31B smoke extraction blocked on two model-architectural "
                "decisions; both options are listed."
            ),
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {args.out} (2 named decisions, "
        f"{len(source_failures)} extractor failures captured)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
