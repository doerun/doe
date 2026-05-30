#!/usr/bin/env python3
"""Tests for compare report claim/diagnostic output partitioning."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from bench.gates import compare_output_partition_gate as gate


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPARE_SAMPLE = REPO_ROOT / "examples" / "compare-report.sample.json"


def _load() -> dict:
    return json.loads(COMPARE_SAMPLE.read_text(encoding="utf-8"))


def test_compare_output_partition_gate_accepts_sample_report() -> None:
    assert gate.evaluate_report(_load()) == []


def test_compare_output_partition_gate_rejects_claimable_diagnostic_class() -> None:
    report = _load()
    workload = report["workloads"][0]
    workload["benchmarkClass"] = "diagnostic"
    workload["claimEligible"] = True

    codes = {item["code"] for item in gate.evaluate_report(report)}

    assert "claimable_row_not_comparable_class" in codes
    assert "diagnostic_row_marked_claimable" in codes


def test_compare_output_partition_gate_rejects_claimable_comparability_reasons() -> None:
    report = _load()
    workload = report["workloads"][0]
    workload["claimEligible"] = True
    workload["comparability"]["reasons"] = ["hidden fallback"]

    assert {
        "code": "claimable_row_has_diagnostic_reasons",
        "path": "workloads[0].comparability.reasons",
        "message": "compute_test: claimEligible=true cannot carry diagnostic comparability reasons",
    } in gate.evaluate_report(report)


def test_compare_output_partition_gate_rejects_claimable_non_comparable_row() -> None:
    report = _load()
    workload = report["workloads"][0]
    workload["claimEligible"] = True
    workload["workloadComparable"] = False
    workload["comparability"]["comparable"] = False

    codes = {item["code"] for item in gate.evaluate_report(report)}

    assert "claimable_row_not_workload_comparable" in codes
    assert "claimable_row_not_comparable" in codes


def test_compare_output_partition_gate_rejects_comparable_report_failures() -> None:
    report = copy.deepcopy(_load())
    report["comparisonStatus"] = "comparable"
    report["comparabilityFailures"] = [{"reason": "mismatch"}]

    assert {
        "code": "comparable_report_has_failures",
        "path": "comparabilityFailures",
        "message": "comparisonStatus=comparable cannot carry comparabilityFailures",
    } in gate.evaluate_report(report)
