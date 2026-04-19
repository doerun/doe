#!/usr/bin/env python3
"""Derive a predicted per-pattern cycle/byte footprint for one E2B layer block.

Reads bench/out/streaming-executor/e2b-layer-block-smoke-trace.json's
layerBlockSmoke.perKernelShapes (14 patterns × invocations) and
computes a naive footprint prediction per invocation. The aggregate
per-layer + whole-model predictions are the baseline for predicted-
vs-observed diffs once plan Build-order step 3 (E2B simulator
execution) lands a real simulator trace.

Derivation is intentionally naive — the diff's useful signal is
*where observed diverges from predicted*, not precision of the
predictions. Prediction model:

  elementsPerPe       = product of per-invocation dims, per pattern
                        (e.g. gather: num_tokens * hidden_size * rows_per_pe)
  bytesPerPe          = elementsPerPe * 4   (f32)
  cyclesPerPe         = elementsPerPe       (1 op / element baseline)
  bytesPerLayer       = bytesPerPe * invocation.widthPEs
  cyclesPerLayer      = cyclesPerPe           (single-pass; parallelism
                                               is captured in width)
  bytesPerModel       = bytesPerLayer * numLayers
  cyclesPerModel      = cyclesPerLayer * numLayers

Skips invocations marked dormant_pattern_no_manifest_step so the
model total reflects what actually runs. audit_needs_deployment_generator
invocations are included but flagged so the dashboard can mark them
as "predicted under smoke assumptions".

Output: bench/out/layer-block-predicted-footprint/e2b-predicted-footprint.json
Schema: config/doe-layer-block-predicted-footprint.schema.json
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TRACE = REPO_ROOT / "bench/out/streaming-executor/e2b-layer-block-smoke-trace.json"
MANIFEST = REPO_ROOT / "runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json"
OUT = REPO_ROOT / "bench/out/layer-block-predicted-footprint/e2b-predicted-footprint.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def elements_per_pe(pattern: str, params: dict) -> int:
    """Naive element-count estimate from an invocation's paramsShape."""
    p = params or {}
    if pattern == "gather":
        return int(p.get("num_tokens", 0)) * int(p.get("hidden_size", 0)) * int(p.get("rows_per_pe", 1))
    if pattern == "rope":
        return int(p.get("head_dim", 0)) * int(p.get("num_pairs", 1))
    if pattern == "reduction":
        # single-PE-per-token; hidden reduction = hiddenDim ops.
        return 1
    if pattern == "tiled_matmul":
        return int(p.get("Mt", 0)) * int(p.get("Kt", 0)) * int(p.get("Nt", 0))
    if pattern in ("attention_tiled",):
        return int(p.get("head_dim", 0)) * int(p.get("kv_len", 0)) * int(p.get("q_len", 1))
    if pattern == "attention_decode":
        return int(p.get("head_dim", 0)) * int(p.get("kv_chunk", 0))
    if pattern in ("attention_streaming", "attention_linear"):
        return int(p.get("head_dim", 0)) * int(p.get("kv_len", 0))
    if pattern == "kv_write":
        return int(p.get("head_dim", 0)) * int(p.get("max_seq_len", 0))
    if pattern == "kv_read":
        return int(p.get("head_dim", 0)) * int(p.get("read_len", 0))
    if pattern == "sample":
        return int(p.get("chunk_size", 0))
    if pattern == "fused_gemv_dequant":
        return int(p.get("out_dim", 0)) * int(p.get("in_dim_per_pe", 1))
    if pattern == "fused_ffn":
        return int(p.get("in_per_pe", 1)) * int(p.get("out_dim", 0))
    if pattern == "dequant":
        return int(p.get("num_blocks", 1)) * 32  # Q4K block = 32 elements
    return 0


