#!/usr/bin/env python3
"""Run a CSL host runner through the Cerebras WSC appliance API.

This is the hardware-side sibling of csl_sdk_driver.py. It keeps the
existing cs_python runners unchanged: compile with SdkCompiler, stage
the runner and support files with SdkLauncher, then invoke the same host
command using %CMADDR% substitution on appliance hardware.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code-dir", required=True)
    parser.add_argument("--layout", default="layout.csl")
    parser.add_argument("--compiler-args", required=True)
    parser.add_argument("--compile-output", default=".")
    parser.add_argument("--artifact-json", default="artifact_path.json")
    parser.add_argument("--runner-command", required=True)
    parser.add_argument("--stage", action="append", default=[])
    parser.add_argument(
        "--download",
        action="append",
        default=[],
        help="Download mapping SRC:DST from appliance after run.",
    )
    parser.add_argument("--receipt-out", default="")
    parser.add_argument(
        "--system",
        action="store_true",
        help="Run on allocated CS hardware instead of appliance simfabric.",
    )
    parser.add_argument(
        "--disable-version-check",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pass disable_version_check to SdkCompiler and SdkLauncher.",
    )
    return parser.parse_args()


def load_appliance_api() -> tuple[Any, Any]:
    try:
        from cerebras.sdk.client import SdkCompiler, SdkLauncher  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on WSC user node.
        raise SystemExit(
            "cerebras.sdk.client is unavailable. Install cerebras_appliance "
            "and cerebras_sdk wheels on a WSC user node before using "
            "csl_appliance_driver.py."
        ) from exc
    return SdkCompiler, SdkLauncher


def write_json(path_text: str, payload: dict[str, Any]) -> None:
    if not path_text:
        return
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    SdkCompiler, SdkLauncher = load_appliance_api()
    simulator = not args.system
    started = time.time()
    receipt: dict[str, Any] = {
        "schemaVersion": 1,
        "artifactKind": "doe_csl_appliance_driver_receipt",
        "mode": (
            "wsc_appliance_system" if args.system else "wsc_appliance_simulator"
        ),
        "compile": {"status": "not_attempted"},
        "run": {"status": "not_attempted"},
        "downloads": [],
    }

    try:
        with SdkCompiler(disable_version_check=args.disable_version_check) as compiler:
            artifact_path = compiler.compile(
                args.code_dir,
                args.layout,
                args.compiler_args,
                args.compile_output,
            )
        receipt["compile"] = {
            "status": "succeeded",
            "artifactPath": artifact_path,
            "codeDir": args.code_dir,
            "layout": args.layout,
            "compilerArgs": args.compiler_args,
            "compileOutput": args.compile_output,
        }
        Path(args.artifact_json).write_text(
            json.dumps(
                {"artifact_path": artifact_path},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        with SdkLauncher(
            artifact_path,
            simulator=simulator,
            disable_version_check=args.disable_version_check,
        ) as launcher:
            for staged in args.stage:
                launcher.stage(staged)
            response = launcher.run(args.runner_command)
            receipt["run"] = {
                "status": "succeeded",
                "command": args.runner_command.replace(
                    "%CMADDR%",
                    "$DOE_CSL_CMADDR",
                ),
                "response": str(response)[-4000:],
            }
            for mapping in args.download:
                if ":" not in mapping:
                    raise ValueError(f"--download expects SRC:DST, got {mapping!r}")
                src, dst = mapping.split(":", 1)
                launcher.download_artifact(src, dst)
                receipt["downloads"].append({"src": src, "dst": dst})
    except Exception as exc:  # pylint: disable=broad-except
        if receipt["compile"]["status"] == "not_attempted":
            receipt["compile"] = {
                "status": "failed",
                "error": type(exc).__name__,
                "message": str(exc),
            }
        else:
            receipt["run"] = {
                "status": "failed",
                "error": type(exc).__name__,
                "message": str(exc),
            }
        receipt["elapsedSeconds"] = time.time() - started
        write_json(args.receipt_out, receipt)
        raise

    receipt["elapsedSeconds"] = time.time() - started
    write_json(args.receipt_out, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
