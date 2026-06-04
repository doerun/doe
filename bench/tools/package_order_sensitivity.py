#!/usr/bin/env python3
"""Detect order-sensitive package phase deltas from swapped benchmark runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]

DELTA_FIELD = "comparisonMinusBaselineP50Ms"
METHOD = "phase-delta-order-swap-sign-check"
ORDER_SENSITIVE = "order_sensitive_diagnostic"
DIRECTION_STABLE = "direction_stable_diagnostic"
KEEP_DIAGNOSTIC = "keep_diagnostic_until_order_sensitivity_is_explained"
REGULAR_GATES = "eligible_for_regular_claim_gates"


@dataclass(frozen=True)
class PhaseKey:
    workload_id: str
    section: str
    phase: str

    def sort_key(self) -> tuple[str, str, str]:
        return (self.workload_id, self.section, self.phase)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare two doe_package_phase_delta artifacts collected in swapped "
            "execution order and flag phase directions that flip sign."
        )
    )
    parser.add_argument(
        "--first-order-report",
        required=True,
        help="Path to the phase-delta report from the first execution order.",
    )
    parser.add_argument(
        "--second-order-report",
        required=True,
        help="Path to the phase-delta report from the swapped execution order.",
    )
    parser.add_argument(
        "--first-order-label",
        required=True,
        help="Human-readable label for the first execution order.",
    )
    parser.add_argument(
        "--second-order-label",
        required=True,
        help="Human-readable label for the swapped execution order.",
    )
    parser.add_argument(
        "--json-out",
        default="",
        help="Optional path for the order-sensitivity artifact.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Number of largest order-sensitive rows to print.",
    )
    return parser.parse_args()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def resolve(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {rel(path)}")
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def artifact_hash(payload: dict[str, Any]) -> str:
    material = dict(payload)
    material.pop("artifactHash", None)
    encoded = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _label(report: dict[str, Any], side: str) -> str:
    payload = report.get(side, {})
    if not isinstance(payload, dict):
        raise ValueError(f"phase-delta report missing {side} object")
    label = str(payload.get("label", "")).strip()
    if not label:
        raise ValueError(f"phase-delta report missing {side}.label")
    return label


def _phase_rows(report: dict[str, Any]) -> dict[PhaseKey, dict[str, Any]]:
    if report.get("artifactKind") != "doe_package_phase_delta":
        raise ValueError("input report artifactKind must be doe_package_phase_delta")
    workloads = report.get("workloads", {})
    if not isinstance(workloads, dict):
        raise ValueError("phase-delta report missing workloads object")

    rows: dict[PhaseKey, dict[str, Any]] = {}
    for workload_id, workload in workloads.items():
        if not isinstance(workload, dict):
            raise ValueError(f"workload entry is not an object: {workload_id}")
        timing = workload.get("timing", {})
        if isinstance(timing, dict):
            _add_row(rows, str(workload_id), timing)
        for section in (
            "setup",
            "step",
            "derived",
            "residentBufferLoad",
            "residentBufferLoadAmortized",
        ):
            section_rows = workload.get(section, [])
            if not isinstance(section_rows, list):
                raise ValueError(f"workload {workload_id} section {section} is not a list")
            for row in section_rows:
                if isinstance(row, dict):
                    _add_row(rows, str(workload_id), row)
    return rows


def _add_row(
    rows: dict[PhaseKey, dict[str, Any]],
    workload_id: str,
    row: dict[str, Any],
) -> None:
    section = str(row.get("section", "")).strip()
    phase = str(row.get("phase", "")).strip()
    if not section or not phase:
        raise ValueError(f"phase row missing section or phase for workload {workload_id}")
    row_workload = str(row.get("workloadId", workload_id)).strip()
    key = PhaseKey(row_workload or workload_id, section, phase)
    if key in rows:
        raise ValueError(
            "duplicate phase row: "
            f"workload={key.workload_id} section={key.section} phase={key.phase}"
        )
    rows[key] = row


def _number(row: dict[str, Any], field: str) -> float:
    value = row.get(field)
    if not isinstance(value, (int, float)):
        raise ValueError(f"phase row field {field} is not numeric")
    return float(value)


def _sign(value: float) -> int:
    if value > 0.0:
        return 1
    if value < 0.0:
        return -1
    return 0


def _direction(first: float, second: float) -> str:
    first_sign = _sign(first)
    second_sign = _sign(second)
    if first_sign == 0 or second_sign == 0:
        return "zero_involved"
    if first_sign != second_sign:
        return "sign_flip"
    if first_sign > 0:
        return "same_positive"
    return "same_negative"


def _input_report(
    *,
    path: Path,
    report: dict[str, Any],
    order_label: str,
) -> dict[str, Any]:
    return {
        "path": rel(path),
        "sha256": sha256_file(path),
        "orderLabel": order_label,
        "baselineLabel": _label(report, "baseline"),
        "comparisonLabel": _label(report, "comparison"),
    }


def compare_reports(
    *,
    first_path: Path,
    first_report: dict[str, Any],
    first_order_label: str,
    second_path: Path,
    second_report: dict[str, Any],
    second_order_label: str,
) -> dict[str, Any]:
    first_baseline = _label(first_report, "baseline")
    first_comparison = _label(first_report, "comparison")
    second_baseline = _label(second_report, "baseline")
    second_comparison = _label(second_report, "comparison")
    if (first_baseline, first_comparison) != (second_baseline, second_comparison):
        raise ValueError(
            "phase-delta labels do not match: "
            f"first=({first_baseline}, {first_comparison}) "
            f"second=({second_baseline}, {second_comparison})"
        )

    first_rows = _phase_rows(first_report)
    second_rows = _phase_rows(second_report)
    first_keys = set(first_rows)
    second_keys = set(second_rows)
    if first_keys != second_keys:
        missing_from_first = sorted(
            (key.sort_key() for key in second_keys - first_keys),
        )
        missing_from_second = sorted(
            (key.sort_key() for key in first_keys - second_keys),
        )
        raise ValueError(
            "phase row sets do not match: "
            f"missingFromFirst={missing_from_first}, "
            f"missingFromSecond={missing_from_second}"
        )

    phase_rows: list[dict[str, Any]] = []
    for key in sorted(first_keys, key=lambda item: item.sort_key()):
        first_delta = _number(first_rows[key], DELTA_FIELD)
        second_delta = _number(second_rows[key], DELTA_FIELD)
        direction = _direction(first_delta, second_delta)
        phase_rows.append(
            {
                "workloadId": key.workload_id,
                "section": key.section,
                "phase": key.phase,
                "firstOrderDeltaMs": first_delta,
                "secondOrderDeltaMs": second_delta,
                "direction": direction,
                "directionStable": direction in ("same_positive", "same_negative"),
                "positiveMeansBaselineLower": True,
            }
        )

    sign_flip_count = sum(1 for row in phase_rows if row["direction"] == "sign_flip")
    zero_involved_count = sum(1 for row in phase_rows if row["direction"] == "zero_involved")
    status = ORDER_SENSITIVE if sign_flip_count else DIRECTION_STABLE
    recommendation = KEEP_DIAGNOSTIC if sign_flip_count else REGULAR_GATES
    phase_rows.sort(
        key=lambda row: (
            row["direction"] != "sign_flip",
            -abs(float(row["firstOrderDeltaMs"]) - float(row["secondOrderDeltaMs"])),
            row["workloadId"],
            row["section"],
            row["phase"],
        )
    )

    report = {
        "schemaVersion": 1,
        "artifactKind": "doe_package_order_sensitivity",
        "comparisonMethod": METHOD,
        "status": status,
        "deltaField": DELTA_FIELD,
        "positiveMeansBaselineLower": True,
        "inputReports": [
            _input_report(
                path=first_path,
                report=first_report,
                order_label=first_order_label,
            ),
            _input_report(
                path=second_path,
                report=second_report,
                order_label=second_order_label,
            ),
        ],
        "summary": {
            "baselineLabel": first_baseline,
            "comparisonLabel": first_comparison,
            "firstOrderLabel": first_order_label,
            "secondOrderLabel": second_order_label,
            "matchedPhaseCount": len(phase_rows),
            "signFlipCount": sign_flip_count,
            "zeroInvolvedCount": zero_involved_count,
            "recommendation": recommendation,
        },
        "phaseRows": phase_rows,
    }
    report["artifactHash"] = artifact_hash(report)
    return report


def format_text_report(report: dict[str, Any], top: int) -> str:
    lines = [
        (
            f"{report['summary']['firstOrderLabel']} vs "
            f"{report['summary']['secondOrderLabel']}"
        ),
        f"status: {report['status']}",
        f"recommendation: {report['summary']['recommendation']}",
        "workload | section | phase | direction | first delta ms | second delta ms",
    ]
    for row in report["phaseRows"][: max(top, 0)]:
        lines.append(
            " | ".join(
                [
                    row["workloadId"],
                    row["section"],
                    row["phase"],
                    row["direction"],
                    f"{row['firstOrderDeltaMs']:.6f}",
                    f"{row['secondOrderDeltaMs']:.6f}",
                ]
            )
        )
    return "\n".join(lines)


def write_json_report(report: dict[str, Any], out_path: str) -> Path:
    path = resolve(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def main() -> int:
    args = parse_args()
    try:
        first_path = resolve(args.first_order_report)
        second_path = resolve(args.second_order_report)
        report = compare_reports(
            first_path=first_path,
            first_report=load_json(first_path),
            first_order_label=args.first_order_label,
            second_path=second_path,
            second_report=load_json(second_path),
            second_order_label=args.second_order_label,
        )
        print(format_text_report(report, args.top))
        if args.json_out:
            path = write_json_report(report, args.json_out)
            print(f"wrote {rel(path)}")
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
