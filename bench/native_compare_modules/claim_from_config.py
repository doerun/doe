"""Thin config-backed claim flow over an existing compare report."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from native_compare_modules import claim_report as claim_report_mod
from native_compare_modules import config_support as config_support_mod


def _default_claim_out(compare_report_path: Path) -> Path:
    name = compare_report_path.name
    if name.endswith(".compare.json"):
        return compare_report_path.with_name(name.replace(".compare.json", ".claim.json"))
    if name.endswith(".json"):
        return compare_report_path.with_name(name[:-5] + ".claim.json")
    return compare_report_path.with_name(name + ".claim.json")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", help="Compare report JSON path")
    parser.add_argument("--config", default="", help="Optional compare config for claim defaults")
    parser.add_argument("--mode", default="", choices=["", "local", "release"])
    parser.add_argument("--min-timed-samples", type=int, default=0)
    parser.add_argument("--benchmark-policy", default="")
    parser.add_argument("--out", default="")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config_payload: dict[str, object] = {}
    if args.config:
        config_payload = config_support_mod.load_json(Path(args.config))
        if not isinstance(config_payload, dict):
            raise ValueError(f"invalid config: expected object in {args.config}")

    mode = args.mode
    if not mode:
        value = config_support_mod.first_config_value(
            config_payload,
            ["claimability.mode", "claimabilityMode"],
        )
        if value is not None:
            mode = config_support_mod.as_str(value, field="claimability.mode")
    if mode not in {"local", "release"}:
        raise ValueError("claim mode must be provided or set in config claimability.mode")

    min_timed_samples = args.min_timed_samples
    if min_timed_samples == 0:
        value = config_support_mod.first_config_value(
            config_payload,
            ["claimability.minTimedSamples", "claimMinTimedSamples"],
        )
        if value is not None:
            min_timed_samples = config_support_mod.as_int(
                value,
                field="claimability.minTimedSamples",
            )

    benchmark_policy_path = args.benchmark_policy
    if not benchmark_policy_path:
        value = config_support_mod.first_config_value(
            config_payload,
            ["benchmarkPolicy.path", "benchmarkPolicyPath"],
        )
        if value is not None:
            benchmark_policy_path = config_support_mod.as_str(
                value,
                field="benchmarkPolicy.path",
            )
    compare_report_path = Path(args.report)
    compare_report = claim_report_mod.load_compare_report_with_path(compare_report_path)
    benchmark_policy = config_support_mod.load_benchmark_methodology_policy(
        benchmark_policy_path
    )
    report = claim_report_mod.build_claim_report(
        compare_report=compare_report,
        compare_report_path=compare_report_path,
        benchmark_policy=benchmark_policy,
        mode=mode,
        min_timed_samples=min_timed_samples,
    )
    out_path = Path(args.out) if args.out else _default_claim_out(compare_report_path)
    claim_report_mod.write_claim_report(report, out_path)
    print(f"Claim report: {out_path}")
    return 0 if report.get("pass") is True else 2
