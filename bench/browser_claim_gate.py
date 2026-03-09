#!/usr/bin/env python3
"""Repeated-window claim gate for promoted browser diagnostics."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import output_paths


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def default_report_path(root: Path) -> Path:
    return root / "bench/out/browser-claim" / utc_stamp() / "browser_claim_report.json"


def default_artifact_root(root: Path) -> Path:
    return root / "nursery/fawn-browser/artifacts" / utc_stamp() / "browser-claim"


def parse_args() -> argparse.Namespace:
    root = repo_root()
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(root))
    parser.add_argument(
        "--policy",
        default=str(root / "config/browser-claim-policy.json"),
    )
    parser.add_argument(
        "--promotion-approvals",
        default=str(root / "nursery/fawn-browser/bench/workflows/browser-promotion-approvals.json"),
    )
    parser.add_argument(
        "--ownership",
        default=str(root / "config/browser-ownership.json"),
    )
    parser.add_argument(
        "--window-count",
        type=int,
        default=0,
        help="Override the policy minWindows value.",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Output JSON report path. Defaults to bench/out/browser-claim/<timestamp>/browser_claim_report.json",
    )
    parser.add_argument(
        "--artifact-root",
        default="",
        help="Artifact directory root for repeated browser windows.",
    )
    parser.add_argument(
        "--reuse-artifact-root",
        default="",
        help="Reuse an existing repeated-window artifact root instead of rerunning browser windows.",
    )
    parser.add_argument("--chrome", default="")
    parser.add_argument("--dawn-chrome", default="")
    parser.add_argument("--doe-chrome", default="")
    parser.add_argument("--doe-lib", default="")
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    import hashlib

    return hashlib.sha256(encoded).hexdigest()


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(ratio * len(ordered)))
    return ordered[rank - 1]


def summarize_values(values: list[float]) -> dict[str, Any]:
    return {
        "sampleCount": len(values),
        "minMs": min(values),
        "maxMs": max(values),
        "p50Ms": percentile(values, 0.50),
        "p95Ms": percentile(values, 0.95),
        "p99Ms": percentile(values, 0.99),
    }


def percent_delta(left: float | None, right: float | None) -> float | None:
    if left is None or right is None or left <= 0.0:
        return None
    return ((left - right) / left) * 100.0


def parse_policy(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    if payload.get("schemaVersion") != 1:
        raise ValueError("browser claim policy schemaVersion must be 1")
    mode = payload.get("mode")
    if mode not in {"local", "release"}:
        raise ValueError("browser claim policy mode must be local or release")
    min_windows = payload.get("minWindows")
    if not isinstance(min_windows, int) or min_windows <= 0:
        raise ValueError("browser claim policy minWindows must be > 0")
    required_percentiles = payload.get("requiredPositivePercentiles")
    if not isinstance(required_percentiles, list) or not required_percentiles:
        raise ValueError("browser claim policy requiredPositivePercentiles must be non-empty")
    require_modes = payload.get("requireModes")
    if not isinstance(require_modes, list) or sorted(require_modes) != ["dawn", "doe"]:
        raise ValueError("browser claim policy requireModes must be ['dawn', 'doe']")
    require_claim_scopes = payload.get("requireClaimScopes")
    if not isinstance(require_claim_scopes, list) or not require_claim_scopes:
        raise ValueError("browser claim policy requireClaimScopes must be non-empty")
    expected_rows = payload.get("expectedStrictCandidateRows")
    if not isinstance(expected_rows, int) or expected_rows <= 0:
        raise ValueError("browser claim policy expectedStrictCandidateRows must be > 0")
    max_flake = payload.get("maxFlakePercent")
    if not isinstance(max_flake, (int, float)) or max_flake < 0:
        raise ValueError("browser claim policy maxFlakePercent must be >= 0")
    return payload


def extract_claim_rows(report_payload: dict[str, Any], required_claim_scopes: set[str]) -> dict[str, dict[str, Any]]:
    rows = report_payload.get("l1", {}).get("rows", [])
    if not isinstance(rows, list):
        raise ValueError("layered report missing l1.rows")
    claim_rows: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        workload_id = row.get("sourceWorkloadId")
        if not isinstance(workload_id, str) or not workload_id:
            continue
        if row.get("comparabilityExpectation") != "strict":
            continue
        if row.get("claimScope") not in required_claim_scopes:
            continue
        if row.get("requiredStatus") != "ok":
            continue
        claim_rows[workload_id] = row
    return claim_rows


def metric_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def metric_ms(metrics: dict[str, Any]) -> float | None:
    us_per_op = metric_number(metrics.get("usPerOp"))
    if us_per_op is not None and us_per_op > 0.0:
        return us_per_op / 1000.0
    us_per_frame = metric_number(metrics.get("usPerFrame"))
    if us_per_frame is not None and us_per_frame > 0.0:
        return us_per_frame / 1000.0
    us_per_submit = metric_number(metrics.get("usPerSubmit"))
    if us_per_submit is not None and us_per_submit > 0.0:
        return us_per_submit / 1000.0
    ms_per_pipeline = metric_number(metrics.get("msPerPipeline"))
    if ms_per_pipeline is not None and ms_per_pipeline > 0.0:
        return ms_per_pipeline
    ms_per_resize = metric_number(metrics.get("msPerResize"))
    if ms_per_resize is not None and ms_per_resize > 0.0:
        return ms_per_resize
    elapsed_ms = metric_number(metrics.get("elapsedMs"))
    if elapsed_ms is None or elapsed_ms <= 0.0:
        return None
    divisor = None
    for counter_key in ("iterations", "submitCount", "resizeCount", "pipelineCount"):
        counter = metrics.get(counter_key)
        if isinstance(counter, int) and counter > 0:
            divisor = counter
            break
    if divisor is None:
        return elapsed_ms
    return elapsed_ms / divisor


def run_window(
    root: Path,
    window_index: int,
    windows_dir: Path,
    artifacts_root: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    gate_script = root / "bench/browser_gate.py"
    gate_report = windows_dir / f"window-{window_index:02d}.browser_gate.json"
    window_artifacts = artifacts_root / f"window-{window_index:02d}"
    command = [
        sys.executable,
        str(gate_script),
        "--root",
        str(root),
        "--promotion-approvals",
        str(Path(args.promotion_approvals).resolve()),
        "--ownership",
        str(Path(args.ownership).resolve()),
        "--artifact-root",
        str(window_artifacts),
        "--report",
        str(gate_report),
    ]
    if args.chrome:
        command.extend(["--chrome", args.chrome])
    if args.dawn_chrome:
        command.extend(["--dawn-chrome", args.dawn_chrome])
    if args.doe_chrome:
        command.extend(["--doe-chrome", args.doe_chrome])
    if args.doe_lib:
        command.extend(["--doe-lib", args.doe_lib])
    subprocess.run(command, cwd=root, check=True)
    gate_payload = load_json(gate_report)
    if gate_payload.get("ok") is not True:
        raise RuntimeError(f"browser_gate failed for window-{window_index:02d}")
    return gate_payload


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    policy_path = Path(args.policy).resolve()
    policy = parse_policy(policy_path)
    report_path = Path(args.report).resolve() if args.report else default_report_path(root)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    artifacts_root = Path(args.artifact_root).resolve() if args.artifact_root else default_artifact_root(root)
    artifacts_root.mkdir(parents=True, exist_ok=True)
    windows_dir = report_path.parent / "windows"
    windows_dir.mkdir(parents=True, exist_ok=True)

    requested_windows = args.window_count if args.window_count > 0 else int(policy["minWindows"])
    if requested_windows < int(policy["minWindows"]):
        print(
            "FAIL: --window-count must be >= policy minWindows "
            f"({policy['minWindows']})"
        )
        return 1

    failures: list[str] = []
    per_window_rows: list[dict[str, Any]] = []
    claim_scope_rows: dict[str, dict[str, Any]] = {}
    required_claim_scopes = set(policy["requireClaimScopes"])

    if args.reuse_artifact_root:
        reuse_root = Path(args.reuse_artifact_root).resolve()
        window_dirs = sorted(path for path in reuse_root.iterdir() if path.is_dir() and path.name.startswith("window-"))
        if args.window_count > 0 and len(window_dirs) != requested_windows:
            failures.append(
                f"reuse artifact root has {len(window_dirs)} windows, expected {requested_windows}"
            )
        requested_windows = len(window_dirs)
        artifacts_root = reuse_root
        for window_dir in window_dirs:
            window_index = int(window_dir.name.split("-")[-1])
            layered_path = window_dir / "dawn-vs-doe.browser-layered.superset.diagnostic.json"
            summary_path = window_dir / "dawn-vs-doe.browser-layered.superset.summary.json"
            check_path = window_dir / "dawn-vs-doe.browser-layered.superset.check.json"
            smoke_path = window_dir / "dawn-vs-doe.browser.playwright-smoke.diagnostic.json"
            layered_report = load_json(layered_path)
            summary_report = load_json(summary_path)
            check_report = load_json(check_path)
            gate_payload = {
                "artifacts": {
                    "smokeReport": str(smoke_path),
                    "layeredReport": str(layered_path),
                    "summaryReport": str(summary_path),
                    "checkReport": str(check_path),
                },
                "hashes": {
                    "smokeReport": stable_hash(load_json(smoke_path)),
                    "layeredReport": stable_hash(layered_report),
                    "summaryReport": stable_hash(summary_report),
                    "checkReport": stable_hash(check_report),
                },
            }
            if not smoke_path.exists():
                failures.append(f"{window_dir.name}: smoke report missing")
            current_rows = extract_claim_rows(layered_report, required_claim_scopes)
            if len(current_rows) != int(policy["expectedStrictCandidateRows"]):
                failures.append(
                    f"{window_dir.name}: expected "
                    f"{policy['expectedStrictCandidateRows']} strict candidate rows, found {len(current_rows)}"
                )
            if not claim_scope_rows:
                claim_scope_rows = current_rows
            elif set(current_rows) != set(claim_scope_rows):
                failures.append(f"{window_dir.name}: strict candidate row set drift")

            browser_evidence = layered_report.get("browserEnvironmentEvidence", {})
            per_window_rows.append(
                {
                    "window": window_index,
                    "gateReport": "",
                    "smokeReport": str(smoke_path),
                    "layeredReport": str(layered_path),
                    "summaryReport": str(summary_path),
                    "checkReport": str(check_path),
                    "hashes": gate_payload["hashes"],
                    "browserEnvironmentEvidence": browser_evidence,
                }
            )
    else:
        for window_index in range(1, requested_windows + 1):
            gate_payload = run_window(root, window_index, windows_dir, artifacts_root, args)
            layered_report = load_json(Path(gate_payload["artifacts"]["layeredReport"]))
            summary_report = load_json(Path(gate_payload["artifacts"]["summaryReport"]))
            check_report = load_json(Path(gate_payload["artifacts"]["checkReport"]))

            if summary_report.get("benchmarkClass") != "directional":
                failures.append(f"window-{window_index:02d}: summary benchmarkClass drift")
            run_payload = summary_report.get("run", {})
            if policy["requireStrictRun"] and run_payload.get("strictRun") is not True:
                failures.append(f"window-{window_index:02d}: strictRun must be true")
            if policy["requireHeadless"] and layered_report.get("headless") is not True:
                failures.append(f"window-{window_index:02d}: headless must be true")
            browser_evidence = layered_report.get("browserEnvironmentEvidence", {})
            if (
                not policy["allowDataUrlFallback"]
                and isinstance(browser_evidence, dict)
                and browser_evidence.get("dataUrlFallbackEnabled") is not False
            ):
                failures.append(f"window-{window_index:02d}: data URL fallback must be disabled")
            if policy["promotionApprovalsRequired"] and check_report.get("promotionChecked") is not True:
                failures.append(f"window-{window_index:02d}: promotionChecked must be true")

            current_rows = extract_claim_rows(layered_report, required_claim_scopes)
            if len(current_rows) != int(policy["expectedStrictCandidateRows"]):
                failures.append(
                    f"window-{window_index:02d}: expected "
                    f"{policy['expectedStrictCandidateRows']} strict candidate rows, found {len(current_rows)}"
                )
            if not claim_scope_rows:
                claim_scope_rows = current_rows
            elif set(current_rows) != set(claim_scope_rows):
                failures.append(f"window-{window_index:02d}: strict candidate row set drift")

            per_window_rows.append(
                {
                    "window": window_index,
                    "gateReport": str((windows_dir / f"window-{window_index:02d}.browser_gate.json").resolve()),
                    "smokeReport": gate_payload["artifacts"]["smokeReport"],
                    "layeredReport": gate_payload["artifacts"]["layeredReport"],
                    "summaryReport": gate_payload["artifacts"]["summaryReport"],
                    "checkReport": gate_payload["artifacts"]["checkReport"],
                    "hashes": gate_payload["hashes"],
                    "browserEnvironmentEvidence": browser_evidence,
                }
            )

    workload_rows: list[dict[str, Any]] = []
    claimable_count = 0
    comparable_count = 0

    for workload_id in sorted(claim_scope_rows):
        row_template = claim_scope_rows[workload_id]
        dawn_values: list[float] = []
        doe_values: list[float] = []
        observed_iterations: list[int] = []
        reasons: list[str] = []

        for window_index in range(1, requested_windows + 1):
            layered_path = Path(per_window_rows[window_index - 1]["layeredReport"])
            layered_report = load_json(layered_path)
            row = extract_claim_rows(layered_report, required_claim_scopes).get(workload_id)
            if not isinstance(row, dict):
                reasons.append(f"window-{window_index:02d}: workload missing")
                continue
            runtimes = row.get("runtimes", {})
            if not isinstance(runtimes, dict):
                reasons.append(f"window-{window_index:02d}: runtimes missing")
                continue
            for mode, bucket in (("dawn", dawn_values), ("doe", doe_values)):
                runtime_payload = runtimes.get(mode)
                if not isinstance(runtime_payload, dict):
                    reasons.append(f"window-{window_index:02d}: {mode} runtime payload missing")
                    continue
                if runtime_payload.get("status") != "ok":
                    reasons.append(f"window-{window_index:02d}: {mode} status={runtime_payload.get('status')}")
                    continue
                metrics = runtime_payload.get("metrics", {})
                if not isinstance(metrics, dict):
                    reasons.append(f"window-{window_index:02d}: {mode} metrics missing")
                    continue
                timing_ms = metric_ms(metrics)
                iterations = metrics.get("iterations")
                if timing_ms is None or timing_ms <= 0.0:
                    reasons.append(f"window-{window_index:02d}: {mode} timing metric must be > 0")
                    continue
                if isinstance(iterations, int) and iterations > 0:
                    observed_iterations.append(iterations)
                bucket.append(timing_ms)

        if len(set(observed_iterations)) > 1:
            reasons.append("iteration count drift across windows or modes")

        comparable = len(dawn_values) == requested_windows and len(doe_values) == requested_windows and not reasons
        if comparable:
            comparable_count += 1

        dawn_stats = summarize_values(dawn_values) if dawn_values else {}
        doe_stats = summarize_values(doe_values) if doe_values else {}
        delta_percent = {
            "p50Percent": percent_delta(metric_number(dawn_stats.get("p50Ms")), metric_number(doe_stats.get("p50Ms"))),
            "p95Percent": percent_delta(metric_number(dawn_stats.get("p95Ms")), metric_number(doe_stats.get("p95Ms"))),
            "p99Percent": percent_delta(metric_number(dawn_stats.get("p99Ms")), metric_number(doe_stats.get("p99Ms"))),
        }

        flake_percent = 0.0
        if comparable and metric_number(dawn_stats.get("p50Ms")) and metric_number(doe_stats.get("p50Ms")):
            positive_windows = 0
            for left, right in zip(dawn_values, doe_values):
                if percent_delta(left, right) is not None and percent_delta(left, right) > 0.0:
                    positive_windows += 1
            flake_percent = (1.0 - (positive_windows / requested_windows)) * 100.0
            if flake_percent > float(policy["maxFlakePercent"]):
                reasons.append(
                    f"flakePercent={flake_percent:.2f} exceeds policy maxFlakePercent={policy['maxFlakePercent']:.2f}"
                )

        claimable = comparable and len(dawn_values) >= int(policy["minWindows"])
        if claimable:
            for percentile_key in policy["requiredPositivePercentiles"]:
                value = metric_number(delta_percent.get(percentile_key))
                if value is None or value <= 0.0:
                    reasons.append(f"{percentile_key} must be > 0")
                    claimable = False
            if flake_percent > float(policy["maxFlakePercent"]):
                claimable = False

        if claimable:
            claimable_count += 1

        workload_rows.append(
            {
                "id": workload_id,
                "name": row_template.get("sourceWorkloadName", workload_id),
                "domain": row_template.get("domain", ""),
                "scenarioTemplate": row_template.get("scenarioTemplate", ""),
                "claimScope": row_template.get("claimScope", ""),
                "comparabilityExpectation": row_template.get("comparabilityExpectation", ""),
                "comparisonStatus": "comparable" if comparable else "diagnostic",
                "claimability": {
                    "claimable": claimable,
                    "reasons": reasons,
                    "windowCount": requested_windows,
                    "flakePercent": flake_percent,
                },
                "deltaPercent": delta_percent,
                "left": {
                    "runtime": "dawn",
                    "timingSources": ["browser-performance-now"],
                    "stats": dawn_stats,
                    "samplesMs": dawn_values,
                },
                "right": {
                    "runtime": "doe",
                    "timingSources": ["browser-performance-now"],
                    "stats": doe_stats,
                    "samplesMs": doe_values,
                },
            }
        )

    comparison_status = "comparable" if comparable_count == len(workload_rows) and not failures else "diagnostic"
    claim_status = "claimable" if claimable_count == len(workload_rows) and comparison_status == "comparable" else "diagnostic"
    ok = not failures and comparison_status == "comparable" and claim_status == "claimable"

    payload = {
        "schemaVersion": 1,
        "reportKind": "browser-claim-report",
        "generatedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "benchmarkClass": "comparable",
        "comparisonStatus": comparison_status,
        "claimStatus": claim_status,
        "timingClass": "scenario",
        "timingSource": "browser-performance-now",
        "claimabilityPolicy": {
            "mode": policy["mode"],
            "minTimedSamples": policy["minWindows"],
            "requiredPositivePercentiles": policy["requiredPositivePercentiles"],
            "maxFlakePercent": policy["maxFlakePercent"],
        },
        "policyPath": str(policy_path),
        "promotionApprovalsPath": str(Path(args.promotion_approvals).resolve()),
        "ownershipPath": str(Path(args.ownership).resolve()),
        "windowCount": requested_windows,
        "windows": per_window_rows,
        "claimabilitySummary": {
            "workloadCount": len(workload_rows),
            "comparableCount": comparable_count,
            "claimableCount": claimable_count,
        },
        "workloads": workload_rows,
        "failures": failures,
    }
    report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    tail_health = {
        "schemaVersion": 1,
        "generatedAt": payload["generatedAt"],
        "reportPath": str(report_path),
        "requiredPositivePercentiles": policy["requiredPositivePercentiles"],
        "rows": [
            {
                "workloadId": row["id"],
                "comparisonStatus": row["comparisonStatus"],
                "claimable": row["claimability"]["claimable"],
                "flakePercent": row["claimability"]["flakePercent"],
                "deltaPercent": row["deltaPercent"],
            }
            for row in workload_rows
        ],
    }
    tail_health_path = Path(f"{report_path.with_suffix('')}.tail-health.json")
    tail_health_path.write_text(json.dumps(tail_health, indent=2) + "\n", encoding="utf-8")

    gate_result = {
        "ok": ok,
        "generatedAt": payload["generatedAt"],
        "comparisonStatus": comparison_status,
        "claimStatus": claim_status,
        "windowCount": requested_windows,
        "workloadCount": len(workload_rows),
        "claimableCount": claimable_count,
        "comparableCount": comparable_count,
        "reportPath": str(report_path),
        "failures": failures + [
            f"{row['id']}: {'; '.join(row['claimability']['reasons'])}"
            for row in workload_rows
            if row["claimability"]["reasons"]
        ],
    }
    gate_result_path = Path(f"{report_path.with_suffix('')}.claim-gate-result.json")
    gate_result_path.write_text(json.dumps(gate_result, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "schemaVersion": 1,
        "generatedAt": payload["generatedAt"],
        "reportPath": str(report_path),
        "gateResultPath": str(gate_result_path),
        "tailHealthPath": str(tail_health_path),
        "artifactsRoot": str(artifacts_root),
        "windowReports": [row["gateReport"] for row in per_window_rows],
    }
    manifest_path = Path(f"{report_path.with_suffix('')}.manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    output_paths.write_run_manifest_for_outputs(
        [report_path, gate_result_path, tail_health_path, manifest_path],
        {
            "runType": "browser-claim-gate",
            "fullRun": True,
            "claimGateRan": True,
            "browserGateRan": True,
            "windowCount": requested_windows,
            "status": "pass" if ok else "fail",
            "reportPath": str(report_path),
        },
    )

    if args.emit_json or True:
        print(json.dumps(gate_result, indent=2))

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
