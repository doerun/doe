#!/usr/bin/env python3
"""Run the Qwen af16 HostPlan locally and bind the observed blocker."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = (
    REPO_ROOT.parent
    / "doppler/models/local/qwen-3-6-27b-q4k-eaf16/manifest.json"
)
DEFAULT_OUT_DIR = (
    REPO_ROOT / "bench/out/r3-2-27b-af16-local-simfabric-ceiling"
)
HOSTPLAN_ROOT = REPO_ROOT / "bench/fixtures/cerebras-hostplans/qwen3-6-27b-af16"
RUNNER = (
    REPO_ROOT
    / "bench/runners/csl-runners/qwen3_6_27b_af16_hostplan_streaming_runner.py"
)
DEFAULT_EMBED_ROI_HIDDEN_PER_PE = 512
PROMPT_TOKEN_IDS = [
    248045,
    846,
    198,
    760,
    1829,
    314,
    279,
    12515,
    369,
    248046,
    198,
    248045,
    74455,
    198,
    248068,
    271,
    248069,
    271,
]


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-doppler-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--cslc-executable", default="cslc")
    parser.add_argument("--skip-sdk-compile", action="store_true")
    parser.add_argument(
        "--session-embed-roi-hidden-per-pe",
        type=int,
        default=DEFAULT_EMBED_ROI_HIDDEN_PER_PE,
        help=(
            "Forwarded to the HostPlan runner. Zero uses the HostPlan "
            "compile parameter."
        ),
    )
    parser.add_argument(
        "--session-embed-roi-jobs",
        type=int,
        default=1,
        help="Forwarded to the HostPlan runner.",
    )
    parser.add_argument(
        "--stop-after-launch",
        type=int,
        default=-1,
        help="Forwarded to the HostPlan runner.",
    )
    parser.add_argument(
        "--launch-timeout-seconds",
        type=int,
        default=120,
        help="Forwarded to the HostPlan runner.",
    )
    return parser.parse_args()


def run_command(command: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdoutTail": proc.stdout.splitlines()[-20:],
        "stderrTail": proc.stderr.splitlines()[-20:],
    }


def last_progress_event(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    last: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            last = event
    return last


def first_blocker(trace: dict[str, Any]) -> str:
    blockers = trace.get("blockers") or []
    if not blockers:
        return ""
    first = blockers[0]
    if isinstance(first, dict):
        return str(first.get("class") or first.get("detail") or "blocked")
    return str(first)


def build_receipt(
    *,
    trace_path: Path,
    session_dir: Path,
    sdk_compile: dict[str, Any] | None,
    runner_result: dict[str, Any],
    runner_options: dict[str, Any],
) -> dict[str, Any]:
    trace = load_json(trace_path) if trace_path.is_file() else {}
    progress_path = session_dir / "progress.jsonl"
    event = last_progress_event(progress_path)
    artifact_paths = {
        "trace": rel(trace_path) if trace_path.is_file() else "",
        "sessionProgress": rel(progress_path) if progress_path.is_file() else "",
    }
    artifact_hashes = {
        "traceSha256": sha256_file(trace_path) if trace_path.is_file() else "",
        "sessionProgressSha256": (
            sha256_file(progress_path) if progress_path.is_file() else ""
        ),
    }
    status = str(trace.get("status") or "missing_trace")
    blocker = first_blocker(trace)
    if event and event.get("phase") == "hostplan_launch_blocked":
        blocker = str(event.get("error") or blocker or "hostplan_launch_blocked")
    if not blocker and runner_options.get("stopAfterLaunch", -1) >= 0:
        blocker = "operator_stop_after_launch"
    if not blocker and not event and status != "output_ready":
        blocker = "no_session_progress_emitted"
    verdict = "unblocked" if status == "output_ready" else "blocked"
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_qwen3_6_27b_af16_local_simfabric_ceiling_receipt",
        "modelId": "qwen-3-6-27b-q4k-eaf16",
        "verdict": verdict,
        "status": status,
        "blocker": blocker,
        "lastPhaseReached": str((event or {}).get("phase") or ""),
        "lastLaunchIndex": (event or {}).get("launchIndex"),
        "artifacts": artifact_paths,
        "artifactHashes": artifact_hashes,
        "sdkCompile": sdk_compile,
        "runnerOptions": runner_options,
        "runner": runner_result,
        "claim": {
            "scope": (
                "Local Qwen af16 HostPlan execution attempt against real "
                "RDRR weights and generated CSL. The receipt records the "
                "first observed blocker."
            ),
            "notWhat": (
                "Not a hardware receipt and not a parity claim unless "
                "verdict is unblocked with a returned transcript."
            ),
        },
    }


def main() -> int:
    args = parse_args()
    out_dir = args.out_dir if args.out_dir.is_absolute() else REPO_ROOT / args.out_dir
    session_dir = out_dir / "session"
    trace_path = out_dir / "trace.json"
    receipt_path = out_dir / "receipt.json"
    out_dir.mkdir(parents=True, exist_ok=True)

    sdk_compile = None
    if not args.skip_sdk_compile:
        sdk_compile = run_command([
            args.python,
            "runtime/zig/tools/csl_sdk_driver.py",
            rel(HOSTPLAN_ROOT / "simulator-plan.json"),
            "--cslc-executable",
            args.cslc_executable,
        ])

    command = [
        args.python,
        rel(RUNNER),
        "--source-doppler-manifest",
        str(args.source_doppler_manifest),
        "--prefill-token-count",
        str(len(PROMPT_TOKEN_IDS)),
        "--decode-token-count",
        "8",
        "--execute",
        "--session-lm-head-dispatch-mode",
        "dense_gemv_width_tiled_session",
        "--session-lm-head-tile-width",
        "32",
        "--session-lm-head-tile-dispatch-budget",
        "0",
        "--session-embed-roi-hidden-per-pe",
        str(args.session_embed_roi_hidden_per_pe),
        "--session-embed-roi-jobs",
        str(args.session_embed_roi_jobs),
        "--launch-timeout-seconds",
        str(args.launch_timeout_seconds),
        "--session-prefill-q4k-gemv-output-pe-rows",
        "4",
        "--session-out-dir",
        rel(session_dir),
        "--out",
        rel(trace_path),
    ]
    for token_id in PROMPT_TOKEN_IDS:
        command.extend(["--prompt-token-id", str(token_id)])
    if args.stop_after_launch >= 0:
        command.extend(["--stop-after-launch", str(args.stop_after_launch)])

    runner_result = run_command(command)
    receipt = build_receipt(
        trace_path=trace_path,
        session_dir=session_dir,
        sdk_compile=sdk_compile,
        runner_result=runner_result,
        runner_options={
            "sessionEmbedRoiHiddenPerPe": args.session_embed_roi_hidden_per_pe,
            "sessionEmbedRoiJobs": args.session_embed_roi_jobs,
            "stopAfterLaunch": args.stop_after_launch,
            "launchTimeoutSeconds": args.launch_timeout_seconds,
        },
    )
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {rel(receipt_path)} verdict={receipt['verdict']} "
        f"blocker={receipt['blocker']}"
    )
    return 0 if receipt["verdict"] == "unblocked" else 1


if __name__ == "__main__":
    sys.exit(main())
