#!/usr/bin/env python3
"""Per-stream buffer-size recommender (SdkLayout hardening gap 4 residual).

For each stream in a Gemma-4 execution plan, computes:
  - current:  next_power_of_two(max(1024, payloadBytes)) — the floor-
    based sizing the generator uses today
  - recommended:  next_power_of_two(max(payloadBytes, 1)) — the
    payload-derived minimum, no 1024 floor
  - overallocationRatio: current / payloadBytes
  - savedBytesIfRecommended: current - recommended (per stream)

Emits `doe_stream_buffer_size_recommendation`. Evidence only; runner
behavior is unchanged until SdkLayout exposes backpressure/queue-depth
telemetry that confirms these minimums are safe at run time.

Usage:
  python3 bench/tools/recommend_stream_buffer_sizes.py \\
    --plan bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json \\
    --out-json bench/out/e2b-full-graph/stream-buffer-size-recommendation.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--plan", required=True,
        help="Path to a Gemma-4 stream execution plan JSON.",
    )
    p.add_argument(
        "--out-json", default="",
        help="Optional path for the machine-readable recommendation artifact.",
    )
    return p.parse_args()


def resolve(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def next_power_of_two(n: int) -> int:
    if n <= 1:
        return 1
    return 1 << (n - 1).bit_length()


def current_buffer_size(payload_bytes: int) -> int:
    return next_power_of_two(max(1024, payload_bytes))


def recommended_buffer_size(payload_bytes: int) -> int:
    return next_power_of_two(max(payload_bytes, 1))


def main() -> int:
    args = parse_args()
    plan_path = resolve(args.plan)
    if not plan_path.is_file():
        print(f"FAIL: plan not found: {args.plan}")
        return 1

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    schedule = plan.get("perLayerSchedule") or []
    if not schedule:
        print("FAIL: plan has no perLayerSchedule")
        return 1

    # Group payloads by streamId. In practice payloadBytes are fixed
    # per stream across layers for Gemma-4 layer-block plans; confirm
    # that and flag any variance so recommendations remain honest.
    stream_payload_samples: dict[str, list[int]] = defaultdict(list)
    for layer in schedule:
        for stream in layer.get("streams") or []:
            sid = stream.get("streamId")
            pb = stream.get("payloadBytes")
            if sid and isinstance(pb, int):
                stream_payload_samples[sid].append(pb)

    per_stream_records = []
    current_total = 0
    recommended_total = 0
    for sid, samples in sorted(stream_payload_samples.items()):
        distinct = sorted(set(samples))
        max_payload = max(samples)
        current = current_buffer_size(max_payload)
        recommended = recommended_buffer_size(max_payload)
        current_total += current
        recommended_total += recommended
        per_stream_records.append({
            "streamId": sid,
            "payloadBytesMax": max_payload,
            "payloadBytesDistinct": distinct,
            "layerCount": len(samples),
            "currentBufferBytes": current,
            "recommendedBufferBytes": recommended,
            "overallocationRatio": (
                current / max_payload if max_payload > 0 else None
            ),
            "savedBytesIfRecommended": current - recommended,
        })

    verdict = {
        "schemaVersion": 1,
        "artifactKind": "doe_stream_buffer_size_recommendation",
        "modelId": plan.get("modelId"),
        "target": plan.get("target"),
        "planPath": rel(plan_path),
        "numLayers": len(schedule),
        "currentFormula": "next_power_of_two(max(1024, payloadBytes))",
        "recommendedFormula": "next_power_of_two(max(payloadBytes, 1))",
        "perStream": per_stream_records,
        "totals": {
            "currentBufferBytesSum": current_total,
            "recommendedBufferBytesSum": recommended_total,
            "savedBytesIfRecommendedSum": current_total - recommended_total,
        },
        "runtimeImpact": (
            "Recommendation is evidence-only. Runtime behavior is unchanged "
            "until SdkLayout exposes backpressure and queue-depth telemetry "
            "that confirms these minimums are safe; see R3-2 in "
            "docs/cerebras-model-ledgers.md."
        ),
    }

    if args.out_json:
        out_path = resolve(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {rel(out_path)}")

    print(
        f"streams={len(per_stream_records)}, "
        f"current_total={current_total}B, "
        f"recommended_total={recommended_total}B, "
        f"savings_if_recommended={current_total - recommended_total}B"
    )
    for r in per_stream_records:
        print(
            f"  {r['streamId']}: payload={r['payloadBytesMax']}B "
            f"current={r['currentBufferBytes']}B "
            f"recommended={r['recommendedBufferBytes']}B "
            f"saved={r['savedBytesIfRecommended']}B "
            f"(ratio {r['overallocationRatio']:.1f}x)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
