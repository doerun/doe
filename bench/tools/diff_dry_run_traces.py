#!/usr/bin/env python3
"""Diff two doe_streaming_executor_dry_run_trace artifacts.

Use cases:
  1. Predicted-vs-hardware: future hardware-observed trace vs the Python
     dry-run. Substitute the hardware-observed bandwidth constant into
     the dry-run first and rerun, then diff — residual gaps point at
     real-runtime inefficiencies rather than model mismatch.
  2. A/B config comparison: two dry-runs with different
     prefetchSchedule / kvPolicy / bandwidth settings, to reason about
     what the streaming executor should pick.
  3. Scale comparison: E2B vs 31B as a sanity check that the plan chain
     scales correctly across models.

Emits a doe_dry_run_trace_diff artifact: schema-validated JSON with
per-field deltas + a list of per-layer deltas.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--left", required=True, help="Path to the baseline trace")
    p.add_argument("--right", required=True, help="Path to the comparison trace")
    p.add_argument("--out-json", required=True)
    p.add_argument(
        "--label-left",
        default="left",
        help="Short identifier for the baseline side (shows up in the diff artifact)",
    )
    p.add_argument("--label-right", default="right")
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def numeric_delta(left: Any, right: Any) -> dict[str, Any]:
    """For numeric fields, emit left / right / delta / pctChange."""
    try:
        l = float(left)
        r = float(right)
    except (TypeError, ValueError):
        return {"left": left, "right": right, "match": left == right}
    delta = r - l
    pct = ((r - l) / l * 100.0) if l != 0 else None
    return {
        "left": l,
        "right": r,
        "delta": delta,
        "pctChange": pct,
        "match": delta == 0.0,
    }


def main() -> int:
    args = parse_args()
    left = load_json(resolve(args.left))
    right = load_json(resolve(args.right))

    def dotted(trace: dict, *keys: str) -> Any:
        d = trace
        for k in keys:
            if not isinstance(d, dict) or k not in d:
                return None
            d = d[k]
        return d

    per_pe_fields = [
        "sramBudget",
        "persistentBytes",
        "ringBufferOccupancyLayers",
        "ringBufferOccupancyBytes",
        "setupBytes",
        "perLayerBytes",
        "prefetchOverlapBytes",
    ]
    agg_fields = [
        "numTransformerLayers",
        "totalBytesTransferredPerPe",
        "totalLatencyCyclesPerPe",
        "perLayerLatencyCyclesPerPe",
    ]

    per_pe_delta = {
        f: numeric_delta(dotted(left, "perPe", f), dotted(right, "perPe", f))
        for f in per_pe_fields
    }
    per_pe_delta["fitsInPerPeSramBudget"] = {
        "left": dotted(left, "perPe", "fitsInPerPeSramBudget"),
        "right": dotted(right, "perPe", "fitsInPerPeSramBudget"),
        "match": dotted(left, "perPe", "fitsInPerPeSramBudget")
                 == dotted(right, "perPe", "fitsInPerPeSramBudget"),
    }
    agg_delta = {
        f: numeric_delta(dotted(left, "aggregate", f), dotted(right, "aggregate", f))
        for f in agg_fields
    }

    # Per-layer deltas (up to the shorter schedule; mismatched layer
    # counts are flagged explicitly).
    left_sched = left.get("perLayerSchedule", [])
    right_sched = right.get("perLayerSchedule", [])
    layer_count_match = len(left_sched) == len(right_sched)
    layer_deltas = []
    for l_step, r_step in zip(left_sched, right_sched):
        layer_deltas.append({
            "layerIndex": l_step.get("layerIndex"),
            "payloadBytes": numeric_delta(l_step.get("payloadBytes"), r_step.get("payloadBytes")),
            "latencyCycles": numeric_delta(l_step.get("latencyCycles"), r_step.get("latencyCycles")),
            "prefetchTargetLayer": numeric_delta(
                l_step.get("prefetchTargetLayer"), r_step.get("prefetchTargetLayer"),
            ),
        })

    match_fields = (
        list(per_pe_delta.values())
        + list(agg_delta.values())
        + [step["payloadBytes"] for step in layer_deltas]
        + [step["latencyCycles"] for step in layer_deltas]
    )
    all_match = layer_count_match and all(
        (isinstance(m, dict) and m.get("match", False)) for m in match_fields
    )

    diff = {
        "schemaVersion": 1,
        "artifactKind": "doe_dry_run_trace_diff",
        "target": "wse3",
        "sides": {
            "left": {
                "label": args.label_left,
                "tracePath": rel(resolve(args.left)),
                "modelId": left.get("modelId", ""),
                "assumedBandwidthBytesPerCycle": left.get("assumedBandwidthBytesPerCycle"),
            },
            "right": {
                "label": args.label_right,
                "tracePath": rel(resolve(args.right)),
                "modelId": right.get("modelId", ""),
                "assumedBandwidthBytesPerCycle": right.get("assumedBandwidthBytesPerCycle"),
            },
        },
        "perPe": per_pe_delta,
        "aggregate": agg_delta,
        "layerCountMatch": layer_count_match,
        "perLayer": layer_deltas,
        "allMatch": all_match,
    }

    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(diff, indent=2) + "\n", encoding="utf-8")

    agg_bytes = diff["aggregate"]["totalBytesTransferredPerPe"]
    agg_cycles = diff["aggregate"]["totalLatencyCyclesPerPe"]
    print(
        f"dry-run diff: {args.label_left} vs {args.label_right} — "
        f"bytes Δ={agg_bytes.get('delta')!s} "
        f"({agg_bytes.get('pctChange')}), "
        f"cycles Δ={agg_cycles.get('delta')!s}, "
        f"allMatch={all_match} → {rel(out_path)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
