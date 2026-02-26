#!/usr/bin/env python3
"""Validate timing source/class policy for Vulkan compare reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="bench/out/dawn-vs-doe.json")
    parser.add_argument("--timing-policy", default="config/backend-timing-policy.json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def canonical(source: str) -> str:
    if not source:
        return ""
    return source.split("+", 1)[0]


def domain_policy(policy: dict[str, Any], domain: str) -> dict[str, Any]:
    domains = policy.get("domains") if isinstance(policy.get("domains"), dict) else {}
    entry = domains.get(domain) if isinstance(domains, dict) else None
    return entry if isinstance(entry, dict) else {}


def main() -> int:
    args = parse_args()
    report = load_json(Path(args.report))
    policy = load_json(Path(args.timing_policy))

    failures: list[str] = []
    workloads = report.get("workloads")
    if not isinstance(workloads, list):
        print("FAIL: invalid report workloads")
        return 1

    for workload in workloads:
        if not isinstance(workload, dict):
            continue
        workload_id = str(workload.get("id", "unknown"))
        domain = str(workload.get("domain", ""))
        policy_entry = domain_policy(policy, domain)
        required_class = str(policy_entry.get("requiredTimingClass", "any"))
        allowed_sources = {
            canonical(str(item))
            for item in policy_entry.get("allowedTimingSources", [])
            if isinstance(item, str)
        }
        require_upload_source = policy_entry.get("requireUploadIgnoreFirstSource")

        comparability = workload.get("comparability")
        if isinstance(comparability, dict):
            left_class = str(comparability.get("leftTimingClass", ""))
            right_class = str(comparability.get("rightTimingClass", ""))
            if required_class != "any" and left_class != required_class:
                failures.append(
                    f"{workload_id}: leftTimingClass mismatch expected={required_class} got={left_class}"
                )
            if required_class != "any" and right_class != required_class:
                failures.append(
                    f"{workload_id}: rightTimingClass mismatch expected={required_class} got={right_class}"
                )

        for side_name in ("left", "right"):
            side = workload.get(side_name)
            if not isinstance(side, dict):
                continue
            samples = side.get("commandSamples")
            if not isinstance(samples, list):
                continue
            for sample in samples:
                if not isinstance(sample, dict):
                    continue
                if sample.get("returnCode") != 0:
                    continue
                source = canonical(str(sample.get("timingSource", "")))
                if allowed_sources and source not in allowed_sources:
                    failures.append(
                        f"{workload_id}: {side_name} timingSource {source!r} not in allowed set {sorted(allowed_sources)}"
                    )
                timing = sample.get("timing")
                if (
                    isinstance(require_upload_source, str)
                    and require_upload_source
                    and isinstance(timing, dict)
                    and timing.get("uploadIgnoreFirstApplied") is True
                ):
                    adjusted = canonical(str(timing.get("uploadIgnoreFirstAdjustedTimingSource", "")))
                    if adjusted != canonical(require_upload_source):
                        failures.append(
                            f"{workload_id}: {side_name} upload ignore-first adjusted source {adjusted!r} expected {require_upload_source!r}"
                        )

    if failures:
        print("FAIL: vulkan timing policy gate")
        for item in failures:
            print(f"  {item}")
        return 1

    print("PASS: vulkan timing policy gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
