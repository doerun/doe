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
GOVERNED_LANE_ROOT = REPO_ROOT / "bench/out/dual-compile-evidence/governed-lane-sdk-handoff"


# Pattern → governed-lane sim-success dir (relative to GOVERNED_LANE_ROOT).
# Only patterns with an existing governed-lane receipt — dormant and
# audit-blocked patterns will leave observedFixtureEvidence null.
OBSERVED_FIXTURE_DIRS: dict[str, str] = {
    "gather":              "sim-success-gather",
    "element_wise":        "sim-success-elementwise-double",
    "reduction":           "sim-success-reduce-sum-workgroup",
    "rope":                "sim-success-rope",
    "tiled_matmul":        "sim-success-tiled-matmul",
    "attention_tiled":     "sim-success-attention-tiled",
    "attention_decode":    "sim-success-attention-decode",
    "attention_linear":    "sim-success-attention-linear",
    "sample":              "sim-success-sample",
    "fused_gemv_dequant":  "sim-success-fused-gemv-dequant",
    "kv_write":            "sim-success-kv-write",
    "dequant":             "sim-success-dequant",
}


def parse_cslc_params(cmd_list: list[str]) -> str | None:
    for tok in cmd_list or []:
        if tok.startswith("--params="):
            return tok[len("--params="):]
    return None


