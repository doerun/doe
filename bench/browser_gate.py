#!/usr/bin/env python3
"""Run and validate promoted browser diagnostics through lane wrappers."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import output_paths


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_gate_report_path(root: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return root / "bench/out/browser-promotion" / stamp / "browser_gate.json"


def default_artifact_root(root: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return root / "nursery/fawn-browser/artifacts" / stamp


def parse_args() -> argparse.Namespace:
    root = repo_root()
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(root))
    parser.add_argument(
        "--promotion-approvals",
        default=str(root / "nursery/fawn-browser/bench/workflows/browser-promotion-approvals.json"),
    )
    parser.add_argument(
        "--ownership",
        default=str(root / "config/browser-ownership.json"),
    )
    parser.add_argument(
        "--artifact-root",
        default="",
        help="Optional artifact directory for smoke/layered outputs.",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Optional gate report path. Defaults to bench/out/browser-promotion/<timestamp>/browser_gate.json",
    )
    parser.add_argument("--chrome", default="")
    parser.add_argument("--dawn-chrome", default="")
    parser.add_argument("--doe-chrome", default="")
    parser.add_argument("--doe-lib", default="")
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resolve_dawn_chrome(root: Path, explicit: str) -> str:
    if explicit:
        return explicit
    candidate = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if candidate.exists():
        return str(candidate)
    return ""


def run_step(label: str, command: list[str], cwd: Path) -> None:
    print(f"[browser-gate] {label}: {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def validate_ownership(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schemaVersion") != 1:
        errors.append("ownership schemaVersion must be 1")
    areas = payload.get("areas")
    if not isinstance(areas, dict):
        return errors + ["ownership missing areas object"]
    required_areas = {
        "browser_runtime_integration",
        "browser_compatibility",
        "browser_performance_methodology",
    }
    for area in required_areas:
        row = areas.get(area)
        if not isinstance(row, dict):
            errors.append(f"ownership missing area: {area}")
            continue
        for key in (
            "runtimeIntegrationOwner",
            "qualityOwner",
            "benchmarkMethodologyOwner",
            "promotedAt",
        ):
            if not isinstance(row.get(key), str) or not row[key].strip():
                errors.append(f"ownership {area} missing non-empty {key}")
        if row.get("nurseryExitApproved") is not True:
            errors.append(f"ownership {area} nurseryExitApproved must be true")
    return errors


def validate_smoke_report(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("reportKind") != "chromium-webgpu-playwright-smoke":
        errors.append("smoke reportKind must be chromium-webgpu-playwright-smoke")
    if payload.get("benchmarkClass") != "diagnostic":
        errors.append("smoke benchmarkClass must be diagnostic")
    comparison = payload.get("comparison")
    if not isinstance(comparison, dict):
        errors.append("smoke comparison missing")
        return errors
    if comparison.get("bothComputeSmokePass") is not True:
        errors.append("smoke bothComputeSmokePass must be true")
    if comparison.get("bothRenderSmokePass") is not True:
        errors.append("smoke bothRenderSmokePass must be true")
    mode_results = payload.get("modeResults")
    if not isinstance(mode_results, list) or len(mode_results) < 2:
        errors.append("smoke modeResults must include dawn and doe")
        return errors
    modes_seen = set()
    for row in mode_results:
        if not isinstance(row, dict):
            errors.append("smoke modeResults entry must be object")
            continue
        mode = row.get("mode")
        if not isinstance(mode, str):
            errors.append("smoke modeResults entry missing mode")
            continue
        modes_seen.add(mode)
        if row.get("webgpuAvailable") is not True:
            errors.append(f"smoke mode {mode} webgpuAvailable must be true")
        if row.get("adapterAvailable") is not True:
            errors.append(f"smoke mode {mode} adapterAvailable must be true")
        if row.get("errors"):
            errors.append(f"smoke mode {mode} errors must be empty")
        smoke = row.get("smoke")
        if not isinstance(smoke, dict):
            errors.append(f"smoke mode {mode} missing smoke object")
            continue
        for key in ("computeIncrement", "renderTriangle"):
            part = smoke.get(key)
            if not isinstance(part, dict) or part.get("pass") is not True:
                errors.append(f"smoke mode {mode} {key} pass must be true")
    if modes_seen != {"dawn", "doe"}:
        errors.append(f"smoke modeResults must contain dawn and doe, found {sorted(modes_seen)}")
    return errors


def validate_layered_artifacts(
    report_payload: dict[str, Any],
    summary_payload: dict[str, Any],
    check_payload: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if report_payload.get("reportKind") != "browser-layered-diagnostic":
        errors.append("layered reportKind must be browser-layered-diagnostic")
    if not isinstance(report_payload.get("browserEnvironmentEvidence"), dict):
        errors.append("layered report missing browserEnvironmentEvidence")
    if summary_payload.get("reportKind") != "browser-layered-superset-summary":
        errors.append("summary reportKind must be browser-layered-superset-summary")
    if summary_payload.get("comparisonStatus") != "diagnostic":
        errors.append("summary comparisonStatus must be diagnostic")
    if summary_payload.get("claimStatus") != "diagnostic":
        errors.append("summary claimStatus must be diagnostic")
    run = summary_payload.get("run")
    if not isinstance(run, dict):
        errors.append("summary missing run object")
    else:
        if run.get("strictRun") is not True:
            errors.append("summary run.strictRun must be true")
        if run.get("overallRequiredFailures") != 0:
            errors.append("summary overallRequiredFailures must be 0")
        for phase in ("l1", "l2"):
            phase_payload = run.get(phase)
            if not isinstance(phase_payload, dict):
                errors.append(f"summary missing {phase} object")
                continue
            for mode in ("dawn", "doe"):
                mode_payload = phase_payload.get(mode)
                if not isinstance(mode_payload, dict):
                    errors.append(f"summary missing {phase}.{mode}")
                    continue
                if mode_payload.get("requiredFailures") != 0:
                    errors.append(f"summary {phase}.{mode}.requiredFailures must be 0")
    if check_payload.get("ok") is not True:
        errors.append("check payload ok must be true")
    if check_payload.get("reportChecked") is not True:
        errors.append("check payload reportChecked must be true")
    if check_payload.get("promotionChecked") is not True:
        errors.append("check payload promotionChecked must be true")
    required_modes = check_payload.get("requiredModes")
    if required_modes != ["dawn", "doe"]:
        errors.append(f"check requiredModes must be ['dawn', 'doe'], found {required_modes}")
    summary = check_payload.get("summary")
    if not isinstance(summary, dict) or summary.get("rowCount", 0) <= 0:
        errors.append("check summary.rowCount must be > 0")
    return errors


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    artifacts_root = Path(args.artifact_root).resolve() if args.artifact_root else default_artifact_root(root)
    artifacts_root.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.report).resolve() if args.report else default_gate_report_path(root)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    smoke_report = artifacts_root / "dawn-vs-doe.browser.playwright-smoke.diagnostic.json"
    layered_report = artifacts_root / "dawn-vs-doe.browser-layered.superset.diagnostic.json"
    summary_report = artifacts_root / "dawn-vs-doe.browser-layered.superset.summary.json"
    check_report = artifacts_root / "dawn-vs-doe.browser-layered.superset.check.json"

    approvals_path = Path(args.promotion_approvals).resolve()
    ownership_path = Path(args.ownership).resolve()

    preflight = [
        "./nursery/fawn-browser/scripts/preflight.sh",
        "--mode",
        "bench",
    ]
    run_step("preflight", preflight, root)

    smoke_command = [
        "./nursery/fawn-browser/scripts/run-smoke.sh",
        "--mode",
        "both",
        "--strict",
        "--out",
        str(smoke_report),
    ]
    if args.chrome:
        smoke_command.extend(["--chrome", args.chrome])
    if args.doe_lib:
        smoke_command.extend(["--doe-lib", args.doe_lib])
    run_step("smoke", smoke_command, root)

    bench_command = [
        "./nursery/fawn-browser/scripts/run-bench.sh",
        "--mode",
        "both",
        "--strict-run",
        "--require-promotion-approvals",
        "--promotion-approvals",
        str(approvals_path),
        "--out",
        str(layered_report),
        "--summary-out",
        str(summary_report),
        "--check-out",
        str(check_report),
    ]
    if args.chrome:
        bench_command.extend(["--chrome", args.chrome])
    resolved_dawn_chrome = resolve_dawn_chrome(root, args.dawn_chrome)
    if resolved_dawn_chrome:
        bench_command.extend(["--dawn-chrome", resolved_dawn_chrome])
    if args.doe_chrome:
        bench_command.extend(["--doe-chrome", args.doe_chrome])
    if args.doe_lib:
        bench_command.extend(["--doe-lib", args.doe_lib])
    run_step("layered", bench_command, root)

    ownership_errors = validate_ownership(load_json(ownership_path))
    smoke_payload = load_json(smoke_report)
    smoke_errors = validate_smoke_report(smoke_payload)
    report_payload = load_json(layered_report)
    summary_payload = load_json(summary_report)
    check_payload = load_json(check_report)
    layered_errors = validate_layered_artifacts(report_payload, summary_payload, check_payload)

    failures = ownership_errors + smoke_errors + layered_errors
    payload = {
        "laneId": "browser_diagnostic",
        "ok": not failures,
        "generatedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ownershipOk": not ownership_errors,
        "smokeOk": not smoke_errors,
        "layeredOk": not layered_errors,
        "artifacts": {
            "smokeReport": str(smoke_report),
            "layeredReport": str(layered_report),
            "summaryReport": str(summary_report),
            "checkReport": str(check_report),
            "promotionApprovals": str(approvals_path),
            "ownership": str(ownership_path),
        },
        "hashes": {
            "smokeReport": stable_hash(smoke_payload),
            "layeredReport": stable_hash(report_payload),
            "summaryReport": stable_hash(summary_payload),
            "checkReport": stable_hash(check_payload),
        },
        "failures": failures,
    }
    report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    output_paths.write_run_manifest_for_outputs(
        [report_path],
        {
            "runType": "browser-gate",
            "fullRun": True,
            "claimGateRan": False,
            "status": "pass" if not failures else "fail",
            "smokeReport": str(smoke_report),
            "layeredReport": str(layered_report),
        },
    )
    if args.emit_json or True:
        print(json.dumps(payload, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
