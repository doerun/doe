#!/usr/bin/env python3
"""Validate per-workload Metal sync model from trace metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from compare_dawn_vs_doe_modules import metal_sync_contract


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


def expected_sync_mode(policy: dict[str, Any], domain: str) -> str:
    domains = policy.get("domains") if isinstance(policy.get("domains"), dict) else {}
    entry = domains.get(domain) if isinstance(domains, dict) else None
    if not isinstance(entry, dict):
        return "either"
    raw = entry.get("requiredSyncModel")
    return raw if isinstance(raw, str) else "either"


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
        expected = expected_sync_mode(policy, domain)
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
                continue
            for err in metal_sync_contract.evaluate_sync_meta(trace_meta, expected):
                failures.append(f"{workload_id}: {err}")

    if failures:
        print("FAIL: metal sync conformance")
        for item in failures:
            print(f"  {item}")
        return 1

    print("PASS: metal sync conformance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