def load_observed_evidence(pattern: str) -> dict | None:
    """Return observed governed-lane evidence for a pattern, or None."""
    sub = OBSERVED_FIXTURE_DIRS.get(pattern)
    if not sub:
        return None
    fixture_dir = GOVERNED_LANE_ROOT / sub
    driver_path = fixture_dir / "driver-result.json"
    trace_path = fixture_dir / "trace.json"
    if not driver_path.exists():
        return None
    dr = json.loads(driver_path.read_text())
    compile_targets = dr.get("compile", {}).get("targets") or []
    compile_cmd = compile_targets[0].get("command") if compile_targets else []
    observed_params = parse_cslc_params(compile_cmd)
    run_status = dr.get("run", {}).get("status", "unknown")
    compile_status = dr.get("compile", {}).get("status", "unknown")
    out = {
        "fixtureDir": str(fixture_dir.relative_to(REPO_ROOT)),
        "driverResultPath": str(driver_path.relative_to(REPO_ROOT)),
        "driverResultSha256": sha256(driver_path),
        "observedCslcParamsString": observed_params,
        "compileStatus": compile_status,
        "runStatus": run_status,
    }
    if trace_path.exists():
        out["tracePath"] = str(trace_path.relative_to(REPO_ROOT))
        out["traceSha256"] = sha256(trace_path)
        trace_data = json.loads(trace_path.read_text())
        for k in ("width", "chunkSize", "totalElements", "runtimePassed", "runtimeMaxAbsErr"):
            if k in trace_data:
                out[k] = trace_data[k]
        # Quantitative observed bytes/cycles from trace dims. totalElements
        # counts across all PEs; divide by width for per-PE. f32 baseline
        # matches the predicted model. cycles are not in trace.json — leave
        # observedCyclesPerPe null until the simulator's cycle counts land.
        te = trace_data.get("totalElements")
        w = trace_data.get("width")
        if isinstance(te, int) and isinstance(w, int) and w > 0:
            els = te // w
            out["observedElementsPerPe"] = els
            out["observedBytesPerPe"] = els * 4
        else:
            out["observedElementsPerPe"] = None
            out["observedBytesPerPe"] = None
        out["observedCyclesPerPe"] = None  # not carried by trace.json today
    return out


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
        # Single-PE-per-token mode (emit_csl_reduction.zig): each PE sums
        # hidden_size f32 values for one token. Prior formula returned 1
        # per PE and underpredicted observed by ~1000x for the E2B
        # hiddenDim=1536 case — divergence ratio fed back and this
        # correction uses hidden_size from the carried paramsShape.
        return int(p.get("hidden_size", 1))
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

        # Bind observed governed-lane evidence (existing) so each
        # pattern carries a predicted-vs-observed pair where available.
        observed_fixture = load_observed_evidence(pattern)
        predicted_cslc = (
            invocations[0].get("cslcParamsString") if invocations else
            entry.get("cslcParamsString", "")
        )
        shape_match = None
        if observed_fixture and observed_fixture.get("observedCslcParamsString"):
            shape_match = (
                predicted_cslc == observed_fixture["observedCslcParamsString"]
            )

        # Quantitative predicted-vs-observed ratio — null when observed
        # bytes aren't available.
        observed_bytes = (observed_fixture or {}).get("observedBytesPerPe")
        predicted_to_observed_bytes_ratio = None
        if observed_bytes and pattern_bytes and observed_bytes > 0:
            predicted_to_observed_bytes_ratio = round(pattern_bytes / observed_bytes, 4)

        # Classification of the divergence. Separates smoke-vs-deployment
        # shape gaps (expected, non-actionable today) from formula
        # mismatches (actionable — the prediction model disagrees with
        # the observed evidence at the fixture's own shape).
        divergence_classification: str | None = None
        width_ratio_hint: float | None = None
        if predicted_to_observed_bytes_ratio is not None:
            r = predicted_to_observed_bytes_ratio
            if 0.9 <= r <= 1.1:
                divergence_classification = "exact_match"
            elif r > 1.1:
                divergence_classification = "expected_shape_divergence"
            else:
                divergence_classification = "unexpected_divergence_formula_suspect"
            # Width-ratio hint: the fixture usually runs at width:4 while
            # the predicted uses the --size arg. A ratio that matches
            # (predicted_width / observed_width)^k for small k is
            # consistent with pure shape scaling. Record the raw width
            # ratio so downstream consumers can spot-check.
            pred_width = (invocations[0].get("paramsShape", {}).get("width") if invocations else None) or 0
            obs_width = (observed_fixture or {}).get("width") or 0
            if pred_width and obs_width:
                width_ratio_hint = round(pred_width / obs_width, 4)

        pattern_entry = {
            "pattern": pattern,
            "status": status,
            "invocationCount": len(invocations),
            "bytesPerPe": pattern_bytes,
            "cyclesPerPe": pattern_cycles,
            "invocations": inv_predictions,
            "predictedCslcParamsString": predicted_cslc,
            "observedFixtureEvidence": observed_fixture,
            "predictedMatchesObservedShape": shape_match,
            "observedBytesPerPe": observed_bytes,
            "observedCyclesPerPe": (observed_fixture or {}).get("observedCyclesPerPe"),
            "predictedToObservedBytesRatio": predicted_to_observed_bytes_ratio,
            "divergenceClassification": divergence_classification,
            "widthRatioHint": width_ratio_hint,
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
            # Divergence rollup — how many patterns have observed bytes
            # bound, how many match predicted shape exactly, how many
            # have non-null ratio. A non-null ratio != 1 is the signal
            # "this pattern's shape at deployment doesn't match the
            # smoke fixture run; expect divergence when step-3 real
            # traces land".
            "observedEvidenceBoundCount": sum(
                1 for p in per_pattern
                if p.get("observedFixtureEvidence") is not None
            ),
            "predictedMatchesObservedShapeCount": sum(
                1 for p in per_pattern
                if p.get("predictedMatchesObservedShape") is True
            ),
            "predictedToObservedBytesRatioSamples": [
                {"pattern": p["pattern"], "ratio": p["predictedToObservedBytesRatio"]}
                for p in per_pattern
                if p.get("predictedToObservedBytesRatio") is not None
            ],
            "divergenceClassificationTally": {
                cls: sum(1 for p in per_pattern if p.get("divergenceClassification") == cls)
                for cls in (
                    "exact_match",
                    "expected_shape_divergence",
                    "unexpected_divergence_formula_suspect",
                )
            },
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
