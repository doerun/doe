#!/usr/bin/env python3
"""Generate config/backend-lane-map.json from backend-runtime-policy lanes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


BACKEND_IDS = ("dawn_delegate", "doe_metal", "doe_vulkan", "doe_d3d12")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--policy",
        default="config/backend-runtime-policy.json",
        help="Runtime policy path used as source for lane mapping.",
    )
    parser.add_argument(
        "--out",
        default="config/backend-lane-map.json",
        help="Output lane map artifact path.",
    )
    return parser.parse_args()


def load_policy(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid runtime policy object: {path}")
    lanes = payload.get("lanes")
    if not isinstance(lanes, dict):
        raise ValueError(f"invalid runtime policy lanes object: {path}")
    return payload


def build_lane_map(policy: dict[str, Any], source_policy_path: str) -> dict[str, Any]:
    lanes = policy["lanes"]
    lane_to_backend: dict[str, str] = {}
    backend_to_lanes: dict[str, list[str]] = {backend_id: [] for backend_id in BACKEND_IDS}

    for lane_name in sorted(lanes.keys()):
        lane_payload = lanes[lane_name]
        if not isinstance(lane_payload, dict):
            raise ValueError(f"lane payload is not an object: {lane_name}")
        backend_name = lane_payload.get("defaultBackend")
        if not isinstance(backend_name, str):
            raise ValueError(f"lane defaultBackend must be string: {lane_name}")
        if backend_name not in backend_to_lanes:
            raise ValueError(f"unknown backend in lane policy: {lane_name} -> {backend_name}")
        lane_to_backend[lane_name] = backend_name
        backend_to_lanes[backend_name].append(lane_name)

    return {
        "schemaVersion": 1,
        "sourcePolicyPath": source_policy_path,
        "laneToBackend": lane_to_backend,
        "backendToLanes": backend_to_lanes,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    path.write_text(rendered, encoding="utf-8")


def main() -> int:
    args = parse_args()
    policy_path = Path(args.policy)
    output_path = Path(args.out)

    policy = load_policy(policy_path)
    lane_map = build_lane_map(policy, args.policy.replace("\\", "/"))
    write_json(output_path, lane_map)
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
