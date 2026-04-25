#!/usr/bin/env python3
"""Classify a CSL simulator run as plumbing-pass / plumbing-partial / failed,
and surface a separate numeric-parity status for downstream consumers.

The driver-result JSON and progress JSONL emitted by `csl_sdk_driver.py` and
`int4ple_compile_target_sim_runner.py` carry enough information to tell three
distinct success classes apart:

  - ``compile_only``: every cslc invocation succeeded but the runtime side did
    not run a single launch end-to-end (e.g. wallclock timeout before
    launch[0]).
  - ``plumbing_partial``: at least one launch completed cleanly, but the run
    eventually failed or timed out before the prefill/decode tail.
  - ``plumbing_pass``: every host-plan launch that the runtime attempted
    completed cleanly.

Numeric parity is a separate classification because the simulator never
compares against a reference transcript by itself — bytes coming out of a
`hostplan_launch_complete status=succeeded` event are not validated for
correctness. This gate emits ``numeric_parity_status = unknown`` until a
parity comparison source (Doppler reference logits, KV digests) is wired in;
the receipt shape leaves the slot in place so future iterations can drop in
real comparison without rewriting the contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

PLUMBING_PASS = "plumbing_pass"
PLUMBING_PARTIAL = "plumbing_partial"
COMPILE_ONLY = "compile_only"
COMPILE_FAILED = "compile_failed"
DRIVER_EXCEPTION = "driver_exception"
ARTIFACTS_MISSING = "artifacts_missing"

PARITY_UNKNOWN = "unknown"
PARITY_NOT_ATTEMPTED = "not_attempted"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--hostplan-bundle",
        default="bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan",
        help="Path to a HostPlan bundle directory containing trace.json.driver-result.json"
        " and trace.json.progress.jsonl.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Receipt output path. Defaults to <bundle>/simulator-evidence.json.",
    )
    parser.add_argument(
        "--require",
        choices=["plumbing_pass", "plumbing_partial", "compile_only"],
        default=None,
        help="If set, exit non-zero unless the classification is at least this strict.",
    )
    return parser.parse_args()


def resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def load_driver_result(bundle_dir: Path) -> dict[str, Any] | None:
    path = bundle_dir / "trace.json.driver-result.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def iter_progress_events(bundle_dir: Path) -> list[dict[str, Any]]:
    path = bundle_dir / "trace.json.progress.jsonl"
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def summarize_launches(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Walk progress events in order; for each launch, the most recent
    terminal event wins. The progress JSONL is append-only across regen
    runs, so a launch that failed in an earlier run and then succeeded in
    the latest run must report as succeeded — not as both.
    """
    final_state: dict[int, tuple[str, str]] = {}
    started: set[int] = set()
    last_launch_started = -1
    for event in events:
        if not isinstance(event, dict):
            continue
        phase = str(event.get("phase") or "")
        launch_index = event.get("launchIndex")
        if not isinstance(launch_index, int):
            continue
        if phase == "hostplan_launch_start":
            started.add(launch_index)
            if launch_index > last_launch_started:
                last_launch_started = launch_index
        elif phase == "hostplan_launch_complete":
            status = str(event.get("status") or "") or "unknown"
            final_state[launch_index] = ("complete", status)
        elif phase == "hostplan_launch_blocked":
            final_state[launch_index] = ("blocked", str(event.get("error") or "blocked"))
    succeeded: list[int] = []
    failed: list[dict[str, Any]] = []
    last_succeeded = -1
    for idx in sorted(final_state):
        kind, detail = final_state[idx]
        if kind == "complete" and detail == "succeeded":
            succeeded.append(idx)
            if idx > last_succeeded:
                last_succeeded = idx
        else:
            failed.append({"launchIndex": idx, "reason": detail})
    return {
        "launchesStarted": sorted(started),
        "launchesSucceeded": succeeded,
        "launchesFailed": failed,
        "lastLaunchStartedIndex": last_launch_started,
        "lastLaunchSucceededIndex": last_succeeded,
    }


def classify(driver_result: dict[str, Any] | None, launch_summary: dict[str, Any]) -> str:
    if driver_result is None:
        return ARTIFACTS_MISSING
    compile_status = str((driver_result.get("compile") or {}).get("status") or "")
    compile_reason = str((driver_result.get("compile") or {}).get("reason") or "")
    run_status = str((driver_result.get("run") or {}).get("status") or "")
    run_reason = str((driver_result.get("run") or {}).get("reason") or "")
    # Driver-level exceptions (schema validation, missing inputs, Python
    # crashes) typically set both compile.status="failed" and run.reason
    # ="driver_exception" because the driver halts before separating the
    # phases. Surface the more specific class so users do not chase a
    # phantom CSL compile bug.
    if compile_reason.startswith("driver_exception") or run_reason.startswith("driver_exception"):
        return DRIVER_EXCEPTION
    if compile_status == "failed":
        return COMPILE_FAILED
    succeeded = launch_summary["launchesSucceeded"]
    if not succeeded:
        return COMPILE_ONLY
    if run_status == "succeeded" and not launch_summary["launchesFailed"]:
        return PLUMBING_PASS
    return PLUMBING_PARTIAL


def numeric_parity_status() -> str:
    # Numeric parity needs reference logits/KV digests to compare against.
    # Until that source is wired in, the gate must report parity as unknown
    # rather than imply success based on plumbing metrics alone.
    return PARITY_UNKNOWN


def build_receipt(bundle_dir: Path) -> dict[str, Any]:
    driver_result = load_driver_result(bundle_dir)
    events = iter_progress_events(bundle_dir)
    launch_summary = summarize_launches(events)
    plumbing = classify(driver_result, launch_summary)
    return {
        "schemaVersion": 1,
        "artifactKind": "csl_simulator_evidence_receipt",
        "hostplanBundle": str(bundle_dir),
        "compileStatus": str((driver_result or {}).get("compile", {}).get("status") or ""),
        "runStatus": str((driver_result or {}).get("run", {}).get("status") or ""),
        "runReason": str((driver_result or {}).get("run", {}).get("reason") or ""),
        "plumbingClassification": plumbing,
        "numericParity": {
            "status": numeric_parity_status(),
            "reason": "no reference transcript wired",
            "compareSource": None,
        },
        **launch_summary,
    }


def required_at_least(classification: str, threshold: str) -> bool:
    levels = [
        ARTIFACTS_MISSING,
        DRIVER_EXCEPTION,
        COMPILE_FAILED,
        COMPILE_ONLY,
        PLUMBING_PARTIAL,
        PLUMBING_PASS,
    ]
    try:
        return levels.index(classification) >= levels.index(threshold)
    except ValueError:
        return False


def main() -> int:
    args = parse_args()
    bundle_dir = resolve(args.hostplan_bundle)
    if not bundle_dir.is_dir():
        print(f"FAIL: hostplan bundle not found: {bundle_dir}", file=sys.stderr)
        return 2
    receipt = build_receipt(bundle_dir)
    out_path = resolve(args.out) if args.out else (bundle_dir / "simulator-evidence.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    plumbing = receipt["plumbingClassification"]
    print(
        f"PASS: wrote csl simulator evidence ({out_path})"
        f"  plumbing={plumbing}"
        f"  parity={receipt['numericParity']['status']}"
    )
    if args.require is not None and not required_at_least(plumbing, args.require):
        print(
            f"FAIL: required at least {args.require}, got {plumbing}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
