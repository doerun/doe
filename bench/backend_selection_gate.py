#!/usr/bin/env python3
"""Validate backend selection telemetry against backend-runtime policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from compare_dawn_vs_doe_modules import backend_contract


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="bench/out/dawn-vs-doe.json")
    parser.add_argument("--policy", default="config/backend-runtime-policy.json")
    parser.add_argument("--lane", default="")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def infer_lane(report: dict[str, Any], explicit_lane: str) -> str:
    if explicit_lane:
        return explicit_lane
    config_path = str(report.get("configPath", ""))
    if ".metal.release" in config_path:
        return "local_metal_release"
    if ".metal.comparable" in config_path or ".metal.extended.comparable" in config_path:
        return "local_metal_comparable"
    if ".metal.directional" in config_path:
        return "local_metal_directional"
    if ".local.vulkan.release" in config_path:
        return "local_vulkan_release"
    if ".local.vulkan.comparable" in config_path or ".local.vulkan.extended.comparable" in config_path:
        return "local_vulkan_comparable"
    if ".local.vulkan.directional" in config_path:
        return "local_vulkan_directional"
    return "amd_vulkan_release"


def main() -> int:
    args = parse_args()
    report = load_json(Path(args.report))
    policy = load_json(Path(args.policy))

    lanes = policy.get("lanes") if isinstance(policy.get("lanes"), dict) else {}
    lane = infer_lane(report, args.lane)
    lane_policy = lanes.get(lane) if isinstance(lanes, dict) else None
    if not isinstance(lane_policy, dict):
        print(f"FAIL: missing lane policy for {lane}")
        return 1

    expected_backend = lane_policy.get("defaultBackend")
    strict_no_fallback = bool(lane_policy.get("strictNoFallback", False))

    failures: list[str] = []
    workloads = report.get("workloads")
    if not isinstance(workloads, list):
        print("FAIL: invalid report workloads")
        return 1

    for workload in workloads:
        if not isinstance(workload, dict):
            continue
        workload_id = str(workload.get("id", "unknown"))
        left = workload.get("left")
        if not isinstance(left, dict):
            continue
        samples = left.get("commandSamples")
        if not isinstance(samples, list):
            continue
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            if sample.get("returnCode") != 0:
                continue
            trace_meta = sample.get("traceMeta")
            if not isinstance(trace_meta, dict):
                failures.append(f"{workload_id}: missing traceMeta")
                continue
            errors = backend_contract.backend_telemetry_errors(trace_meta)
            for err in errors:
                failures.append(f"{workload_id}: {err}")
            backend_id = trace_meta.get("backendId")
            if isinstance(expected_backend, str) and backend_id != expected_backend:
                failures.append(
                    f"{workload_id}: backendId mismatch expected={expected_backend} got={backend_id!r}"
                )
            if strict_no_fallback and trace_meta.get("fallbackUsed") is True:
                failures.append(f"{workload_id}: fallbackUsed=true not allowed in strict lane")

    if failures:
        print("FAIL: backend selection gate")
        for item in failures:
            print(f"  {item}")
        return 1

    print(f"PASS: backend selection gate (lane={lane})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
