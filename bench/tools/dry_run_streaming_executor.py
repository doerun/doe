#!/usr/bin/env python3
"""Streaming-executor dry-run simulator.

Consumes a doe_stream_execution_plan.json and a doe_model_runtime_receipt
(for the memory-plan link) and produces a predicted-runtime trace that
mirrors what the eventual SdkLayout streaming executor will emit at
real runtime. The trace artifact is deterministic + schema-validated so
future real hardware traces can be diff'd against it.

What the dry-run computes (all per-PE):
  - bytesTransferredSetup: sum of one-shot setup streams
  - bytesTransferredPerLayer: sum of per-layer stream payloads
  - bytesTransferredTotal: setup + per-layer * numLayers
  - ringBufferOccupancy: max simultaneous outstanding prefetch layers
    given the policy's lookaheadLayers
  - prefetchOverlapBytes: how much of the next-layer payload fits in
    parallel with current compute (bounded by ring-buffer depth)
  - fitsInPerPeSramBudget: whether persistent + max(lookahead * per_layer)
    fits under the memory-plan's SRAM budget per PE
  - estimatedLayerLatencyCycles: payload_bytes / assumed_bandwidth_bpcy
    (pure model — the constant is explicit in the receipt so future
    hardware comparison can substitute the observed constant)

No SDK. No simulator. Pure arithmetic over the plan shape.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

# Bandwidth constant is explicit in the trace so future hardware
# comparison can substitute observed bytes-per-cycle and rerun the
# dry-run for a "predicted vs actual" diff. WSE-3 memcpy bandwidth per
# PE is a placeholder — swap when a measured number lands.
DEFAULT_ASSUMED_BANDWIDTH_BPCY = 4.0  # 4 bytes/cycle per-PE (placeholder)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--execution-plan", required=True)
    p.add_argument("--model-receipt", required=True)
    p.add_argument("--out-json", required=True)
    p.add_argument(
        "--assumed-bandwidth-bpcy",
        type=float,
        default=DEFAULT_ASSUMED_BANDWIDTH_BPCY,
        help="Assumed per-PE bandwidth in bytes/cycle. Emitted verbatim so a future hardware-observed value can substitute.",
    )
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(p.resolve())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    plan_path = resolve(args.execution_plan)
    receipt_path = resolve(args.model_receipt)
    plan = load_json(plan_path)
    receipt = load_json(receipt_path)

    setup_bytes = sum(
        int(s.get("payloadBytes", 0))
        for layer in [plan["setupPhase"]]
        for s in layer
        if "payloadBytes" in s
    )
    # The setup phase in the current emitter only names streamId + source;
    # the actual payloadBytes live in the stream-graph. Cross-reference.
    stream_graph_path = None
    if "source" in plan:
        stream_graph_path = plan["source"].get("streamGraphPath")
    stream_payload: dict[str, int] = {}
    if stream_graph_path:
        sg_path = resolve(stream_graph_path)
        if sg_path.exists():
            sg = load_json(sg_path)
            for s in sg.get("streams", []):
                stream_payload[s["streamId"]] = int(s.get("payloadBytes", 0))
    # Backfill setup bytes using stream-graph lookup.
    setup_bytes = sum(
        stream_payload.get(s["streamId"], 0)
        for s in plan["setupPhase"]
    )

    per_layer_schedule = plan["perLayerSchedule"]
    num_layers = int(plan["numTransformerLayers"])
    per_layer_bytes = int(plan.get("steadyStatePayloadBytesPerLayer", 0))

    prefetch = plan.get("prefetchPolicy", {})
    lookahead = int(prefetch.get("lookaheadLayers", 1))

    # Ring-buffer occupancy: under a lookahead of L, at steady state we
    # hold up to L+1 layer payloads (current compute + L prefetched).
    ring_occupancy_layers = lookahead + 1
    ring_occupancy_bytes_per_pe = ring_occupancy_layers * per_layer_bytes

    per_pe_sram = receipt["streamingMigration"].get("perPeSramBudget", 0)
    persistent_bpp = receipt["streamingMigration"].get("persistentBytesPerPe", 0)
    fits_budget = (persistent_bpp + ring_occupancy_bytes_per_pe) <= per_pe_sram

    # Per-layer latency estimate. Compute-bound vs bandwidth-bound is
    # future work; for now, assume bandwidth-bound on data transfer.
    bandwidth = max(args.assumed_bandwidth_bpcy, 1e-6)
    per_layer_latency_cycles = per_layer_bytes / bandwidth
    total_bytes = setup_bytes + num_layers * per_layer_bytes
    total_latency_cycles = setup_bytes / bandwidth + num_layers * per_layer_latency_cycles

    # prefetchOverlapBytes: the bytes that can overlap next-layer
    # prefetch with current-layer compute, bounded by ring-buffer slots.
    prefetch_overlap_bytes = min(per_layer_bytes, (lookahead) * per_layer_bytes)

    trace = {
        "schemaVersion": 1,
        "artifactKind": "doe_streaming_executor_dry_run_trace",
        "target": "wse3",
        "modelId": plan.get("modelId", ""),
        "sourcePlan": {
            "executionPlanPath": rel(plan_path),
            "modelReceiptPath": rel(receipt_path),
            "streamGraphPath": stream_graph_path or "",
        },
        "executorStatus": plan.get("executorStatus", "plan_only"),
        "assumedBandwidthBytesPerCycle": args.assumed_bandwidth_bpcy,
        "perPe": {
            "sramBudget": int(per_pe_sram),
            "persistentBytes": int(persistent_bpp),
            "ringBufferOccupancyLayers": ring_occupancy_layers,
            "ringBufferOccupancyBytes": ring_occupancy_bytes_per_pe,
            "fitsInPerPeSramBudget": fits_budget,
            "setupBytes": setup_bytes,
            "perLayerBytes": per_layer_bytes,
            "prefetchOverlapBytes": prefetch_overlap_bytes,
        },
        "aggregate": {
            "numTransformerLayers": num_layers,
            "totalBytesTransferredPerPe": total_bytes,
            "totalLatencyCyclesPerPe": total_latency_cycles,
            "perLayerLatencyCyclesPerPe": per_layer_latency_cycles,
        },
        "perLayerSchedule": [
            {
                "layerIndex": step["layerIndex"],
                "prefetchTargetLayer": step["prefetchTargetLayer"],
                "payloadBytes": sum(int(s.get("payloadBytes", 0)) for s in step.get("streams", [])),
                "latencyCycles": sum(int(s.get("payloadBytes", 0)) for s in step.get("streams", [])) / bandwidth,
            }
            for step in per_layer_schedule
        ],
        "notes": (
            "Predicted trace from the Python dry-run executor. Not a hardware "
            "trace. The assumed bandwidth is a placeholder; future hardware "
            "runs should emit an observed bandwidth and this dry-run should be "
            "re-run with --assumed-bandwidth-bpcy=<observed> so the comparison "
            "is apples-to-apples on trace shape rather than constant choice."
        ),
    }

    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    status = "fits" if fits_budget else "OVERFLOW"
    print(
        f"dry-run: {num_layers} layers, "
        f"{total_bytes} bytes/PE, ringOccupancy={ring_occupancy_layers}L × "
        f"{per_layer_bytes}B = {ring_occupancy_bytes_per_pe}B ({status}) "
        f"→ {rel(out_path)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
