#!/usr/bin/env python3
"""Orchestrate browser benchmark superset: generate -> run -> check -> summary."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WORKLOADS = REPO_ROOT / "bench/workloads.amd.vulkan.extended.json"
DEFAULT_RULES = REPO_ROOT / "nursery/fawn-browser/bench/projection-rules.json"
DEFAULT_MANIFEST = (
    REPO_ROOT / "nursery/fawn-browser/bench/generated/browser_projection_manifest.json"
)
DEFAULT_WORKFLOWS = (
    REPO_ROOT / "nursery/fawn-browser/bench/workflows/browser-workflow-manifest.json"
)
BENCH_OUT_ROOT = REPO_ROOT / "bench/out"
BENCH_OUT_SCRATCH_ROOT = REPO_ROOT / "bench/out/scratch"
ARTIFACTS_ROOT = REPO_ROOT / "nursery/fawn-browser/artifacts"
DEFAULT_REPORT_FILE = "dawn-vs-doe.browser-layered.superset.diagnostic.json"
DEFAULT_SUMMARY_FILE = "dawn-vs-doe.browser-layered.superset.summary.json"
DEFAULT_CHECK_FILE = "dawn-vs-doe.browser-layered.superset.check.json"


def host_doe_lib_extension() -> str:
    if sys.platform == "darwin":
        return "dylib"
    if sys.platform in {"win32", "cygwin"}:
        return "dll"
    return "so"


def default_doe_lib() -> Path:
    preferred_ext = host_doe_lib_extension()
    candidates: list[Path] = []
    env_doe_lib = os.getenv("FAWN_DOE_LIB")
    if env_doe_lib:
        candidates.append(Path(env_doe_lib))
    candidates.extend(
        [
            REPO_ROOT / f"zig/zig-out/lib/libwebgpu_doe.{preferred_ext}",
            REPO_ROOT / "zig/zig-out/lib/libwebgpu_doe.so",
            REPO_ROOT / "zig/zig-out/lib/libwebgpu_doe.dylib",
            REPO_ROOT / "zig/zig-out/lib/libwebgpu_doe.dll",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def default_chrome_binary() -> Path:
    release_local_out = Path(
        os.getenv(
            "FAWN_CHROMIUM_RELEASE_LOCAL_OUT",
            str(REPO_ROOT / "nursery/fawn-browser/out/fawn_release_local"),
        )
    )
    chromium_lane_out = REPO_ROOT / "nursery/chromium_webgpu_lane/out/fawn_release_local"
    host_fawn_app = Path.home() / "Applications/Fawn.app/Contents/MacOS/Chromium"
    candidates: list[Path] = []
    env_chrome = os.getenv("FAWN_CHROME_BIN")
    if env_chrome:
        candidates.append(Path(env_chrome))
    candidates.extend(
        [
            release_local_out / "chrome",
            release_local_out / "Fawn.app/Contents/MacOS/Chromium",
            release_local_out / "Chromium.app/Contents/MacOS/Chromium",
            chromium_lane_out / "chrome",
            chromium_lane_out / "Fawn.app/Contents/MacOS/Chromium",
            chromium_lane_out / "Chromium.app/Contents/MacOS/Chromium",
            host_fawn_app,
            REPO_ROOT / "nursery/fawn-browser/src/out/fawn_release/chrome",
            REPO_ROOT / "nursery/fawn-browser/src/out/fawn_release/Fawn.app/Contents/MacOS/Chromium",
            REPO_ROOT / "nursery/fawn-browser/src/out/fawn_release/Chromium.app/Contents/MacOS/Chromium",
            REPO_ROOT / "nursery/chromium_webgpu_lane/src/out/fawn_release/chrome",
            REPO_ROOT / "nursery/chromium_webgpu_lane/src/out/fawn_release/Fawn.app/Contents/MacOS/Chromium",
            REPO_ROOT / "nursery/chromium_webgpu_lane/src/out/fawn_release/Chromium.app/Contents/MacOS/Chromium",
            REPO_ROOT / "nursery/fawn-browser/src/out/fawn_debug/chrome",
            REPO_ROOT / "nursery/fawn-browser/src/out/fawn_debug/Fawn.app/Contents/MacOS/Chromium",
            REPO_ROOT / "nursery/fawn-browser/src/out/fawn_debug/Chromium.app/Contents/MacOS/Chromium",
            REPO_ROOT / "nursery/chromium_webgpu_lane/src/out/fawn_debug/chrome",
            REPO_ROOT / "nursery/chromium_webgpu_lane/src/out/fawn_debug/Fawn.app/Contents/MacOS/Chromium",
            REPO_ROOT / "nursery/chromium_webgpu_lane/src/out/fawn_debug/Chromium.app/Contents/MacOS/Chromium",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


DEFAULT_CHROME = default_chrome_binary()
DEFAULT_DOE_LIB = default_doe_lib()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workloads", default=str(DEFAULT_WORKLOADS))
    parser.add_argument("--rules", default=str(DEFAULT_RULES))
    parser.add_argument("--manifest-out", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--workflows", default=str(DEFAULT_WORKFLOWS))
    parser.add_argument("--chrome", default=str(DEFAULT_CHROME))
    parser.add_argument(
        "--dawn-chrome",
        default="",
        help="Browser executable for dawn mode (defaults to --chrome).",
    )
    parser.add_argument(
        "--doe-chrome",
        default="",
        help="Browser executable for doe mode (defaults to --chrome).",
    )
    parser.add_argument("--doe-lib", default=str(DEFAULT_DOE_LIB))
    parser.add_argument("--mode", choices=["dawn", "doe", "both"], default="both")
    parser.add_argument("--headless", default="true", choices=["true", "false"])
    parser.add_argument("--chrome-arg", action="append", default=[])
    parser.add_argument(
        "--out",
        default="",
        help=(
            "Layered report output path. Defaults to "
            "nursery/fawn-browser/artifacts/<timestamp>/"
            f"{DEFAULT_REPORT_FILE}."
        ),
    )
    parser.add_argument(
        "--summary-out",
        default="",
        help=(
            "Superset summary output path. Defaults to "
            "nursery/fawn-browser/artifacts/<timestamp>/"
            f"{DEFAULT_SUMMARY_FILE}."
        ),
    )
    parser.add_argument(
        "--check-out",
        default="",
        help=(
            "Coverage checker output path. Defaults to "
            "nursery/fawn-browser/artifacts/<timestamp>/"
            f"{DEFAULT_CHECK_FILE}."
        ),
    )
    parser.add_argument(
        "--allow-bench-out",
        action="store_true",
        help="Allow writing diagnostic superset artifacts under bench/out/scratch.",
    )
    parser.add_argument(
        "--allow-data-url-fallback",
        action="store_true",
        help="Allow data: URL fallback if local server bind fails in the layered runner.",
    )
    parser.add_argument(
        "--require-promotion-approvals",
        action="store_true",
        help="Require Track B contracts owner and coordinator approvals in checker output.",
    )
    parser.add_argument(
        "--promotion-approvals",
        default=str(
            REPO_ROOT
            / "nursery/fawn-browser/bench/workflows/browser-promotion-approvals.json"
        ),
        help="Path to promotion approvals JSON passed to checker.",
    )
    parser.add_argument(
        "--skip-run",
        action="store_true",
        help="Skip Playwright run and validate an existing report only.",
    )
    parser.add_argument(
        "--strict-run",
        action="store_true",
        help="Fail the runner when required L1/L2 scenarios are not ok.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing.",
    )
    return parser.parse_args()


def timestamp_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def default_output_paths() -> tuple[Path, Path, Path]:
    root = ARTIFACTS_ROOT / timestamp_id()
    return root / DEFAULT_REPORT_FILE, root / DEFAULT_SUMMARY_FILE, root / DEFAULT_CHECK_FILE


def path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def ensure_allowed_out_path(path: Path, allow_bench_out: bool) -> None:
    if not path_within(path, BENCH_OUT_ROOT):
        return
    if not allow_bench_out:
        raise ValueError(
            "refusing to write diagnostic browser superset output under "
            f"{BENCH_OUT_ROOT}; write under {ARTIFACTS_ROOT} or pass --allow-bench-out"
        )
    if not path_within(path, BENCH_OUT_SCRATCH_ROOT):
        raise ValueError(
            "diagnostic browser superset output under bench/out must be in "
            f"{BENCH_OUT_SCRATCH_ROOT}"
        )


def run_step(label: str, command: list[str], *, dry_run: bool) -> None:
    print(f"[browser-superset] {label}: {' '.join(command)}")
    if dry_run:
        return
    subprocess.run(command, check=True)


def run_step_capture_json(label: str, command: list[str], *, dry_run: bool) -> dict[str, Any]:
    print(f"[browser-superset] {label}: {' '.join(command)}")
    if dry_run:
        return {}
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.stdout.strip():
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"checker did not emit valid JSON (rc={completed.returncode}): {exc}"
            ) from exc
    else:
        payload = {}
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        if stderr:
            print(stderr, file=sys.stderr)
        raise subprocess.CalledProcessError(
            completed.returncode,
            command,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return payload


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def summarize_manifest(manifest_payload: dict[str, Any]) -> dict[str, int]:
    rows = manifest_payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("manifest missing rows[]")

    summary = {
        "rowCount": len(rows),
        "high": 0,
        "medium": 0,
        "non_projectable": 0,
        "l1_browser_api": 0,
        "l0_only": 0,
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        projection_class = row.get("projectionClass")
        layer_target = row.get("layerTarget")
        if isinstance(projection_class, str):
            summary[projection_class] = summary.get(projection_class, 0) + 1
        if isinstance(layer_target, str):
            summary[layer_target] = summary.get(layer_target, 0) + 1
    return summary


def summarize_layered_report(report_payload: dict[str, Any], mode: str) -> dict[str, Any]:
    l1 = report_payload.get("l1", {})
    l2 = report_payload.get("l2", {})
    rows_l1 = l1.get("rows", []) if isinstance(l1, dict) else []
    rows_l2 = l2.get("rows", []) if isinstance(l2, dict) else []

    mode_order = report_payload.get("modeOrder")
    if not isinstance(mode_order, list) or not mode_order:
        mode_order = [mode] if mode in {"dawn", "doe"} else ["dawn", "doe"]

    def count(rows: list[Any], required_predicate) -> dict[str, dict[str, int]]:
        per_mode: dict[str, dict[str, int]] = {}
        for runtime in mode_order:
            if not isinstance(runtime, str):
                continue
            per_mode[runtime] = {
                "ok": 0,
                "fail": 0,
                "unsupported": 0,
                "l0_only": 0,
                "missing": 0,
                "requiredFailures": 0,
            }

        for row in rows:
            if not isinstance(row, dict):
                continue
            runtimes = row.get("runtimes")
            if not isinstance(runtimes, dict):
                runtimes = {}
            required = required_predicate(row)
            for runtime in list(per_mode.keys()):
                runtime_row = runtimes.get(runtime)
                if not isinstance(runtime_row, dict):
                    per_mode[runtime]["missing"] += 1
                    if required:
                        per_mode[runtime]["requiredFailures"] += 1
                    continue
                status = runtime_row.get("status")
                if status not in {"ok", "fail", "unsupported", "l0_only"}:
                    status = "missing"
                per_mode[runtime][status] = per_mode[runtime].get(status, 0) + 1
                if required and status != "ok":
                    per_mode[runtime]["requiredFailures"] += 1

        return per_mode

    l1_counts = count(rows_l1, lambda row: row.get("requiredStatus") == "ok")
    l2_counts = count(rows_l2, lambda row: row.get("requiredStatus") == "ok")

    overall_required_failures = 0
    for runtime in l1_counts.keys():
        overall_required_failures += l1_counts[runtime]["requiredFailures"]
        overall_required_failures += l2_counts.get(runtime, {}).get("requiredFailures", 0)

    return {
        "modeOrder": mode_order,
        "l1": l1_counts,
        "l2": l2_counts,
        "overallRequiredFailures": overall_required_failures,
    }


def main() -> int:
    args = parse_args()

    workloads = Path(args.workloads).resolve()
    rules = Path(args.rules).resolve()
    manifest_out = Path(args.manifest_out).resolve()
    workflows = Path(args.workflows).resolve()
    chrome = Path(args.chrome).resolve()
    dawn_chrome = Path(args.dawn_chrome).resolve() if args.dawn_chrome else chrome
    doe_chrome = Path(args.doe_chrome).resolve() if args.doe_chrome else chrome
    doe_lib = Path(args.doe_lib).resolve()
    promotion_approvals = Path(args.promotion_approvals).resolve()
    default_out, default_summary, default_check = default_output_paths()
    out = Path(args.out).resolve() if args.out else default_out
    summary_out = Path(args.summary_out).resolve() if args.summary_out else default_summary
    check_out = Path(args.check_out).resolve() if args.check_out else default_check
    try:
        ensure_allowed_out_path(out, args.allow_bench_out)
        ensure_allowed_out_path(summary_out, args.allow_bench_out)
        ensure_allowed_out_path(check_out, args.allow_bench_out)
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 2

    if not args.skip_run:
        if args.mode in {"dawn", "both"} and not dawn_chrome.exists():
            print(f"FAIL: dawn mode chrome binary not found: {dawn_chrome}")
            return 2
        if args.mode in {"doe", "both"} and not doe_chrome.exists():
            print(f"FAIL: doe mode chrome binary not found: {doe_chrome}")
            return 2
        if args.mode in {"doe", "both"} and not doe_lib.exists():
            print(f"FAIL: doe runtime library not found: {doe_lib}")
            return 2

    generate_command = [
        sys.executable,
        str(REPO_ROOT / "nursery/fawn-browser/scripts/generate-browser-projection-manifest.py"),
        "--workloads",
        str(workloads),
        "--rules",
        str(rules),
        "--out",
        str(manifest_out),
    ]
    run_step("generate", generate_command, dry_run=args.dry_run)

    run_command: list[str] | None = None
    if not args.skip_run:
        run_command = [
            "node",
            str(REPO_ROOT / "nursery/fawn-browser/scripts/webgpu-playwright-layered-bench.mjs"),
            "--mode",
            args.mode,
            "--chrome",
            str(chrome),
            "--dawn-chrome",
            str(dawn_chrome),
            "--doe-chrome",
            str(doe_chrome),
            "--doe-lib",
            str(doe_lib),
            "--manifest",
            str(manifest_out),
            "--workflows",
            str(workflows),
            "--headless",
            args.headless,
            "--out",
            str(out),
        ]
        if args.allow_bench_out:
            run_command.append("--allow-bench-out")
        if args.allow_data_url_fallback:
            run_command.append("--allow-data-url-fallback")
        for chrome_arg in args.chrome_arg:
            run_command.extend(["--chrome-arg", chrome_arg])
        if args.strict_run:
            run_command.append("--strict")

        run_step("layered-run", run_command, dry_run=args.dry_run)

    check_command = [
        sys.executable,
        str(REPO_ROOT / "nursery/fawn-browser/scripts/check-browser-benchmark-superset.py"),
        "--workloads",
        str(workloads),
        "--manifest",
        str(manifest_out),
        "--workflows",
        str(workflows),
        "--json",
    ]
    if out.exists() and not args.dry_run:
        check_command.extend(["--report", str(out)])
        if args.mode == "both":
            check_command.extend(["--require-modes", "dawn,doe"])
        else:
            check_command.extend(["--require-modes", args.mode])
    if args.require_promotion_approvals:
        check_command.extend(
            [
                "--require-promotion-approvals",
                "--promotion-approvals",
                str(promotion_approvals),
            ]
        )
    check_payload = run_step_capture_json("check", check_command, dry_run=args.dry_run)

    if args.dry_run:
        return 0

    manifest_payload = load_json(manifest_out)
    report_payload = load_json(out) if out.exists() else {}
    check_out.parent.mkdir(parents=True, exist_ok=True)
    check_out.write_text(f"{json.dumps(check_payload, indent=2)}\n", encoding="utf-8")
    run_summary = summarize_layered_report(report_payload, args.mode) if report_payload else {}
    run_status = "report_present" if report_payload else ("run_skipped" if args.skip_run else "report_missing")
    run_reason = ""
    if run_status == "run_skipped":
        run_reason = "--skip-run was set"
    elif run_status == "report_missing":
        run_reason = (
            "layered report was not produced; run may have failed before write or was blocked in environment"
        )

    summary = {
        "schemaVersion": 2,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "reportKind": "browser-layered-superset-summary",
        "benchmarkClass": "directional",
        "comparisonStatus": "diagnostic",
        "claimStatus": "diagnostic",
        "timingClass": "scenario",
        "timingSource": "browser-performance-now",
        "invocation": {
            "argv": sys.argv[1:],
            "cwd": str(Path.cwd()),
            "pythonExecutable": sys.executable,
        },
        "inputs": {
            "workloads": str(workloads),
            "rules": str(rules),
            "manifest": str(manifest_out),
            "workflows": str(workflows),
            "chrome": str(chrome),
            "dawnChrome": str(dawn_chrome),
            "doeChrome": str(doe_chrome),
            "doeLib": str(doe_lib),
            "mode": args.mode,
            "promotionApprovals": str(promotion_approvals),
        },
        "commands": {
            "generate": generate_command,
            "run": run_command if run_command is not None else [],
            "check": check_command,
        },
        "artifacts": {
            "layeredReportPath": str(out),
            "checkResultPath": str(check_out),
            "summaryPath": str(summary_out),
            "manifestPath": str(manifest_out),
            "workflowsPath": str(workflows),
        },
        "projectionContract": {
            "projectionContractHash": manifest_payload.get("projectionContractHash"),
            "sourceWorkloadsSha256": manifest_payload.get("sourceWorkloadsSha256"),
            "rulesSha256": manifest_payload.get("rulesSha256"),
            "sourceWorkloadsPath": manifest_payload.get("sourceWorkloadsPath"),
            "rulesPath": manifest_payload.get("rulesPath"),
        },
        "check": check_payload,
        "projection": summarize_manifest(manifest_payload),
        "run": {
            "status": run_status,
            "reason": run_reason,
            "reportPath": str(out),
            "reportPresent": bool(report_payload),
            "skipRun": bool(args.skip_run),
            "strictRun": bool(args.strict_run),
            "modeOrder": run_summary.get("modeOrder", []),
            "l1": run_summary.get("l1", {}),
            "l2": run_summary.get("l2", {}),
            "overallRequiredFailures": run_summary.get("overallRequiredFailures"),
            "browserEnvironmentEvidence": report_payload.get("browserEnvironmentEvidence", {}),
        },
    }

    summary_out.parent.mkdir(parents=True, exist_ok=True)
    summary_out.write_text(f"{json.dumps(summary, indent=2)}\n", encoding="utf-8")

    print(f"[browser-superset] summary written: {summary_out}")
    print(f"[browser-superset] check written: {check_out}")
    if summary["run"].get("overallRequiredFailures") is not None:
        print(
            "[browser-superset] overall required failures: "
            f"{summary['run'].get('overallRequiredFailures')}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