def main() -> int:
    trace = json.loads(TRACE.read_text())
    manifest = json.loads(MANIFEST.read_text())
    smoke = trace.get("layerBlockSmoke", {})
    shapes = smoke.get("perKernelShapes") or []
    num_layers = int(manifest.get("modelConfig", {}).get("numLayers", 0))
    num_pes_smoke = int(trace.get("region", {}).get("peCount", 1))  # the stub kernel's peCount

    F32 = 4
    total_bytes_per_layer = 0
    total_cycles_per_layer = 0
    per_pattern = []
    for entry in shapes:
        pattern = entry.get("pattern", "")
        status = entry.get("status")
        invocations = entry.get("invocations") or []
        if not invocations and "paramsShape" in entry:
            # Back-compat for patterns that don't use invocations[].
            invocations = [{
                "stepName": entry.get("manifestSteps", ["(single)"])[0] if entry.get("manifestSteps") else "(single)",
                "paramsShape": entry["paramsShape"],
                "cslcParamsString": entry.get("cslcParamsString", ""),
            }]

        inv_predictions = []
        pattern_bytes = 0
        pattern_cycles = 0
        for inv in invocations:
            params = inv.get("paramsShape", {})
            els = elements_per_pe(pattern, params)
            bytes_per_pe = els * F32
            cycles_per_pe = els
            pattern_bytes += bytes_per_pe
            pattern_cycles += cycles_per_pe
            inv_predictions.append({
                "stepName": inv.get("stepName", "(unknown)"),
                "elementsPerPe": els,
                "bytesPerPe": bytes_per_pe,
                "cyclesPerPe": cycles_per_pe,
            })

        pattern_entry = {
            "pattern": pattern,
            "status": status,
            "invocationCount": len(invocations),
            "bytesPerPe": pattern_bytes,
            "cyclesPerPe": pattern_cycles,
            "invocations": inv_predictions,
        }
        per_pattern.append(pattern_entry)
        if status == "dormant_pattern_no_manifest_step":
            continue
        # Even audit-blocked patterns contribute to the baseline — the
        # dashboard can subtract them if needed.
        total_bytes_per_layer += pattern_bytes
        total_cycles_per_layer += pattern_cycles

    artifact = {
        "schemaVersion": 1,
        "artifactKind": "doe_layer_block_predicted_footprint",
        "generatedFrom": {
            "tracePath": str(TRACE.relative_to(REPO_ROOT)),
            "traceSha256": sha256(TRACE),
            "manifestPath": str(MANIFEST.relative_to(REPO_ROOT)),
            "manifestSha256": sha256(MANIFEST),
        },
        "modelId": trace.get("modelId", ""),
        "numLayers": num_layers,
        "predictionModel": {
            "name": "naive_elements_times_one_cycle_and_f32_bytes",
            "dtypeBytes": F32,
            "cyclesPerElement": 1,
            "notes": (
                "Baseline for predicted-vs-observed diffs. Predictions are "
                "deliberately coarse so divergence from observed simulator "
                "traces carries signal. elementsPerPe is a per-pattern formula "
                "from paramsShape (see derive_layer_block_predicted_footprint.py)."
            ),
        },
        "perPattern": per_pattern,
        "aggregate": {
            "bytesPerLayerPerPe": total_bytes_per_layer,
            "cyclesPerLayerPerPe": total_cycles_per_layer,
            "bytesPerModelPerPe": total_bytes_per_layer * num_layers,
            "cyclesPerModelPerPe": total_cycles_per_layer * num_layers,
            "activePatternCount": sum(
                1 for p in per_pattern
                if p["status"] != "dormant_pattern_no_manifest_step"
            ),
            "dormantPatternCount": sum(
                1 for p in per_pattern
                if p["status"] == "dormant_pattern_no_manifest_step"
            ),
        },
        "notes": (
            "Derived from layerBlockSmoke.perKernelShapes in the E2B layer-"
            "block smoke trace. Dormant patterns (status=dormant_pattern_no_"
            "manifest_step) are excluded from aggregate totals — they don't "
            "run in the current model graph. audit_needs_deployment_generator "
            "entries are included at smoke shapes; real deployment widths "
            "from the step-1 execution-plan generator will shift those numbers "
            "once landed."
        ),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(artifact, indent=2) + "\n")
    ag = artifact["aggregate"]
    print(
        f"predicted footprint: {ag['activePatternCount']} active + "
        f"{ag['dormantPatternCount']} dormant patterns; "
        f"{ag['bytesPerLayerPerPe']:,} bytes/layer/PE × {num_layers} layers = "
        f"{ag['bytesPerModelPerPe']:,} bytes/PE -> "
        f"{OUT.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
